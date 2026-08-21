"""Carga de los criterios del Cash Flow desde la base — el punto ÚNICO donde las
dos pantallas resuelven con qué números calculan.

Antes cada API armaba su propio diccionario: el indirecto mezclaba
`WC_MODEL_DEFAULTS` con lo guardado (en tres lugares distintos de `pl_api`), y el
directo heredaba a mano cinco claves bajo una condición frágil. Acá se resuelve
una sola vez y los dos motores reciben la misma resolución.

También vive acá la REGLA DE ESCENARIO VECINO. Los dos métodos cruzan el año
—los depósitos de estadías de enero entran en octubre del año anterior— y cada
uno elegía el escenario vecino con una regla distinta: el indirecto prefería el
FORECAST del año anterior y el BUDGET del siguiente; el directo prefería el
mismo tipo y la misma versión. Para un Budget 2027 eso podía significar que uno
mirara el Forecast 2026 y el otro el Budget 2026 — distinto revenue, distintos
depósitos, y ninguna pantalla lo decía.
"""
from __future__ import annotations

from sqlalchemy import select

from app.engine import cashflow_criterios as crit
from app.models.cashflow_directo_config import CashFlowDirectoConfig
from app.models.cashflow_wc_params import CashFlowWCParams
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.pl_manual_input import PLManualInput
from app.models.scenario import Scenario

# Tipo de escenario preferido para cada lado del cruce de año. Para el año que
# pasó, el forecast es la mejor foto de lo que realmente ocurrió; para el que
# viene, el presupuesto es lo único que hay.
PREFERENCIA_VECINO = {-1: "FORECAST", 1: "BUDGET"}


async def escenario_vecino(session, scenario, delta: int):
    """Escenario del año ±1 del mismo hotel. REGLA ÚNICA para los dos métodos."""
    objetivo = (scenario.year or 0) + delta
    if not objetivo:
        return None
    cands = (await session.execute(select(Scenario).where(
        Scenario.hotel_id == scenario.hotel_id,
        Scenario.year == objetivo))).scalars().all()
    if not cands:
        return None
    prefer = PREFERENCIA_VECINO.get(delta, scenario.type)
    # Orden de preferencia: el tipo que corresponde, después el forecast vigente,
    # después la versión «Working» —que es la viva, la que el owner edita— y por
    # último el id, para que el desempate sea DETERMINISTA. Sin ese último
    # criterio dos deploys podían elegir escenarios distintos, porque la consulta
    # no trae orden garantizado.
    def _rango(c):
        return (c.type == prefer,
                bool(getattr(c, "is_current_forecast", False)),
                (c.version or "").strip().lower() == "working")
    cands.sort(key=lambda c: (_rango(c), c.id), reverse=True)
    return cands[0]


async def _aguinaldo_de_planilla(session, scenario) -> list[float] | None:
    """Aguinaldo provisionado por mes según la planilla REAL del escenario.
    None si el escenario no tiene detalle de planilla (p.ej. actuals por
    snapshot) → se usa el monto fijo de los Criterios como respaldo."""
    filas = (await session.execute(select(PayrollConceptEntry).where(
        PayrollConceptEntry.scenario_id == scenario.id))).scalars().all()
    out = [0.0] * 12
    for f in filas:
        if 1 <= (f.month or 0) <= 12:
            out[f.month - 1] += float(f.c6021_aguinaldo or 0)
    return out if any(abs(v) > 0.005 for v in out) else None


async def _honorarios_del_pl(session, scenario_id) -> float | None:
    """% de honorarios de administración configurado en el P&L (mgmt fee 3% +
    royalties). El directo lo tenía en un 5% fijo propio mientras el P&L usaba
    3%: el mismo concepto daba $299,867 en una pantalla y $179,920 en la otra."""
    filas = (await session.execute(select(PLManualInput).where(
        PLManualInput.scenario_id == scenario_id))).scalars().all()
    if not filas:
        return None
    return sum(float(f.mgmt_fee_pct_3 or 0) + float(f.mgmt_fee_pct_5 or 0)
               for f in filas) / len(filas)


