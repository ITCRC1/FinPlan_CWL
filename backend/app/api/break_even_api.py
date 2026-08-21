# -*- coding: utf-8 -*-
"""API del módulo Break-Even (Fase 1).

Spec: `FINPLAN_BREAK_EVEN.md` §7 (seguridad) · `FINPLAN_TAB_BREAK-E.md` (pantallas).

## Dónde salen los MONTOS, que es la parte que el spec no podía saber

Las semillas no traen monto (spec §8.1): el monto es dato de periodo y vive en el
P&L. Acá se lee con **`audit_api._sources`**, que es la función que FinPlan ya usa
para reconciliar — sirve tanto para un escenario importado (detalle GL) como para
uno de checkbook (opex + costos + planilla + repartos). Reusarla y no escribir una
cuarta consulta es deliberado: una copia que se queda atrás hace que este módulo
diga una cosa mientras el P&L dice otra.

La `pl_line` de cada monto sale de **`pl_engine.construir_resolvedor`**, el mismo
resolvedor del motor. Mismo criterio.

## `data_version` y el escenario: los dos, y tienen que coincidir

El spec exige `data_version` obligatorio (`ACTUAL|BUDGET|FORECAST`) porque un
equilibrio calculado sobre la base equivocada se ve idéntico a uno correcto. En
FinPlan el dato no vive en «una versión» sino en un **escenario** concreto, que ya
tiene su `type`. Así que se piden **los dos** y se verifica que digan lo mismo: si
no coinciden, 422. Pedir solo el escenario haría al parámetro decorativo; pedir
solo la versión no alcanza para elegir entre seis presupuestos 2027.

⚠️ **Ningún escenario de hoy reproduce los números del Excel de referencia**
(medido el 2026-08-16: el más cercano es `BUDGET Final 2026`, $4.872.775 contra
$4.373.146). El Excel se armó sobre un «Budget 2025 Dec» que no está cargado. La
prueba de aceptación corre contra un fixture por eso — ver
`tests/test_break_even_acepta.py`.
"""
from __future__ import annotations

import re

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errores import ErrorApi
from app.textos import Idioma, t
from app.api import _be_base
from app.engine import break_even as be
from app.engine import pl_engine
from app.hotel_actual import HOTEL_ID
from app.models.break_even import (
    BeCostClassification, BeDepartment, DEPT_ACTIVO,
)
from app.models.scenario import Scenario

def _motivo(idioma: str, valor: str | None) -> str | None:
    """El motor pone una CLAVE en `motivo`; acá se vuelve texto.

    Se deja pasar lo que no sea clave: hay motivos que vienen de otras
    estructuras y todavía son texto. Un `motivo` que se muestra crudo se lee
    como una explicación, así que no puede quedar la clave en pantalla.
    """
    if not valor:
        return valor
    return t(idioma, valor) if re.fullmatch(r"[a-z_]+\.[a-z_]+", valor) else valor


router = APIRouter()

#: Rol requerido para EDITAR. La UI deshabilita inputs, pero eso no protege
#: nada: un PATCH directo entra igual. La autorización real es ésta (spec §7).
ROLES_QUE_EDITAN = {"admin"}


# ─── Autorización y contexto ──────────────────────────────────────────────────

def _exigir_edicion(user) -> None:
    rol = getattr(user, "role", None) or (user or {}).get("role")
    if rol not in ROLES_QUE_EDITAN:
        raise ErrorApi(403, "break_even.requiere_rol_edicion")


async def _escenario_coherente(db: AsyncSession, scenario_id: str,
                               data_version: str) -> Scenario:
    """El escenario existe, es de esta propiedad y su tipo == `data_version`."""
    try:
        be.exigir_data_version(data_version)
    except be.VersionDeDatoRequerida as e:
        raise HTTPException(422, str(e))

    s = await db.get(Scenario, scenario_id)
    if s is None:
        raise ErrorApi(404, "escenario.no_existe_id", escenario=scenario_id)
    if s.hotel_id != HOTEL_ID:
        # Scoping por propiedad: sin esto, cambiar el id en la URL deja leer
        # (y con el PATCH, editar) los datos de otra propiedad.
        raise ErrorApi(403, "escenario.de_otra_propiedad")
    if s.type != data_version:
        raise ErrorApi(422, "break_even.data_version_no_coincide",
                       data_version=data_version, escenario=scenario_id,
                       tipo=s.type)
    return s


# ─── Montos del P&L ───────────────────────────────────────────────────────────

