# -*- coding: utf-8 -*-
"""El ingreso por línea, calculado desde la CUENTA y no desde el resumen.

**Por qué existe (owner, 2026-08-14).** En el Revenue Detail salían en cero
«F&B Beverage», «F&B Miscellaneous», «Other Rooms Revenue» y «Misc Revenue
Others», y el owner dijo que eso no es cierto. Tenía razón, y la causa no estaba
en el reporte.

`compute_pl_month` prefiere el **resumen importado** (`actual_pl_lines`) sobre el
detalle del mayor. Es correcto para el P&L —de ahí sale el número que se
reporta— pero ese resumen es **más grueso** que el mayor:

* todo el A&B viene en una sola línea: no tiene comida / bebida / misceláneos;
* no tiene «Other Rooms Revenue»;
* mete el ingreso misceláneo DENTRO de Sustainability (los $108,931 de
  diferencia entre $249,600 y $140,669);
* usa códigos viejos —`REV_TRANSPORT`, `REV_CROWTHER`— que conviven con los
  canónicos y duplicaban dos filas del cuadro.

El detalle del mayor sí tiene la apertura completa, porque la lleva la CUENTA.
Así que este cuadro se calcula desde ahí, igual que el de A&B.

**No compite con el P&L: lo explica.** Si la suma de este detalle no da el
`TOTAL_REVENUES` del P&L, es que el resumen y el mayor no dicen lo mismo — y eso
hay que verlo, no esconderlo. Por eso el endpoint devuelve las dos cifras.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.errores import ErrorApi
from app.auth import get_current_user
from app.db import get_session
from app.engine import pl_engine, recalculate as recalc
from app.models.revenue_account_entry import RevenueAccountEntry
from app.models.scenario import Scenario

router = APIRouter()

ZERO = Decimal("0")
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]


async def _resolvedor(session):
    """La misma búsqueda (departamento, cuenta) → línea que usa el motor.

    ⚠️ La primera versión usaba un diccionario de coincidencia EXACTA por
    (depto, cuenta). Perdía el SPA: su ingreso está en el departamento **0130**,
    que no tiene regla propia —el mapeo lo tiene bajo el 0140— y el motor lo
    rutea por regla de repuesto. El detalle salía $35,115.86 por debajo del P&L
    y cada fila se veía bien.

    Usar el resolvedor del motor es lo único que garantiza que el detalle vea
    exactamente lo mismo que el P&L. Una copia de la lógica se queda atrás.
    """
    mapeos = await recalc.load_active_account_mappings(session)
    resolve = pl_engine.construir_resolvedor(mapeos)

    def linea(dept: str, cuenta: str) -> str | None:
        if not cuenta.startswith("4") or cuenta in pl_engine.ALLOCATION_ACCOUNTS:
            return None
        regla, _como = resolve(dept, cuenta)
        code = (regla or {}).get("report_line_code") or ""
        return code if code.startswith("REV_") else None

    return linea


@router.get("/reports/ingreso-detalle/")
async def ingreso_detalle(
    scenarios: str = Query(..., description="ids separados por coma"),
    _=Depends(get_current_user),
):
    """El ingreso por línea del P&L, por mes, calculado desde las cuentas."""
    ids = [x.strip() for x in scenarios.split(",") if x.strip()]
    if not ids:
        raise ErrorApi(422, "escenarios.requerido")

    salida, nombres = [], {}
    async with get_session() as s:
        linea = await _resolvedor(s)
        cfg = await recalc.load_report_line_config(s)
        for r in cfg:
            if str(r["line_code"]).startswith("REV_"):
                nombres[r["line_code"]] = r.get("line_name") or r["line_code"]

        for sid in ids:
            e = await s.get(Scenario, sid)
            if e is None:
                continue
            rae = (await s.execute(select(RevenueAccountEntry).where(
                RevenueAccountEntry.scenario_id == sid))).scalars().all()

            meses = []
            for m in range(1, 13):
                col = MESES[m - 1]
                d: dict[str, Decimal] = {}
                # ⚠️ Una fuente por mes, nunca las dos: sumarlas da el doble.
                gl = await recalc.actual_rows_for_month(s, sid, m)
                if gl:
                    for f in gl:
                        ln = linea(str(f.get("dept_code") or ""),
                                   str(f["account_code"] or ""))
                        if ln:
                            d[ln] = d.get(ln, ZERO) + Decimal(str(f["amount"] or 0))
                else:
                    # El presupuesto arma el ingreso por LÍNEA (tarifa × noches),
                    # no por cuenta. La apertura solo existe si alguien cargó el
                    # detalle en `revenue_account_entries`.
                    for f in rae:
                        ln = linea(str(f.dept_code or ""), str(f.account_code))
                        if ln:
                            d[ln] = d.get(ln, ZERO) + Decimal(str(getattr(f, col) or 0))
                meses.append({"month": m, **{k: float(v) for k, v in d.items()}})

            # Lo que dice el P&L, para poder comparar y no para reemplazarlo.
            pl = []
            for m in range(1, 13):
                lineas = await recalc.compute_pl_month(s, e, m)
                pl.append({"month": m, "total_revenues": float(next(
                    (l.amount_usd for l in lineas
                     if l.line_code == "TOTAL_REVENUES"), 0))})

            salida.append({"scenario_id": sid, "type": e.type, "version": e.version,
                           "year": e.year, "meses": meses, "pl": pl})

    return {"escenarios": salida, "nombres": nombres}
