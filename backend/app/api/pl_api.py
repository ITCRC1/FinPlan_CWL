"""
P&L API — Full P&L report + manual inputs + full recalculation.

GET  /api/pl/{scenario_id}/month/{month}/   P&L for one month (computed live)
GET  /api/pl/{scenario_id}/monthly/         P&L for all 12 months + annual
GET  /api/pl/{scenario_id}/manual/          manual inputs (all months)
PUT  /api/pl/{scenario_id}/manual/{month}/  upsert manual inputs for a month
POST /api/pl/{scenario_id}/recalculate/     payroll → allocations → P&L (persist)
"""
from datetime import datetime
from decimal import Decimal
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from app.importers.registro_dep import registro_de_subida
from fastapi import Depends
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm.attributes import flag_modified

from app.api._candado import candado
from app.api._cashflow_criterios import (cargar_criterios, cargar_overrides_wc,
                                          escenario_vecino as escenario_vecino_anio,
                                          ventana_wc)
from app.engine.renta_anual import renta_liquidacion
from app.db import get_session
from app.errores import ErrorApi
from app.models.scenario import Scenario, ScenarioLockedError
from app.models.pl_manual_input import PLManualInput
from app.models.historical_kpi import HistoricalKpi
from app.models.scenario_stat import ScenarioStat
from app.models.cashflow_params import CashFlowParams
from app.models.tax_params import TaxParams
from app.engine import recalculate as recalc
from app.engine import pl_engine
from app.engine.cashflow_budget import (
    compute_cashflow_budget, compute_wc_calibration, wc_actuals_from_balances,
    wc_breakdown, wc_cost_base, overrides_from_version_rows, INPUT_KEYS,
    WC_MODEL_DEFAULTS, effective_timing_matrix, WC_TIMING_OFFSETS)
from app.models.cashflow_version import CashFlowVersion
from app.models.belowgop_account_entry import BelowGopAccountEntry
from app.models.actual_entry import ActualEntry
from app.models.nonop_entry import NonOpEntry
from app.models.cashflow_budget_input import CashFlowBudgetInput
from app.models.cashflow_budget_driver import CashFlowBudgetDriver
from app.models.cashflow_wc_params import CashFlowWCParams
from app.models.balance_sheet_line import BalanceSheetLine
from app.engine.tax import calculate_tax
from app.hotel_actual import HOTEL_ID

router = APIRouter(tags=["pl"])


def _line_to_dict(ln: pl_engine.PLLineResult, kpis: dict | None = None) -> dict:
    d = {
        "line_code": ln.line_code,
        "line_name": ln.line_name,
        "section": ln.section,
        "dept_code": ln.dept_code or "",
        "amount_usd": float(ln.amount_usd),
        "is_calculated": ln.is_calculated,
    }
    # PAR/POR (USALI per-room metrics) when room KPIs are available.
    if kpis is not None:
        par, por = pl_engine.par_por(
            ln.amount_usd, kpis.get("rooms_available"), kpis.get("rooms_occupied"))
        d["par"] = par
        d["por"] = por
    return d


_EMPTY_KPIS = {
    "rooms_available": 0, "rooms_occupied": 0.0, "guests": 0.0,
    "occupancy_pct": 0.0, "adr": 0.0, "revpar": 0.0,
}


def _kpis(r) -> dict:
    if r is None:
        return dict(_EMPTY_KPIS)
    # HistoricalKpi uses adr_usd/revpar_usd; RevenueResult uses adr/revpar
    adr = getattr(r, "adr", None) or getattr(r, "adr_usd", 0)
    revpar = getattr(r, "revpar", None) or getattr(r, "revpar_usd", 0)
    return {
        "rooms_available": r.rooms_available,
        "rooms_occupied": float(r.rooms_occupied),
        "guests": float(r.guests),
        "occupancy_pct": float(r.occupancy_pct),
        "adr": float(adr),
        "revpar": float(revpar),
    }


def _kpis_from_stat(s: ScenarioStat) -> dict:
    """KPIs from a ScenarioStat row. RevPAR derived as adr*occupied/available."""
    avail = s.rooms_available
    occ = float(s.rooms_occupied)
    adr = float(s.adr)
    return {
        "rooms_available": avail,
        "rooms_occupied": occ,
        "guests": float(s.guests),
        "occupancy_pct": float(s.occupancy_pct),
        "adr": adr,
        "revpar": (adr * occ / avail) if avail else 0.0,
    }


async def _get_scenario_or_404(session, scenario_id: str) -> Scenario:
    s = await session.get(Scenario, scenario_id)
    if not s:
        raise ErrorApi(404, "escenario.no_encontrado")
    return s


@router.get("/pl/{scenario_id}/month/{month}/")
async def get_pl_month(scenario_id: str, month: int):
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        is_actual = scenario.type == "ACTUAL"
        revenue_results = None if is_actual else await recalc.load_revenue_results(session, scenario)
        lines = await recalc.compute_pl_month(session, scenario, month, revenue_results)
        kpis = _kpis(None if is_actual else revenue_results[month])
        return {
            "scenario_id": scenario_id,
            "month": month,
            "year": scenario.year,
            "kpis": kpis,
            "lines": [_line_to_dict(ln, kpis) for ln in lines],
        }


async def _monthly_results(session, scenario) -> list[dict]:
    """Compute the P&L for all 12 months once.

    Returns [{month, kpis(dict), lines(list[PLLineResult])}] for months 1..12.
    Shared by the monthly endpoint and the YTD / Full Year aggregator (A2) so
    the heavy compute happens once and aggregations are pure sums on top.
    """
    is_actual = scenario.type == "ACTUAL"
    revenue_results = None if is_actual else await recalc.load_revenue_results(session, scenario)

    # Room KPIs: prefer ScenarioStat (authoritative, covers all scenario types).
    # Fallback to HistoricalKpi for ACTUAL, or rate-card revenue_results otherwise.
    stat_kpis: dict[int, ScenarioStat] = {}
    stat_q = await session.execute(
        select(ScenarioStat).where(ScenarioStat.scenario_id == scenario.id)
    )
    for s in stat_q.scalars().all():
        stat_kpis[s.month] = s

    # Rolling forecast: closed months (<= actuals_through) take the linked ACTUAL's
    # room stats too, consistent with the P&L lines (which already blend in
    # compute_pl_month). Without this the KPIs of closed months would show this
    # forecast's own (reforecast) stats while the revenue came from the Actual.
    through = scenario.actuals_through or 0
    actual_stat_kpis: dict[int, ScenarioStat] = {}
    if scenario.type == "FORECAST" and through > 0:
        actual = await recalc.linked_actual_scenario(session, scenario)
        if actual is not None:
            aq = await session.execute(
                select(ScenarioStat).where(ScenarioStat.scenario_id == actual.id)
            )
            for s in aq.scalars().all():
                actual_stat_kpis[s.month] = s

    hist_kpis: dict[int, HistoricalKpi] = {}
    if is_actual and not stat_kpis:
        hist_q = await session.execute(
            select(HistoricalKpi).where(
                HistoricalKpi.hotel_id == scenario.hotel_id,
                HistoricalKpi.year == scenario.year,
                HistoricalKpi.room_type_id == 0,
            )
        )
        for h in hist_q.scalars().all():
            hist_kpis[h.month] = h

    out = []
    for month in range(1, 13):
        lines = await recalc.compute_pl_month(session, scenario, month, revenue_results)
        if through >= month and month in actual_stat_kpis:
            kpis = _kpis_from_stat(actual_stat_kpis[month])
        elif month in stat_kpis:
            kpis = _kpis_from_stat(stat_kpis[month])
        else:
            kpis_src = hist_kpis.get(month) if is_actual else (
                revenue_results[month] if revenue_results else None)
            kpis = _kpis(kpis_src)
        out.append({"month": month, "kpis": kpis, "lines": lines})
    return out


async def _payroll_series(session, scenario) -> list[float]:
    """Planilla total (USD) por mes 1..12 del escenario — para sacarla de la base
    de A/P e IVA del modelo SOLO cuando la planilla no es tercerizada. Vacío (0)
    si el escenario no tiene detalle de planilla (p.ej. Actuals por snapshot)."""
    out = []
    for m in range(1, 13):
        d = await recalc.payroll_by_dept(session, scenario.id, m)
        out.append(float(sum(d.values())))
    return out


async def _aguinaldo_series(session, scenario) -> list[float]:
    """Aguinaldo provisionado por mes (USD) según la planilla real del escenario.

    El modelo de caja lo tenía en $8,300 fijos tecleados en los Criterios. Con la
    nómina de Budget 2027 el real es $12,340 por mes ($148,115 al año contra
    $99,600): la salida de diciembre estaba 49% subestimada, y como la provisión
    se cancela contra sí misma el anual daba 0.00 y parecía apagada.
    Vacío (ceros) si el escenario no tiene detalle de planilla.
    """
    from app.models.payroll_concept_entry import PayrollConceptEntry
    filas = (await session.execute(select(PayrollConceptEntry).where(
        PayrollConceptEntry.scenario_id == scenario.id))).scalars().all()
    out = [0.0] * 12
    for f in filas:
        if 1 <= (f.month or 0) <= 12:
            out[f.month - 1] += float(f.c6021_aguinaldo or 0)
    return out


def _apply_tax_correction(amounts: dict[str, float],
                          monthly_ebt: list[float] | None = None,
                          *, ebt_anual: float | None = None) -> None:
    """Repara el impuesto de renta de una columna del P&L. **Solo para
    escenarios que el motor CALCULA — nunca para los que traen el dato subido.**

    ⚠️ **A quién NO se le aplica.** Regla del owner: «en los históricos solo
    debe aceptar lo que se sube… nada más». Si el P&L del escenario sale del
    mayor o de un snapshot importado, el impuesto que está ahí ES el impuesto:
    ninguna fórmula lo reemplaza, lo corrige ni lo redistribuye. Quien lo
    decide es `_lo_subido_manda`, y quien obedece es `_aggregate_selected`.
    Antes esta función corría sobre todos los escenarios, y por eso un
    histórico podía mostrar un impuesto que nadie había contabilizado.

    Para los presupuestos calculados el motor ya escribe el impuesto mes a mes
    con su signo, y con el piso de cero aplicado al AÑO (ver
    `pl_engine.renta_por_mes`). Quedan solo reparaciones para datos que el
    motor NO produjo:

    - EBT ≤ 0 con impuesto POSITIVO → no se paga renta sobre una pérdida.
    - EBT > 0 sin impuesto (|tax| < $1) → aplicar la tasa estatutaria… **salvo
      que el AÑO no pague**. Ese es el borde que faltaba: en un ejercicio que
      cierra en pérdida el impuesto del año es cero, y entonces ninguna
      ventana suya —un mes, un YTD parcial— puede mostrar impuesto, por más
      que ESA ventana dé EBT positivo. Sin `ebt_anual` no hay cómo saberlo.
    - EBT > 0 con un impuesto que coincide con la vieja suma mensual
      `Σ MAX(0, EBT_mes × 30%)` → es de fórmula, no contabilizado, y se
      reemplaza por el 30% del EBT del período. Si no coincide, es una cifra
      real y no se toca.

    Solo se ajustan líneas que existen (nunca inventar un código sin metadata)."""
    tax = amounts.get("INCOME_TAXES", 0.0)
    ebt = amounts.get("EBT", 0.0)

    def _set(valor: float) -> None:
        if "INCOME_TAXES" in amounts:
            amounts["INCOME_TAXES"] = valor
        if "NET_PROFIT" in amounts:
            amounts["NET_PROFIT"] = round(ebt - valor, 2)

    # El AÑO manda sobre la ventana. Un ejercicio que cierra en pérdida no
    # paga renta, así que no hay nada que prorratear hacia ninguna columna.
    if ebt_anual is not None and ebt_anual <= 0:
        if tax > 0:
            _set(0.0)
        return

    if ebt <= 0:
        if tax > 0:
            _set(0.0)
        return
    if abs(tax) < 1.0:
        _set(round(ebt * 0.30, 2))
        return
    if monthly_ebt and len(monthly_ebt) > 1:
        por_mes = round(sum(max(0.0, e) for e in monthly_ebt) * 0.30, 2)
        if abs(tax - por_mes) < 1.0:
            _set(round(ebt * 0.30, 2))