async def montos_del_escenario(db: AsyncSession, scenario: Scenario,
                               month: int = 0) -> list[be.Monto]:
    """La base de COSTO del escenario.

    ⚠️ **Ya no recorre el GL: es una vista de `_be_base`.** Antes había dos
    recorridos del GL con dos criterios —uno para el costo acá, y ninguno para
    el ingreso, que por eso salía en cero en las catorce filas del tab—. Uno
    solo no puede contradecirse con el otro.

    El filtro no cambió ni un centavo: mismas filas y mismo total en los cinco
    escenarios medidos (`scripts/cuadre_base_break_even`), y hay prueba.
    """
    base = await _be_base.construir(db, scenario, month)
    return base.costos()


#: La lista blanca de secciones de costo vive en `_be_base`, que es donde se
#: decide qué entra a la base. Se reexporta porque las pruebas la nombran.
SECCIONES_DE_COSTO = _be_base.SECCIONES_DE_COSTO


async def costo_del_pl(db: AsyncSession, s: Scenario, month: int) -> Decimal:
    """El costo total del periodo SEGÚN EL P&L, para contrastar el del equilibrio.

    Es el número traído de afuera que convierte la fila «Validations» en un
    control. Sale de la identidad del propio reporte:

        costo (sin impuesto) = TOTAL_REVENUES − NET_PROFIT − INCOME_TAXES

    Se resta el impuesto porque el costo del equilibrio (`variable + fijo`) no
    lo incluye: la regla lo marca `excluded_from_be` y el motor lo saca del
    costo fijo. Comparar sin restarlo acusaría un descuadre que no existe.
    """
    from app.engine.recalculate import compute_pl_month

    meses = range(1, 13) if not month else [month]
    rev = neto = impuesto = Decimal("0")
    for m in meses:
        for ln in await compute_pl_month(db, s, m):
            v = Decimal(str(ln.amount_usd))
            if ln.line_code == "TOTAL_REVENUES":
                rev += v
            elif ln.line_code == "NET_PROFIT":
                neto += v
            elif ln.line_code == "INCOME_TAXES":
                impuesto += v
    return rev - neto - impuesto


async def _reglas(db: AsyncSession) -> list[be.Regla]:
    filas = (await db.execute(
        select(BeCostClassification, BeDepartment)
        .join(BeDepartment, BeDepartment.id == BeCostClassification.be_department_id)
        .where(BeCostClassification.property_id == HOTEL_ID)
    )).all()
    return [
        be.Regla(dept_slug=d.slug, dept_code=c.dept_code, account=c.account,
                 pl_line=c.pl_line, pct_variable=Decimal(str(c.pct_variable)),
                 map_source=c.map_source, excluded_from_be=c.excluded_from_be,
                 be_section=c.be_section, account_name=c.account_name)
        for c, d in filas
    ]


# ─── Endpoints de lectura ─────────────────────────────────────────────────────

@router.get("/break-e/departments/")
async def departamentos(db: AsyncSession = Depends(get_db)):
    """El catálogo. La UI genera los sub-tabs de acá, NO de una lista escrita a
    mano: hay 8 departamentos esperando que aparezcan sin tocar código."""
    filas = (await db.execute(select(BeDepartment).order_by(
        BeDepartment.display_order, BeDepartment.slug))).scalars().all()
    return {"departamentos": [
        {"slug": d.slug, "name": d.name, "display_order": d.display_order,
         "generates_revenue": d.generates_revenue, "dept_codes": d.dept_codes,
         "status": d.status, "activo": d.status == DEPT_ACTIVO}
        for d in filas]}