async def cargar_criterios(session, scenario) -> tuple[dict, list[dict]]:
    """Devuelve (criterios efectivos, avisos).

    Los avisos son problemas de configuración que hay que ver en pantalla, no
    tapar en el motor: criterios compartidos que quedaron distintos entre las dos
    pantallas, y filas de la matriz de timing que no reparten el 100%.
    """
    wc = (await session.execute(select(CashFlowWCParams).where(
        CashFlowWCParams.scenario_id == scenario.id))).scalar_one_or_none()
    wc_params = {k: v for k, v in ((wc.params or {}) if wc else {}).items()
                 if k != "_overrides"}
    wc_enabled = bool(wc.enabled) if wc else False

    cfg = await session.get(CashFlowDirectoConfig, scenario.id)
    directo_params = (cfg.params if cfg else None) or {}

    extras: dict = {}
    ser = await _aguinaldo_de_planilla(session, scenario)
    if ser is not None:
        extras["aguinaldo_series"] = ser
    hon = await _honorarios_del_pl(session, scenario.id)
    if hon is not None:
        extras["honorarios_pct"] = hon

    c = crit.resolver(wc_enabled=wc_enabled, wc_params=wc_params,
                      directo_params=directo_params, extras=extras)

    avisos = [{"tipo": "criterio_divergente", **d}
              for d in crit.divergencias(c, wc_params, directo_params)]
    return c, avisos


async def series_pl(session, scn) -> tuple[list[float], list[float], list[float], list[float]]:
    """(revenue, costos operativos, A&B, capex) por mes de un escenario.

    Es la MISMA lectura para los dos métodos: `costos` es la base devengada
    completa —`TOTAL_OPEXP + TOTAL_OVERHEAD + TOTAL_NON_OP`— o sea que incluye la
    planilla, el alquiler, el honorario de administración, el seguro y los otros
    gastos below-GOP. Antes el flujo directo armaba su propia base sumando líneas
    sueltas y dejaba afuera todo el bloque non-op.
    """
    from app.engine import recalculate as recalc
    rev, cost, fb, capex = [0.0] * 12, [0.0] * 12, [0.0] * 12, [0.0] * 12
    for m in range(1, 13):
        i = m - 1
        for ln in await recalc.compute_pl_month(session, scn, m):
            code, amt = (ln.line_code or ""), float(ln.amount_usd or 0)
            if code == "TOTAL_REVENUES":
                rev[i] = amt
            elif code in ("TOTAL_OPEXP", "TOTAL_OVERHEAD", "TOTAL_NON_OP"):
                cost[i] += amt
            elif code == "REV_FB":
                fb[i] = amt
            elif code == "CAPITAL_EXPENSE":
                capex[i] = amt
    return rev, cost, fb, capex


async def payroll_series(session, scenario) -> list[float]:
    """Planilla total (USD) por mes. Solo se usa para SACARLA de la base de A/P e
    IVA cuando la planilla NO es tercerizada (`payroll_outsourced=False`)."""
    from app.engine import recalculate as recalc
    out = []
    for m in range(1, 13):
        d = await recalc.payroll_by_dept(session, scenario.id, m)
        out.append(float(sum(d.values())))
    return out


async def ventana_wc(session, scenario) -> tuple[dict, dict]:
    """Ventana de años vecinos para el modelo de timing — LA MISMA para los dos.

    Devuelve (ventana, integrado). La matriz de cobro alcanza 4 meses antes y 1
    después, así que sin los años vecinos los depósitos de las estadías de enero
    (que entraron en octubre del año anterior) y el 40% de la factura de
    diciembre se pierden o se inventan.
    """
    prev = await escenario_vecino(session, scenario, -1)
    nxt = await escenario_vecino(session, scenario, +1)
    if prev is None and nxt is None:
        return {}, {"prior": None, "next": None}
    pr = await series_pl(session, prev) if prev is not None else (None, None, None, None)
    nx = await series_pl(session, nxt) if nxt is not None else (None, None, None, None)
    ventana = {"prior_rev": pr[0], "prior_costs": pr[1], "prior_fb": pr[2],
               "next_rev": nx[0], "next_costs": nx[1], "next_fb": nx[2]}
    integrado = {
        "prior": {"id": prev.id, "year": prev.year, "type": prev.type,
                  "version": prev.version} if prev else None,
        "next": {"id": nxt.id, "year": nxt.year, "type": nxt.type,
                 "version": nxt.version} if nxt else None,
    }
    return ventana, integrado


async def cargar_overrides_wc(session, scenario_id) -> dict:
    """Los `_overrides` (copia editable de los reales de meses cerrados) viven
    dentro del mismo blob que los criterios, pero NO son un criterio."""
    wc = (await session.execute(select(CashFlowWCParams).where(
        CashFlowWCParams.scenario_id == scenario_id))).scalar_one_or_none()
    return ((wc.params or {}) if wc else {}).get("_overrides") or {}