async def _lo_subido_manda(session, scenario) -> bool:
    """¿El P&L de este escenario sale de lo que se SUBIÓ, y no de un cálculo?

    Cuando esto da True el reporte no le aplica ninguna corrección al impuesto:
    lo que está en el mayor o en el snapshot es el número.

    **Vive en el motor** (`recalculate.lo_subido_manda`), no acá. La misma
    pregunta decide si el recálculo puede pisar los auxiliares; tenerla escrita
    dos veces es exactamente cómo se separan dos reglas que tienen que decir lo
    mismo. Este alias queda para no reescribir los tres llamados del reporte.
    """
    return await recalc.lo_subido_manda(session, scenario)


def _aggregate_selected(sel: list[dict], *, lo_subido_manda: bool = False,
                       ebt_anual: float | None = None) -> dict:
    """Sum a chosen set of monthly results (each {month, kpis, lines}) into one
    column → {kpis, lines}. Lines carry summed amount + PAR/POR over the
    aggregated room KPIs. Building block for single month, YTD and Full Year.

    `lo_subido_manda=True` (escenario histórico / importado) → **la columna
    sale tal cual la sumó el motor sobre el dato subido**, sin corrección de
    impuesto. Es la regla del owner: en un histórico no se calcula nada que ya
    venga cargado. Ver `_lo_subido_manda` y `_apply_tax_correction`."""
    amounts: dict[str, float] = {}
    meta: dict[str, pl_engine.PLLineResult] = {}
    for m in sel:
        for ln in m["lines"]:
            amounts[ln.line_code] = amounts.get(ln.line_code, 0.0) + float(ln.amount_usd)
            meta.setdefault(ln.line_code, ln)
    if not lo_subido_manda:
        _apply_tax_correction(
            amounts,
            [sum(float(ln.amount_usd) for ln in m["lines"] if ln.line_code == "EBT")
             for m in sel],
            ebt_anual=ebt_anual,
        )

    avail = sum(m["kpis"]["rooms_available"] for m in sel)
    occ = sum(m["kpis"]["rooms_occupied"] for m in sel)
    guests = sum(m["kpis"]["guests"] for m in sel)
    # ADR y RevPAR salen de las ESTADÍSTICAS del escenario, no de la línea
    # REV_ROOMS. La razón: el owner abrió el room revenue en tres cuentas —4000
    # Room Revenue, 4001 Cancellations, 4002 No Show— y las tres consolidan en
    # REV_ROOMS. Un no-show NO ocupa habitación, así que su ingreso no puede
    # estar en el numerador de una tarifa por habitación ocupada: derivarlo de
    # la línea consolidada inflaría el ADR apenas esas cuentas tengan dato, y en
    # silencio, porque el ADR no tiene contra qué cuadrar.
    #
    # El ADR mensual ya viene cargado en `scenario_stats` (o del cálculo por
    # drivers) y nunca pasó por las cuentas. Se agrega ponderando por noches
    # ocupadas, que es lo único correcto: el promedio simple de doce meses le
    # daría el mismo peso a un mes lleno que a uno cerrado.
    adr_ponderado = sum(m["kpis"].get("adr", 0.0) * m["kpis"]["rooms_occupied"]
                        for m in sel)
    if adr_ponderado:
        adr = adr_ponderado / occ if occ else 0.0
    else:
        # Sin ADR en las estadísticas no hay de dónde sacarlo: se deriva de la
        # línea, como antes. Es el caso de un escenario sin `scenario_stats`
        # cargadas — ahí no hay contaminación posible porque tampoco hay
        # apertura de cuentas.
        adr = (amounts.get("REV_ROOMS", 0.0) / occ) if occ else 0.0
    kpis = {
        "rooms_available": avail,
        "rooms_occupied": occ,
        "guests": guests,
        "occupancy_pct": (occ / avail) if avail else 0.0,
        "adr": adr,
        # Mismo criterio que `_kpis_from_stat`: RevPAR = ADR × ocupación. Dejarlo
        # sobre REV_ROOMS rompería la identidad RevPAR = ADR × occ/avail.
        "revpar": (adr * occ / avail) if avail else 0.0,
    }
    lines = []
    for code, amt in amounts.items():
        ln = meta[code]
        par, por = pl_engine.par_por(amt, avail, occ)
        lines.append({
            "line_code": code,
            "line_name": ln.line_name,
            "section": ln.section,
            "dept_code": ln.dept_code or "",
            "amount_usd": round(amt, 2),
            "is_calculated": ln.is_calculated,
            "par": par,
            "por": por,
        })
    return {"kpis": kpis, "lines": lines}


def _ebt_anual(monthly: list[dict]) -> float:
    """El EBT de los doce meses: es lo que decide si el ejercicio paga renta."""
    return sum(float(ln.amount_usd) for m in monthly for ln in m["lines"]
               if ln.line_code == "EBT")


def _aggregate(monthly: list[dict], through_month: int, *,
               lo_subido_manda: bool = False) -> dict:
    """YTD / Full Year column = sum of months 1..through_month."""
    sel = [m for m in monthly if m["month"] <= through_month]
    return {"through_month": through_month,
            **_aggregate_selected(sel, lo_subido_manda=lo_subido_manda,
                                  ebt_anual=_ebt_anual(monthly))}


def _scenario_label(s: Scenario) -> str:
    return " ".join(str(x) for x in (s.type, s.version, s.year) if x)


@router.get("/pl/{scenario_id}/monthly/")
async def get_pl_monthly(scenario_id: str):
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        monthly = await _monthly_results(session, scenario)
        subido = await _lo_subido_manda(session, scenario)

        months = [{
            "month": m["month"],
            "kpis": m["kpis"],
            "lines": [_line_to_dict(ln, m["kpis"]) for ln in m["lines"]],
        } for m in monthly]

        full = _aggregate(monthly, 12, lo_subido_manda=subido)
        annual = {ln["line_code"]: ln["amount_usd"] for ln in full["lines"]}
        return {
            "scenario_id": scenario_id,
            "year": scenario.year,
            "months": months,
            "annual": annual,
            "annual_kpis": full["kpis"],
        }


@router.get("/pl/{scenario_id}/ytd/{month}/")
async def get_pl_ytd(scenario_id: str, month: int):
    """P&L acumulado de enero al mes dado (Year-To-Date). Cada línea suma los
    meses 1..month con sus PAR/POR sobre los KPIs acumulados."""
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        monthly = await _monthly_results(session, scenario)
        agg = _aggregate(monthly, month,
                         lo_subido_manda=await _lo_subido_manda(session, scenario))
        return {
            "scenario_id": scenario_id,
            "year": scenario.year,
            "through_month": month,
            "kpis": agg["kpis"],
            "lines": agg["lines"],
        }


@router.get("/pl/compare/")
async def get_pl_compare(scenarios: str, month: int = 12):
    """Comparar varias versiones en una sola llamada (generaliza el Command Center).

    `scenarios` = ids separados por coma. Para cada escenario devuelve los 3
    horizontes del reporte ejecutivo: `month` (mes solo), `ytd` (1..month) y
    `full` (12 meses). Base del Dashboard y del Full P&L a dueños.
    """
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")
    ids = [s.strip() for s in scenarios.split(",") if s.strip()]
    if not ids:
        raise ErrorApi(422, "escenarios.requerido")
    versions = []
    async with get_session() as session:
        for sid in ids:
            scenario = await session.get(Scenario, sid)
            if not scenario:
                continue  # skip ids that no longer exist; caller compares the rest
            monthly = await _monthly_results(session, scenario)
            # Regla del owner: a un escenario con el dato SUBIDO no se le
            # corrige nada; las columnas salen tal cual las sumó el motor.
            subido = await _lo_subido_manda(session, scenario)
            anual = _ebt_anual(monthly)
            def _col(sel):
                return _aggregate_selected(sel, lo_subido_manda=subido,
                                           ebt_anual=anual)
            one = _col([m for m in monthly if m["month"] == month])
            ytd = _col([m for m in monthly if m["month"] <= month])
            full = _col(monthly)
            versions.append({
                "scenario_id": sid,
                "label": _scenario_label(scenario),
                "type": scenario.type,
                "year": scenario.year,
                "version": scenario.version,
                "month": one,
                "ytd": ytd,
                "full": full,
            })
    return {"month": month, "versions": versions}


@router.get("/pl/compare-range/")
async def get_pl_compare_range(scenarios: str, from_month: int = 1, to_month: int = 12):
    """Como `/pl/compare/`, pero para un RANGO arbitrario de meses (Q1..Q4,
    un semestre, etc.) en vez de mes+YTD+Full.

    No es una resta entre columnas de `/pl/compare/` ya armadas: ADR se pondera
    por noches ocupadas y el impuesto tiene una corrección anual (ver
    `_aggregate_selected`) — ninguna de las dos es aditiva ni restable línea a
    línea. Un trimestre necesita su propia pasada por el mismo motor, con su
    propio `ebt_anual` de los 12 meses reales del escenario.
    """
    if not (1 <= from_month <= to_month <= 12):
        raise ErrorApi(422, "mes.rango_invalido")
    ids = [s.strip() for s in scenarios.split(",") if s.strip()]
    if not ids:
        raise ErrorApi(422, "escenarios.requerido")
    versions = []
    async with get_session() as session:
        for sid in ids:
            scenario = await session.get(Scenario, sid)
            if not scenario:
                continue
            monthly = await _monthly_results(session, scenario)
            subido = await _lo_subido_manda(session, scenario)
            anual = _ebt_anual(monthly)
            sel = [m for m in monthly if from_month <= m["month"] <= to_month]
            rango = _aggregate_selected(sel, lo_subido_manda=subido, ebt_anual=anual)
            versions.append({
                "scenario_id": sid,
                "label": _scenario_label(scenario),
                "type": scenario.type,
                "year": scenario.year,
                "version": scenario.version,
                "range": rango,
            })
    return {"from_month": from_month, "to_month": to_month, "versions": versions}