@router.get("/break-e/result/")
async def resultado(
    scenario_id: str = Query(...),
    data_version: str = Query(..., description="ACTUAL|BUDGET|FORECAST — obligatorio"),
    month: int = Query(0, ge=0, le=12, description="0 = año completo"),
    idioma: str = Idioma,
    db: AsyncSession = Depends(get_db),
):
    """El Resumen y el Por Departamento salen los dos de acá."""
    s = await _escenario_coherente(db, scenario_id, data_version)
    # UNA proyección del GL, y de ahí sale todo: el costo Y el ingreso por
    # departamento. Ver `_be_base` — antes eran dos recorridos con dos criterios.
    base = await _be_base.construir(db, s, month)
    reglas = await _reglas(db)

    pl = await pl_engine_totales(db, s, month)
    r = be.calcular(
        data_version=data_version, revenue=pl["revenue"],
        revenue_rooms=pl["revenue_rooms"], montos=base.costos(), reglas=reglas,
        adr=pl["adr"], rooms_available=pl["rooms_available"],
    )

    # ── El ingreso por departamento, que es lo que faltaba ───────────────────
    #
    # El motor clasifica COSTO y deja `DeptoBE.revenue` para «quien llama». No
    # lo llamaba nadie: los catorce departamentos salían con ingreso $0, el
    # margen igual al costo variable en negativo y el `% MC` en «—». El tab
    # existe para mostrar margen por departamento y no podía mostrarlo.
    ingresos = base.ingreso_por_departamento()
    for slug, monto in ingresos.items():
        d = r.por_departamento.setdefault(slug, be.DeptoBE(slug=slug))
        d.revenue = monto
    cuadres = _be_base.validar_contra_pl(base, pl["revenue"])

    def n(x):
        return None if x is None else float(round(x, 2))

    return {
        "scenario_id": scenario_id, "data_version": data_version, "month": month,
        "resumen": {
            "revenue": n(r.revenue), "variable_cost": n(r.variable_cost),
            "fixed_cost": n(r.fixed_cost), "excluded_cost": n(r.excluded_cost),
            "contribution_margin": n(r.contribution_margin),
            "cm_pct": n(r.cm_pct), "ebt": n(r.ebt), "net": n(r.net),
        },
        "equilibrio": {
            "be_revenue": n(r.be_revenue),
            "be_pct_of_revenue": n(r.be_pct_of_revenue),
            "margin_of_safety": n(r.margin_of_safety),
            "margin_of_safety_pct": n(r.margin_of_safety_pct),
            "operating_leverage": n(r.operating_leverage),
            # Por qué vino en None. Sin esto la pantalla muestra un guion sin
            # explicación, y un guion sin motivo se lee como «falta el dato».
            "operating_leverage_motivo": _motivo(idioma, r.operating_leverage_motivo),
            # El nombre lleva `linear` y la UI TIENE que rotularlo: en CWL la
            # ocupación va de 52% en febrero a 0,7% en septiembre.
            "be_revenue_monthly_linear": n(r.be_revenue_monthly_linear),
            "es_prorrateo_lineal": True,
        },
        "habitaciones": {
            "rooms_mix": n(r.rooms_mix), "be_room_nights": n(r.be_room_nights),
            "be_occupancy": n(r.be_occupancy), "be_trevpar": n(r.be_trevpar),
            "supone_mezcla_constante": True,
        },
        "por_departamento": [
            {"slug": d.slug, "variable_cost": n(d.variable_cost),
             "fixed_cost": n(d.fixed_cost), "excluded_cost": n(d.excluded_cost),
             "total_cost": n(d.total_cost), "revenue": n(d.revenue),
             "contribution_margin": n(d.contribution_margin),
             "cm_pct": n(d.cm_pct)}
            for d in sorted(r.por_departamento.values(), key=lambda x: x.slug)],
        "motivo": _motivo(idioma, r.motivo),
        "sin_clasificar": len(r.sin_clasificar),
        "reglas_huerfanas": len(r.reglas_huerfanas),
        # Ingreso que no cae en ningún departamento. Se informa, no se reparte:
        # sumarlo a uno le daría un margen que no es suyo, repartirlo se lo
        # daría a todos. Hoy son `REV_SUSTAINABILITY` y `REV_MISC_OTHER`.
        "ingreso_sin_departamento": n(base.ingreso_sin_departamento()),
        "lineas_sin_departamento": sorted(
            (l for l, m in base.ingreso_pl.items()
             if not base.depto_de_linea.get(l) and m),
            key=lambda l: -abs(float(base.ingreso_pl[l]))),
        # El cuadre contra el P&L, que el owner pidió que fuera explícito. Va en
        # la respuesta y no solo en una prueba: un ingreso mal atribuido deja el
        # total del hotel igual y solo mueve el margen de un depto contra otro.
        "cuadre_con_pl": [
            {"concepto": c.concepto, "base": n(c.base), "pl": n(c.pl),
             "diferencia": n(c.diferencia), "cuadra": c.cuadra}
            for c in cuadres],
    }


