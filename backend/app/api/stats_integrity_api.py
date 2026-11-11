# -*- coding: utf-8 -*-
"""Master Data → Estadísticas → «Stats»: las estadísticas de Integrity al mes.

Owner, 2026-11-10: *«puedes ponerla en otro sub tab para no mezclar»* · *«la
contabilidad manda»* · *«solo full month»*.

Lee el Balance de Comprobación guardado (`mayor_movimientos`, el que se sube en
la Auditoría del mayor), toma las cuentas clase 9, suma los días de cada una y
las cruza con el catálogo homologado (`seed_data/stats_integrity_<HOTEL>.json`).
No escribe nada y no hay otra puerta de carga: el dato es el de contabilidad.
Ver `app/engine/stats_integrity.py`.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.engine import jornada
from app.engine import stats_integrity as si
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID
from app.models.mayor_movimiento import MayorMovimiento

router = APIRouter()


@router.get("/stats-integrity/catalogo/")
async def catalogo(_=Depends(get_current_user)):
    """El catálogo homologado, sin valores."""
    cat = si.leer_catalogo(HOTEL_ID)
    return {"hotel": cat.get("hotel", HOTEL_ID), "version": cat.get("version", ""),
            "grupos": cat.get("grupos", {}), "cuentas": cat.get("cuentas", [])}


@router.get("/stats-integrity/{anio}/")
async def valores(anio: int, db: AsyncSession = Depends(get_db),
                  _=Depends(get_current_user)):
    """El año: cada cuenta del catálogo con sus 12 meses (suma de los días), los
    totales por grupo, los meses que tienen balanza guardada y lo que Integrity
    registró fuera del catálogo."""
    if not 2000 <= anio <= 2100:
        raise ErrorApi(422, "stats_integrity.anio_invalido", anio=anio)
    cat = si.leer_catalogo(HOTEL_ID)
    filas = (await db.execute(
        select(MayorMovimiento.mes, MayorMovimiento.cuenta,
               MayorMovimiento.debito, MayorMovimiento.credito)
        .where(MayorMovimiento.hotel_id == HOTEL_ID, MayorMovimiento.anio == anio,
               MayorMovimiento.seg1.like("9%")))).all()
    meses = (await db.execute(
        select(distinct(MayorMovimiento.mes))
        .where(MayorMovimiento.hotel_id == HOTEL_ID, MayorMovimiento.anio == anio))).scalars().all()
    vista = si.armar_vista(cat, si.agregar(filas), meses)
    vista["anio"] = anio
    vista["hotel"] = HOTEL_ID
    return vista


# ─── El plan (Budget / Forecast) al lado de lo que registra Integrity ────────

#: Kilos de la config del reparto → área de Integrity. Los hijos de cada área
#: suman a su área (la config tiene filas por depto hijo).
_AREA_DE_DEPTO = {"0110": "rooms", "0111": "rooms", "0112": "rooms", "0113": "rooms",
                  "0114": "rooms", "0115": "rooms", "0116": "rooms",
                  "0120": "fb", "0121": "fb", "0122": "fb", "0123": "fb",
                  "0130": "spa", "0131": "spa", "0132": "spa", "0133": "spa", "0140": "spa"}


async def _fte_por_depto(db: AsyncSession, scenario_id: str) -> tuple[dict[str, list[float]], dict[str, str]]:
    """FTE por depto de planilla y mes, con las mismas reglas del reporte de
    headcount (`payroll_api.get_dept_report_monthly`): la posición sintética
    «GL» de los actuales no es gente, y el FTE cargado a mano por depto
    (`actual_dept_fte`) reemplaza al de las posiciones.

    **Una diferencia a propósito:** acá NO se sacan Cafetería (0220) ni la
    lavandería interna (0161). Para el P&L son allocation, pero su gente trabaja
    horas e Integrity las registra en la 9980 de su depto: sacarlas dejaría esas
    horas reales sin plan contra qué compararse."""
    from app.api.payroll_api import _dept_fte_override
    from app.models.payroll_position import PayrollPosition, get_fte

    out: dict[str, list[float]] = {}
    nombres: dict[str, str] = {}
    override = await _dept_fte_override(scenario_id, db)
    for p in (await db.execute(select(PayrollPosition).where(
            PayrollPosition.scenario_id == scenario_id))).scalars():
        if p.dept_name:
            nombres.setdefault(p.dept_code, p.dept_name)
        if p.position_code == "GL" or p.dept_code in override:
            continue
        fila = out.setdefault(p.dept_code, [0.0] * 12)
        for m in range(1, 13):
            fila[m - 1] += float(get_fte(p, m))
    for d, meses in override.items():
        fila = out.setdefault(d, [0.0] * 12)
        for m, f in meses.items():
            if 1 <= m <= 12:
                fila[m - 1] = f
    return out, nombres


@router.get("/stats-integrity/{anio}/plan/{scenario_id}/")
async def plan(anio: int, scenario_id: str, db: AsyncSession = Depends(get_db),
               _=Depends(get_current_user)):
    """Noches disponibles y ocupadas por tipo de habitación (Rooms / Villas /
    Residencias), tratamientos de Spa y kilos de lavandería del escenario, al
    lado de lo que registra Integrity para el mismo año.

    **El plan no se recalcula acá**: sale de lo que ya calcula el sistema —las
    noches por tipo son las de «Ingresos por tipo» (`get_revenue_by_room_type`),
    el Spa es su ingreso del P&L ÷ el precio promedio, y los kilos son los de la
    config del reparto—. Un segundo cálculo de las mismas noches es como se
    llegó a tener seis (ver `las noches disponibles se calculan en seis lugares`).
    """
    from decimal import Decimal

    from app.api import revenue_api
    from app.engine import recalculate as rc
    from app.models.laundry_allocation_config import LaundryAllocationConfig
    from app.models.laundry_params import LaundryParams
    from app.models.room_type_config import RoomTypeConfig
    from app.models.scenario import Scenario
    from app.models.scenario_stat import ScenarioStat
    from app.models.spa_budget import SpaBudget
    from app.models.statistical_entry import StatisticalEntry

    esc = await db.get(Scenario, scenario_id)
    if esc is None:
        raise ErrorApi(404, "escenario.no_encontrado")

    # Los tipos en el orden del inventario: su posición es el nivel 7 (01…08),
    # el mismo orden con que se armó el catálogo homologado. Se numeran TODOS
    # antes de filtrar, para que SH07 sea 07 en cualquier año; después quedan
    # solo los que ya existen en el año del escenario (las Villas no estaban en
    # 2026 y no tienen nada que mostrar en el Forecast 2026).
    rts = (await db.execute(select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == HOTEL_ID)
                            .order_by(RoomTypeConfig.sort_order))).scalars().all()
    tipos = [{"codigo": rt.code or "", "nombre": rt.name, "depto": rt.dept_code or "0110",
              "n7": f"{i:02d}", "unidades": rt.units}
             for i, rt in enumerate(rts, 1)
             if rt.active and (rt.vigente_desde_anio is None or rt.vigente_desde_anio <= esc.year)]

    def cargar(por_tipo, meses_rev, solo_meses=None):
        for m in meses_rev:
            if solo_meses is not None and m["month"] not in solo_meses:
                continue
            for r in m["rows"]:
                c = r.get("room_type_code") or ""
                if not c:
                    continue
                por_tipo[(c, m["month"])] = {
                    "disponibles": float(r.get("nights_available") or 0),
                    "ocupadas": float(r.get("nights_occupied") or 0),
                    "pax": float(r.get("pax") or 0)}

    por_tipo: dict = {}
    total_sin_tipo: dict = {}
    fuente = "motor"
    corte = int(esc.actuals_through or 0)
    if esc.type == "ACTUAL":
        # El ACTUAL: la estadística real por tipo, la misma de Room Stats.
        ra = await revenue_api._room_stats_from_actuals(esc.id, esc.year, db)
        if ra:
            cargar(por_tipo, ra["months"])
            fuente = "actual"
        else:
            # 2024 y 2025: la apertura por tipo (`actual_room_stats`) empieza en
            # 2026. De antes solo hay el total del hotel por mes; se muestra eso
            # y no se inventa un reparto por tipo.
            for st in (await db.execute(select(ScenarioStat).where(
                    ScenarioStat.scenario_id == esc.id))).scalars():
                total_sin_tipo[st.month] = {"disponibles": float(st.rooms_available or 0),
                                            "ocupadas": float(st.rooms_occupied or 0)}
            fuente = "actual_sin_tipo"
    elif esc.type == "FORECAST" and corte > 0:
        # Forecast rodante: los meses cerrados son los del ACTUAL enlazado, que
        # trae la estadística real por tipo; los propios solo tienen el total.
        actual = await rc.linked_actual_scenario(db, esc)
        if actual is not None:
            ra = await revenue_api._room_stats_from_actuals(actual.id, actual.year, db)
            if ra:
                cargar(por_tipo, ra["months"], set(range(1, corte + 1)))
        for st in (await db.execute(select(ScenarioStat).where(
                ScenarioStat.scenario_id == esc.id))).scalars():
            if st.month > corte:
                total_sin_tipo[st.month] = {"disponibles": float(st.rooms_available or 0),
                                            "ocupadas": float(st.rooms_occupied or 0)}
        fuente = "forecast_rodante"
    else:
        r = await revenue_api.get_revenue_by_room_type(esc.id, db)
        cargar(por_tipo, r["months"])

    # Spa: tratamientos = ingreso de Spa del P&L ÷ precio promedio del mes.
    spa = [None] * 12
    spa_rows = {s.month: s for s in (await db.execute(select(SpaBudget).where(
        SpaBudget.scenario_id == esc.id))).scalars()}
    if spa_rows:
        res = await rc.load_revenue_results(db, esc)
        for m in range(1, 13):
            s = spa_rows.get(m)
            if s is not None and (s.avg_price or 0) > 0 and m in res:
                spa[m - 1] = float(Decimal(str(res[m].spa or 0)) / Decimal(str(s.avg_price)))

    # Kilos: la config del reparto, sumada por área; uniformes y huéspedes de los parámetros.
    kilos: dict[str, list[float]] = {}
    for c in (await db.execute(select(LaundryAllocationConfig).where(
            LaundryAllocationConfig.scenario_id == esc.id))).scalars():
        area = _AREA_DE_DEPTO.get(c.dept_code)
        if not area or not c.participates:
            continue
        fila = kilos.setdefault(area, [0.0] * 12)
        for m in range(1, 13):
            fila[m - 1] += float(c.kilos_for(m))
    lp = (await db.execute(select(LaundryParams).where(
        LaundryParams.scenario_id == esc.id))).scalar_one_or_none()
    if lp is not None:
        kilos["uniformes"] = [float(lp.uniformes_for(m)) for m in range(1, 13)]
        kilos["huespedes"] = [float(lp.huespedes_for(m)) for m in range(1, 13)]

    filas = (await db.execute(
        select(MayorMovimiento.mes, MayorMovimiento.cuenta,
               MayorMovimiento.debito, MayorMovimiento.credito)
        .where(MayorMovimiento.hotel_id == HOTEL_ID, MayorMovimiento.anio == anio,
               MayorMovimiento.seg1.like("9%")))).all()

    agregado = si.agregar(filas)
    vista = si.armar_plan(tipos, por_tipo, total_sin_tipo, spa, kilos, agregado)

    # Horas regulares: días del mes × 8 × FTE (`jornada.horas_del_mes`, owner
    # 2026-11-10) por depto de planilla, contra la 9980 —que Integrity registra
    # por día, así que un mes de 31 días a tiempo completo da 248, no 240—. En un Forecast rodante los meses
    # cerrados son los del ACTUAL enlazado, igual que las noches.
    fte_plan, nombres = await _fte_por_depto(db, esc.id)
    if esc.type == "FORECAST" and corte > 0:
        actual = await rc.linked_actual_scenario(db, esc)
        if actual is not None:
            fte_act, nom_act = await _fte_por_depto(db, actual.id)
            nombres = {**nom_act, **nombres}
            for d in set(fte_plan) | set(fte_act):
                propio = fte_plan.get(d, [0.0] * 12)
                real = fte_act.get(d, [0.0] * 12)
                fte_plan[d] = [real[i] if i < corte else propio[i] for i in range(12)]
    # La base: la 9979 del escenario donde esté cargada; si no, días del mes × 8.
    bases = await _base_del_escenario(db, esc.id, anio)
    horas_plan = {d: [float(bases[i] * Decimal(str(f))) for i, f in enumerate(fila)]
                  for d, fila in fte_plan.items() if any(fila)}
    nombres.update({c["depto"]: c["depto_nombre"] for c in si.leer_catalogo(HOTEL_ID)["cuentas"]
                    if c.get("depto") and c["depto"] not in nombres})
    horas_por_fte = [float(b) for b in bases]
    vista["horas"] = si.armar_horas(horas_plan, nombres, agregado, horas_por_fte)

    vista.update({"anio": anio, "escenario": {"id": esc.id, "type": esc.type, "version": esc.version,
                                              "year": esc.year, "actuals_through": corte},
                  "fuente": fuente})
    return vista


async def _base_del_escenario(db: AsyncSession, scenario_id: str, anio: int) -> list:
    """Las horas de 1 FTE de cada mes: la 9979 del escenario o días del mes × 8."""
    from app.models.statistical_entry import StatisticalEntry
    cargadas: dict[int, float] = {}
    for mes, valor in (await db.execute(
            select(StatisticalEntry.month, StatisticalEntry.value).where(
                StatisticalEntry.scenario_id == scenario_id,
                StatisticalEntry.account_code == jornada.CUENTA_BASE))).all():
        cargadas[mes] = cargadas.get(mes, 0.0) + float(valor or 0)
    return jornada.bases_del_anio(anio, cargadas)


@router.get("/stats-integrity/{anio}/fte/{scenario_id}/")
async def reporte_fte(anio: int, scenario_id: str, db: AsyncSession = Depends(get_db),
                      _=Depends(get_current_user)):
    """El reporte de FTE por depto y puesto (owner, 2026-11-10).

    El plan sale de la planilla del escenario: el FTE de cada posición y sus
    horas (FTE × la base del mes). Las horas reales son las que registra
    contabilidad en Integrity (9980-9986, por puesto), convertidas al set
    9902-9905. El puente posición → puesto es `puestos_integrity_<hotel>.json`.
    Solo lee.
    """
    from app.models.payroll_position import PayrollPosition, get_fte
    from app.models.scenario import Scenario

    esc = await db.get(Scenario, scenario_id)
    if esc is None:
        raise ErrorApi(404, "escenario.no_encontrado")

    nombres: dict[str, str] = {}
    posiciones = []
    for p in (await db.execute(select(PayrollPosition).where(
            PayrollPosition.scenario_id == scenario_id)
            .order_by(PayrollPosition.dept_code, PayrollPosition.position_code))).scalars():
        if p.dept_name:
            nombres.setdefault(p.dept_code, p.dept_name)
        # «GL» es la posición sintética de los actuales: no es una persona.
        if p.position_code == "GL":
            continue
        posiciones.append({"depto": p.dept_code, "codigo": p.position_code or "",
                           "nombre": p.position_name, "empleado": p.employee_name or "",
                           "fte": [float(get_fte(p, m)) for m in range(1, 13)]})
    catalogo = si.leer_catalogo(HOTEL_ID)
    nombres.update({c["depto"]: c["depto_nombre"] for c in catalogo["cuentas"]
                    if c.get("depto") and c["depto"] not in nombres})

    bases = await _base_del_escenario(db, scenario_id, anio)
    agregado = si.agregar((await db.execute(
        select(MayorMovimiento.mes, MayorMovimiento.cuenta,
               MayorMovimiento.debito, MayorMovimiento.credito)
        .where(MayorMovimiento.hotel_id == HOTEL_ID, MayorMovimiento.anio == anio,
               MayorMovimiento.seg1.like("99%")))).all())

    vista = si.armar_fte(posiciones, nombres, bases, si.leer_mapa_puestos(HOTEL_ID),
                         si.nombres_de_puestos(catalogo), si.horas_integrity_por_puesto(agregado))
    vista.update({"anio": anio, "escenario": {"id": esc.id, "type": esc.type,
                                              "version": esc.version, "year": esc.year}})
    return vista