# ─── Manual inputs ────────────────────────────────────────────────────────────
class ManualInputPayload(BaseModel):
    rent: Decimal = Decimal("0")
    mgmt_fee_pct_3: Decimal = Decimal("0")   # opt-in driver; real fee = 8xxx accounts
    mgmt_fee_pct_5: Decimal = Decimal("0")
    properties_insurance: Decimal = Decimal("0")
    capital_reserve: Decimal = Decimal("0")
    capital_reserve_pct: Decimal = Decimal("0")
    large_capex: Decimal = Decimal("0")
    bank_interest: Decimal = Decimal("0")
    depreciation: Decimal = Decimal("0")
    income_tax_rate: Decimal = Decimal("0.30")


def _manual_to_dict(m: PLManualInput) -> dict:
    return {
        "month": m.month,
        "rent": str(m.rent),
        "mgmt_fee_pct_3": str(m.mgmt_fee_pct_3),
        "mgmt_fee_pct_5": str(m.mgmt_fee_pct_5),
        "properties_insurance": str(m.properties_insurance),
        "capital_reserve": str(m.capital_reserve),
        "capital_reserve_pct": str(m.capital_reserve_pct),
        "large_capex": str(m.large_capex),
        "bank_interest": str(m.bank_interest),
        "depreciation": str(m.depreciation),
        "income_tax_rate": str(m.income_tax_rate),
    }


@router.get("/pl/{scenario_id}/manual/")
async def get_manual_inputs(scenario_id: str):
    from sqlalchemy import select
    async with get_session() as session:
        await _get_scenario_or_404(session, scenario_id)
        rows = (await session.execute(
            select(PLManualInput).where(PLManualInput.scenario_id == scenario_id)
            .order_by(PLManualInput.month)
        )).scalars().all()
        return [_manual_to_dict(m) for m in rows]


@router.post("/pl/{scenario_id}/manual/{month}/")
async def upsert_manual_input(scenario_id: str, month: int, payload: ManualInputPayload):
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")
    from sqlalchemy import select
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        try:
            scenario.assert_editable()
        except ScenarioLockedError as e:
            raise HTTPException(409, str(e))

        existing = (await session.execute(
            select(PLManualInput).where(
                PLManualInput.scenario_id == scenario_id,
                PLManualInput.month == month,
            )
        )).scalar_one_or_none()

        fields = payload.model_dump()
        if existing:
            for k, v in fields.items():
                setattr(existing, k, v)
        else:
            session.add(PLManualInput(scenario_id=scenario_id, month=month, **fields))
        await session.commit()
    return {"ok": True, "month": month}


# ─── Scenario stats (room KPIs per month) ─────────────────────────────────────
class StatRow(BaseModel):
    month: int
    rooms_available: int = 0
    rooms_occupied: Decimal = Decimal("0")
    guests: Decimal = Decimal("0")
    occupancy_pct: Decimal = Decimal("0")
    adr: Decimal = Decimal("0")


@router.get("/pl/{scenario_id}/stats/")
async def get_scenario_stats(scenario_id: str):
    async with get_session() as session:
        await _get_scenario_or_404(session, scenario_id)
        rows = (await session.execute(
            select(ScenarioStat).where(ScenarioStat.scenario_id == scenario_id)
            .order_by(ScenarioStat.month)
        )).scalars().all()
        return [{
            "month": r.month,
            "rooms_available": r.rooms_available,
            "rooms_occupied": str(r.rooms_occupied),
            "guests": str(r.guests),
            "occupancy_pct": str(r.occupancy_pct),
            "adr": str(r.adr),
        } for r in rows]


@router.put("/pl/{scenario_id}/stats/")
async def upsert_scenario_stats(scenario_id: str, rows: list[StatRow]):
    """Bulk replace room KPI stats for a scenario (all 12 months)."""
    from sqlalchemy import delete
    async with get_session() as session:
        # Una versión enllavada no se puede sobreescribir.
        (await _get_scenario_or_404(session, scenario_id)).assert_editable()
        await session.execute(
            delete(ScenarioStat).where(ScenarioStat.scenario_id == scenario_id)
        )
        for r in rows:
            session.add(ScenarioStat(
                scenario_id=scenario_id,
                month=r.month,
                rooms_available=r.rooms_available,
                rooms_occupied=r.rooms_occupied,
                guests=r.guests,
                occupancy_pct=r.occupancy_pct,
                adr=r.adr,
            ))
        await session.commit()
    return {"ok": True, "imported": len(rows)}


# ─── Totales de gasto por tipo (planilla / costos / opex) ─────────────────────
@router.get("/scenarios/{scenario_id}/expense-totals/")
async def expense_totals(scenario_id: str):
    """Total anual por TIPO de gasto: planilla (6xxx), costos (5xxx), opex (7xxx).
    Maneja escenarios checkbook (entries) e importados (ActualEntry por clase)."""
    async with get_session() as session:
        await _get_scenario_or_404(session, scenario_id)
        payroll = cos = opex = 0.0
        for m in range(1, 13):
            pbd = await recalc.payroll_by_dept(session, scenario_id, m)
            cbd = await recalc.cos_by_dept(session, scenario_id, m)
            obd = await recalc.opex_by_dept(session, scenario_id, m)
            payroll += float(sum(pbd.values()))
            cos += float(sum(cbd.values()))
            opex += float(sum(obd.values()))
            for r in await recalc.actual_rows_for_month(session, scenario_id, m):
                ac = str(r["account_code"] or ""); amt = float(r["amount"] or 0)
                if ac.startswith("5"): cos += amt
                elif ac.startswith("6"): payroll += amt
                elif ac.startswith("7"): opex += amt
        return {"scenario_id": scenario_id, "payroll": round(payroll, 2),
                "cos": round(cos, 2), "opex": round(opex, 2)}


# ─── Flujo de caja proyectado (D1) ────────────────────────────────────────────
_CF_DEFAULTS = {"opening_cash": 0.0, "dso_days": 10, "dpo_days": 30, "distributions_annual": 0.0}


class CashFlowParamsPayload(BaseModel):
    opening_cash: Decimal = Decimal("0")
    dso_days: int = 10
    dpo_days: int = 30
    distributions_annual: Decimal = Decimal("0")


@router.put("/scenarios/{scenario_id}/cashflow/params/")
async def upsert_cashflow_params(scenario_id: str, payload: CashFlowParamsPayload):
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        await _get_scenario_or_404(session, scenario_id)
        row = (await session.execute(
            select(CashFlowParams).where(CashFlowParams.scenario_id == scenario_id)
        )).scalar_one_or_none()
        if row:
            row.opening_cash = payload.opening_cash
            row.dso_days = payload.dso_days
            row.dpo_days = payload.dpo_days
            row.distributions_annual = payload.distributions_annual
        else:
            session.add(CashFlowParams(scenario_id=scenario_id, **payload.model_dump()))
        await session.commit()
    return {"ok": True}


# ─── Cash Flow Budget (estructura tipo planilla del usuario) ──────────────────
async def _wc_calibration(session, scenario) -> dict:
    """Calibración: % WC implícito de los actuales (Δ Balance Sheet / ventas).
    Busca el escenario ACTUAL del mismo hotel+año con Balance Sheet cargado."""
    actual = (await session.execute(select(Scenario).where(
        Scenario.hotel_id == scenario.hotel_id, Scenario.year == scenario.year,
        Scenario.type == "ACTUAL"))).scalars().first()
    if actual is None:
        return {}
    bs = (await session.execute(select(BalanceSheetLine).where(
        BalanceSheetLine.scenario_id == actual.id))).scalars().all()
    if not bs:
        return {}
    balances: dict = {}
    for ln in bs:
        balances.setdefault((ln.year, ln.month), {})[ln.label.strip().lower()] = float(ln.usd)
    amonthly = await _monthly_results(session, actual)
    rev_by_m = {m["month"]: next((float(l.amount_usd) for l in m["lines"]
                if l.line_code == "TOTAL_REVENUES"), 0.0) for m in amonthly}
    return compute_wc_calibration(balances, rev_by_m, scenario.year)


# Las tres líneas de A&B. El 10% de servicio de ley se cobra sobre TODO el
# consumo de alimentos y bebidas, no solo sobre la comida.
#
# ⚠️ Antes esto era `REV_FB` a secas y estaba bien, porque esa línea llevaba todo
# el A&B. Desde el corte del 2026-08-14 `REV_FB` es SOLO comida: la bebida y los
# misceláneos se habrían caído de la base del servicio y del pasivo asociado.
#
# No se notaba todavía por una casualidad: el presupuesto colapsaba las tres en
# `REV_FB`, así que el error se compensaba solo. Arreglar una cosa sin la otra
# rompía los presupuestos — por eso van juntas.
LINEAS_AB = ("REV_FB", "REV_FB_BEV", "REV_FB_MISC")


def _ingreso_ab(por_linea: dict) -> float:
    """El ingreso de A&B completo, sea cual sea el camino del motor.

    En el resumen importado solo existe `REV_FB` (con todo adentro) y las otras
    dos vienen en cero; en el camino por cuenta existen las tres. Sumarlas es
    correcto en los dos casos y no hay doble conteo."""
    return sum(float(por_linea.get(c, 0.0) or 0.0) for c in LINEAS_AB)


async def _scenario_rev_costs(session, scn) -> tuple[list[float], list[float], list[float], list[float]]:
    """Revenue, costos operativos, net profit y revenue de A&B (REV_FB) mensuales
    (12) de un escenario — para la ventana de Working Capital del cruce de año, la
    proyección del balance y el 10% de servicio pass-through."""
    monthly = await _monthly_results(session, scn)
    ml = {m["month"]: {ln.line_code: float(ln.amount_usd) for ln in m["lines"]} for m in monthly}
    rev = [ml.get(m, {}).get("TOTAL_REVENUES", 0.0) for m in range(1, 13)]
    cost = [(ml.get(m, {}).get("TOTAL_OPEXP", 0.0) + ml.get(m, {}).get("TOTAL_OVERHEAD", 0.0)
             + ml.get(m, {}).get("TOTAL_NON_OP", 0.0)) for m in range(1, 13)]
    net = [ml.get(m, {}).get("NET_PROFIT", 0.0) for m in range(1, 13)]
    fb = [_ingreso_ab(ml.get(m, {})) for m in range(1, 13)]
    return rev, cost, net, fb


async def _capex_dep_series(session, scn) -> tuple[list[float], list[float]]:
    """CapEx y depreciación por mes (12) de un escenario.

    El CapEx SIEMPRE incrementa el activo fijo —la reserva del 4% del revenue es
    el piso— y la depreciación lo baja. Sin estas dos series el balance
    proyectado deja el activo fijo congelado y la caja termina absorbiendo la
    depreciación, que no es un desembolso.
    """
    monthly = await _monthly_results(session, scn)
    ml = {m["month"]: {ln.line_code: float(ln.amount_usd) for ln in m["lines"]}
          for m in monthly}
    capex = [float((ml.get(m) or {}).get("CAPITAL_EXPENSE", 0) or 0) for m in range(1, 13)]
    dep = [float((ml.get(m) or {}).get("TOTAL_DEPRECIATIONS", 0)
                 or (ml.get(m) or {}).get("DEPRECIATION", 0) or 0) for m in range(1, 13)]
    # La reserva de reposición (el 4% del revenue) se aparta contra un pasivo.
    reserva = [float((ml.get(m) or {}).get("CAPITAL_RESERVE", 0) or 0) for m in range(1, 13)]
    return capex, dep, reserva