async def pl_engine_totales(db: AsyncSession, s: Scenario, month: int) -> dict:
    """Ingreso, ADR y habitaciones disponibles del escenario.

    Sale del propio motor del P&L para que no haya un segundo ingreso total en
    el sistema — el módulo tiene que dar el MISMO número que el reporte.
    """
    from app.engine.recalculate import compute_pl_month
    from app.models.hotel import Hotel

    meses = range(1, 13) if not month else [month]
    rev = rev_rooms = Decimal("0")
    for m in meses:
        for ln in await compute_pl_month(db, s, m):
            if ln.line_code == "TOTAL_REVENUES":
                rev += Decimal(str(ln.amount_usd))
            elif ln.line_code == "REV_ROOMS":
                rev_rooms += Decimal(str(ln.amount_usd))

    # ── Noches ocupadas y disponibles ────────────────────────────────────────
    #
    # ⚠️ **No salen de `KPI_OCCUPIED_ROOMS`**: esas líneas existen en el
    # `report_line_config` pero el motor **no las llena** — medido, dan 0 en los
    # siete presupuestos. Un KPI en cero se ve igual que un hotel vacío.
    #
    # Salen de `occupancy_budgets`, que es donde se planifican de verdad
    # (`/revenue/room-nights`). Para el `BUDGET Final 2026` son 4.363,29 noches.
    # ⚠️ **Hay DOS fuentes de noches y hay que mirar las dos.** Los presupuestos
    # y forecast se planifican en `occupancy_budgets`; los ACTUAL vienen del PMS
    # y viven en `actual_room_stats`. Leer solo la primera dejaba a los ACTUAL
    # en cero — y un cero acá no se ve como «no hay dato», se ve como un hotel
    # que no vendió una noche, que es de lo peor que puede mostrar este módulo.
    # ⚠️ **`scenario_stats` es LA fuente**, y da para los 12 escenarios con dato
    # —incluidos los ACTUAL 2024 y 2025—. Las dos primeras versiones de esto
    # leían `occupancy_budgets` y `actual_room_stats`, que cubren una parte cada
    # una, y por eso el owner veía columnas en cero: *«entonces no se puede poner
    # 4 escenarios a la par»*. No era que faltara el dato — era que se estaba
    # mirando la tabla equivocada.
    #
    # Verificado contra su hoja: `ACTUAL 2024` da **2.774,0 noches de 10.980**,
    # exacto lo que muestra su captura.
    #
    # Las otras dos quedan de respaldo y en este orden a propósito: si algún día
    # un escenario tiene `occupancy_budgets` pero no `scenario_stats`, sigue
    # funcionando en vez de caer al cálculo teórico.
    from app.models.scenario_stat import ScenarioStat
    from app.models.occupancy_budget import OccupancyBudget
    from app.models.actual_room_stat import ActualRoomStat
    from sqlalchemy import func as _f

    async def _suma(modelo, col_oc, col_disp=None):
        cols = [_f.sum(getattr(modelo, col_oc))]
        if col_disp:
            cols.append(_f.sum(getattr(modelo, col_disp)))
        q = select(*cols).where(modelo.scenario_id == s.id)
        if month:
            q = q.where(modelo.month == month)
        fila = (await db.execute(q)).one()
        oc = Decimal(str(fila[0] or 0))
        dp = Decimal(str(fila[1] or 0)) if col_disp else Decimal("0")
        return oc, dp

    ocupadas, disp_reales = await _suma(ScenarioStat, "rooms_occupied", "rooms_available")
    if not ocupadas:
        ocupadas, _ = await _suma(OccupancyBudget, "rooms_occupied")
    if not ocupadas:
        ocupadas, disp_reales = await _suma(
            ActualRoomStat, "nights_occupied", "nights_available")

    # ⚠️ Las disponibles **respetan los meses cerrados**: CWL cierra octubre, y
    # `rooms × 365` sobreestima el inventario — lo que **baja** la ocupación de
    # equilibrio, o sea que el error se ve como una buena noticia.
    hotel = await db.get(Hotel, s.hotel_id)
    cerrados = set(hotel.closed_months_list) if hotel else set()
    dias_mes = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    disponibles = disp_reales or Decimal(str(sum(
        (hotel.rooms if hotel else 0) * dias_mes[m - 1]
        for m in meses if m not in cerrados)))
    # ADR = ingreso de habitaciones / noches ocupadas. Sin noches queda en 0 y
    # las métricas de cuarto salen en None por la guarda del motor.
    adr = (rev_rooms / ocupadas) if ocupadas else Decimal("0")
    return {"revenue": rev, "revenue_rooms": rev_rooms, "adr": adr,
            "rooms_available": disponibles, "rooms_occupied": ocupadas}


