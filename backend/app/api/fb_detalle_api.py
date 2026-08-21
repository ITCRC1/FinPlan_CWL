# -*- coding: utf-8 -*-
"""A&B por cuenta: comida, bebida y misceláneos, ingreso y costo.

**Por qué existe (owner, 2026-08-14).** Su cuadro de cierre abre el A&B en
comida / bebida / misceláneos, para los dos lados —lo que se vende y lo que
cuesta— y saca el porcentaje de costo de cada uno. El P&L no puede darlo: ahí
todo el A&B es **una sola línea** (`REV_FB`). El corte vive un nivel más abajo,
en la cuenta del mayor.

**Los grupos son LÍNEAS del P&L, no una lista escrita acá.** Al separar el costo
de ventas (owner, 2026-08-14) el A&B quedó partido en el propio mapeo:
`REV_FB` / `REV_FB_BEV` / `REV_FB_MISC` del lado de la venta y
`COS_FB_FOOD` / `COS_FB_BEV` / `COS_FB_MISC` del lado del costo.

La primera versión de este módulo agrupaba **adivinando por el nombre** de la
cuenta («Food», «Beer», «Bev Cost»…) porque el corte todavía no existía. Ya no
hace falta: una cuenta nueva cae donde diga el mapeo, que es el único lugar
donde debe decidirse. Si mañana se agrega una cuenta de bebida, entra sola.

**Una sola fuente por mes, nunca las dos.** Igual que `gasto_por_clase_api`: si
el mes tiene detalle del GL manda el GL; si no, mandan los checkbooks de la app.
Sumar las dos da exactamente el doble, y el error no avisa — ya pasó.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.errores import ErrorApi
from app.auth import get_current_user
from app.db import get_session
from app.engine import recalculate as recalc
from app.models.cost_entry import CostEntry
from app.models.mapping import AccountMapping
from app.models.revenue_account_entry import RevenueAccountEntry
from app.models.scenario import Scenario

router = APIRouter()

ZERO = Decimal("0")
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]

# El departamento de A&B. El corte de este cuadro es dentro de él.
DEPT_FB = "0120"

# Las líneas del P&L de cada grupo. El corte vive en el mapeo.
LINEAS_ING = {"comida": "REV_FB", "bebida": "REV_FB_BEV", "misc": "REV_FB_MISC"}
LINEAS_COS = {"comida": "COS_FB_FOOD", "bebida": "COS_FB_BEV", "misc": "COS_FB_MISC"}
GRUPOS = ("comida", "bebida", "misc")


async def _cuentas_por_grupo(session, lineas: dict[str, str]) -> dict[str, str]:
    """{cuenta: grupo}, leyendo qué cuentas cuelgan de cada línea del P&L.

    ⚠️ Se consulta la TABLA directo y no `recalc.load_active_account_mappings`:
    ese cargador devuelve cinco campos para el motor del P&L. Antes de esto el
    módulo agrupaba por el NOMBRE de la cuenta y lo pedía por ahí — el cargador
    no trae el nombre, así que todas llegaban vacías, ninguna clasificaba, y la
    pantalla mostraba las seis cuentas de A&B como «sin clasificar»
    (owner, 2026-08-14). Ahora el grupo sale de la línea, que sí viene.
    """
    filas = (await session.execute(
        select(AccountMapping).where(
            AccountMapping.report_id == "P&L_DETAIL_OWNERS",
            AccountMapping.active_status == "YES",
            AccountMapping.report_line_code.in_(list(lineas.values())),
        ))).scalars().all()
    por_linea = {v: k for k, v in lineas.items()}
    return {str(m.account_code): por_linea[m.report_line_code] for m in filas
            if str(m.dept_code or "") == DEPT_FB}


async def _por_mes(session, scenario_id: str, cuentas_ing: dict[str, str],
                   cuentas_cos: dict[str, str]) -> tuple[list[dict], set[str]]:
    """Los seis números por mes. El segundo valor queda por compatibilidad: con
    el corte en el mapeo ya no hay cuentas que no se puedan clasificar."""
    sin_grupo: set[str] = set()

    # El ingreso del presupuesto vive en su propia tabla: el motor de revenue
    # trabaja por LÍNEA (tarifa × noches) y no por cuenta, así que la apertura
    # solo existe si alguien cargó el detalle.
    rae = (await session.execute(select(RevenueAccountEntry).where(
        RevenueAccountEntry.scenario_id == scenario_id))).scalars().all()
    ce = (await session.execute(select(CostEntry).where(
        CostEntry.scenario_id == scenario_id))).scalars().all()

    filas = []
    for m in range(1, 13):
        col = MESES[m - 1]
        d = {f"{lado}_{g}": ZERO for lado in ("ing", "cos") for g in GRUPOS}

        # ⚠️ Una fuente por mes, nunca las dos. Ver el encabezado del módulo.
        gl = await recalc.actual_rows_for_month(session, scenario_id, m)
        if gl:
            for r in gl:
                cta = str(r["account_code"] or "")
                monto = Decimal(str(r["amount"] or 0))
                if cta in cuentas_ing:
                    d[f"ing_{cuentas_ing[cta]}"] += monto
                elif cta in cuentas_cos:
                    d[f"cos_{cuentas_cos[cta]}"] += monto
        else:
            for e in rae:
                cta = str(e.account_code or "")
                if cta in cuentas_ing:
                    d[f"ing_{cuentas_ing[cta]}"] += Decimal(str(getattr(e, col) or 0))
            for e in ce:
                cta = str(e.account_code or "")
                if cta in cuentas_cos:
                    d[f"cos_{cuentas_cos[cta]}"] += Decimal(str(getattr(e, col) or 0))

        fila = {"month": m, **{k: float(v) for k, v in d.items()}}
        fila["ing_total"] = sum(float(d[f"ing_{g}"]) for g in GRUPOS)
        fila["cos_total"] = sum(float(d[f"cos_{g}"]) for g in GRUPOS)
        filas.append(fila)
    return filas, sin_grupo


@router.get("/reports/fb-detalle/")
async def fb_detalle(
    scenarios: str = Query(..., description="ids separados por coma"),
    _=Depends(get_current_user),
):
    """Ingreso y costo de A&B abiertos en comida / bebida / misceláneos.

    Devuelve **los doce meses**: quien llama arma el mes y el acumulado sin
    volver a preguntar.
    """
    ids = [x.strip() for x in scenarios.split(",") if x.strip()]
    if not ids:
        raise ErrorApi(422, "escenarios.requerido")

    salida, sin_grupo = [], set()
    async with get_session() as s:
        cuentas_ing = await _cuentas_por_grupo(s, LINEAS_ING)
        cuentas_cos = await _cuentas_por_grupo(s, LINEAS_COS)
        for sid in ids:
            e = await s.get(Scenario, sid)
            if e is None:
                continue     # un id que ya no existe no tumba la comparación
            meses, faltan = await _por_mes(s, sid, cuentas_ing, cuentas_cos)
            sin_grupo |= faltan
            salida.append({"scenario_id": sid, "type": e.type,
                           "version": e.version, "year": e.year, "meses": meses})

    return {
        "escenarios": salida,
        "cuentas": {
            "ingreso": [{"cuenta": c, "nombre": "", "grupo": g}
                        for c, g in sorted(cuentas_ing.items())],
            "costo": [{"cuenta": c, "nombre": "", "grupo": g}
                      for c, g in sorted(cuentas_cos.items())],
        },
        # Se reporta, no se esconde: si una cuenta de A&B no cae en ningún grupo,
        # el desglose deja de sumar el total y hay que saberlo.
        "sin_clasificar": sorted(sin_grupo),
    }