async def _adjacent_scenario(session, scenario, delta: int, prefer_type: str):
    """Escenario del año±delta del mismo hotel, prefiriendo prefer_type y (en
    forecasts) el is_current_forecast — la base del cruce de año."""
    cands = (await session.execute(select(Scenario).where(
        Scenario.hotel_id == scenario.hotel_id,
        Scenario.year == scenario.year + delta))).scalars().all()
    if not cands:
        return None
    cands.sort(key=lambda s: (s.type == prefer_type, bool(getattr(s, "is_current_forecast", False))),
               reverse=True)
    return cands[0]


# Cuentas 8xxx que SON "Non Allocated Expenses" (efectivo, GOP→EBITDA):
# Rent + Owner/Mgmt Fees + Insurance + Other. Capital/Interés/Depreciación/Tax NO.
_NONALLOC_ACCTS = {"8000", "8010", "8005", "8015", "8025"}
_NONALLOC_LINES = {"RENT", "MGMT_FEE_3", "MGMT_FEE_5_ROYALTIES", "PROPERTY_INSURANCE", "OTHER_EXPENSES"}
_BG_MONTH_COLS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


async def _real_nonalloc_series(session, scenario) -> list[float] | None:
    """Below-GOP REAL (Non Allocated Expenses) por mes [12], de las cuentas 8xxx
    reales — AUTOMÁTICO, salteando el total roto del P&L y la fórmula 3% fantasma.
    Resuelve la fuente disponible: BelowGopAccountEntry → ActualEntry → NonOpEntry.
    Magnitud positiva (gasto). None si no hay nada (→ se respeta el P&L)."""
    out = [0.0] * 12
    bg = (await session.execute(select(BelowGopAccountEntry).where(
        BelowGopAccountEntry.scenario_id == scenario.id))).scalars().all()
    hit = False
    for e in bg:
        if (e.account_code or "").strip() in _NONALLOC_ACCTS:
            for i, c in enumerate(_BG_MONTH_COLS):
                out[i] += float(getattr(e, c, 0) or 0)
            hit = True
    if hit:
        return out
    ae = (await session.execute(select(ActualEntry).where(
        ActualEntry.scenario_id == scenario.id))).scalars().all()
    for e in ae:
        if (e.account_code or "").strip() in _NONALLOC_ACCTS:
            for i in range(12):
                out[i] += float(e.get_month(i + 1) or 0)
            hit = True
    if hit:
        return out
    no = (await session.execute(select(NonOpEntry).where(
        NonOpEntry.scenario_id == scenario.id))).scalars().all()
    for e in no:
        if (e.report_line_code or "").strip() in _NONALLOC_LINES:
            for i in range(12):
                out[i] += float(e.get_month(i + 1) or 0)
            hit = True
    return out if hit else None


async def _cashflow_budget_payload(session, scenario) -> dict:
    row = (await session.execute(
        select(CashFlowParams).where(CashFlowParams.scenario_id == scenario.id)
    )).scalar_one_or_none()
    opening = float(row.opening_cash) if row else 0.0
    # De dónde salió esa caja inicial. Viaja en cada carga, no solo al anclar:
    # si no, al recargar la página el monto queda sin explicación.
    anclaje = None
    if row is not None and getattr(row, "anchor_scenario_id", None):
        anclaje = {"scenario_id": row.anchor_scenario_id, "label": row.anchor_label,
                   "anchored_at": row.anchored_at.isoformat() if row.anchored_at else None}
    monthly = await _monthly_results(session, scenario)
    ml = {m["month"]: {ln.line_code: float(ln.amount_usd) for ln in m["lines"]} for m in monthly}
    # Non Allocated Expenses: el P&L trae el total mal (0) o la fórmula 3% fantasma.
    # Traemos el below-GOP REAL de las cuentas 8xxx → automático, transparente. Sin
    # datos reales (8xxx) → 0 (mata el 3% fantasma; al cargar el real fluye solo).
    # El P&L YA mezcla bien las dos fuentes del below-GOP: las cuentas 8xxx que se
    # cargan a mano y los fees que salen por fórmula (% del revenue). Descartarlo
    # entero —como se hacía acá— dejaba afuera el management fee: en Budget 2027
    # el P&L dice $281,920.38 y este reporte mostraba $102,000. Faltaban los
    # $179,920.38 del 3%, y el mismo concepto daba distinto en el P&L y en la caja.
    #
    # El descarte se escribió cuando el 3% se aplicaba SIN estar configurado (el
    # "3% fantasma"). Eso se arregló en la migración 066: hoy el fee sale de
    # pl_manual_inputs y sin porcentaje cargado vale 0 — verificado escenario por
    # escenario, solo los 2027 lo tienen en 3%.
    #
    # Se conserva el rescate que motivó el parche: si el P&L trae el total en cero
    # todo el año pero las cuentas 8xxx sí tienen datos, mandan las cuentas.
    nonop_pl = [float((ml.get(mm) or {}).get("TOTAL_NON_OP", 0) or 0) for mm in range(1, 13)]
    if not any(abs(v) > 0.005 for v in nonop_pl):
        rescate = await _real_nonalloc_series(session, scenario)
        if rescate is not None:
            nonop_pl = rescate
    for i, mm in enumerate(range(1, 13)):
        ml.setdefault(mm, {})["TOTAL_NON_OP"] = nonop_pl[i]
    inputs_q = (await session.execute(select(CashFlowBudgetInput).where(
        CashFlowBudgetInput.scenario_id == scenario.id))).scalars().all()
    inputs: dict[str, list[float]] = {}
    for e in inputs_q:
        inputs.setdefault(e.row_key, [0.0] * 12)
        if 1 <= e.month <= 12:
            inputs[e.row_key][e.month - 1] = float(e.value)
    drv_q = (await session.execute(select(CashFlowBudgetDriver).where(
        CashFlowBudgetDriver.scenario_id == scenario.id))).scalars().all()
    drivers = {d.row_key: {"mode": d.mode, "lag": d.lag,
                           "pct": float(d.pct) if d.mode in ("pct_sales", "days", "lead_lag") else None}
               for d in drv_q}
    # CRITERIOS: la misma resolución que usa el flujo directo. Antes cada API
    # armaba su propio diccionario y el mismo concepto podía valer distinto en
    # cada pantalla (A/P al 60% acá y al 70% allá, retenciones de tarjeta al
    # 2.5% acá y al 0% allá). Ahora hay una sola fuente y las diferencias que
    # queden se reportan en `avisos_criterios` en vez de quedar escondidas.
    wc_params, avisos_criterios = await cargar_criterios(session, scenario)
    # _overrides = copia editable de los reales (p.ej. Ene–May de la versión
    # congelada); va aparte, no es un parámetro del modelo de timing.
    wc_overrides = await cargar_overrides_wc(session, scenario.id)
    wc_model = {"enabled": bool(wc_params.get("enabled")), "params": wc_params,
                "timing_matrix": effective_timing_matrix(wc_params),
                "timing_offsets": list(WC_TIMING_OFFSETS)}
    payroll = await _payroll_series(session, scenario)
    # WC REAL para meses cerrados: del balance del Actual vinculado (Δ mensual).
    # Forecast → hasta su corte (actuals_through); Actual → todos sus meses.
    wc_actuals = None
    cash_actuals = None
    through = 12 if scenario.type == "ACTUAL" else (scenario.actuals_through or 0)
    if through > 0:
        actual = scenario if scenario.type == "ACTUAL" else await recalc.linked_actual_scenario(session, scenario)
        if actual is not None:
            bs = (await session.execute(select(BalanceSheetLine).where(
                BalanceSheetLine.scenario_id == actual.id))).scalars().all()
            if bs:
                balances: dict = {}
                for ln in bs:
                    balances.setdefault((ln.year, ln.month), {})[ln.label.strip().lower()] = float(ln.usd)
                wc_actuals = wc_actuals_from_balances(balances, scenario.year, through)
                # caja real (banks, sin totales) por mes cerrado → ancla la caja final
                cash_actuals = {}
                for m in range(1, through + 1):
                    d = balances.get((scenario.year, m))
                    if not d:
                        continue
                    banks = sum(v for k, v in d.items() if "bank" in k and "total" not in k)
                    cash_actuals[m] = banks
    # Cruce de año: la matriz de timing cobra meses adyacentes (ene 2027 → oct-dic
    # 2026). Con el modelo activo, traemos el revenue/costos del Forecast del año
    # anterior y del Budget del año siguiente y corremos la matriz sobre la ventana
    # combinada → los anticipos caen en el año correcto (no se duplican / no se pierden).
    # Ventana de años vecinos — la MISMA función que usa el flujo directo. Antes
    # cada método elegía el escenario vecino con su propia regla y podían
    # terminar mirando presupuestos distintos para el mismo año.
    wc_window = None
    integrated = None
    if wc_model["enabled"]:
        wc_window, integrated = await ventana_wc(session, scenario)
        wc_window = wc_window or None
    # Impuesto de renta de la liquidación anual. Solo baja al flujo si el owner
    # lo activó en el tab de Impuestos Y da a pagar: un saldo a favor no es caja
    # que entra, es un crédito que se arrastra al año siguiente.
    _dist = float(row.distributions_annual or 0) if row else 0.0
    _args = (ml, inputs, opening, drivers, wc_model, payroll,
             wc_actuals, cash_actuals, wc_window)
    # Primera pasada: de acá sale la retención de Renta de tarjeta del año, que
    # es el crédito contra el impuesto. Segunda pasada: el flujo ya con el
    # impuesto adentro. El impuesto no altera la retención, así que dos pasadas
    # alcanzan y no hay que resolver nada en círculo.
    previo = compute_cashflow_budget(*_args, wc_overrides=wc_overrides,
                                     distributions_annual=_dist)
    _rt = next((r for r in previo["rows"] if r.get("key") == "WC_RENTTAX"), None)
    creditos = -sum(_rt["values"]) if _rt else 0.0
    renta = renta_liquidacion(ml, wc_params, creditos_tarjeta=creditos)
    cf = compute_cashflow_budget(*_args, wc_overrides=wc_overrides,
                                 distributions_annual=_dist,
                                 renta_annual=renta["pasa_al_flujo"],
                                 renta_pay_month=renta["mes_pago"])
    calibration = await _wc_calibration(session, scenario)
    return {"scenario_id": scenario.id, "year": scenario.year, "opening_cash": opening,
            "renta": renta,
            "opening_anchor": anclaje,
            "calibration": calibration, "wc_model": wc_model, "wc_integrated": integrated,
            "has_overrides": bool(wc_overrides), **cf}


@router.get("/scenarios/{scenario_id}/cashflow-budget/")
async def get_cashflow_budget(scenario_id: str):
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        return await _cashflow_budget_payload(session, scenario)