@router.get("/break-e/classification/")
async def clasificacion(
    dept_slug: str = Query(...),
    scenario_id: str = Query(...),
    data_version: str = Query(...),
    month: int = Query(0, ge=0, le=12),
    db: AsyncSession = Depends(get_db),
):
    """Las filas de la pantalla de Configuración de un departamento.

    Trae el MONTO de cada regla. Sin esa columna se edita a ciegas — es lo que
    convierte la pantalla en una decisión y no en un formulario.
    """
    s = await _escenario_coherente(db, scenario_id, data_version)
    d = (await db.execute(select(BeDepartment).where(
        BeDepartment.slug == dept_slug))).scalar_one_or_none()
    if d is None:
        raise ErrorApi(404, "break_even.departamento_no_existe",
                       departamento=dept_slug)

    filas = (await db.execute(select(BeCostClassification).where(
        BeCostClassification.property_id == HOTEL_ID,
        BeCostClassification.be_department_id == d.id,
    ).order_by(BeCostClassification.be_section,
               BeCostClassification.account))).scalars().all()

    montos = await montos_del_escenario(db, s, month)
    por_clave: dict[tuple, Decimal] = {}
    por_linea: dict[str, Decimal] = {}
    for m in montos:
        por_clave[(m.dept_code, m.account)] = (
            por_clave.get((m.dept_code, m.account), Decimal("0")) + m.amount)
        por_linea[m.pl_line] = por_linea.get(m.pl_line, Decimal("0")) + m.amount

    out = []
    for c in filas:
        monto = (por_clave.get((c.dept_code, c.account))
                 if c.account else por_linea.get(c.pl_line)) or Decimal("0")
        pv = Decimal(str(c.pct_variable))
        out.append({
            "id": c.id, "dept_code": c.dept_code, "account": c.account,
            "account_name": c.account_name, "pl_line": c.pl_line,
            "be_section": c.be_section, "original_class": c.original_class,
            "pct_variable": float(pv),
            # El % fijo NO se guarda: se deriva. Va calculado para la pantalla.
            "pct_fixed": float(Decimal("1") - pv),
            "map_source": c.map_source,
            "excluded_from_be": c.excluded_from_be,
            "amount": float(round(monto, 2)),
            "amount_variable": float(round(monto * pv, 2)),
            "amount_fixed": float(round(monto * (Decimal("1") - pv), 2)),
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })
    return {
        "departamento": {"slug": d.slug, "name": d.name,
                         "generates_revenue": d.generates_revenue},
        "filas": out,
        "lineas_linea": sum(1 for x in out if x["map_source"] == "LINEA"),
    }


@router.get("/break-e/unclassified/")
async def sin_clasificar(
    scenario_id: str = Query(...),
    data_version: str = Query(...),
    month: int = Query(0, ge=0, le=12),
    db: AsyncSession = Depends(get_db),
):
    """Cuentas con movimiento y sin regla — y su espejo, reglas sin movimiento.

    Es la pantalla que evita que el modelo se degrade en silencio cuando el
    catálogo crece. Mientras estén acá, esos montos se cuentan **100% fijos**.
    """
    s = await _escenario_coherente(db, scenario_id, data_version)
    r = be.calcular(data_version=data_version, revenue=Decimal("1"),
                    montos=await montos_del_escenario(db, s, month),
                    reglas=await _reglas(db))
    return {
        "sin_regla": [
            {"dept_code": x.dept_code, "account": x.account,
             "pl_line": x.pl_line, "amount": float(round(x.amount, 2))}
            for x in sorted(r.sin_clasificar, key=lambda y: -y.amount)],
        "reglas_huerfanas": r.reglas_huerfanas,
    }


# ─── Endpoints de escritura ───────────────────────────────────────────────────

class PctBody(BaseModel):
    pct_variable: float = Field(..., ge=0, le=1)


@router.patch("/break-e/classification/{row_id}/")
async def editar_pct(row_id: str, body: PctBody,
                     db: AsyncSession = Depends(get_db)):
    """El autosave de la pantalla. **`pct_variable` es lo único editable.**"""
    c = await db.get(BeCostClassification, row_id)
    if c is None:
        raise ErrorApi(404, "break_even.regla_no_existe")
    if c.property_id != HOTEL_ID:
        raise ErrorApi(403, "break_even.regla_de_otra_propiedad")
    if c.excluded_from_be:
        raise ErrorApi(409, "break_even.linea_excluida")
    c.pct_variable = Decimal(str(body.pct_variable))
    await db.commit()
    return {"ok": True, "id": c.id, "pct_variable": float(c.pct_variable),
            "pct_fixed": float(Decimal("1") - Decimal(str(c.pct_variable)))}


class BulkBody(BaseModel):
    """Solo campos ENUMERADOS. Nunca un filtro libre del cliente convertido en
    query — es la diferencia entre editar un departamento y editar la base."""
    pct_variable: float = Field(..., ge=0, le=1)
    row_ids: list[str] = Field(default_factory=list)
    department_slug: str | None = None
    be_section: str | None = None


