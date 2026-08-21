"""
recalculate.py — full-scenario recalculation orchestrator (CLAUDE.md §recalc).

Order:
  1. Payroll  — refresh auto concepts (6000 SW, 6020 CCSS, 6021 Aguinaldo)
  2. Allocations — regenerate cafetería (0220) + lavandería (0161), net to $0
  3. P&L — build and persist pl_lines for all 12 months
  (Revenue is computed on the fly from rate cards/occupancy — nothing to persist.)

This module is DB-aware on purpose: it ties the pure engines together. The pure
P&L math lives in pl_engine.py and is unit-tested independently.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import uuid
from decimal import Decimal

from sqlalchemy import select, delete, func

from app.models.scenario import Scenario
from app.models.exchange_rate import ExchangeRate, get_tc_for_month
from app.models.payroll_position import PayrollPosition
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.cost_entry import CostEntry
from app.models.opex_entry import OpexEntry
from app.models.nonop_entry import NonOpEntry
from app.models.allocation_entry import AllocationEntry
from app.models.benefit_allocation_config import BenefitAllocationConfig
from app.models.cafeteria_allocation_config import CafeteriaAllocationConfig
from app.models.laundry_allocation_config import LaundryAllocationConfig
from app.models.salary_allocation_config import SalaryAllocationConfig
from app.models.rooms_allocation_config import RoomsAllocationConfig
from app.models.department_catalog import DepartmentCatalog
from app.models.laundry_params import LaundryParams
from app.models.pl_line import PLLine
from app.models.pl_manual_input import PLManualInput
from app.models.actual_entry import ActualEntry
from app.models.actual_pl_line import ActualPLLine
from app.models.mapping import AccountMapping, ReportLineConfig

from app.models.room_type_config import RoomTypeConfig
from app.models.sales_channel_config import SalesChannelConfig
from app.models.rate_card import RateCard
from app.models.occupancy_budget import OccupancyBudget
from app.models.package_config import PackageConfig
from app.models.revenue_other import RevenueOther
from app.models.revenue_entry import RevenueEntry, REVENUE_LINES
from app.models.scenario_stat import ScenarioStat

from app.engine.revenue_calculator import calculate_revenue, RevenueResult
from app.engine.payroll_calculator import (
    recalculate_entry, total_entry, repartir_beneficio,
)
from app.engine.allocation_calculator import (
    calculate_cafeteria_distribution,
    calculate_laundry_distribution,
    calculate_salary_distribution,
    calculate_rooms_by_pct,
    loaded_salary_breakdown,
)
from app.engine.payroll_calculator import calc_sw, CCSS_RATE, AGUINALDO_DIVISOR
from app.engine import pl_engine
from app.engine.meses_cerrados import meses_cerrados as meses_cerrados_de

ZERO = Decimal("0")
MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"]

PAYROLL_ALL_COLS = [
    "c6000_sw", "c6001_overtime", "c6002_day_off", "c6003_working_holiday",
    "c6004_disabilities", "c6010_commissions", "c6020_ccss", "c6021_aguinaldo",
    "c6022_occ_hazard", "c6023_vacation_prov", "c6024_vacations_taken",
    "c6025_cafeteria", "c6026_severance", "c6027_incentive_bonus",
    "c6028_housing", "c6029_transport", "c6030_other",
]


# ─── Revenue ──────────────────────────────────────────────────────────────────
# RevenueEntry.line (uppercase) → RevenueResult field
_REVENUE_LINE_TO_FIELD = {ln: ln.lower() for ln in REVENUE_LINES}


async def revenue_results_from_checkbook(
    session, scenario: Scenario
) -> dict[int, RevenueResult]:
    """Build RevenueResult per month from direct RevenueEntry amounts.

    Used when scenario.revenue_source == 'checkbook': the user types the USD
    amount per P&L revenue line, so we read those straight into the result
    instead of deriving them from rate cards × occupancy. Room KPIs (available /
    occupied / guests) come from ScenarioStat; ADR / RevPAR / occupancy% derive
    from them on read (RevenueResult properties).
    """
    sid = scenario.id
    entries = (await session.execute(
        select(RevenueEntry).where(RevenueEntry.scenario_id == sid)
    )).scalars().all()
    stats = {
        s.month: s for s in (await session.execute(
            select(ScenarioStat).where(ScenarioStat.scenario_id == sid)
        )).scalars().all()
    }

    results: dict[int, RevenueResult] = {}
    for month in range(1, 13):
        r = RevenueResult(month=month, year=scenario.year)
        for e in entries:
            field = _REVENUE_LINE_TO_FIELD.get(e.line.upper())
            if field is not None:
                setattr(r, field, e.get_month(month) or ZERO)
        st = stats.get(month)
        if st is not None:
            r.rooms_available = int(st.rooms_available or 0)
            r.rooms_occupied = st.rooms_occupied or ZERO
            r.guests = st.guests or ZERO
        results[month] = r
    return results


async def load_revenue_results(session, scenario: Scenario) -> dict[int, RevenueResult]:
    """Compute RevenueResult for all 12 months (mirrors revenue_api)."""
    if getattr(scenario, "revenue_source", "drivers") == "checkbook":
        return await revenue_results_from_checkbook(session, scenario)
    sid = scenario.id
    channels = (await session.execute(
        select(SalesChannelConfig).where(SalesChannelConfig.scenario_id == sid)
    )).scalars().all()
    rate_cards = (await session.execute(
        select(RateCard).where(RateCard.scenario_id == sid)
    )).scalars().all()
    occupancies = (await session.execute(
        select(OccupancyBudget).where(OccupancyBudget.scenario_id == sid)
    )).scalars().all()
    pkg_configs = (await session.execute(
        select(PackageConfig).where(PackageConfig.scenario_id == sid)
    )).scalars().all()
    other_revenues = (await session.execute(
        select(RevenueOther).where(RevenueOther.scenario_id == sid)
    )).scalars().all()
    room_types = (await session.execute(
        select(RoomTypeConfig)
        .where(RoomTypeConfig.hotel_id == scenario.hotel_id)
        .order_by(RoomTypeConfig.sort_order)
    )).scalars().all()
    room_type_units = {rt.id: rt.units for rt in room_types}
    # Override de unidades por escenario (master data por año), si existe.
    from app.models.scenario_master import ScenarioMaster
    sm = (await session.execute(
        select(ScenarioMaster).where(ScenarioMaster.scenario_id == scenario.id)
    )).scalar_one_or_none()
    if sm and sm.units_json:
        import json
        try:
            for rtid, u in json.loads(sm.units_json).items():
                if rtid in room_type_units:
                    room_type_units[rtid] = int(u)
        except (ValueError, TypeError):
            pass

    results: dict[int, RevenueResult] = {}
    for month in range(1, 13):
        results[month] = calculate_revenue(
            month=month,
            year=scenario.year,
            rate_cards=[rc for rc in rate_cards if rc.month == month],
            occ_budgets=[ob for ob in occupancies if ob.month == month],
            channels=[c for c in channels if getattr(c, "month", month) == month] or channels,
            pkg_configs=pkg_configs,
            other_revenues=[ot for ot in other_revenues if ot.month == month],
            room_type_units=room_type_units,
        )
    return results


def revenue_line_dict(r: RevenueResult) -> dict[str, Decimal]:
    return {
        "rooms": r.rooms, "food": r.food, "beverage": r.beverage,
        "activities": r.activities, "transport": r.transport,
        "sustainability": r.sustainability, "spa": r.spa, "retail": r.retail,
        "fnb_misc": r.fnb_misc, "innoceana": r.innoceana, "laundry": r.laundry,
        "club": r.club, "club_actividad": r.club_actividad,
        "club_visitantes": r.club_visitantes,
    }


# ─── Per-dept aggregations ────────────────────────────────────────────────────
async def payroll_by_dept(session, scenario_id: str, month: int) -> dict[str, Decimal]:
    rows = (await session.execute(
        select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id,
            PayrollConceptEntry.month == month,
        )
    )).scalars().all()
    out: dict[str, Decimal] = {}
    for e in rows:
        total = sum((getattr(e, c) or ZERO) for c in PAYROLL_ALL_COLS)
        out[e.dept_code] = out.get(e.dept_code, ZERO) + total
    return out


async def cos_by_dept(session, scenario_id: str, month: int) -> dict[str, Decimal]:
    rows = (await session.execute(
        select(CostEntry).where(CostEntry.scenario_id == scenario_id)
    )).scalars().all()
    out: dict[str, Decimal] = {}
    for e in rows:
        out[e.dept_code] = out.get(e.dept_code, ZERO) + (e.get_month(month) or ZERO)
    return out


async def opex_by_dept(session, scenario_id: str, month: int) -> dict[str, Decimal]:
    rows = (await session.execute(
        select(OpexEntry).where(OpexEntry.scenario_id == scenario_id)
    )).scalars().all()
    out: dict[str, Decimal] = {}
    for e in rows:
        out[e.dept_code] = out.get(e.dept_code, ZERO) + (e.get_month(month) or ZERO)
    return out


async def alloc_by_dept(session, scenario_id: str, month: int) -> dict[str, Decimal]:
    rows = (await session.execute(
        select(AllocationEntry).where(
            AllocationEntry.scenario_id == scenario_id,
            AllocationEntry.month == month,
        )
    )).scalars().all()
    out: dict[str, Decimal] = {}
    for e in rows:
        out[e.target_dept] = out.get(e.target_dept, ZERO) + (e.amount_usd or ZERO)
    return out


async def manual_for(session, scenario_id: str, month: int) -> pl_engine.ManualInputs:
    row = (await session.execute(
        select(PLManualInput).where(
            PLManualInput.scenario_id == scenario_id,
            PLManualInput.month == month,
        )
    )).scalar_one_or_none()
    if row is None:
        return pl_engine.ManualInputs()
    return pl_engine.ManualInputs(
        rent=row.rent,
        mgmt_fee_pct_3=row.mgmt_fee_pct_3,
        mgmt_fee_pct_5=row.mgmt_fee_pct_5,
        properties_insurance=row.properties_insurance,
        capital_reserve=row.capital_reserve,
        capital_reserve_pct=row.capital_reserve_pct,
        large_capex=row.large_capex,
        bank_interest=row.bank_interest,
        depreciation=row.depreciation,
        income_tax_rate=row.income_tax_rate,
    )


# ─── Account mapping (DB-driven P&L engine support) ──────────────────────────
def _cache_de_configuracion(session) -> dict:
    """Caché que vive lo mismo que la sesión, o sea UNA petición.

    El P&L se computa mes a mes, así que estas dos tablas —el mapeo de cuentas
    (810 filas) y la estructura del reporte (90)— se releían 25 veces por
    pantalla, idénticas las 25. Eran 50 de las 280 consultas que costaba abrir
    el Cash Flow Budget, y ese costo fue lo que vació el pool de conexiones y
    tumbó las pantallas con «Failed to fetch».

    Se guarda en `session.info`, que SQLAlchemy expone justo para esto. El
    alcance es la petición: nada puede cambiar el mapeo en el medio —
    `mapping_api` solo escribe, nunca recomputa el P&L en la misma llamada—, así
    que no hay riesgo de servir un mapeo viejo. Un caché con TTL sí lo tendría, y
    de todos los errores posibles acá el peor es el que devuelve un número
    plausible calculado con el mapeo de ayer.
    """
    return session.info.setdefault("finplan_config_cache", {})


def _vigente_en(m, periodo: str | None) -> bool:
    """¿Rige esta regla en `periodo` (`YYYY-MM`)? `None` = la vigente hoy.

    Se lee con `getattr` y no con el método del modelo a propósito: por acá
    pasan filas de la base, diccionarios y dobles de prueba, y una regla sin
    columnas de vigencia —cualquier cosa anterior a la migración 123— tiene que
    seguir contando como vigente siempre, no reventar.
    """
    desde = getattr(m, "vigente_desde", None)
    hasta = getattr(m, "vigente_hasta", None)
    if periodo is None:
        return hasta is None
    if desde and periodo < desde:
        return False
    if hasta and periodo > hasta:
        return False
    return True


async def load_active_account_mappings(
    session, report_id: str = "P&L_DETAIL_OWNERS", periodo: str | None = None,
) -> list[dict]:
    """Return active account_mapping rows as plain dicts for pl_engine.

    `periodo` (`YYYY-MM`) pide el mapeo VIGENTE EN ESE MES; `None` —el default,
    y lo que usa todo el P&L del día a día— pide el vigente hoy.

    Existe por D9: desde jul-2026 la cuenta 7120 dejó `OH_ADMIN` y se fue a
    `OH_CC_COMMISSIONS`. Las dos reglas conviven en la tabla, y sin filtrar por
    vigencia cuál gana depende del orden físico de las filas — `construir_resolvedor`
    se queda con la primera que ve para cada (depto, cuenta). Filtrar acá es lo
    que hace que un período ya enviado a SCP siga devolviendo lo mismo.
    """
    cache = _cache_de_configuracion(session)
    clave = ("account_mapping", report_id, periodo)
    if clave in cache:
        # copia de la lista: si alguien la ordena o le agrega, no envenena al resto
        return list(cache[clave])
    rows = (await session.execute(
        select(AccountMapping)
        .where(AccountMapping.report_id == report_id, AccountMapping.active_status == "YES")
    )).scalars().all()
    rows = [m for m in rows if _vigente_en(m, periodo)]
    salida = [
        {
            "account_code": m.account_code,
            "dept_code": m.dept_code or "",
            "report_line_code": m.report_line_code,
            "active_status": m.active_status,
            "rollup_operator": m.rollup_operator,
        }
        for m in rows
    ]
    cache[clave] = salida
    return list(salida)


async def load_report_line_config(session, report_id: str = "P&L_DETAIL_OWNERS") -> list[dict]:
    """Return active report_line_config rows as plain dicts for pl_engine."""
    cache = _cache_de_configuracion(session)
    clave = ("report_line_config", report_id)
    if clave in cache:
        return list(cache[clave])
    rows = (await session.execute(
        select(ReportLineConfig)
        .where(ReportLineConfig.report_id == report_id, ReportLineConfig.active == True)
        .order_by(ReportLineConfig.display_order)
    )).scalars().all()
    salida = [
        {
            "line_code": r.line_code,
            "line_name": r.line_name,
            "section": r.section,
            "line_type": r.line_type,
            "display_order": r.display_order,
            "calculation_logic": r.calculation_logic,
            "active": r.active,
        }
        for r in rows
    ]
    cache[clave] = salida
    return list(salida)


# ─── Actuals (ActualEntry) ────────────────────────────────────────────────────
async def actual_rows_for_month(session, scenario_id: str, month: int) -> list[dict]:
    """Raw {account_code, dept_code, amount} rows from ActualEntry for one month."""
    rows = (await session.execute(
        select(ActualEntry).where(ActualEntry.scenario_id == scenario_id)
    )).scalars().all()
    return [
        {"account_code": e.account_code, "dept_code": e.dept_code,
         "amount": e.get_month(month)}
        for e in rows
    ]


async def actual_pl_lines_for_month(session, scenario_id: str, month: int) -> dict[str, Decimal]:
    """Stored line-level actual amounts {line_code: amount} for one month."""
    rows = (await session.execute(
        select(ActualPLLine).where(
            ActualPLLine.scenario_id == scenario_id,
            ActualPLLine.month == month,
        )
    )).scalars().all()
    return {r.line_code: r.amount_usd for r in rows}


# ─── Checkbook → account-level rows (budget/forecast built from scratch) ──────
async def checkbook_account_rows_for_month(
    session, scenario_id: str, month: int
) -> list[dict]:
    """
    Roll the in-app checkbooks up to account-level rows
    [{account_code, dept_code, amount}] — the same shape as ActualEntry — so a
    budget/forecast built from scratch flows through the *same* validated
    DB-driven P&L engine as the imported actuals.

    Sources:
      OpexEntry            → account_code (7xxx)
      CostEntry            → account_code (5xxx; empty in CWL — costs go to 7xxx)
      PayrollConceptEntry  → one row per non-zero concept column (6000…6030)

      AllocationEntry      → cargo y crédito de cada reparto, por su cuenta

    Below-GOP (NonOpEntry, 8xxx) is NOT rolled up here: those P&L lines are
    seeded directly by report_line_code (see nonop_line_seeds_for_month) because
    several lines share one GL account and the account→line mapping can't split
    them. Revenue is line-level from rate cards and is injected as seeds too.

    Los REPARTOS sí entran. Antes no, con el argumento de que «netean a cero»
    —cierto para el total, pero repartir es justamente mover el costo de sitio:
    dejarlos afuera hacía que la lavandería y la cafetería se quedaran con TODO
    su costo en overhead y que Habitaciones, A&B y Spa nunca recibieran su
    parte. El cálculo se hacía, se dibujaba en pantalla, y el P&L lo ignoraba.

    El crédito viaja con ellos, así que el gasto total no se mueve: lo único
    que cambia es en qué línea del P&L queda cada colón. Ojo: el crédito
    necesita regla de mapeo, si no se cae y el gasto sube (migración 079).

    No hay realimentación: el costo a repartir se calcula de opex, planilla y
    costos —nunca de allocation_entries—, así que meter esto acá no altera la
    base del próximo reparto.
    """
    rows: list[dict] = []
    cd = pl_engine.consolidate_dept  # sub-dept → P&L parent (Rooms/F&B/Spa/Admin)

    opex = (await session.execute(
        select(OpexEntry).where(OpexEntry.scenario_id == scenario_id)
    )).scalars().all()
    for e in opex:
        amt = e.get_month(month) or ZERO
        if amt:
            rows.append({"account_code": e.account_code, "dept_code": cd(e.dept_code),
                         "amount": amt})

    costs = (await session.execute(
        select(CostEntry).where(CostEntry.scenario_id == scenario_id)
    )).scalars().all()
    for e in costs:
        amt = e.get_month(month) or ZERO
        if amt:
            rows.append({"account_code": e.account_code, "dept_code": cd(e.dept_code),
                         "amount": amt})

    payroll = (await session.execute(
        select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id,
            PayrollConceptEntry.month == month,
        )
    )).scalars().all()
    for e in payroll:
        for col in PAYROLL_ALL_COLS:
            amt = getattr(e, col) or ZERO
            if amt:
                rows.append({
                    "account_code": pl_engine.payroll_account_for_column(col),
                    "dept_code": cd(e.dept_code), "amount": amt,
                })

    # Los repartos, cargo y crédito, cada uno por su cuenta. Es lo que hace que
    # el reparto de verdad llegue al P&L y no se quede dibujado en su pantalla.
    repartos = (await session.execute(
        select(AllocationEntry).where(
            AllocationEntry.scenario_id == scenario_id,
            AllocationEntry.month == month,
        )
    )).scalars().all()
    for e in repartos:
        amt = e.amount_usd or ZERO
        if amt:
            rows.append({"account_code": e.account, "dept_code": cd(e.target_dept),
                         "amount": amt})

    return rows


async def nonop_line_seeds_for_month(
    session, scenario_id: str, month: int
) -> dict[str, Decimal]:
    """
    Sum the below-GOP mini checkbook (NonOpEntry) by report_line_code for one
    month → {report_line_code: amount}. These seed the P&L lines directly
    (Capital Reserve, Large Capex, Depreciation, Asset Loss, Rent, Insurance,
    Other, Bank Interest, Leasings, Financial Losses) since the account→line
    mapping can't separate lines that share a GL account.
    """
    rows = (await session.execute(
        select(NonOpEntry).where(NonOpEntry.scenario_id == scenario_id)
    )).scalars().all()
    out: dict[str, Decimal] = {}
    for e in rows:
        amt = e.get_month(month) or ZERO
        if amt:
            out[e.report_line_code] = out.get(e.report_line_code, ZERO) + amt
    return out


# ─── Rolling forecast: linked ACTUAL scenario ─────────────────────────────────
async def linked_actual_scenario(session, scenario: Scenario) -> Scenario | None:
    """The ACTUAL scenario for the same hotel + year (most recent if several)."""
    return (await session.execute(
        select(Scenario)
        .where(
            Scenario.hotel_id == scenario.hotel_id,
            Scenario.year == scenario.year,
            Scenario.type == "ACTUAL",
        )
        .order_by(Scenario.created_at.desc())
    )).scalars().first()


# ─── Compute P&L for a single month (no persistence) ──────────────────────────
async def compute_pl_month(
    session, scenario: Scenario, month: int,
    revenue_results: dict[int, RevenueResult] | None = None,
    periodo: str | None = None,
) -> list[pl_engine.PLLineResult]:
    """Wrapper: computa el P&L del mes y expone ambos vocabularios de código (viejo
    importado / nuevo checkbook) con el mismo valor, para que todo consumidor funcione.

    `periodo` (`YYYY-MM`) computa con el mapeo VIGENTE EN ESE MES; `None` —el
    default y lo que usa toda la app— con el vigente hoy. Lo necesita el reporte
    a SCP: un período ya enviado tiene que devolver lo mismo al reejecutarse
    aunque el mapeo haya cambiado después (ver D9 en docs/OWNERS_Q.md)."""
    lines = await _compute_pl_month_core(session, scenario, month, revenue_results,
                                         periodo)
    return pl_engine.canonicalize_pl_lines(pl_engine.add_pl_aliases(lines))


# Cuánto se tolera entre el resumen y el detalle antes de considerar que NO
# dicen lo mismo. Un dólar: por debajo es redondeo.
TOLERANCIA_FINO = Decimal("1")

# Los totales que tienen que coincidir para poder usar el detalle. Si estos siete
# dan igual, los dos caminos cuentan la misma plata y solo cambia el corte.
_TOTALES_CLAVE = ("TOTAL_REVENUES", "TOTAL_OPERATING_EXPENSES",
                  "TOTAL_OVERHEAD_EXPENSES", "TOTAL_GOP",
                  "EBITDA_BEFORE_CAPITAL", "EBT", "NET_PROFIT")


async def _detalle_fino_si_cuadra(session, scenario, month: int,
                                  line_amounts: dict,
                                  periodo: str | None = None) -> list | None:
    """El P&L del detalle del mayor, SOLO si da los mismos totales que el resumen.

    **El problema (owner, 2026-08-14).** Para un escenario con resumen importado
    el P&L sale de `actual_pl_from_lines`, que corre sobre la plantilla del motor
    viejo. Esa plantilla **no emite ni una** de las líneas nuevas: ni `COS_*`, ni
    `COH_*`, ni `REV_FB_BEV`, ni `REV_ROOMS_OTHER`, ni los `PROFIT_*`. Por eso
    `OPERATING_PROFIT` salía en cero y el A&B aparecía sin abrir.

    El resumen es **más grueso que el mayor**: todo el A&B en una línea, sin el
    otro ingreso de habitaciones, y el misceláneo metido dentro de Sustainability.
    El detalle sí tiene la apertura, porque la lleva la cuenta.

    **Por qué no se puede usar siempre.** Los dos caminos no siempre cuentan lo
    mismo. Verificado contra producción:

        · Actual 2025 y 2026 → cuadran al centavo, línea por línea
        · Actual 2024 → NO: el detalle tiene $40,613 de gasto de más y $3,085 de
          ingreso de menos. Son las filas sin número de cuenta que el importador
          se tragaba y la diferencia de Innoceana.

    Con 2024, usar el detalle cambiaría el GOP reportado en $43,698 — el número
    que el owner ya revisó y cerró. Y no usarlo pero mostrar su apertura daría un
    desglose que no suma su propio total, que es peor.

    Así que se elige con evidencia: si los siete totales coinciden, el detalle no
    cambia el resultado y se gana la apertura. Si no, manda el resumen, como
    siempre. **Nunca en silencio a medias.**

    ⚠️ **Se juzgan solo los meses que el escenario REPORTA** (`meses_propios`):
    un forecast con corte toma sus meses cerrados del ACTUAL enlazado, así que
    su resumen y su detalle de esos meses no producen nada y no pueden decidir
    nada. Ver `veredicto_del_detalle`.

    ⚠️ **La decisión es por ESCENARIO, no por mes.** La primera versión decidía
    mes a mes y dejó el Actual 2024 MEZCLADO: los meses que cuadraban traían el
    detalle y los otros el resumen, así que `OPERATING_PROFIT` sumaba solo parte
    del año y ya no daba `GOP + overhead`. Un cuadro internamente incoherente es
    peor que uno grueso — el grueso al menos cierra consigo mismo.
    """
    if not await _el_detalle_cuadra(session, scenario):
        return None
    filas = await actual_rows_for_month(session, scenario.id, month)
    if not filas:
        return None
    mappings = await load_active_account_mappings(session, periodo=periodo)
    report_lines = await load_report_line_config(session)
    if not mappings or not report_lines:
        return None
    return pl_engine.calculate_pl_from_mapping(filas, mappings, report_lines)


async def meses_propios(session, scenario) -> list[int]:
    """Los meses que este escenario produce con SUS PROPIAS fuentes.

    Un forecast con corte (`actuals_through`) **no reporta sus meses cerrados**:
    `_compute_pl_month_core` los toma del ACTUAL enlazado y ni mira el resumen ni
    el detalle de este escenario. Preguntar por esos meses es preguntar por datos
    que nadie lee.

    Espeja *exactamente* la condición de desvío de `_compute_pl_month_core`,
    enlace incluido: si no hay ACTUAL enlazado el desvío no ocurre y los doce
    meses vuelven a ser propios.
    """
    corte = scenario.actuals_through or 0
    if scenario.type == "FORECAST" and corte >= 1:
        if await linked_actual_scenario(session, scenario) is not None:
            return list(range(corte + 1, 13))
    return list(range(1, 13))


async def veredicto_del_detalle(session, scenario) -> dict:
    """Por qué el motor elige la fuente que elige, con la evidencia a la vista.

    Devuelve la decisión Y su motivo, en vez del `bool` mudo de antes. El owner
    lo dijo así: «el **detalle** es la forma de manejar reportes, el **validado**
    es la forma de decir que el detalle está bien y que el resumen valida eso.
    **Para mí ambos son importantes.**» Un desacuerdo entre las dos hojas es la
    señal que él quiere ver — resolverlo en silencio la borra.

    ⚠️ **Se evalúan SOLO los meses propios** (ver `meses_propios`). La primera
    versión recorría los doce siempre, y para un forecast con corte eso mezclaba
    meses que el reporte ni siquiera usa. Medido el 2026-08-16 contra
    producción, el `FORECAST Working 2026` (corte=6) daba los siete totales
    descuadrados sobre 12 meses; respetando su corte, el ingreso, el GOP, el
    EBITDA, el EBT y el impuesto quedan en **cero diferencia** y solo sobrevive
    un traslado real de $1.303,00 de `OPEX_LAUNDRY` a overhead. O sea que casi
    todo el descuadre vivía en **mayo**, un mes cerrado que ese forecast toma
    del Actual 2026 y que este escenario no reporta.

    Se calcula una vez por escenario y se guarda en la caché de la sesión: se
    consulta en cada mes, y recorrer el año entero doce veces sería carísimo.
    """
    cache = _cache_de_configuracion(session)
    clave = ("veredicto_detalle", scenario.id)
    if clave in cache:
        return cache[clave]

    meses = await meses_propios(session, scenario)
    corte = scenario.actuals_through or 0
    base = {
        "meses_evaluados": meses,
        "actuals_through": corte,
        "tolerancia": float(TOLERANCIA_FINO),
        "totales_clave": list(_TOTALES_CLAVE),
        "diferencias": [],
    }

    def _cerrar(manda: str, motivo: str, **extra) -> dict:
        v = {**base, "manda": manda, "motivo": motivo, **extra}
        cache[clave] = v
        return v

    canon = {k: v[0] for k, v in pl_engine._MOTOR_TO_CANON.items()}
    mappings = await load_active_account_mappings(session)
    report_lines = await load_report_line_config(session)
    if not mappings or not report_lines:
        return _cerrar("resumen", "No hay mapeo de cuentas configurado: el "
                                  "detalle no se puede consolidar.")

    resumen: dict[str, Decimal] = {}
    detalle: dict[str, Decimal] = {}
    meses_con_detalle: list[int] = []
    for m in meses:
        for code, monto in (await actual_pl_lines_for_month(session, scenario.id, m)).items():
            c = canon.get(code, code)
            resumen[c] = resumen.get(c, ZERO) + Decimal(str(monto or 0))
        filas = await actual_rows_for_month(session, scenario.id, m)
        if not filas:
            continue
        meses_con_detalle.append(m)
        for ln in pl_engine.calculate_pl_from_mapping(filas, mappings, report_lines):
            c = canon.get(ln.line_code, ln.line_code)
            detalle[c] = detalle.get(c, ZERO) + ln.amount_usd

    base["meses_con_detalle"] = meses_con_detalle
    if not meses_con_detalle:
        return _cerrar("resumen", "El escenario no tiene detalle del mayor en "
                                  "los meses que reporta.")

    diferencias = []
    for c in _TOTALES_CLAVE:
        r, d = resumen.get(c, ZERO), detalle.get(c, ZERO)
        if abs(r - d) > TOLERANCIA_FINO:
            diferencias.append({"total": c, "resumen": float(r),
                                "detalle": float(d), "diferencia": float(d - r)})
    base["diferencias"] = diferencias

    rango = f"{meses[0]}–{meses[-1]}" if meses else "—"
    recorte = (f" (meses {rango}: los meses 1–{corte} los reporta el Actual "
               f"enlazado, no este escenario)") if len(meses) < 12 else ""
    if diferencias:
        cuales = ", ".join(f"{x['total']} {x['diferencia']:+,.2f}" for x in diferencias)
        return _cerrar("resumen",
                       f"Manda el RESUMEN: el detalle no reproduce "
                       f"{len(diferencias)} de los {len(_TOTALES_CLAVE)} totales "
                       f"de control{recorte} → {cuales}.")
    return _cerrar("detalle",
                   f"Manda el DETALLE: reproduce los {len(_TOTALES_CLAVE)} "
                   f"totales de control del resumen{recorte}, y además abre las "
                   f"líneas que el resumen no tiene.")


async def _el_detalle_cuadra(session, scenario) -> bool:
    """¿El detalle del mayor da los MISMOS totales que el resumen, en los meses
    que este escenario reporta? Es el veredicto reducido a sí o no."""
    return (await veredicto_del_detalle(session, scenario))["manda"] == "detalle"


async def lo_subido_manda(session, scenario) -> bool:
    """¿Los números de este escenario SE SUBIERON, en vez de calcularse?

    Regla del owner: «en los históricos solo debe aceptar lo que se sube… nada
    más» · «los históricos rompen los auxiliares… y se va directo al GL».

    **La pregunta es por el ORIGEN del dato, no por el TIPO del escenario.** Un
    `BUDGET` o un `FORECAST` importado es tan histórico como un `ACTUAL`: sus
    cifras salieron de un archivo, no de la planilla ni de los checkbooks.
    Preguntar `type == "ACTUAL"` los dejaba caer en la rama de cálculo completa,
    que les pisa monedas, planilla y repartos — justo los auxiliares que la
    regla manda no tocar.

    Espeja la condición de `_compute_pl_month_core`, que es quien de verdad
    elige la fuente: manda lo subido cuando el escenario **no** está en modo
    checkbook **y** tiene datos cargados. El «y» no es un detalle — los
    presupuestos 2028-2035 están en modo `imported` y VACÍOS, así que el motor
    los calcula desde los checkbooks; mirar solo `source_mode` los trataría como
    históricos y les congelaría un P&L que nadie subió. Es la misma doctrina que
    `scenarios_api.LLAVES_DEL_MAYOR`: «`source_mode='imported'` sin ninguno de
    los dos NO es un escenario histórico: es uno que dice serlo y no lo es».
    """
    if getattr(scenario, "source_mode", "imported") == "checkbook":
        return False
    # Se cachea en la sesión —la misma caché que evita releer el mapeo 25 veces
    # por pantalla—: un escenario `imported` y VACÍO recorre los doce meses sin
    # encontrar nada, y hay endpoints que preguntan más de una vez.
    cache = _cache_de_configuracion(session)
    clave = ("lo_subido_manda", scenario.id)
    if clave in cache:
        return cache[clave]
    veredicto = False
    for m in range(1, 13):
        if (await actual_pl_lines_for_month(session, scenario.id, m)
                or await actual_rows_for_month(session, scenario.id, m)):
            veredicto = True
            break
    cache[clave] = veredicto
    return veredicto


async def _compute_pl_month_core(
    session, scenario: Scenario, month: int,
    revenue_results: dict[int, RevenueResult] | None = None,
    periodo: str | None = None,
) -> list[pl_engine.PLLineResult]:
    # Rolling forecast blend: a closed month (<= actuals_through) is the recorded
    # truth — compute it from the linked ACTUAL scenario instead of this
    # forecast's checkbooks. Later months fall through to the forecast below.
    if (scenario.type == "FORECAST" and (scenario.actuals_through or 0) >= month):
        actual = await linked_actual_scenario(session, scenario)
        if actual is not None:
            return await compute_pl_month(session, actual, month, periodo=periodo)
    # source_mode='checkbook' → skip the imported snapshot and build the P&L from
    # the in-app checkbooks (so "edit checkbook → account total → P&L" takes
    # effect). 'imported' (default) reads the loaded snapshot below.
    checkbook_mode = getattr(scenario, "source_mode", "imported") == "checkbook"
    if not checkbook_mode:
        # If recorded data was imported (any scenario type — actuals, or budget/
        # forecast snapshots loaded from the workbook), compute from it instead of
        # the in-app checkbooks. Prefer line-level (macro P&L) then account-level.
        #
        # …salvo que el escenario tenga prendido `usar_detalle`. Ahí se salta el
        # resumen y va derecho al mayor. Existe para el caso en que el
        # INCOMPLETO es el resumen: el guardián de `_detalle_fino_si_cuadra`
        # compara los dos y, si no coinciden, se queda con el resumen — así que
        # un resumen al que le faltan líneas descarta al detalle que sí las
        # tiene. Ver la migración 125.
        line_amounts = ({} if getattr(scenario, "usar_detalle", False)
                        else await actual_pl_lines_for_month(session, scenario.id, month))
        if line_amounts:
            fino = await _detalle_fino_si_cuadra(session, scenario, month, line_amounts,
                                                 periodo)
            return fino if fino is not None else pl_engine.actual_pl_from_lines(line_amounts)
        acct_rows = await actual_rows_for_month(session, scenario.id, month)
        if acct_rows:
            mappings = await load_active_account_mappings(session, periodo=periodo)
            report_lines = await load_report_line_config(session)
            if mappings and report_lines:
                return pl_engine.calculate_pl_from_mapping(acct_rows, mappings, report_lines)
            return pl_engine.calculate_full_pl(**pl_engine.build_actual_inputs(acct_rows))
    if scenario.type == "ACTUAL":
        # ACTUAL scenario with no imported data yet → empty P&L.
        return pl_engine.calculate_full_pl(
            revenue_by_line={}, payroll_by_dept={}, cos_by_dept={}, opex_by_dept={},
        )

    # Budget / forecast built from the in-app checkbooks. Roll the checkbook
    # detail up to account-level rows and route them through the SAME validated
    # DB-driven mapping engine the actuals use (revenue is injected as seeds, as
    # it is line-level from rate cards with no 4xxx detail to roll up). This is
    # what makes "edit checkbook → account total → P&L" work. Falls back to the
    # legacy dept-grouping engine if the account mapping is not configured.
    if revenue_results is None:
        revenue_results = await load_revenue_results(session, scenario)

    # La renta es ANUAL: no se puede resolver mirando un mes solo. `_pl_del_ano`
    # arma los doce de una vez y les reparte el impuesto del ejercicio.
    anual = await _pl_del_ano(session, scenario, revenue_results, periodo)
    if anual is not None:
        return [replace(ln) for ln in anual[month - 1]]
    # Estamos DENTRO de esa pasada: este mes lo produce el presupuesto (no lo
    # desvió el forecast rodante), así que le toca su propia renta. Se anota para
    # `_pl_del_ano` sepa a cuáles ponerles la renta y a cuáles no.
    _meses_propios_en_curso(session, scenario).append(month)

    rev = revenue_line_dict(revenue_results[month])
    mappings = await load_active_account_mappings(session, periodo=periodo)
    report_lines = await load_report_line_config(session)
    if mappings and report_lines:
        acct_rows = await checkbook_account_rows_for_month(session, scenario.id, month)
        nonop_seeds = await nonop_line_seeds_for_month(session, scenario.id, month)
        return pl_engine.calculate_budget_pl_from_mapping(
            acct_rows, mappings, report_lines,
            revenue_by_line=rev, manual=await manual_for(session, scenario.id, month),
            extra_seeds=nonop_seeds, income_tax=ZERO,
        )

    return pl_engine.calculate_full_pl(
        revenue_by_line=rev,
        payroll_by_dept=await payroll_by_dept(session, scenario.id, month),
        cos_by_dept=await cos_by_dept(session, scenario.id, month),
        opex_by_dept=await opex_by_dept(session, scenario.id, month),
        alloc_by_dept=await alloc_by_dept(session, scenario.id, month),
        manual=await manual_for(session, scenario.id, month),
        income_tax=ZERO,
    )


_CLAVE_ANUAL = "pl_del_ano"


def _meses_propios_en_curso(session, scenario: Scenario) -> list[int]:
    """Los meses que el presupuesto está produciendo en la pasada de `_pl_del_ano`.

    Un forecast rodante NO produce sus meses cerrados: `_compute_pl_month_core`
    los desvía al ACTUAL enlazado, que trae la renta CONTABILIZADA. A esos meses
    no se les puede pisar el impuesto con una provisión estimada. La lista se
    llena desde el propio camino de presupuesto, así que no hay que replicar en
    ningún lado la condición de desvío: el que la evalúa es quien la anota.
    """
    cache = _cache_de_configuracion(session)
    return cache.setdefault((_CLAVE_ANUAL, "propios", scenario.id), [])


def _poner_renta(lineas: list[pl_engine.PLLineResult], renta: Decimal) -> None:
    """Escribe el impuesto del mes —con su signo— y recalcula el neto.

    Se puede hacer al final, y no adentro del motor, porque `INCOME_TAXES` y
    `NET_PROFIT` son las DOS ÚLTIMAS líneas del reporte y **nada aguas abajo
    depende de ellas** (verificado contra `report_line_config`: ninguna otra
    fórmula las menciona). Eso es lo que permite armar los doce meses UNA sola
    vez —el mismo costo de consultas que antes— en vez de armarlos dos veces,
    una para leer el EBT y otra para aplicar el impuesto. El P&L es la pantalla
    que ya tumbó el pool de conexiones una vez; duplicarle el costo no es gratis.
    """
    ebt = pl_engine.get_line(lineas, "EBT")
    for ln in lineas:
        if ln.line_code == "INCOME_TAXES":
            ln.amount_usd = renta
        elif ln.line_code == "NET_PROFIT":
            ln.amount_usd = ebt - renta


async def _pl_del_ano(session, scenario: Scenario,
                      revenue_results: dict[int, RevenueResult] | None,
                      periodo: str | None = None):
    """Los doce meses del P&L de un presupuesto, con la renta ya calculada.

    **El criterio, en palabras del owner.** «El impuesto de renta *se calcula
    mes a mes no importa si es negativo o positivo*. Y *se consolida
    anualmente*» — «algunos meses puede ser negativo, otros positivos, pero *en
    forma anual debe ser positivo*.» El detalle está en
    `pl_engine.renta_por_mes`.

    **El error que corrige.** El P&L calculaba `MAX(0, EBT_mes × 30%)`, con el
    piso de cero DENTRO de cada mes. Las pérdidas de un mes dejaban de compensar
    las ganancias de otro y el impuesto del año salía inflado justo en el 30% de
    esas pérdidas: medido contra producción el 2026-08-16, el Budget Final 2027
    provisionaba $128.861 de más (35,7% efectivo) y el Working 2027 $171.053 de
    más (39,2%), contra un estatutario del 30%. Y de paso, un mes en pérdida
    aparecía sin efecto fiscal cuando en realidad genera un crédito. En
    Corcovado pega todos los años porque el lodge cierra en octubre.

    **Por qué hace falta ver el año entero.** El piso de cero sigue existiendo,
    solo que es ANUAL: si el ejercicio completo da pérdida no hay impuesto en
    ningún mes. Eso no se puede decidir mirando un mes solo, y el P&L se computa
    un mes a la vez — así que la vuelta se da acá: se arman los doce (con la
    renta en cero, que no cambia el EBT), se resuelve con
    `pl_engine.renta_por_mes` y se escribe en cada mes.

    Se guarda en la caché de la sesión —la misma que evita releer el mapeo 25
    veces por pantalla—, así que los doce meses se arman UNA vez por escenario y
    por petición. El costo en consultas es el de antes, no el doble.

    Devuelve `None` mientras la pasada está en curso: eso es lo que corta la
    recursión y lo que hace que cada mes se compute con la renta en cero.

    ⚠️ **Forecast rodante.** Los meses cerrados salen del ACTUAL enlazado con la
    renta contabilizada y no se tocan (`_meses_propios_en_curso`). Su EBT sí
    entra en la base anual: el ejercicio se liquida completo, no por tramos.
    """
    cache = _cache_de_configuracion(session)
    # El período entra en la llave: pedir el año con el mapeo de junio y con el
    # de hoy son dos resultados distintos, y compartirles el caché serviría el
    # que se haya calculado primero.
    clave = (_CLAVE_ANUAL, scenario.id, periodo)
    if clave in cache:
        return cache[clave]              # None = la pasada está en curso

    cache[clave] = None                  # centinela para los doce de abajo
    propios = _meses_propios_en_curso(session, scenario)
    try:
        meses = [await _compute_pl_month_core(session, scenario, m, revenue_results,
                                              periodo)
                 for m in range(1, 13)]
        ebts = [pl_engine.get_line(x, "EBT") for x in meses]
        # La tasa es un parámetro FISCAL del ejercicio, no del mes: se toma la
        # de enero. Aunque alguien cargue tasas distintas por mes, la que se
        # liquida sigue siendo una sola.
        tasa = pl_engine._d((await manual_for(session, scenario.id, 1)).income_tax_rate)
        renta = pl_engine.renta_por_mes(ebts, tasa)
        for m in propios:
            _poner_renta(meses[m - 1], renta[m - 1])
    except Exception:
        cache.pop(clave, None)           # que un fallo no deje el centinela pegado
        raise
    finally:
        cache.pop((_CLAVE_ANUAL, "propios", scenario.id), None)
    cache[clave] = meses
    return meses


async def _derivar_monedas(session, scenario: Scenario,
                           cerrados: set[int] | None = None,
                           avisos: list[str] | None = None) -> int:
    """Pasa a dólares las líneas del checkbook marcadas en COLONES.

    El dato maestro de esas líneas son los colones; los dólares de cada mes se
    derivan con el TC DE ESE MES. Corre ANTES del P&L, así que todo lo que lee el
    checkbook sigue viendo dólares y no tiene que saber de monedas.

    Es lo que hace que un cambio de tipo de cambio se absorba: mueva el TC de un
    mes, recalcule, y ese mes se re-expresa solo.

    ⚠️ **Los meses CERRADOS no se re-expresan.** Esta función es el camino por el
    que un cambio de tipo de cambio en UN mes reescribía los DOCE: el TC vive en
    una tabla aparte y basta tocarlo para que julio ya cerrado cambie de monto.
    Cuando un mes cerrado quedaría distinto se avisa con el monto — congelarlo en
    silencio sería el mismo defecto con otro signo.
    """
    cerrados = cerrados or set()
    avisos = avisos if avisos is not None else []
    rates = (await session.execute(
        select(ExchangeRate).where(ExchangeRate.scenario_id == scenario.id)
    )).scalars().all()
    if not rates:
        return 0
    tocadas = 0
    congelados: dict[int, Decimal] = {}
    for Model in (OpexEntry, CostEntry):
        filas = (await session.execute(
            select(Model).where(Model.scenario_id == scenario.id)
        )).scalars().all()
        for e in filas:
            if not getattr(e, "en_colones", False):
                continue
            for month in range(1, 13):
                nuevo = e.derivar_usd(month, get_tc_for_month(rates, month))
                if month in cerrados:
                    diff = nuevo - (e.get_month(month) or ZERO)
                    if diff:
                        congelados[month] = congelados.get(month, ZERO) + diff
                    continue
                e.set_month(month, nuevo)
            tocadas += 1
    for month in sorted(congelados):
        avisos.append(
            f"Mes {month} está cerrado: el checkbook en colones NO se re-expresó. "
            f"Con el tipo de cambio de hoy habría quedado ${congelados[month]:,.2f} "
            f"distinto.")
    return tocadas


# ─── Orchestration steps ──────────────────────────────────────────────────────
async def _recalc_payroll(session, scenario: Scenario,
                          avisos: list[str] | None = None,
                          cerrados: set[int] | None = None) -> int:
    """Refresca los conceptos automáticos de la planilla, posición por mes.

    ⚠️ **Los meses CERRADOS no se reescriben, pero SÍ pesan en el reparto.**

    Esa segunda mitad es la que no se puede saltear. `repartir_beneficio` reparte
    un monto ANUAL entre todas las filas del año por FTE: si las filas de los
    meses cerrados se dejaran fuera de la lista, el mismo monto se repartiría
    entre menos filas y **los meses abiertos subirían solos**. O sea: proteger
    julio movería agosto. Por eso las filas cerradas entran al reparto igual que
    hoy —el denominador no cambia— y después se les devuelve su valor anterior.

    Tampoco se INVENTA planilla en un mes cerrado: una posición creada en agosto
    no nace con filas de julio.
    """
    avisos = avisos if avisos is not None else []
    cerrados = cerrados or set()
    from app.models.payroll_params import (
        PayrollParams, DEFAULT_CCSS_RATE, DEFAULT_AGUINALDO_DIVISOR,
    )
    rates = (await session.execute(
        select(ExchangeRate).where(ExchangeRate.scenario_id == scenario.id)
    )).scalars().all()
    if not rates:
        # Sin tipo de cambio no se puede pasar el salario de colones a dólares.
        # Antes salía en silencio: el botón de recalcular devolvía 0 y el usuario
        # creía que la planilla se había actualizado. Ahora se avisa.
        n_pos = (await session.execute(
            select(func.count()).select_from(PayrollPosition)
            .where(PayrollPosition.scenario_id == scenario.id)
        )).scalar_one()
        if n_pos:
            avisos.append(
                f"La planilla NO se recalculó: este escenario no tiene tipo de cambio "
                f"y tiene {n_pos} posiciones. Cárguelo en Tipo de Cambio y vuelva a recalcular.")
        return 0
    # Parámetros de planilla del escenario (o defaults históricos si no hay fila).
    pp = (await session.execute(
        select(PayrollParams).where(PayrollParams.scenario_id == scenario.id)
    )).scalar_one_or_none()
    ccss = pp.ccss_rate if pp else DEFAULT_CCSS_RATE
    agu = pp.aguinaldo_divisor if pp else DEFAULT_AGUINALDO_DIVISOR
    positions = (await session.execute(
        select(PayrollPosition).where(PayrollPosition.scenario_id == scenario.id)
    )).scalars().all()
    updated = 0
    protegidas = 0
    para_ins: list[tuple[PayrollConceptEntry, PayrollPosition]] = []
    # Foto de las filas de meses cerrados, para devolverlas tal cual después del
    # reparto. Se guardan los 17 conceptos: son los únicos que tocan
    # `recalculate_entry` y `repartir_beneficio`.
    congeladas: list[tuple[PayrollConceptEntry, dict]] = []
    for pos in positions:
        sin_salario = not (pos.salary_amount or ZERO)
        for month in range(1, 13):
            tc = get_tc_for_month(rates, month)
            entry = (await session.execute(
                select(PayrollConceptEntry).where(
                    PayrollConceptEntry.scenario_id == scenario.id,
                    PayrollConceptEntry.position_id == pos.id,
                    PayrollConceptEntry.month == month,
                )
            )).scalar_one_or_none()
            if month in cerrados:
                if entry is None:
                    continue          # no se inventa planilla en un mes cerrado
                congeladas.append(
                    (entry, {c: getattr(entry, c) for c in PAYROLL_ALL_COLS}))
                para_ins.append((entry, pos))   # pesa en el reparto, como hoy
                continue
            # Una posición sin salario cargado recalcula a cero. Si la fila ya trae
            # números (planilla importada del GL, p.ej.), recalcular la borraría.
            # Se respeta lo que hay y se avisa; el salario en blanco es un dato que
            # falta, no una instrucción de poner la planilla en cero.
            if entry is not None and sin_salario and total_entry(entry):
                protegidas += 1
                # Igual entra al reparto: proteger la fila es no PISAR su planilla
                # importada, no dejarla fuera del reparto de beneficios. Si se
                # excluye, se queda con el monto viejo del reparto anterior y el
                # total repartido se pasa del monto de la póliza.
                para_ins.append((entry, pos))
                continue
            if entry is None:
                entry = PayrollConceptEntry(
                    scenario_id=scenario.id, position_id=pos.id,
                    dept_code=pos.dept_code, month=month, year=scenario.year,
                )
                session.add(entry)
            recalculate_entry(entry, pos, month, tc, ccss, agu, params=pp)
            para_ins.append((entry, pos))
            updated += 1

    # Repartos de beneficios: necesitan TODAS las filas a la vez, así que van
    # después del bucle. Un reparto no es una tasa.
    # Solo se atienden aquí los de nivel POSICION; los de nivel DEPTO los arma
    # `_recalc_allocations` como AllocationEntry.
    if para_ins:
        tc_mes = {m: get_tc_for_month(rates, m) for m in range(1, 13)}
        cfgs = (await session.execute(
            select(BenefitAllocationConfig).where(
                BenefitAllocationConfig.scenario_id == scenario.id)
        )).scalars().all()
        for cfg in cfgs:
            if not cfg.active or cfg.level != "POSITION" or not cfg.columna:
                continue
            monto = cfg.amount_crc or ZERO
            en_usd = False
            if cfg.source_type == "DEPTO" and cfg.source_dept:
                # El costo de un departamento YA está en dólares: se reparte tal
                # cual. Antes se pasaba a colones con el TC de enero y se volvía a
                # convertir mes a mes — con un TC que varía en el año eso daba
                # cifras equivocadas.
                monto = ZERO
                for m in range(1, 13):
                    monto += await _dept_total_cost(session, scenario.id, cfg.source_dept, m)
                en_usd = True
            repartido = repartir_beneficio(
                para_ins, cfg.columna, monto, tc_mes, base=cfg.basis, en_usd=en_usd)
            if repartido:
                avisos.append(
                    f"{cfg.label or cfg.account} repartido por {cfg.basis} entre "
                    f"{len(para_ins)} filas de planilla: ${repartido:,.2f}.")
    # Devolver los meses cerrados a como estaban. Va DESPUÉS del reparto a
    # propósito: durante el reparto tenían que estar, para que el denominador
    # fuera el del año entero.
    movidas = 0
    for entry, foto in congeladas:
        for col, valor in foto.items():
            if getattr(entry, col) != valor:
                movidas += 1
            setattr(entry, col, valor)
    if congeladas:
        meses = ", ".join(str(m) for m in sorted(cerrados))
        avisos.append(
            f"Planilla: los meses cerrados ({meses}) se dejaron como estaban "
            f"—{len(congeladas)} filas—." +
            (f" El recálculo habría cambiado {movidas} conceptos." if movidas else ""))

    if protegidas:
        avisos.append(
            f"{protegidas} filas de planilla se dejaron como estaban: traen números "
            f"pero su posición no tiene salario cargado. Cargue los salarios para que "
            f"las fórmulas las manejen.")
    return updated


async def _dept_total_cost(session, scenario_id: str, dept_code: str, month: int) -> Decimal:
    total = ZERO
    for d in (await opex_by_dept(session, scenario_id, month)).items():
        if d[0] == dept_code:
            total += d[1]
    for d in (await cos_by_dept(session, scenario_id, month)).items():
        if d[0] == dept_code:
            total += d[1]
    for d in (await payroll_by_dept(session, scenario_id, month)).items():
        if d[0] == dept_code:
            total += d[1]
    return total


async def rooms_family(session, source: str = "0110") -> tuple[set[str], set[str]]:
    """(familia, sets) de Rooms según el catálogo.

    `familia` = Rooms y sus hijos de FUNCIÓN (Front Desk, Reservation,
    Housekeeping, Concierge): los departamentos donde el GL deja el costo de
    habitaciones. `sets` = los hijos marcados como set de categorías (Villas,
    Residencias), que son los DESTINOS del reparto.

    La distinción no se puede deducir de «tener padre 0110» — los cuatro de
    función también lo tienen. Por eso existe la bandera `room_set` (mig 086).

    Un set queda FUERA de la familia a propósito: si entrara, la base incluiría
    lo que ya se le movió y en el siguiente recálculo se repartiría otra vez
    sobre sí mismo.
    """
    filas = (await session.execute(select(DepartmentCatalog))).scalars().all()
    padre = {d.dept_code: (d.parent_dept_code or "").strip() for d in filas}
    es_set = {d.dept_code for d in filas if getattr(d, "room_set", False)}

    def cuelga_de(dept: str) -> bool:
        visto, actual = {dept}, dept
        while True:
            p = padre.get(actual, "")
            if not p or p in visto:
                return False
            if p == source:
                return True
            visto.add(p)
            actual = p

    sets = {d for d in es_set if d != source and cuelga_de(d)}
    familia = {source} | {
        d.dept_code for d in filas
        if d.dept_code not in sets and d.dept_code != source and cuelga_de(d.dept_code)
    }
    return familia, sets


def _rooms_base_por_cuenta(
    opex, costs, payroll, repartos_del_mes, familia: set[str], month: int,
) -> dict[str, Decimal]:
    """Lo que LLEGÓ a la familia Rooms este mes, abierto por cuenta.

    Suma el GL (opex + costos + los 17 conceptos de planilla) MÁS los repartos
    que ya cayeron en la familia en esta misma corrida — cafetería, lavandería y
    salarios. Eso es lo que hace que el reparto a las villas se lleve su parte de
    todo sin encadenar nada: para cuando corre, Rooms ya recibió lo demás.

    Los créditos entran con su signo. Si una regla de salario acredita a Rooms
    —una posición de habitaciones que apoya a otra área— la base baja, que es lo
    correcto: ese costo ya se fue para otro lado.
    """
    base: dict[str, Decimal] = {}

    def sumar(cuenta: str, monto: Decimal) -> None:
        if monto:
            base[cuenta] = base.get(cuenta, ZERO) + monto

    for e in opex:
        if e.dept_code in familia:
            sumar(e.account_code, e.get_month(month) or ZERO)
    for e in costs:
        if e.dept_code in familia:
            sumar(e.account_code, e.get_month(month) or ZERO)
    for e in payroll:
        if e.dept_code not in familia or e.month != month:
            continue
        for col in PAYROLL_ALL_COLS:
            sumar(pl_engine.payroll_account_for_column(col), getattr(e, col) or ZERO)
    for e in repartos_del_mes:
        if e.target_dept in familia:
            sumar(e.account, e.amount_usd or ZERO)

    return {c: m for c, m in base.items() if m}


async def _recalc_allocations(session, scenario: Scenario,
                              avisos: list[str] | None = None,
                              cerrados: set[int] | None = None) -> int:
    """Regenera los asientos de reparto (cafetería, lavandería, salarios, Rooms).

    ⚠️ **El `DELETE` se filtra por mes, no solo la escritura.** Esta función
    borra TODO el reparto del escenario y lo refabrica. Filtrar solo la
    escritura dejaría el resultado PEOR que sin proteger: los meses cerrados se
    perderían y nada los repondría. El borrado y la escritura tienen que decir lo
    mismo, y por eso salen del mismo conjunto.

    Un mes cerrado se protege **solo si ya tiene asientos**. Si no tiene ninguno
    no hay nada que congelar, y saltearlo dejaría un agujero permanente en un
    escenario que nunca se recalculó.

    ⚠️ **En un histórico no se reparte nada: el reparto YA VIENE HECHO en el
    mayor.** El guard vive acá y no en el endpoint a propósito. `recalculate_
    scenario` ya no llega —corta antes, en `lo_subido_manda`— pero la pantalla
    de repartos llama a esta función DIRECTO (`allocation_api.calculate_
    allocations`), y ese camino no tenía filtro por origen: apretar el botón
    sobre el `ACTUAL 2025` le fabricaba cafetería y lavandería encima de un
    mayor que ya las traía repartidas, y sin la exclusión de Cafetería (0220)
    que sí aplica el P&L de importados (`pl_engine.ACTUAL_EXCLUDED_DEPTS`). Dos
    caminos a la misma tabla que protegen distinto son un camino sin protección.
    """
    avisos = avisos if avisos is not None else []
    cerrados = cerrados or set()
    sid = scenario.id

    if scenario.type == "ACTUAL" or await lo_subido_manda(session, scenario):
        # No se borra ni se escribe: se cuenta lo que hay y se avisa. Borrar
        # sería peor que calcular de más — se perdería el reparto que vino en el
        # archivo, y nada lo repondría.
        actuales = (await session.execute(
            select(func.count()).select_from(AllocationEntry)
            .where(AllocationEntry.scenario_id == sid)
        )).scalar_one()
        avisos.append(
            "Repartos: este escenario toma sus números de lo que se subió, así "
            "que el reparto ya viene hecho en el mayor. No se recalculó nada"
            + (f" — se dejaron los {actuales} asientos que ya tenía." if actuales
               else "."))
        return actuales

    # Meses cerrados que YA tienen reparto: esos son los que se respetan.
    con_reparto = {m for (m,) in (await session.execute(
        select(AllocationEntry.month)
        .where(AllocationEntry.scenario_id == sid).distinct()
    )).all()}
    protegidos = cerrados & con_reparto

    borrado = delete(AllocationEntry).where(AllocationEntry.scenario_id == sid)
    if protegidos:
        borrado = borrado.where(AllocationEntry.month.notin_(sorted(protegidos)))
    await session.execute(borrado)
    conservados = (await session.execute(
        select(func.count()).select_from(AllocationEntry)
        .where(AllocationEntry.scenario_id == sid)
    )).scalar_one() if protegidos else 0
    if protegidos:
        avisos.append(
            f"Repartos: los meses cerrados ({', '.join(str(m) for m in sorted(protegidos))}) "
            f"se dejaron como estaban — {conservados} asientos.")

    caf_cfg = {c.dept_code: c for c in (await session.execute(
        select(CafeteriaAllocationConfig).where(CafeteriaAllocationConfig.scenario_id == sid)
    )).scalars()}
    lau_cfg = {c.dept_code: c for c in (await session.execute(
        select(LaundryAllocationConfig).where(LaundryAllocationConfig.scenario_id == sid)
    )).scalars()}

    participating_caf = {dc for dc, c in caf_cfg.items() if c.participates}
    participating_lau_cfgs = {dc: c for dc, c in lau_cfg.items() if c.participates}
    participating_lau_depts = set(participating_lau_cfgs.keys())

    lau_params = (await session.execute(
        select(LaundryParams).where(LaundryParams.scenario_id == sid)
    )).scalar_one_or_none()
    acct_linen = lau_params.account_linen if lau_params else "7310"
    acct_uniform = lau_params.account_uniform if lau_params else "7685"
    acct_servicios = lau_params.account_servicios if lau_params else "5301"

    positions = (await session.execute(
        select(PayrollPosition).where(PayrollPosition.scenario_id == sid)
    )).scalars().all()

    # Salary allocation: reglas (fuente position → destinos) + TC para el SW.
    sal_cfgs = [c for c in (await session.execute(
        select(SalaryAllocationConfig).where(SalaryAllocationConfig.scenario_id == sid)
    )).scalars() if c.active]
    rates = (await session.execute(
        select(ExchangeRate).where(ExchangeRate.scenario_id == sid)
    )).scalars().all() if sal_cfgs else []
    # CCSS / aguinaldo del escenario para el costo cargado de la reasignación
    from app.models.payroll_params import PayrollParams
    pp = (await session.execute(select(PayrollParams).where(
        PayrollParams.scenario_id == sid))).scalar_one_or_none() if sal_cfgs else None
    ccss_rate = pp.ccss_rate if pp else CCSS_RATE
    agu_div = pp.aguinaldo_divisor if pp else AGUINALDO_DIVISOR

    # Reparto de Rooms a sus sets (Villas / Residencias). Va al FINAL de la
    # cadena, así que necesita los datos del GL crudos para armar la base.
    rooms_cfgs = [c for c in (await session.execute(
        select(RoomsAllocationConfig).where(RoomsAllocationConfig.scenario_id == sid)
    )).scalars() if c.active]
    rooms_familia: set[str] = set()
    opex_all: list = []
    costs_all: list = []
    payroll_all: list = []
    if rooms_cfgs:
        rooms_familia, _sets = await rooms_family(session, "0110")
        opex_all = (await session.execute(
            select(OpexEntry).where(OpexEntry.scenario_id == sid))).scalars().all()
        costs_all = (await session.execute(
            select(CostEntry).where(CostEntry.scenario_id == sid))).scalars().all()
        payroll_all = (await session.execute(
            select(PayrollConceptEntry).where(
                PayrollConceptEntry.scenario_id == sid))).scalars().all()

    new_entries: list[AllocationEntry] = []
    avisos_rooms: list[str] = []
    for month in range(1, 13):
        if month in protegidos:
            continue               # mes cerrado: su reparto no se refabrica
        desde = len(new_entries)   # dónde arrancan las filas de ESTE mes
        fte_attr = f"fte_{MONTH_ATTRS[month - 1]}"
        # cafetería distributed by FTE
        fte_by_dept: dict[str, Decimal] = {}
        for p in positions:
            if p.dept_code not in participating_caf:
                continue
            fte_by_dept[p.dept_code] = fte_by_dept.get(p.dept_code, ZERO) + (
                getattr(p, fte_attr) or ZERO)
        caf_cost = await _dept_total_cost(session, sid, "0220", month)
        for row in calculate_cafeteria_distribution(caf_cost, fte_by_dept):
            new_entries.append(AllocationEntry(
                scenario_id=sid, allocation_type="CAFETERIA", month=month,
                year=scenario.year, source_dept="0220", target_dept=row["target_dept"],
                amount_usd=row["amount_usd"], basis_value=row["basis_value"],
                basis_type=row["basis_type"], account=row["account"],
                calculated_at=datetime.utcnow(),
            ))

        # lavandería 3 vías (linen 7310 por kilos / uniformes 7685 por FTE /
        # huéspedes 5301 COGS va al 0162)
        uni_fte: dict[str, Decimal] = {}
        for p in positions:
            if p.dept_code not in participating_lau_depts:
                continue
            uni_fte[p.dept_code] = uni_fte.get(p.dept_code, ZERO) + (
                getattr(p, fte_attr) or ZERO)
        lau_cost = await _dept_total_cost(session, sid, "0161", month)
        linen_kilos = {dc: c.kilos_for(month) for dc, c in participating_lau_cfgs.items()}
        kilos_uni = lau_params.uniformes_for(month) if lau_params else ZERO
        kilos_gst = lau_params.huespedes_for(month) if lau_params else ZERO
        lau = calculate_laundry_distribution(
            lau_cost, linen_kilos, uni_fte, kilos_uni, kilos_gst,
            acct_linen=acct_linen, acct_uniform=acct_uniform, acct_servicios=acct_servicios,
        )
        for row in lau["rows"]:
            new_entries.append(AllocationEntry(
                scenario_id=sid, allocation_type="LAUNDRY", month=month,
                year=scenario.year, source_dept="0161", target_dept=row["target_dept"],
                amount_usd=row["amount_usd"], basis_value=row["basis_value"],
                basis_type=row["basis_type"], account=row["account"],
                calculated_at=datetime.utcnow(),
            ))

        # SALARY allocation: por regla (salario de la posición fuente × % → destinos por FTE)
        if sal_cfgs:
            tc = get_tc_for_month(rates, month)
            for cfg in sal_cfgs:
                ov = getattr(cfg, "salary_override", None) or []
                if month - 1 < len(ov) and ov[month - 1]:
                    sw = Decimal(str(ov[month - 1]))          # salario manual (planilla en 0)
                else:
                    sw = sum(
                        (calc_sw(p, month, tc) for p in positions
                         if p.dept_code == cfg.source_dept and p.position_code == cfg.position_code),
                        ZERO,
                    )
                # costo CARGADO: SW + CCSS + aguinaldo + cafetería (% del salario) + dummy
                loaded = loaded_salary_breakdown(
                    sw, ccss_rate, agu_div, getattr(cfg, "cafeteria_pct", ZERO))["total"]
                dm = getattr(cfg, "dummy_monthly", None) or []
                if month - 1 < len(dm) and dm[month - 1]:
                    loaded += Decimal(str(dm[month - 1]))
                targets = [t for t in (cfg.target_depts or []) if t]
                tgt_fte: dict[str, Decimal] = {}
                for p in positions:
                    if p.dept_code in targets:
                        tgt_fte[p.dept_code] = tgt_fte.get(p.dept_code, ZERO) + (getattr(p, fte_attr) or ZERO)
                for row in calculate_salary_distribution(
                    loaded, cfg.portion_pct, tgt_fte, cfg.source_dept, cfg.account or "6000",
                ):
                    new_entries.append(AllocationEntry(
                        scenario_id=sid, allocation_type="SALARY", month=month,
                        year=scenario.year, source_dept=cfg.source_dept, target_dept=row["target_dept"],
                        amount_usd=row["amount_usd"], basis_value=row["basis_value"],
                        basis_type=row["basis_type"], account=row["account"],
                        calculated_at=datetime.utcnow(),
                    ))

        # ── ROOMS → sets (Villas / Residencias). ÚLTIMO de la cadena ─────────
        # Corre después de cafetería, lavandería y salarios a propósito: así la
        # base «lo que llegó a Rooms» ya incluye esos repartos y las villas se
        # llevan su proporción de todo. Si corriera antes habría que encadenar
        # el FTE para que la cafetería les diera su parte.
        if rooms_cfgs:
            base = _rooms_base_por_cuenta(
                opex_all, costs_all, payroll_all, new_entries[desde:],
                rooms_familia, month)
            fte_rooms = sum(
                (getattr(p, fte_attr) or ZERO
                 for p in positions if p.dept_code in rooms_familia), ZERO)
            pct = {c.dept_code: c.pct_for(month) for c in rooms_cfgs}
            filas, fte_set, avisos = calculate_rooms_by_pct(
                base, pct, source_dept="0110", fte=fte_rooms)
            for a in avisos:
                avisos_rooms.append(f"Mes {month}: {a}")
            for row in filas:
                new_entries.append(AllocationEntry(
                    scenario_id=sid, allocation_type="ROOMS", month=month,
                    year=scenario.year, source_dept="0110",
                    target_dept=row["target_dept"],
                    amount_usd=row["amount_usd"],
                    # La base que se guarda es el FTE que le toca al set: no
                    # manda en el cálculo, pero es lo que deja leer costo por
                    # FTE en el reporte por set.
                    basis_value=fte_set.get(row["target_dept"], ZERO),
                    basis_type=row["basis_type"], account=row["account"],
                    calculated_at=datetime.utcnow(),
                ))

    # Los avisos del reparto de Rooms suben al recálculo. Un porcentaje que
    # suma más de 100% NO arma el asiento: sin este aviso el owner vería el
    # costo intacto en Rooms y no tendría cómo saber por qué.
    avisos.extend(avisos_rooms)

    new_entries = _consolidar_repartos(new_entries)
    session.add_all(new_entries)
    # Se cuentan los asientos VIGENTES —nuevos + conservados—, no los escritos.
    # Quien lee este número quiere saber cuánto reparto tiene el escenario; si
    # solo contara los nuevos, proteger meses parecería haber perdido asientos.
    return len(new_entries) + conservados


def _consolidar_repartos(entries: list[AllocationEntry]) -> list[AllocationEntry]:
    """Junta las filas de reparto que caen en la misma llave única.

    Desde que Salary Allocation es 1 regla = 1 destino, varias reglas apuntan al
    mismo departamento en el mismo mes con la misma cuenta: el guía y el capitán
    apoyan los dos a Transportation, y Property Support le suma un tercer pedazo.
    Cada regla emitía su fila y la unique las rechazaba, así que reventaba TODO
    el recálculo — y como la transacción se revierte entera, quedaban los
    repartos viejos en pie sin ningún aviso. Eso es lo que pasó con el dato de
    prueba de $51,886: el owner apretaba Aplicar y no cambiaba nada.

    Se suman los montos. La base NO se suma: es el FTE del departamento destino,
    el mismo para todas las filas que comparten llave, así que se toma la mayor.
    Si el cargo viene de varias fuentes el origen queda como VARIOS: el P&L rutea
    por el destino, el origen es informativo.
    """
    juntas: dict[tuple, AllocationEntry] = {}
    for e in entries:
        clave = (e.allocation_type, e.month, e.target_dept, e.account, e.basis_type)
        previa = juntas.get(clave)
        if previa is None:
            juntas[clave] = e
            continue
        previa.amount_usd = (previa.amount_usd or ZERO) + (e.amount_usd or ZERO)
        if (e.basis_value or ZERO) > (previa.basis_value or ZERO):
            previa.basis_value = e.basis_value
        if previa.source_dept != e.source_dept:
            previa.source_dept = "VARIOS"
    return list(juntas.values())


async def _persist_pl(session, scenario: Scenario,
                      revenue_results: dict[int, RevenueResult] | None,
                      cerrados: set[int] | None = None) -> int:
    """Persiste el P&L del año en `pl_lines`.

    ⚠️ **El `DELETE` se filtra igual que la escritura**, por el mismo motivo que
    en los repartos: borrar todo y reescribir solo una parte pierde los meses
    cerrados sin reponerlos.

    Se protege solo lo que este escenario PRODUCE (`meses_propios`). Los meses
    que un forecast rodante ESPEJA del ACTUAL enlazado se vuelven a escribir
    siempre: ahí la única fuente es lo subido —*«en un histórico manda lo
    subido»*— y congelar el espejo solo lo dejaría viejo.
    """
    sid = scenario.id
    propios = set(await meses_propios(session, scenario))
    protegidos = (cerrados or set()) & propios
    # Un mes cerrado sin líneas guardadas no tiene nada que proteger: si se
    # salteara, quedaría vacío para siempre.
    if protegidos:
        con_lineas = {m for (m,) in (await session.execute(
            select(PLLine.month).where(PLLine.scenario_id == sid).distinct()
        )).all()}
        protegidos &= con_lineas

    borrado = delete(PLLine).where(PLLine.scenario_id == sid)
    if protegidos:
        borrado = borrado.where(PLLine.month.notin_(sorted(protegidos)))
    await session.execute(borrado)
    count = 0
    for month in range(1, 13):
        if month in protegidos:
            continue
        lines = await compute_pl_month(session, scenario, month, revenue_results)
        for ln in lines:
            session.add(PLLine(
                scenario_id=sid, month=month, year=scenario.year,
                line_code=ln.line_code, line_name=ln.line_name, section=ln.section,
                dept_code=ln.dept_code or "", amount_usd=ln.amount_usd,
                is_calculated=ln.is_calculated,
            ))
            count += 1
    return count


# ─── Master entry point ───────────────────────────────────────────────────────
#: Las columnas de mes del checkbook de ingresos, enero primero.
_MESES_REV = ["jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"]


async def sincronizar_ingreso_al_checkbook(
    session, scenario, revenue_results, cerrados: set[int] | None = None,
) -> int:
    """Baja el ingreso DERIVADO al sub-mayor, en el mismo recálculo que lo calcula.

    ## El desfase que esto cierra

    Owner, 2026-08-17: *«si todo estaba trabajando bien… no entiendo por qué se
    desincroniza. Esto no puede volver a pasar.»* Y tenía razón en las dos
    partes: el dato estaba, y se había separado solo.

    Cómo pasó, sin que nada fallara: hasta el 15-ago los presupuestos leían el
    ingreso del checkbook (`revenue_source = 'checkbook'`), así que **el
    checkbook ERA la fuente** y el botón «pasar al checkbook» era el único
    camino. Con el mixer de canales (migraciones 116-117) los seis presupuestos
    2027 pasaron a `drivers`: desde entonces el P&L calcula el ingreso con
    tarifas × ocupación × canales, y **nadie vuelve a escribir el checkbook**.
    Quedó una copia congelada en la última vez que alguien apretó el botón.

    Medido en el `BUDGET Working 2027`: el checkbook decía **$6.449.238** y el
    modelo vivo **$6.374.026** — $75.212 de diferencia, y **$118.218 solo en
    Rooms**. Nada lo señalaba: el P&L estaba bien, el checkbook estaba bien
    guardado, y los dos decían cosas distintas.

    ⚠️ **Por eso el arreglo va en el recálculo y no en un botón.** Un botón es
    justo lo que falló: depende de que alguien se acuerde. Acá, cada vez que el
    escenario se recalcula, el sub-mayor queda igual al modelo — que es la regla
    del owner: *todo debe viajar al GL, esa es la fuente primaria*.

    ## ⚠️ La guarda que no se puede quitar

    **En modo `checkbook` esto NO escribe nada.** Ahí las filas son montos
    TIPEADOS por el usuario y son la fuente del P&L: sobrescribirlas con el
    ingreso derivado le borraría el presupuesto a alguien, y encima el P&L
    seguiría cuadrando —contra el número equivocado— así que no habría forma de
    notarlo. La condición es el `revenue_source`, no el tipo ni el año.

    Los meses cerrados tampoco se tocan, por la misma razón que el resto del
    recálculo los respeta.

    Devuelve cuántas líneas se escribieron (0 si no había nada que mover).
    """
    from app.models.revenue_entry import REVENUE_LINES, RevenueEntry

    # ⚠️ La guarda. Ver el docstring: en `checkbook` el usuario es la fuente.
    if getattr(scenario, "revenue_source", "drivers") == "checkbook":
        return 0

    derivado: dict[str, list[Decimal]] = {}
    for mes, resultado in (revenue_results or {}).items():
        if not 1 <= int(mes) <= 12:
            continue
        for attr, monto in revenue_line_dict(resultado).items():
            linea = attr.upper()
            if linea not in REVENUE_LINES:
                continue
            derivado.setdefault(linea, [Decimal("0")] * 12)
            derivado[linea][int(mes) - 1] = Decimal(str(monto or 0))
    if not derivado:
        return 0

    filas = {e.line: e for e in (await session.execute(
        select(RevenueEntry).where(
            RevenueEntry.scenario_id == scenario.id,
            RevenueEntry.line.in_(list(derivado)),
        ))).scalars().all()}

    escritas = 0
    for linea, valores in derivado.items():
        fila = filas.get(linea)
        if fila is None:
            fila = RevenueEntry(id=str(uuid.uuid4()), scenario_id=scenario.id,
                                hotel_id=scenario.hotel_id, line=linea)
            session.add(fila)
        cambio = False
        for i, col in enumerate(_MESES_REV):
            if cerrados and (i + 1) in cerrados:
                continue
            nuevo = valores[i]
            if Decimal(str(getattr(fila, col) or 0)) != nuevo:
                setattr(fila, col, nuevo)
                cambio = True
        if cambio:
            escritas += 1
    await session.flush()
    return escritas


async def sincronizar_noches(session, scenario, revenue_results,
                             cerrados: set[int] | None = None) -> int:
    """Baja las NOCHES al mismo tiempo que la plata.

    ## El desfase, medido

    `scenario_stats` solo se escribía cuando alguien apretaba el push al
    checkbook, y el P&L y el Break-Even la prefieren sobre el modelo vivo.
    Resultado: **el ingreso fresco y las noches viejas, en la misma pantalla.**

    En los seis presupuestos 2027: `Draft1..Final` decían **4.363,29** noches
    contra **4.981,79** del modelo, y **10.020** disponibles contra **12.045**.
    El `Working 2027`, 4.981,79 contra 5.215,59.

    Lo que se rompe no son las líneas de plata —ésas salen del modelo vivo— sino
    **todo lo que se divide por noches**: ADR, ocupación, TRevPAR y el
    equilibrio en noches. En el `Final 2027` el equilibrio daba **2.099 noches
    contra 2.397 reales**, y para el lado peligroso: **se ve más fácil de
    alcanzar de lo que es**.

    ⚠️ **Va en el recálculo, no en el botón**, por la misma razón que el ingreso:
    un botón depende de que alguien se acuerde, y ya se demostró que nadie se
    acuerda.

    ⚠️ **La guarda es la rama de arriba de `recalculate_scenario`.** Un ACTUAL, o
    cualquier escenario donde «lo subido manda», sale por la otra rama y nunca
    llega acá — sus estadísticas vienen del PMS y sobrescribirlas destruiría el
    dato real. Esta función solo corre para los que se CALCULAN.

    `occupancy_pct` y `adr` se derivan de las noches y del ingreso de
    habitaciones: dejarlos como estaban mostraría un ADR que ya no corresponde.
    """
    from app.models.scenario_stat import ScenarioStat

    if not revenue_results:
        return 0

    stats = {s.month: s for s in (await session.execute(
        select(ScenarioStat).where(ScenarioStat.scenario_id == scenario.id)
    )).scalars().all()}

    escritos = 0
    for mes, r in revenue_results.items():
        if not 1 <= int(mes) <= 12:
            continue
        if cerrados and int(mes) in cerrados:
            continue
        st = stats.get(int(mes))
        if st is None:
            st = ScenarioStat(id=str(uuid.uuid4()), scenario_id=scenario.id,
                              month=int(mes))
            session.add(st)
        disp = int(getattr(r, "rooms_available", 0) or 0)
        ocup = Decimal(str(getattr(r, "rooms_occupied", 0) or 0))
        antes = (st.rooms_available, Decimal(str(st.rooms_occupied or 0)))
        st.rooms_available = disp
        st.rooms_occupied = ocup
        st.guests = Decimal(str(getattr(r, "guests", 0) or 0))
        st.occupancy_pct = (ocup / Decimal(str(disp))) if disp else Decimal("0")
        st.adr = (Decimal(str(getattr(r, "rooms", 0) or 0)) / ocup) if ocup else Decimal("0")
        if antes != (disp, ocup):
            escritos += 1
    await session.flush()
    return escritos


async def recalculate_scenario(session, scenario_id: str) -> dict:
    """Recompute payroll → allocations → P&L for a scenario and persist results."""
    scenario = await session.get(Scenario, scenario_id)
    if scenario is None:
        raise ValueError(f"Scenario {scenario_id} not found")
    scenario.assert_editable()

    # Escenarios cuyo número SE SUBIÓ: no se recalcula planilla, ni repartos, ni
    # monedas, ni ingresos — solo se proyecta a `pl_lines` lo que ya está
    # cargado en el mayor o en el snapshot.
    #
    # ⚠️ **Se pregunta por el ORIGEN, no por el TIPO.** Antes acá decía
    # `scenario.type == "ACTUAL"`, y un BUDGET o un FORECAST *importado* caía en
    # la rama de cálculo completa: le derivaba las monedas del checkbook, le
    # refabricaba la planilla y le inventaba asientos de reparto que el archivo
    # nunca trajo. El P&L no se movía —lo lee del snapshot igual— así que el
    # destrozo era invisible en el reporte y solo aparecía en los auxiliares.
    # Es literal la regla del owner: «los históricos rompen los auxiliares… y se
    # va directo al GL».
    #
    # El `or` no es redundancia: un ACTUAL todavía sin cargar da False en
    # `lo_subido_manda` (no tiene datos), y un ACTUAL no se calcula nunca —
    # aunque esté vacío. Sin el `or` se le fabricaría una planilla.
    #
    # ⚠️ Esta rama NO se filtra por mes cerrado, a propósito. No calcula nada:
    # proyecta a `pl_lines` lo que ya está cargado. Congelarla dejaría el
    # proyectado viejo frente a lo subido, que es justo al revés de la regla del
    # owner — «en un histórico manda lo subido».
    if scenario.type == "ACTUAL" or await lo_subido_manda(session, scenario):
        pl_lines = await _persist_pl(session, scenario, None)
        # Mismo sello que la rama de budget: sin esto, un ACTUAL recién
        # recalculado sigue mostrando el aviso de «el reporte quedó atrás» para
        # siempre, porque el sello nunca alcanza al updated_at de los datos.
        scenario.last_recalc_at = datetime.utcnow()
        await session.commit()
        return {
            "scenario_id": scenario_id,
            "payroll_entries_updated": 0,
            "allocation_entries": 0,
            "pl_lines": pl_lines,
            # Vacío, pero presente: las dos ramas devuelven la misma forma, así
            # que quien consuma esto no tiene que adivinar si la llave existe.
            "avisos": [],
            "status": "recalculated",
        }

    avisos: list[str] = []
    # ⚠️ El conjunto se calcula UNA vez y lo comparten las cuatro etapas. Que
    # cada etapa lo resolviera por su cuenta es exactamente cómo se separan dos
    # reglas que tienen que decir lo mismo: bastaría un cambio en una para que el
    # borrado y la escritura protegieran meses distintos.
    cerrados = await meses_cerrados_de(session, scenario)
    if cerrados:
        avisos.append(
            f"Meses cerrados: {', '.join(str(m) for m in sorted(cerrados))}. El "
            f"recálculo no los toca.")

    # Primero las monedas: si una línea está en colones, su dólar depende del TC
    # del mes y todo lo de abajo lee dólares.
    en_crc = await _derivar_monedas(session, scenario, cerrados, avisos)
    if en_crc:
        avisos.append(f"{en_crc} líneas del checkbook están en colones: se "
                      f"reexpresaron con el tipo de cambio de cada mes.")
    await session.flush()

    payroll_updated = await _recalc_payroll(session, scenario, avisos, cerrados)
    await session.flush()

    alloc_entries = await _recalc_allocations(session, scenario, avisos, cerrados)
    await session.flush()

    revenue_results = await load_revenue_results(session, scenario)
    # El ingreso derivado baja al sub-mayor en el MISMO recálculo que lo calcula.
    # Ver `sincronizar_ingreso_al_checkbook`: sin esto el checkbook queda siendo
    # una foto de la última vez que alguien apretó un botón a mano.
    sincronizadas = await sincronizar_ingreso_al_checkbook(
        session, scenario, revenue_results, cerrados)
    if sincronizadas:
        avisos.append(
            f"Ingreso sincronizado al checkbook: {sincronizadas} línea(s). El "
            f"sub-mayor de ingresos refleja el modelo vivo.")
    # Y las NOCHES viajan con la plata. Ver `sincronizar_noches`: sin esto el
    # ingreso queda fresco y el ADR, la ocupación y el equilibrio en noches
    # siguen sobre una foto vieja, en la misma pantalla.
    noches = await sincronizar_noches(session, scenario, revenue_results, cerrados)
    if noches:
        avisos.append(
            f"Noches sincronizadas: {noches} mes(es). El ADR, la ocupación y el "
            f"equilibrio en noches ya salen del modelo vivo.")
    pl_lines = await _persist_pl(session, scenario, revenue_results, cerrados)

    # Marca de recálculo: se compara contra el updated_at de planilla / tipos de
    # cambio / configs de reparto para avisar cuando el reporte quedó atrás de lo
    # que el usuario ya editó.
    scenario.last_recalc_at = datetime.utcnow()
    await session.commit()
    return {
        "scenario_id": scenario_id,
        "payroll_entries_updated": payroll_updated,
        "allocation_entries": alloc_entries,
        "pl_lines": pl_lines,
        "avisos": avisos,
        "status": "recalculated",
    }