# Operating Performance: línea → (fuente, dónde confirmarlo, total, matcher de componentes)
_PL_LINE_META = {
    # OJO: el origen del revenue depende del interruptor del escenario
    # (revenue_source). Decir siempre "rate cards" era mentir en los escenarios
    # que leen el checkbook — se resuelve en vivo, ver _revenue_source_label().
    "REVENUE":  ("", "Ingresos", "/revenue/checkbook", "TOTAL_REVENUES"),
    "OPEX":     ("Planilla + OpEx de departamentos OPERATIVOS (Rooms, F&B, Private Bar, Spa, Tours…)", "Costos · OpEx", "/opex/checkbook", "TOTAL_OPEXP"),
    "OVERHEAD": ("Planilla + OpEx de departamentos OVERHEAD (Admin, Ventas, Mantenimiento, IT…)", "OpEx", "/opex/checkbook", "TOTAL_OVERHEAD"),
}


def _revenue_source_label(scenario) -> str:
    """De dónde sale REALMENTE el revenue de este escenario.

    El P&L lo toma de las tarifas × ocupación o de montos tecleados en el
    checkbook de ingresos, según `revenue_source`. El drill-down afirmaba
    siempre lo primero, así que en Budget 2027 —que lee el checkbook— señalaba
    una fuente que no mueve nada.
    """
    if getattr(scenario, "revenue_source", "drivers") == "checkbook":
        return ("Checkbook de ingresos — montos en USD tecleados por línea. "
                "Las tarifas y la ocupación NO lo mueven: alimentan el cálculo "
                "que se traslada con «Pasar al checkbook».")
    return ("Tarifas × ocupación × canales (drivers). Se recalcula solo al "
            "cambiar tarifas, ocupación o paquetes.")


def _pl_component(ln, kind: str) -> bool:
    sec = (ln.section or "").upper(); code = ln.line_code or ""
    if code.startswith("TOTAL") or "PROFIT" in sec:
        return False
    if kind == "REVENUE":
        return "REVENUE" in sec or code.startswith("REV_")
    # ⚠️ El costo de ventas cuenta como gasto operativo acá, porque el TOTAL
    # contra el que se compara este desglose es `TOTAL_OPERATING_EXPENSES`, que
    # desde el 2026-08-14 es `SUM(OPEX_*) + SUM(COS_*)`. Sin las `COS_*` las
    # partes sumaban menos que el total, justo en la pantalla cuyo trabajo es
    # explicar el total.
    if kind == "OPEX":
        return ("OPERATING EXP" in sec or sec == "OPEXP" or sec == "COST OF SALES"
                or code.startswith(("OPEXP_", "OPEX_", "COS_")))
    # El overhead se salvaba POR CASUALIDAD: la sección nueva se llama
    # «OVERHEAD COST OF SALES» y contiene la subcadena «OVERHEAD». Se explicita
    # para que no dependa de cómo se llame la próxima.
    if kind == "OVERHEAD":
        return (sec.startswith("OVERHEAD") or code.startswith(("OVH_", "OH_", "COH_")))
    return False


async def _nonalloc_account_breakdown(session, scenario, month: int):
    """Componentes de Non Allocated, explicados desde LA MISMA fuente que produce
    el número: las líneas below-GOP del P&L.

    Antes esto listaba solo las cuentas 8xxx cargadas a mano. Desde que la fila
    toma el TOTAL_NON_OP del P&L —que además del GL trae los fees calculados por
    fórmula— ese desglose explicaba $102,000 para justificar $281,920: el
    drill-down contradecía a la línea que pretendía auditar, que es la peor forma
    de fallar para algo cuyo único trabajo es decir de dónde sale la plata.
    """
    ETIQUETAS = {
        "RENT": ("Rent", "cuenta 8000/8010 del below-GOP"),
        "MGMT_FEE_3": ("Management Fee", "% del revenue (Criterios del P&L)"),
        "MGMT_FEE_5_ROYALTIES": ("Royalties", "% del revenue (Criterios del P&L)"),
        "PROPERTY_INSURANCE": ("Property Insurance", "cuenta 8015 del below-GOP"),
        "OTHER_EXPENSES": ("Other Expenses", "cuenta 8025 del below-GOP"),
    }
    lineas = await recalc.compute_pl_month(session, scenario, month)
    partes = []
    for ln in lineas:
        code = (ln.line_code or "").strip()
        if code in ETIQUETAS:
            monto = round(float(ln.amount_usd or 0), 2)
            if monto:
                etiqueta, origen = ETIQUETAS[code]
                partes.append({"code": code, "label": f"{etiqueta} · {origen}", "amount": monto})
    if partes:
        return (partes,
                "P&L below-GOP — cuentas 8xxx cargadas + fees calculados por fórmula "
                "sobre el revenue. Es exactamente lo que suma la línea.",
                "/nonop/checkbook")
    return await _nonalloc_desde_cuentas(session, scenario, month)


async def _nonalloc_desde_cuentas(session, scenario, month: int):
    """Respaldo: las cuentas 8xxx cargadas, cuando el P&L no trae nada below-GOP."""
    names = {"8000": "Rent", "8010": "Rent", "8005": "Owner / Management Fees",
             "8015": "Property Insurance", "8025": "Other Expenses"}
    agg, src = {}, None
    bg = (await session.execute(select(BelowGopAccountEntry).where(
        BelowGopAccountEntry.scenario_id == scenario.id))).scalars().all()
    for e in bg:
        c = (e.account_code or "").strip()
        if c in _NONALLOC_ACCTS:
            agg[c] = agg.get(c, 0.0) + float(getattr(e, _BG_MONTH_COLS[month - 1], 0) or 0)
            src = "BelowGopAccountEntry — detalle GL 8xxx (mismo del reporte de dueños)"
    if not agg:
        ae = (await session.execute(select(ActualEntry).where(
            ActualEntry.scenario_id == scenario.id))).scalars().all()
        for e in ae:
            c = (e.account_code or "").strip()
            if c in _NONALLOC_ACCTS:
                agg[c] = agg.get(c, 0.0) + float(e.get_month(month) or 0)
                src = "ActualEntry — GL importado, cuentas 8xxx"
    if not agg:
        ln_names = {"RENT": "Rent", "MGMT_FEE_3": "Management Fees (3%)",
                    "MGMT_FEE_5_ROYALTIES": "Royalties (5%)", "PROPERTY_INSURANCE": "Property Insurance",
                    "OTHER_EXPENSES": "Other Expenses"}
        no = (await session.execute(select(NonOpEntry).where(
            NonOpEntry.scenario_id == scenario.id))).scalars().all()
        for e in no:
            lc = (e.report_line_code or "").strip()
            if lc in _NONALLOC_LINES:
                agg[lc] = agg.get(lc, 0.0) + float(e.get_month(month) or 0)
                src = "NonOpEntry — mini-checkbook below-GOP"
        parts = [{"code": k, "label": ln_names.get(k, k), "amount": round(v, 2)} for k, v in agg.items() if v]
    else:
        parts = [{"code": k, "label": f"{k} · {names.get(k, k)}", "amount": round(v, 2)} for k, v in agg.items() if v]
    return parts, (src or "Sin datos 8xxx cargados → $0 (cargá el below-GOP para que aparezca)"), "/nonop/checkbook"


@router.get("/scenarios/{scenario_id}/pl-breakdown/")
async def get_pl_breakdown(scenario_id: str, line: str, month: int):
    """Drill-down de Operating Performance: descompone Revenue / Operating Expenses /
    Overhead / Non Allocated en sus cuentas-fuente, con el ORIGEN y dónde ir a
    confirmarlo. Para auditar la integración de todos los cálculos."""
    if not (1 <= month <= 12):
        raise ErrorApi(400, "mes.fuera_de_rango")
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        monthly = await _monthly_results(session, scenario)
        mrec = next((m for m in monthly if m["month"] == month), None)
        plines = mrec["lines"] if mrec else []
        if line == "NONALLOC":
            parts, source, link = await _nonalloc_account_breakdown(session, scenario, month)
            total = round(sum(p["amount"] for p in parts), 2)
            link_label = "Non-Op / Below-GOP"
        elif line in _PL_LINE_META:
            source, link_label, link, tot_code = _PL_LINE_META[line]
            if line == "REVENUE":
                source = _revenue_source_label(scenario)
            parts = [{"code": ln.line_code, "label": ln.line_name, "amount": round(float(ln.amount_usd), 2)}
                     for ln in plines if _pl_component(ln, line) and round(float(ln.amount_usd), 2)]
            total = round(next((float(ln.amount_usd) for ln in plines if ln.line_code == tot_code), 0.0), 2)
        else:
            raise ErrorApi(400, "pl.linea_invalida")
        seen, dedup = set(), []                         # quitar duplicados de alias (mismo label+monto)
        for p in parts:
            k = (p["label"], p["amount"])
            if k in seen:
                continue
            seen.add(k); dedup.append(p)
        parts = dedup
        return {"line": line, "month": month, "month_label": _MONTH_ABBR[month - 1],
                "source": source, "link": link, "link_label": link_label,
                "parts": parts, "total": total}


_MONTH_ABBR = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