@router.post("/break-e/classification/bulk/")
async def editar_masivo(body: BulkBody, db: AsyncSession = Depends(get_db)):
    """Aplicar un % a una selección. Nadie va a teclear 467 porcentajes."""
    q = select(BeCostClassification).where(
        BeCostClassification.property_id == HOTEL_ID,
        BeCostClassification.excluded_from_be.is_(False))
    if body.row_ids:
        q = q.where(BeCostClassification.id.in_(body.row_ids))
    if body.department_slug:
        d = (await db.execute(select(BeDepartment).where(
            BeDepartment.slug == body.department_slug))).scalar_one_or_none()
        if d is None:
            raise ErrorApi(404, "break_even.departamento_desconocido")
        q = q.where(BeCostClassification.be_department_id == d.id)
    if body.be_section:
        q = q.where(BeCostClassification.be_section == body.be_section)
    if not (body.row_ids or body.department_slug or body.be_section):
        raise ErrorApi(422, "break_even.falta_filtro")

    filas = (await db.execute(q)).scalars().all()
    for c in filas:
        c.pct_variable = Decimal(str(body.pct_variable))
    await db.commit()
    return {"ok": True, "actualizadas": len(filas)}


@router.post("/break-e/classification/{dept_slug}/reset/")
async def restablecer(dept_slug: str, db: AsyncSession = Depends(get_db)):
    """Vuelve el departamento a la semilla: `Variable`→100%, `Fixed Cost`→0%."""
    d = (await db.execute(select(BeDepartment).where(
        BeDepartment.slug == dept_slug))).scalar_one_or_none()
    if d is None:
        raise ErrorApi(404, "break_even.departamento_no_existe",
                       departamento=dept_slug)
    filas = (await db.execute(select(BeCostClassification).where(
        BeCostClassification.property_id == HOTEL_ID,
        BeCostClassification.be_department_id == d.id,
        BeCostClassification.excluded_from_be.is_(False)))).scalars().all()
    for c in filas:
        c.pct_variable = Decimal("1") if c.original_class == "Variable" else Decimal("0")
    await db.commit()
    return {"ok": True, "restablecidas": len(filas)}


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 2 — sensibilidad y equilibrio mensual con estacionalidad
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/break-e/sensitivity/")
async def sensibilidad_endpoint(
    scenario_id: str = Query(...),
    data_version: str = Query(...),
    occ_min: float = Query(0.20, ge=0, le=1),
    occ_max: float = Query(0.60, ge=0, le=1),
    occ_paso: float = Query(0.025, gt=0, le=0.5),
    adr_min: float = Query(0.80, gt=0, le=3),
    adr_max: float = Query(1.20, gt=0, le=3),
    adr_paso: float = Query(0.05, gt=0, le=1),
    db: AsyncSession = Depends(get_db),
    idioma: str = Idioma,
):
    """Matriz ocupación × factor de ADR → resultado antes de impuestos.

    Los rangos son configurables (el spec lo pide) pero los defaults reproducen
    la hoja del modelo de referencia: 17 ocupaciones × 9 factores.
    """
    if occ_min >= occ_max or adr_min >= adr_max:
        raise ErrorApi(422, "break_even.minimo_mayor_que_maximo")
    s = await _escenario_coherente(db, scenario_id, data_version)

    montos = await montos_del_escenario(db, s, 0)
    pl = await pl_engine_totales(db, s, 0)
    r = be.calcular(data_version=data_version, revenue=pl["revenue"],
                    revenue_rooms=pl["revenue_rooms"], montos=montos,
                    reglas=await _reglas(db), adr=pl["adr"],
                    rooms_available=pl["rooms_available"])

    mix = (pl["revenue_rooms"] / pl["revenue"]) if pl["revenue"] else Decimal("0")
    # ADR implícito del escenario: ingreso de habitaciones / noches ocupadas.
    # Sin noches, la matriz no se puede escalar y el motor lo dice.
    noches = pl["rooms_occupied"]
    adr = pl["adr"]

    m = be.sensibilidad(
        cm_pct=r.cm_pct, fixed_cost=r.fixed_cost,
        rooms_available=pl["rooms_available"], adr=adr, rooms_mix=mix,
        occ_presupuestada=(noches / pl["rooms_available"]
                           if pl["rooms_available"] else None),
        ocupaciones=be._rango(Decimal(str(occ_min)), Decimal(str(occ_max)),
                              Decimal(str(occ_paso))),
        factores_adr=be._rango(Decimal(str(adr_min)), Decimal(str(adr_max)),
                               Decimal(str(adr_paso))),
    )
    return {
        "ocupaciones": [float(x) for x in m.ocupaciones],
        "factores_adr": [float(x) for x in m.factores_adr],
        "celdas": [[None if c is None else float(round(c, 2)) for c in fila]
                   for fila in m.celdas],
        "celda_presupuesto": m.celda_presupuesto,
        "motivo": _motivo(idioma, m.motivo),
        "base": {"cm_pct": float(round(r.cm_pct, 6)),
                 "fixed_cost": float(round(r.fixed_cost, 2)),
                 "adr": float(round(adr, 2)),
                 "rooms_mix": float(round(mix, 6)),
                 "rooms_available": float(pl["rooms_available"])},
        # La matriz se lee como una predicción y no lo es. Que la pantalla lo diga.
        "supuestos": [
            t(idioma, "break_even.supuesto_mezcla_constante"),
            t(idioma, "break_even.supuesto_margen_constante"),
            t(idioma, "break_even.supuesto_fijos_constantes"),
        ],
    }