@router.get("/scenarios/{scenario_id}/cashflow-budget/wc-breakdown/")
async def get_wc_breakdown(scenario_id: str, row: str, month: int):
    """Drill-down: descompone una celda del modelo WC (row_key, mes 1..12) en sus
    componentes — qué meses/conceptos la forman — para auditar de dónde sale el
    monto (p.ej. Deposits Received de oct = anticipos de estadías nov/dic/ene/feb).
    Corre el modelo sobre la MISMA ventana del cruce de año que el reporte."""
    if not (1 <= month <= 12):
        raise ErrorApi(400, "mes.fuera_de_rango")
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        monthly = await _monthly_results(session, scenario)
        ml = {m["month"]: {ln.line_code: float(ln.amount_usd) for ln in m["lines"]} for m in monthly}
        rev = [ml.get(m, {}).get("TOTAL_REVENUES", 0.0) for m in range(1, 13)]
        gross_costs = [(ml.get(m, {}).get("TOTAL_OPEXP", 0.0) + ml.get(m, {}).get("TOTAL_OVERHEAD", 0.0)
                        + ml.get(m, {}).get("TOTAL_NON_OP", 0.0)) for m in range(1, 13)]
        fb = [_ingreso_ab(ml.get(m, {})) for m in range(1, 13)]
        wcp = (await session.execute(select(CashFlowWCParams).where(
            CashFlowWCParams.scenario_id == scenario.id))).scalar_one_or_none()
        params = {**WC_MODEL_DEFAULTS, **(wcp.params or {})} if wcp else dict(WC_MODEL_DEFAULTS)
        payroll = await _payroll_series(session, scenario)
        costs = wc_cost_base(gross_costs, payroll, params)   # base de costos (igual que el reporte)
        # Ventana del cruce de año — solo si el modelo está activo (igual que el payload)
        pr_r = pr_c = pr_fb = nx_r = nx_c = nx_fb = None
        if wcp and wcp.enabled:
            prior = await _adjacent_scenario(session, scenario, -1, "FORECAST")
            nxt = await _adjacent_scenario(session, scenario, +1, "BUDGET")
            if prior is not None:
                pr_r, pr_c, _, pr_fb = await _scenario_rev_costs(session, prior)
            if nxt is not None:
                nx_r, nx_c, _, nx_fb = await _scenario_rev_costs(session, nxt)
        pr_r, pr_c, pr_fb = pr_r or [], pr_c or [], pr_fb or []
        nx_r, nx_c, nx_fb = nx_r or [], nx_c or [], nx_fb or []
        R = list(pr_r) + rev + list(nx_r)
        C = list(pr_c) + costs + list(nx_c)
        FB = list(pr_fb) + fb + list(nx_fb)
        off = len(pr_r)
        base_year = scenario.year - (off // 12)
        def label_fn(gi: int) -> str:
            return f"{_MONTH_ABBR[gi % 12]}-{str(base_year + gi // 12)[2:]}"
        t = off + (month - 1)
        bd = wc_breakdown(R, C, params, row, t, label_fn, fb=FB)
        bd["row"] = row
        bd["month_label"] = label_fn(t)
        return bd


async def _get_or_create_wcp(session, scenario_id: str) -> CashFlowWCParams:
    wcp = (await session.execute(select(CashFlowWCParams).where(
        CashFlowWCParams.scenario_id == scenario_id))).scalar_one_or_none()
    if wcp is None:
        wcp = CashFlowWCParams(scenario_id=scenario_id, enabled=False, params={})
        session.add(wcp)
    return wcp


@router.post("/scenarios/{scenario_id}/cashflow-budget/copy-from-version/")
async def copy_cashflow_from_version(scenario_id: str, version_id: str, months: str = "1,2,3,4,5"):
    """Copia los REALES de una versión congelada (CashFlowVersion) a OVERRIDES
    editables del escenario en vivo, para los `months` (CSV 1..12, default Ene–May).
    Solo partidas de Working Capital (signos compatibles). Quedan fijos (pisan al
    modelo) y editables; el modelo sigue vivo en los meses no copiados. Devuelve el
    payload recalculado + copy_result (qué líneas se copiaron / no calzaron)."""
    try:
        month_list = sorted({int(m) for m in months.split(",") if m.strip()})
    except ValueError:
        raise ErrorApi(400, "meses.csv_invalido")
    if not month_list or any(not 1 <= m <= 12 for m in month_list):
        raise ErrorApi(400, "meses.fuera_de_rango")
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        scenario = await _get_scenario_or_404(session, scenario_id)
        version = await session.get(CashFlowVersion, version_id)
        if version is None:
            raise ErrorApi(404, "version.congelada_no_encontrada")
        # overrides_from_version_rows ya restringe a las 8 partidas de WC_ROWS por
        # label (CapEx/Other no calzan y no se copian — CapEx invertiría el signo).
        new_ovr, mapped, skipped = overrides_from_version_rows(version.rows or [], month_list)
        wcp = await _get_or_create_wcp(session, scenario_id)
        params = dict(wcp.params or {})
        ov = {k: dict(v) for k, v in (params.get("_overrides") or {}).items()}
        for k, cell in new_ovr.items():
            ov[k] = {**ov.get(k, {}), **cell}
        params["_overrides"] = ov
        wcp.params = params                      # reasignar dispara el UPDATE del JSON
        flag_modified(wcp, "params")             # seguro: forzar dirty del JSON anidado
        await session.commit()
        payload = await _cashflow_budget_payload(session, scenario)
        payload["copy_result"] = {"version_name": version.name, "months": month_list,
                                   "mapped": mapped, "skipped": skipped}
        return payload


class CFBOverridesPayload(BaseModel):
    overrides: dict = {}   # {row_key: {mes(str): valor}}; reemplaza el set completo


@router.put("/scenarios/{scenario_id}/cashflow-budget/wc-overrides/")
async def put_cashflow_wc_overrides(scenario_id: str, payload: CFBOverridesPayload):
    """Reemplaza el set de overrides editables (las celdas fijadas a mano, p.ej.
    los reales copiados y luego ajustados). Mandar {} limpia todos los overrides."""
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        scenario = await _get_scenario_or_404(session, scenario_id)
        # normaliza: descarta valores nulos / meses fuera de rango.
        # Además de las partidas de input (WC/CapEx/Other) se permite override en
        # NONALLOC (Non Allocated Expenses / below-GOP) para cargar reales Ene–May.
        allowed = set(INPUT_KEYS) | {"NONALLOC"}
        clean: dict = {}
        for k, cells in (payload.overrides or {}).items():
            if k not in allowed or not isinstance(cells, dict):
                continue
            cc = {}
            for mk, val in cells.items():
                try:
                    m = int(mk)
                except (TypeError, ValueError):
                    continue
                if 1 <= m <= 12 and val is not None:
                    cc[str(m)] = round(float(val), 2)
            if cc:
                clean[k] = cc
        wcp = await _get_or_create_wcp(session, scenario_id)
        params = dict(wcp.params or {})
        if clean:
            params["_overrides"] = clean
        else:
            params.pop("_overrides", None)
        wcp.params = params
        flag_modified(wcp, "params")             # seguro: forzar dirty del JSON anidado
        await session.commit()
        return await _cashflow_budget_payload(session, scenario)


@router.post("/scenarios/{scenario_id}/cashflow-budget/anchor-opening/")
async def anchor_opening_cash(scenario_id: str, source_scenario_id: str):
    """Ancla la caja inicial de este escenario al CIERRE (caja final de diciembre)
    del cashflow-budget de otro escenario — típicamente el Forecast 2026 current →
    base del Budget 2027. Guarda el valor en CashFlowParams.opening_cash (estable:
    no se mueve aunque el forecast vivo cambie después)."""
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        scenario = await _get_scenario_or_404(session, scenario_id)
        source = await _get_scenario_or_404(session, source_scenario_id)
        src = await _cashflow_budget_payload(session, source)
        ending = 0.0
        for r in src.get("rows", []):
            if r.get("key") == "ENDING_CASH":
                vals = r.get("values") or []
                ending = float(vals[11]) if len(vals) >= 12 else float(r.get("full_year") or 0.0)
                break
        etiqueta = f"{source.type.title()} {source.version} {source.year}"
        ahora = datetime.utcnow()
        row = (await session.execute(select(CashFlowParams).where(
            CashFlowParams.scenario_id == scenario_id))).scalar_one_or_none()
        if row:
            row.opening_cash = ending
            row.anchor_scenario_id = source.id
            row.anchor_label = etiqueta
            row.anchored_at = ahora
        else:
            session.add(CashFlowParams(
                scenario_id=scenario_id, opening_cash=ending,
                dso_days=10, dpo_days=30, distributions_annual=0,
                anchor_scenario_id=source.id, anchor_label=etiqueta, anchored_at=ahora))
        await session.commit()
        payload = await _cashflow_budget_payload(session, scenario)
        payload["anchored_from"] = {"scenario_id": source.id, "year": source.year,
                                    "label": etiqueta, "ending_cash": round(ending, 2),
                                    "anchored_at": ahora.isoformat()}
        return payload


@router.get("/scenarios/{scenario_id}/recalc-state/")
async def get_recalc_state(scenario_id: str):
    """¿El reporte refleja lo último que editó el usuario, o quedó atrás?

    Cambiar un salario, un tipo de cambio o una regla de reparto NO se propaga
    solo: hay que apretar Recalcular. Hasta ahora nada lo decía, así que se podía
    mirar un P&L que no incluía la edición de hace media hora. Se compara el
    `last_recalc_at` del escenario contra el `updated_at` más reciente de las
    tablas cuyo cambio exige recalcular.

    `updated_at` en NULL = fila anterior a la migración 083: no se sabe cuándo
    cambió, así que NO se cuenta como pendiente. Marcar todo como sucio el primer
    día sería un aviso que nadie creería, y un aviso que no se cree es peor que
    ninguno.
    """
    from app.models.payroll_position import PayrollPosition
    from app.models.payroll_params import PayrollParams
    from app.models.exchange_rate import ExchangeRate
    from app.models.salary_allocation_config import SalaryAllocationConfig
    from app.models.cafeteria_allocation_config import CafeteriaAllocationConfig
    from app.models.laundry_allocation_config import LaundryAllocationConfig

    FUENTES = [
        (PayrollPosition, "planilla"),
        (PayrollParams, "parámetros de planilla"),
        (ExchangeRate, "tipos de cambio"),
        (SalaryAllocationConfig, "reparto de salarios"),
        (CafeteriaAllocationConfig, "reparto de cafetería"),
        (LaundryAllocationConfig, "reparto de lavandería"),
    ]
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        ultimo = getattr(scenario, "last_recalc_at", None)
        cambios: list[dict] = []
        for Modelo, etiqueta in FUENTES:
            cuando = (await session.execute(
                select(func.max(Modelo.updated_at)).where(
                    Modelo.scenario_id == scenario_id))).scalar()
            if cuando and (ultimo is None or cuando > ultimo):
                cambios.append({"que": etiqueta, "cuando": cuando.isoformat()})
    return {
        "last_recalc_at": ultimo.isoformat() if ultimo else None,
        "stale": bool(cambios),
        "changed": cambios,
    }


@router.get("/scenarios/{scenario_id}/cashflow-budget/anchor-check/")
async def check_opening_anchor(scenario_id: str):
    """¿La caja inicial anclada sigue siendo el cierre de su escenario fuente?

    El anclaje COPIA Y CONGELA a propósito: así el presupuesto no se mueve solo
    cuando alguien edita el año anterior. El problema no es que se congele — es
    que la etiqueta seguía afirmando "anclada al cierre de X" aunque X hubiera
    cambiado meses atrás, y todo el nivel de caja del año se apoya en ese dato.

    Va en un endpoint aparte y no dentro del payload porque recalcular el cierre
    del escenario fuente cuesta otro P&L completo: metido en la carga normal
    duplicaría el tiempo de la pantalla, que es justo lo que acabamos de arreglar.
    """
    async with get_session() as session:
        row = (await session.execute(select(CashFlowParams).where(
            CashFlowParams.scenario_id == scenario_id))).scalar_one_or_none()
        if row is None or not getattr(row, "anchor_scenario_id", None):
            return {"anchored": False}
        fuente = await session.get(Scenario, row.anchor_scenario_id)
        if fuente is None:
            return {"anchored": True, "label": row.anchor_label, "source_missing": True,
                    "stored": float(row.opening_cash or 0)}
        payload = await _cashflow_budget_payload(session, fuente)
        actual = 0.0
        for r in payload.get("rows", []):
            if r.get("key") == "ENDING_CASH":
                vals = r.get("values") or []
                actual = float(vals[11]) if len(vals) >= 12 else float(r.get("full_year") or 0)
                break
        guardado = float(row.opening_cash or 0)
        return {
            "anchored": True,
            "label": row.anchor_label,
            "anchored_at": row.anchored_at.isoformat() if row.anchored_at else None,
            "stored": round(guardado, 2),
            "current": round(actual, 2),
            "diff": round(actual - guardado, 2),
            "stale": abs(actual - guardado) > 0.5,
        }


class CFBInputRow(BaseModel):
    row_key: str
    values: list[float]   # 12 meses (ene..dic)


class CFBInputsPayload(BaseModel):
    opening_cash: float | None = None
    rows: list[CFBInputRow]


@router.put("/scenarios/{scenario_id}/cashflow-budget/inputs/")
async def put_cashflow_budget_inputs(scenario_id: str, payload: CFBInputsPayload):
    from sqlalchemy import delete
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        scenario = await _get_scenario_or_404(session, scenario_id)
        # opening cash → CashFlowParams.opening_cash
        if payload.opening_cash is not None:
            row = (await session.execute(select(CashFlowParams).where(
                CashFlowParams.scenario_id == scenario_id))).scalar_one_or_none()
            if row:
                # Escribir el monto a mano ROMPE el anclaje: el número ya no es el
                # cierre de nadie. Dejar la etiqueta puesta sería peor que no
                # tenerla — diría que viene de un lugar del que ya no viene.
                if float(row.opening_cash or 0) != float(payload.opening_cash):
                    row.anchor_scenario_id = None
                    row.anchor_label = None
                    row.anchored_at = None
                row.opening_cash = payload.opening_cash
            else:
                session.add(CashFlowParams(scenario_id=scenario_id, opening_cash=payload.opening_cash,
                                           dso_days=10, dpo_days=30, distributions_annual=0))
        # inputs: reemplaza solo las row_key recibidas (válidas), borra-luego-inserta
        keys = [r.row_key for r in payload.rows if r.row_key in INPUT_KEYS]
        if keys:
            await session.execute(delete(CashFlowBudgetInput).where(
                CashFlowBudgetInput.scenario_id == scenario_id,
                CashFlowBudgetInput.row_key.in_(keys)))
        for r in payload.rows:
            if r.row_key not in INPUT_KEYS:
                continue
            for m in range(1, 13):
                v = r.values[m - 1] if m - 1 < len(r.values) else 0.0
                if not v:
                    continue
                session.add(CashFlowBudgetInput(scenario_id=scenario_id, row_key=r.row_key,
                                                month=m, value=v))
        await session.commit()
        return await _cashflow_budget_payload(session, scenario)


_DRIVER_MODES = {"manual", "pct_sales", "days", "lead_lag"}


class CFBDriverRow(BaseModel):
    row_key: str
    mode: str = "manual"          # manual | pct_sales | days | lead_lag
    pct: float | None = None      # fracción (pct_sales/lead_lag) o días (days)
    lag: int = 0                  # meses (solo lead_lag)


class CFBDriversPayload(BaseModel):
    drivers: list[CFBDriverRow]


@router.put("/scenarios/{scenario_id}/cashflow-budget/drivers/")
async def put_cashflow_budget_drivers(scenario_id: str, payload: CFBDriversPayload):
    from sqlalchemy import delete
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        scenario = await _get_scenario_or_404(session, scenario_id)
        keys = [d.row_key for d in payload.drivers if d.row_key in INPUT_KEYS]
        if keys:
            await session.execute(delete(CashFlowBudgetDriver).where(
                CashFlowBudgetDriver.scenario_id == scenario_id,
                CashFlowBudgetDriver.row_key.in_(keys)))
        for d in payload.drivers:
            if d.row_key not in INPUT_KEYS:
                continue
            mode = d.mode if d.mode in _DRIVER_MODES else "manual"
            session.add(CashFlowBudgetDriver(
                scenario_id=scenario_id, row_key=d.row_key, mode=mode,
                pct=(d.pct or 0.0) if mode != "manual" else 0.0,
                lag=int(d.lag) if mode == "lead_lag" else 0))
        await session.commit()
        return await _cashflow_budget_payload(session, scenario)


@router.get("/scenarios/{scenario_id}/balance-sheet-projection/")
async def get_balance_sheet_projection(scenario_id: str, months: int = 24):
    """Balance Sheet COMPLETO proyectado: ancla en el último balance real
    subido (del Actual) y rueda cada línea `months` meses — partidas WC con el
    modelo de timing, Caja como plug (cuadra cada mes), utilidad a Patrimonio.
    El revenue/modelo salen del escenario consultado."""
    from app.engine.cashflow_budget import project_balance_sheet, project_full_balance_sheet, wc_cost_base
    horizon = max(6, min(36, months))
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        monthly = await _monthly_results(session, scenario)
        rev = [next((float(l.amount_usd) for l in m["lines"] if l.line_code == "TOTAL_REVENUES"), 0.0) for m in monthly]
        net = [next((float(l.amount_usd) for l in m["lines"] if l.line_code == "NET_PROFIT"), 0.0) for m in monthly]
        fb = [_ingreso_ab({l.line_code: float(l.amount_usd) for l in m["lines"]})
              for m in monthly]
        # base de costos del modelo WC; si la planilla NO es tercerizada se le resta
        # (sin IVA). Por defecto tercerizada → entra entera (cobro con IVA).
        gross_costs = [sum(next((float(l.amount_usd) for l in m["lines"] if l.line_code == c), 0.0)
                           for c in ("TOTAL_OPEXP", "TOTAL_OVERHEAD", "TOTAL_NON_OP")) for m in monthly]
        # LOS MISMOS CRITERIOS que los dos cash flows. Antes esta pantalla armaba
        # su propio diccionario mezclando WC_MODEL_DEFAULTS con lo guardado, así
        # que podía proyectar el balance con criterios distintos de los que
        # producían el flujo de caja del mismo escenario.
        params, _avisos_crit = await cargar_criterios(session, scenario)
        payroll = await _payroll_series(session, scenario)
        costs = wc_cost_base(gross_costs, payroll, params)

        # ancla: el balance real MÁS RECIENTE cargado (cualquier Actual del hotel)
        act_ids = [a.id for a in (await session.execute(select(Scenario).where(
            Scenario.hotel_id == scenario.hotel_id, Scenario.type == "ACTUAL"))).scalars().all()]
        anchor_lines, anchor_month, ay = [], 0, scenario.year
        bs_all = []
        if act_ids:
            bs_all = (await session.execute(select(BalanceSheetLine).where(
                BalanceSheetLine.scenario_id.in_(act_ids)))).scalars().all()
        if bs_all:
            ay, anchor_month = max((l.year, l.month) for l in bs_all)
            lines = sorted([l for l in bs_all if l.year == ay and l.month == anchor_month],
                           key=lambda l: l.order_idx)
            anchor_lines = [{"label": l.label, "section": l.section, "is_total": l.is_total,
                             "indent": l.indent, "usd": float(l.usd)} for l in lines]
        if not anchor_lines:
            raise ErrorApi(404, "balance.sin_ancla_actual")

        N = anchor_month + horizon
        gy2 = float(params.get("growth_y2", 0.07))
        # La serie arranca en enero del AÑO DEL ANCLA, no del año del escenario.
        #
        # Antes arrancaba en el escenario consultado y después se cortaba en
        # `anchor_month`. Con un Budget 2027 anclado en el balance real de mayo de
        # 2026, la columna «Jun-26» terminaba alimentada con el junio de 2027:
        # TODAS las columnas usaban datos de un año más adelante que su etiqueta.
        # Solo coincidía cuando el escenario era del mismo año que el ancla.
        #
        # Ahora se arma año por año desde el ancla: para cada año se busca su
        # escenario —el forecast si ya pasó, el budget si viene— y el consultado
        # manda en su propio año.
        cap0, dep0, res0 = await _capex_dep_series(session, scenario)

        async def _serie_del_anio(anio: int):
            if anio == scenario.year:
                return (list(rev), list(costs), list(net), list(fb),
                        list(cap0), list(dep0), list(res0))
            scn = await escenario_vecino_anio(session, scenario, anio - scenario.year)
            if scn is None:
                return None
            r2, c2, n2, fb2 = await _scenario_rev_costs(session, scn)
            cap2, dep2, res2 = await _capex_dep_series(session, scn)
            return (r2, wc_cost_base(c2, await _payroll_series(session, scn), params),
                    n2, fb2, cap2, dep2, res2)

        rev_full, costs_full, npft_full, fb_full = [], [], [], []
        capex_full, dep_full, res_full = [], [], []
        anio = ay
        anios_usados = []
        while len(rev_full) < N:
            serie = await _serie_del_anio(anio)
            if serie is None:
                # Sin escenario para ese año: se crece el último con growth_y2.
                # Es un respaldo declarado, no un dato.
                base = len(rev_full) - 12
                if base < 0:
                    break
                serie = ([rev_full[base + i] * (1 + gy2) for i in range(12)],
                         [costs_full[base + i] * (1 + gy2) for i in range(12)],
                         [npft_full[base + i] * (1 + gy2) for i in range(12)],
                         [fb_full[base + i] * (1 + gy2) for i in range(12)],
                         [capex_full[base + i] * (1 + gy2) for i in range(12)],
                         [dep_full[base + i] for i in range(12)],
                         [res_full[base + i] * (1 + gy2) for i in range(12)])
                anios_usados.append({"anio": anio, "origen": "crecimiento"})
            else:
                anios_usados.append({"anio": anio, "origen": "escenario"})
            rev_full += serie[0]; costs_full += serie[1]
            npft_full += serie[2]; fb_full += serie[3]
            capex_full += serie[4]; dep_full += serie[5]; res_full += serie[6]
            anio += 1
        rev_full, costs_full = rev_full[:N], costs_full[:N]
        npft_full, fb_full = npft_full[:N], fb_full[:N]
        proj_wc = project_balance_sheet(rev_full, costs_full, params, months=N, fb=fb_full)
        keys = {ln["key"]: ln["delta"] for ln in proj_wc["lines"]}  # DEPOSITS/AR/AP/ACCRUED/IVA/RENTA
        sl = lambda a: a[anchor_month:anchor_month + horizon] + [0.0] * max(0, horizon - len(a[anchor_month:]))
        deltas = {k2: sl(v) for k2, v in keys.items()}
        # El CapEx SIEMPRE incrementa el activo fijo y la depreciación lo baja.
        deltas["CAPEX"] = sl(capex_full)
        deltas["DEPREC"] = sl(dep_full)
        deltas["RESERVA"] = sl(res_full)
        full = project_full_balance_sheet(anchor_lines, deltas, sl(npft_full), horizon)
        return {"scenario_id": scenario_id, "year": scenario.year,
                "anchor_year": ay, "anchor_month": anchor_month,
                "anios_usados": anios_usados, **full}


class CFBWCModelPayload(BaseModel):
    enabled: bool = False
    params: dict = {}


@router.put("/scenarios/{scenario_id}/cashflow-budget/wc-model/")
async def put_cashflow_budget_wc_model(scenario_id: str, payload: CFBWCModelPayload):
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        scenario = await _get_scenario_or_404(session, scenario_id)
        # sanea: solo claves conocidas; mix_flex es lista de 12, el resto numérico
        clean = {}
        for k, default in WC_MODEL_DEFAULTS.items():
            if k == "enabled":
                continue
            v = payload.params.get(k, default)
            if isinstance(default, bool):           # antes de int/float (bool ⊂ int)
                clean[k] = v if isinstance(v, bool) else str(v).strip().lower() in ("true", "1", "yes", "on")
            elif isinstance(default, list):
                try:
                    arr = [float(x) for x in (v or default)][:12]
                    clean[k] = (arr + list(default))[:12]
                except (TypeError, ValueError):
                    clean[k] = list(default)
            else:
                try:
                    clean[k] = float(v)
                except (TypeError, ValueError):
                    clean[k] = float(default)
        # timing_matrix (12×N): matriz editable de timing por mes. Si viene, se
        # normaliza a 12 filas × len(OFFSETS) floats; el motor la prefiere sobre
        # las cajas NRR/Flex/Stay/Credit.
        #
        # Las matrices de los AÑOS VECINOS (6 filas cada una) se guardan igual. La
        # pantalla de Criterios las deja editar desde que existe la matriz de 24
        # filas, pero acá no se saneaban ni se guardaban: el motor las lee
        # (`cashflow_budget.cobros_por_timing`) y siempre encontraba None, así que
        # las doce filas de años vecinos eran decorativas — el owner las editaba,
        # apretaba Guardar y volvían a estar vacías.
        def _matriz(raw, filas: int):
            if not isinstance(raw, list) or len(raw) < filas:
                return None
            ncol = len(WC_TIMING_OFFSETS)
            norm = []
            for fila in raw[:filas]:
                fila = fila if isinstance(fila, list) else []
                vals = []
                for i in range(ncol):
                    try:
                        vals.append(float(fila[i]) if i < len(fila) else 0.0)
                    except (TypeError, ValueError):
                        vals.append(0.0)
                norm.append(vals)
            return norm

        for clave, filas in (("timing_matrix", 12),
                             ("timing_matrix_prev", 6), ("timing_matrix_next", 6)):
            m = _matriz(payload.params.get(clave), filas)
            if m is not None:
                clean[clave] = m
        row = (await session.execute(select(CashFlowWCParams).where(
            CashFlowWCParams.scenario_id == scenario_id))).scalar_one_or_none()
        if row:
            row.enabled = payload.enabled
            # MERGE, no reemplazo. `params` no guarda solo los criterios: adentro
            # viven también los `_overrides` (la copia editable de los reales
            # Ene–May que se trae de la versión congelada) y las matrices de años
            # vecinos. Al asignar `clean` entero, guardar cualquier criterio
            # BORRABA ese trabajo sin avisar.
            previo = dict(row.params or {})
            previo.update(clean)
            row.params = previo
        else:
            session.add(CashFlowWCParams(scenario_id=scenario_id, enabled=payload.enabled, params=clean))
        await session.commit()
        return await _cashflow_budget_payload(session, scenario)


# ─── Panorama fiscal (D2) ─────────────────────────────────────────────────────
_TAX_DEFAULTS = {"wh_rate": 0.025, "income_tax_rate": 0.30, "card_pct_rooms": 0.90,
                 "card_pct_fb": 0.70, "card_pct_spa": 0.80, "card_pct_tours": 0.75,
                 "card_pct_private_bar": 1.00, "card_pct_other": 0.60}


class TaxParamsPayload(BaseModel):
    wh_rate: Decimal = Decimal("0.025")
    income_tax_rate: Decimal = Decimal("0.30")
    card_pct_rooms: Decimal = Decimal("0.90")
    card_pct_fb: Decimal = Decimal("0.70")
    card_pct_spa: Decimal = Decimal("0.80")
    card_pct_tours: Decimal = Decimal("0.75")
    card_pct_private_bar: Decimal = Decimal("1.00")
    card_pct_other: Decimal = Decimal("0.60")


@router.get("/scenarios/{scenario_id}/tax/")
async def get_tax(scenario_id: str):
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        row = (await session.execute(
            select(TaxParams).where(TaxParams.scenario_id == scenario_id)
        )).scalar_one_or_none()
        params = dict(_TAX_DEFAULTS) if not row else {
            "wh_rate": float(row.wh_rate), "income_tax_rate": float(row.income_tax_rate),
            "card_pct_rooms": float(row.card_pct_rooms), "card_pct_fb": float(row.card_pct_fb),
            "card_pct_spa": float(row.card_pct_spa), "card_pct_tours": float(row.card_pct_tours),
            "card_pct_private_bar": float(row.card_pct_private_bar),
            "card_pct_other": float(row.card_pct_other),
        }
        monthly = await _monthly_results(session, scenario)
        ml = [{"month": m["month"],
               "lines": {ln.line_code: float(ln.amount_usd) for ln in m["lines"]}}
              for m in monthly]
        tax = calculate_tax(ml, params)
        return {"scenario_id": scenario_id, "year": scenario.year, "params": params, **tax}


@router.put("/scenarios/{scenario_id}/tax/params/")
async def upsert_tax_params(scenario_id: str, payload: TaxParamsPayload):
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        await _get_scenario_or_404(session, scenario_id)
        row = (await session.execute(
            select(TaxParams).where(TaxParams.scenario_id == scenario_id)
        )).scalar_one_or_none()
        if row:
            for k, v in payload.model_dump().items():
                setattr(row, k, v)
        else:
            session.add(TaxParams(scenario_id=scenario_id, **payload.model_dump()))
        await session.commit()
    return {"ok": True}


# ─── Owner report Excel export ────────────────────────────────────────────────
class OwnerKpis(BaseModel):
    occ_pct: float = 0.0
    adr: float = 0.0
    revpar: float = 0.0
    pax: float = 0.0


class OwnerPLRow(BaseModel):
    label: str
    value: float = 0.0
    strong: bool = False


class OwnerNote(BaseModel):
    section: str = ""
    ref: str = ""
    month_name: str = ""
    body: str = ""


class OwnerReportPayload(BaseModel):
    scenario_label: str = ""
    kpis: OwnerKpis = OwnerKpis()
    pl_rows: list[OwnerPLRow] = []
    notes: list[OwnerNote] = []


@router.post("/scenarios/{scenario_id}/owner-report/excel/")
async def export_owner_report_excel(scenario_id: str, payload: OwnerReportPayload):
    """Format the on-screen owner report into a styled .xlsx (frontend supplies
    the already-computed numbers so the sheet matches the screen exactly)."""
    from app.export.owner_excel import export_owner_report_to_excel
    async with get_session() as session:
        await _get_scenario_or_404(session, scenario_id)
    xlsx = export_owner_report_to_excel(
        scenario_label=payload.scenario_label,
        kpis=payload.kpis.model_dump(),
        pl_rows=[r.model_dump() for r in payload.pl_rows],
        notes=[n.model_dump() for n in payload.notes],
    )
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="owner_report_{scenario_id}.xlsx"'},
    )


# ─── Recalculate everything ───────────────────────────────────────────────────
@router.post("/pl/{scenario_id}/recalculate/")
async def recalculate(scenario_id: str):
    async with get_session() as session:
        try:
            result = await recalc.recalculate_scenario(session, scenario_id)
        except ScenarioLockedError as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(404, str(e))
    return result


# ─── Versiones de Cash Flow presentadas a dueños (planas / congeladas) ─────────
@router.get("/cashflow-versions/")
async def list_cashflow_versions(hotel_id: str = Query(HOTEL_ID)):
    from app.models.cashflow_version import CashFlowVersion
    async with get_session() as session:
        rows = (await session.execute(select(CashFlowVersion).where(
            CashFlowVersion.hotel_id == hotel_id).order_by(
            CashFlowVersion.order_idx, CashFlowVersion.created_at))).scalars().all()
        return [{"id": v.id, "name": v.name, "kind": getattr(v, "kind", "frozen"),
                 "order_idx": v.order_idx, "n_rows": len(v.rows or []),
                 "created_at": v.created_at.isoformat() if v.created_at else None}
                for v in rows]


@router.get("/cashflow-versions/{version_id}/")
async def get_cashflow_version(version_id: str):
    from app.models.cashflow_version import CashFlowVersion
    async with get_session() as session:
        v = await session.get(CashFlowVersion, version_id)
        if not v:
            raise ErrorApi(404, "version.no_encontrada")
        return {"id": v.id, "name": v.name, "kind": getattr(v, "kind", "frozen"),
                "order_idx": v.order_idx, "rows": v.rows or []}