async def _noches_ocupadas(db: AsyncSession, s: Scenario) -> Decimal:
    """Noches ocupadas del año, del propio motor de estadísticas del P&L."""
    from app.engine.recalculate import compute_pl_month
    total = Decimal("0")
    for m in range(1, 13):
        for ln in await compute_pl_month(db, s, m):
            if ln.line_code in ("ROOM_NIGHTS_OCC", "STAT_ROOM_NIGHTS",
                                "ROOMS_OCCUPIED"):
                total += Decimal(str(ln.amount_usd))
                break
    return total


@router.get("/break-e/monthly/")
async def equilibrio_mensual_endpoint(
    scenario_id: str = Query(...),
    data_version: str = Query(...),
    db: AsyncSession = Depends(get_db),
    idioma: str = Idioma,
):
    """El equilibrio **mes a mes**, con los costos fijos y la mezcla de cada mes.

    Reemplaza al prorrateo lineal de la Fase 1: `BE/12` daba el mismo umbral los
    doce meses, y en CWL la ocupación va de 52% en febrero a 0,7% en septiembre
    —el lodge además cierra en octubre—, así que ese número plano no describía
    ningún mes real.

    ⚠️ **Un mes sin equilibrio no es un error.** En temporada baja el margen no
    cubre el costo fijo del mes a ningún volumen: ese mes sale con `be_revenue`
    en `null` y su motivo. Rellenarlo con cero o con el promedio anual sería
    inventar que el mes cierra.
    """
    s = await _escenario_coherente(db, scenario_id, data_version)
    reglas = await _reglas(db)

    resultados = []
    for mes in range(1, 13):
        montos = await montos_del_escenario(db, s, mes)
        pl = await pl_engine_totales(db, s, mes)
        r = be.calcular(data_version=data_version, revenue=pl["revenue"],
                        revenue_rooms=pl["revenue_rooms"], montos=montos,
                        reglas=reglas)
        r.month = mes
        resultados.append(r)

    filas = be.equilibrio_mensual(resultados)
    anual = sum((f.be_revenue or Decimal("0") for f in filas), Decimal("0"))

    def n(x):
        return None if x is None else float(round(x, 2))

    return {
        "meses": [
            {"month": f.month, "revenue": n(f.revenue),
             "variable_cost": n(f.variable_cost), "fixed_cost": n(f.fixed_cost),
             "cm_pct": n(f.cm_pct), "be_revenue": n(f.be_revenue),
             "holgura": n(f.holgura), "motivo": _motivo(idioma, f.motivo),
             "cierra": f.holgura is not None and f.holgura >= 0}
            for f in filas],
        "suma_be_mensual": n(anual),
        "nota": t(idioma, "break_even.suma_mensual_no_es_el_anual"),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# COMPARAR HASTA 4 VERSIONES — mes · YTD · año completo
# ═══════════════════════════════════════════════════════════════════════════════

MODOS = ("mes", "ytd", "full")


@router.get("/break-e/compare/")
async def comparar(
    scenarios: str = Query(..., description="hasta 4 ids separados por coma"),
    modo: str = Query("full", description="mes | ytd | full"),
    month: int = Query(0, ge=0, le=12, description="el mes, para modo=mes|ytd"),
    db: AsyncSession = Depends(get_db),
):
    """Las 4 versiones lado a lado, en NOCHES, con su validación de costo.

    Owner, 2026-08-17: *«que se puedan comparar 4 versiones a la vez, mes, YTD o
    full year, que todo esté ahí, solo escoger la mezcla»*.

    ## Por qué en noches y no en ingreso

    Es la formulación de su hoja, y resulta que es **la mejor de las dos**:

        noches_equilibrio = costo_fijo / (ingreso_por_noche − costo_var_por_noche)

    Da lo mismo que `FC / CM%` —es la misma identidad— pero **no necesita el
    supuesto de mezcla constante** que sí necesita derivar noches desde el
    ingreso de equilibrio pasando por `MIX_ROOMS` y el ADR.

    ## Los tres modos

    * `mes` — solo ese mes.
    * `ytd` — de enero a ese mes, acumulado.
    * `full` — los doce.

    El divisor de «gasto promedio por mes» sigue al modo: 1, `month`, o 12. Con
    un divisor fijo, el promedio de un YTD de junio saldría por la mitad.

    ⚠️ **`data_version` no se pide acá**: sale del `type` de cada escenario, que
    es justo lo que se está comparando. Exigir uno solo haría imposible poner un
    `ACTUAL` al lado de un `FORECAST`, que es el caso de uso entero.
    """
    if modo not in MODOS:
        raise ErrorApi(422, "break_even.modo_invalido", modos=MODOS)
    ids = [x.strip() for x in scenarios.split(",") if x.strip()][:4]
    if not ids:
        raise ErrorApi(422, "break_even.sin_escenarios")
    if modo in ("mes", "ytd") and not month:
        raise ErrorApi(422, "break_even.modo_necesita_mes", modo=modo)

    meses = ([month] if modo == "mes"
             else list(range(1, month + 1)) if modo == "ytd"
             else list(range(1, 13)))
    reglas = await _reglas(db)

    salida = []
    for sid in ids:
        s = await db.get(Scenario, sid)
        if s is None or s.hotel_id != HOTEL_ID:
            raise ErrorApi(404, "escenario.no_existe_en_propiedad", escenario=sid)

        rev = vc = fc = excl = Decimal("0")
        noches_oc = noches_disp = Decimal("0")
        for m in meses:
            pl = await pl_engine_totales(db, s, m)
            r = be.calcular(data_version=s.type, revenue=pl["revenue"],
                            revenue_rooms=pl["revenue_rooms"],
                            montos=await montos_del_escenario(db, s, m),
                            reglas=reglas)
            rev += r.revenue
            vc += r.variable_cost
            fc += r.fixed_cost
            excl += r.excluded_cost
            noches_oc += pl["rooms_occupied"]
            noches_disp += pl["rooms_available"]

        # El costo del P&L del MISMO periodo. Sin esto la validación compara las
        # partes contra su propia suma y no puede fallar nunca — ver el motor.
        costo_pl = Decimal("0")
        for m in meses:
            costo_pl += await costo_del_pl(db, s, m)

        n = be.equilibrio_en_noches(
            revenue=rev, variable_cost=vc, fixed_cost=fc,
            nights_occupied=noches_oc, nights_available=noches_disp,
            meses=len(meses), costo_del_pl=costo_pl)

        def f(x):
            return None if x is None else float(round(x, 2))

        salida.append({
            "scenario_id": sid,
            "nombre": f"{s.type} · {s.version} · {s.year}",
            "data_version": s.type,
            # Los drivers de arriba de la hoja.
            "nights_available": f(noches_disp), "nights_occupied": f(noches_oc),
            "occupancy_pct": f(n.occupancy_pct),
            "adr": f(rev / noches_oc if noches_oc else None),
            # El bloque de equilibrio en noches.
            "variable": f(vc), "fixed": f(fc), "total_cost": f(vc + fc),
            "average_expense_per_month": f(n.average_expense_per_month),
            "revenue_per_night": f(n.revenue_per_night),
            "variable_cost_per_night": f(n.variable_cost_per_night),
            "contribution_per_night": f(n.contribution_per_night),
            "be_nights": f(n.be_nights),
            "be_occupancy_pct": f(n.be_occupancy_pct),
            "variance_nights": f(n.variance_nights),
            # ⚠️ Cuando la contribución por noche es negativa, cada noche vendida
            # pierde plata y las noches de equilibrio salen negativas. No es un
            # signo mal puesto: es el dato más importante de ese mes.
            "pierde_por_noche": n.pierde_por_noche,
            # ⚠️ Sin noches no hay equilibrio en noches que calcular, y la
            # pantalla tiene que decirlo: un cero se leería como un hotel que no
            # vendió nada. Los ACTUAL 2024 y 2025 de CWL están así — nadie cargó
            # sus estadísticas de habitación.
            "sin_noches": not noches_oc,
            # El bloque azul de la hoja. Ya NO es «que las partes sumen el
            # total» —eso no podía fallar—: es el costo del equilibrio contra el
            # costo del P&L. `cuadra: null` significa **sin control**, y la
            # pantalla tiene que distinguirlo de «cuadra».
            "validacion": {
                "variable_cost": f(vc), "fix_amount": f(fc),
                "total_cost": f(vc + fc), "incomes": f(rev),
                "excluded": f(excl), "costo_del_pl": f(costo_pl),
                "diferencia": f(n.validacion_costo), "cuadra": n.cuadra,
            },
        })

    return {"modo": modo, "month": month, "meses": meses, "versiones": salida}