@router.post("/cashflow-versions/working/")
async def create_working_version(scenario_id: str = Query(...), name: str = Query(...),
                                 order_idx: int = Query(99)):
    """Crea una versión WORKING = copia plana del Cash Flow del escenario (Forecast).
    Todas las líneas quedan editables e independientes del motor; el usuario la
    ajusta mes a mes."""
    from app.models.cashflow_version import CashFlowVersion
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        payload = await _cashflow_budget_payload(session, scenario)
        rows = [{"section": r["section"], "label": r["label"], "values": r["values"],
                 "full_year": r["full_year"],
                 "is_total": r["kind"] in ("subtotal", "subtotal_strong", "total", "total_strong")}
                for r in payload["rows"]]
        v = CashFlowVersion(hotel_id=scenario.hotel_id, name=name, kind="working",
                            order_idx=order_idx, rows=rows)
        session.add(v)
        await session.commit()
        await session.refresh(v)
        return {"id": v.id, "name": v.name, "kind": v.kind, "n_rows": len(rows)}


class CFVersionUpdate(BaseModel):
    name: str | None = None
    rows: list | None = None


@router.put("/cashflow-versions/{version_id}/", dependencies=[Depends(registro_de_subida)])
async def update_cashflow_version(version_id: str, payload: CFVersionUpdate):
    """Actualiza una versión (rows / nombre). Pensado para la WORKING editable."""
    from app.models.cashflow_version import CashFlowVersion
    async with get_session() as session:
        v = await session.get(CashFlowVersion, version_id)
        if not v:
            raise ErrorApi(404, "version.no_encontrada")
        if payload.name is not None:
            v.name = payload.name
        if payload.rows is not None:
            v.rows = payload.rows
        await session.commit()
        return {"id": v.id, "name": v.name, "n_rows": len(v.rows or [])}


@router.post("/cashflow-versions/import/", dependencies=[Depends(registro_de_subida)])
async def import_cashflow_version(
    file: UploadFile = File(...),
    name: str = Query(...),
    hotel_id: str = Query(HOTEL_ID),
    order_idx: int = Query(0),
    dry_run: bool = Query(False),
):
    """Sube un Excel de Cash Flow (Section·Description·Ene..Dic·Full Year) y lo
    guarda como versión plana congelada. dry_run=True solo devuelve el preview."""
    import io
    from app.importers.cashflow_version_importer import parse_cashflow_version
    from app.models.cashflow_version import CashFlowVersion
    try:
        rows = parse_cashflow_version(io.BytesIO(await file.read()))
    except Exception as e:  # noqa: BLE001
        raise ErrorApi(400, "excel.no_se_pudo_leer", detalle=str(e))
    if not rows:
        raise ErrorApi(400, "cashflow.excel_sin_filas")
    if dry_run:
        return {"name": name, "n_rows": len(rows), "rows": rows}
    async with get_session() as session:
        v = CashFlowVersion(hotel_id=hotel_id, name=name, order_idx=order_idx, rows=rows)
        session.add(v)
        await session.commit()
        await session.refresh(v)
        return {"id": v.id, "name": v.name, "n_rows": len(rows)}


@router.delete("/cashflow-versions/{version_id}/")
async def delete_cashflow_version(version_id: str):
    from sqlalchemy import delete
    from app.models.cashflow_version import CashFlowVersion
    async with get_session() as session:
        await session.execute(delete(CashFlowVersion).where(CashFlowVersion.id == version_id))
        await session.commit()
        return {"ok": True}
