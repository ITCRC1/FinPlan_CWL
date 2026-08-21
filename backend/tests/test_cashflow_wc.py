"""
Tests del motor de Working Capital / Cash Flow (cashflow_budget.py).

Cubren las propiedades críticas del modelo de timing CR (documentadas como las
que más fácil se rompen): partidas WC completas, Deposits Applied = mezcla
negativa, aguinaldo que netea a 0 en el año, IVA SIMÉTRICO (Δ del saldo por
pagar, sin max(0) → respeta créditos), retención que solo desplaza timing, y
base de costos según planilla tercerizada vs interna.
"""
from app.engine.cashflow_budget import (
    wc_schedule, compute_wc_model, wc_cost_base, wc_breakdown,
    project_balance_sheet, compute_cashflow_budget, overrides_from_version_rows,
    WC_MODEL_DEFAULTS,
)


def _monthly_min():
    return {m: {"TOTAL_REVENUES": 100000.0, "TOTAL_OPEXP": -60000.0, "TOTAL_OVERHEAD": 0.0,
                "TOTAL_NON_OP": 0.0, "NET_PROFIT": 0.0, "REV_FB": 10000.0} for m in range(1, 13)}


def test_overrides_from_version_maps_wc_only():
    """Mapea labels de la versión congelada a row_keys de WC; ignora totales y
    secciones no-WC (CapEx invierte signo, no se copia)."""
    vrows = [
        {"section": "WORKING CAPITAL", "label": "Deposits Received", "values": [539359, 511902, 507668, 221966, 134474] + [0] * 7, "is_total": False},
        {"section": "WORKING CAPITAL", "label": "Subtotal #3", "values": [0] * 12, "is_total": True},
        {"section": "CAPEX", "label": "Capital Expenditures – New", "values": [-19146] + [0] * 11, "is_total": False},
    ]
    ov, mapped, skipped = overrides_from_version_rows(vrows, [1, 2, 3, 4, 5])
    assert "WC_DEP_RECV" in ov and ov["WC_DEP_RECV"]["1"] == 539359.0
    assert mapped == ["Deposits Received"]            # total y CapEx ignorados
    assert "WC_DEP_APPL" not in ov


def test_overrides_pin_jan_may_model_runs_jun_dec():
    """Override Ene–May pisa al modelo en esos meses; Jun–Dic siguen del modelo."""
    ov = {"WC_DEP_RECV": {"1": 539359.0, "2": 511902.0, "3": 507668.0, "4": 221966.0, "5": 134474.0}}
    wc_model = {"enabled": True, "params": dict(WC_MODEL_DEFAULTS)}
    cf = compute_cashflow_budget(_monthly_min(), {}, 100000.0, wc_model=wc_model, wc_overrides=ov)
    dep = {r["key"]: r for r in cf["rows"]}["WC_DEP_RECV"]
    assert dep["values"][:5] == [539359.0, 511902.0, 507668.0, 221966.0, 134474.0]
    assert dep["override_months"] == [1, 2, 3, 4, 5]
    # sin override, ese mismo mes da el valor del modelo (distinto de los reales)
    base = compute_cashflow_budget(_monthly_min(), {}, 100000.0, wc_model=wc_model)
    base_dep = {r["key"]: r for r in base["rows"]}["WC_DEP_RECV"]
    assert base_dep["values"][0] != 539359.0
    assert "override_months" not in base_dep          # backward-compatible


def test_overrides_none_is_identical():
    """Sin overrides el resultado es idéntico (backward-compatible)."""
    wc_model = {"enabled": True, "params": dict(WC_MODEL_DEFAULTS)}
    a = compute_cashflow_budget(_monthly_min(), {}, 100000.0, wc_model=wc_model)
    b = compute_cashflow_budget(_monthly_min(), {}, 100000.0, wc_model=wc_model, wc_overrides={})
    assert [r["values"] for r in a["rows"]] == [r["values"] for r in b["rows"]]

REV = [100000.0] * 12
COST = [60000.0] * 12


def _params(**over):
    p = dict(WC_MODEL_DEFAULTS)
    p["mix_flex"] = list(WC_MODEL_DEFAULTS["mix_flex"])
    p.update(over)
    return p


def test_compute_wc_model_keys_and_length():
    out = compute_wc_model(REV, COST, _params())
    for k in ("WC_DEP_RECV", "WC_DEP_APPL", "WC_AR", "WC_AP",
              "WC_PROV", "WC_TAX", "WC_RENTTAX"):
        assert k in out, f"falta partida {k}"
        assert len(out[k]) == 12, f"{k} debe tener 12 meses"


def test_deposits_applied_is_negative_mix():
    """WC_DEP_APPL = -(NRR+Flex) del mes (anticipos consumidos al hospedarse)."""
    p = _params()
    s = wc_schedule(REV, COST, p)
    for t in range(12):
        expected = -(p["mix_nrr"] * REV[t] + s["flex"][t])
        assert abs(s["WC_DEP_APPL"][t] - expected) < 1e-6


def test_aguinaldo_provision_nets_to_zero_over_year():
    """Se acumula cada mes y se paga todo en el mes de pago → suma anual = 0."""
    s = wc_schedule(REV, COST, _params(aguinaldo_monthly=8300.0, aguinaldo_pay_month=12))
    assert abs(sum(s["WC_PROV"][:12])) < 1e-6


def test_iva_is_symmetric_telescoping():
    """Suma de WC_TAX = saldo de IVA por pagar del último mes (Δ telescópico)."""
    s = wc_schedule(REV, COST, _params())
    assert abs(sum(s["WC_TAX"]) - s["iva_net"][-1]) < 1e-6


def test_el_credito_de_iva_se_arrastra_no_se_devuelve():
    """Mes con costo > ventas → saldo a FAVOR. Hacienda no lo devuelve en
    efectivo: se acumula y se aplica contra el impuesto de los meses siguientes.

    El modelo viejo hacía `wc_tax = Δ(payable)` con payable negativo, y restar un
    negativo es sumar caja: en los meses de crédito aparecía una ENTRADA de plata
    que nunca ocurre."""
    s = wc_schedule([10000.0] * 12, [50000.0] * 12, _params())
    # Lo que se declara nunca es negativo…
    assert min(s["iva_net"]) == 0
    # …y el saldo a favor crece mes a mes en vez de cobrarse.
    assert s["iva_credito"][-1] > s["iva_credito"][0] > 0
    # Ningún mes trae plata de vuelta por IVA.
    assert max(s["WC_TAX"]) <= 0.005


def test_retention_shifts_timing_not_total():
    """La retención de anticipos solo desplaza el timing: baja la recepción del
    mes y la libera el siguiente; no cambia materialmente el total."""
    s0 = wc_schedule(REV, COST, _params(retention=0.0))
    s1 = wc_schedule(REV, COST, _params(retention=0.05))
    assert s1["WC_DEP_RECV"] != s0["WC_DEP_RECV"]               # cambia el timing
    assert s1["WC_DEP_RECV"][0] < s0["WC_DEP_RECV"][0]          # retiene el 1er mes
    diff = sum(s1["WC_DEP_RECV"]) - sum(s0["WC_DEP_RECV"])
    assert diff <= 1e-6                                          # neto ≤ 0 (solo el último retenido no se libera)


def test_wc_cost_base_outsourced_vs_internal():
    """Planilla tercerizada (default) entra entera a A/P+IVA; interna se resta."""
    costs = [1000.0] * 12
    payroll = [400.0] * 12
    assert wc_cost_base(costs, payroll, _params(payroll_outsourced=True)) == costs
    base_in = wc_cost_base(costs, payroll, _params(payroll_outsourced=False))
    assert all(abs(v - 600.0) < 1e-6 for v in base_in)


def test_mix_flex_blindado_ante_lista_mala():
    """Si mix_flex llega mal formado, el motor usa el default sin crashear."""
    s = wc_schedule(REV, COST, _params(mix_flex=[0.3]))   # lista incompleta
    assert len(s["WC_DEP_RECV"]) == 12


def test_project_balance_sheet_runs():
    """Smoke test: la proyección a 24 meses corre y devuelve un dict no vacío."""
    out = project_balance_sheet(REV, COST, _params(), months=24)
    assert isinstance(out, dict) and out


def test_wc_cross_year_window():
    """Continuidad de WC en el cruce de año: con next_rev, los anticipos de las
    estadías del año siguiente caen en este año (Dic), y sin ventana el
    comportamiento es idéntico al de 12 meses aislados (backward-compatible)."""
    from app.engine.cashflow_budget import compute_wc_model, WC_MODEL_DEFAULTS
    rev_this = [100.0] * 12
    rev_next = [600.0] + [100.0] * 11        # Enero del año siguiente, grande
    p = dict(WC_MODEL_DEFAULTS)
    base = compute_wc_model(rev_this, [0.0] * 12, p)                       # aislado
    win = compute_wc_model(rev_this, [0.0] * 12, p,
                           next_rev=rev_next, next_costs=[0.0] * 12)       # integrado
    # sin ventana == comportamiento de siempre
    assert compute_wc_model(rev_this, [0.0] * 12, p) == base
    # Dic recibe MÁS con la ventana (el anticipo de Enero del año siguiente)
    assert win["WC_DEP_RECV"][11] > base["WC_DEP_RECV"][11] + 100
    # Applied (consumo del mes) NO cambia: depende de la venta del mes, no del cruce
    assert abs(win["WC_DEP_APPL"][5] - base["WC_DEP_APPL"][5]) < 0.01


def test_fb_service_charge_pass_through():
    """10% de servicio de A&B (plata de empleados): se COBRA con la venta de A&B
    (entra) y se PAGA el mes siguiente (sale) → pasivo 'Servicio por pagar'.
    Con A&B constante, cada mes neto 0 salvo el float que arranca en Ene."""
    p = _params(service_rate=0.10, service_lag=1)
    fb = [1000.0] * 12
    s = wc_schedule(REV, COST, p, fb=fb)
    assert "WC_SERVICE" in s and len(s["WC_SERVICE"]) == 12
    # Cobro = 10% del A&B; pago = cobro del mes anterior (lag 1)
    assert abs(s["svc_collected"][3] - 100.0) < 1e-6
    assert abs(s["svc_paid"][3] - 100.0) < 1e-6          # paga el de marzo
    assert abs(s["svc_paid"][0] - 0.0) < 1e-6            # enero no paga nada antes
    # El float anual = 1 mes (lo cobrado en el último mes, pagado el año siguiente)
    assert abs(sum(s["WC_SERVICE"]) - 100.0) < 1e-6
    # Sin fb → la partida existe pero es 0 (backward-compatible)
    s0 = wc_schedule(REV, COST, p)
    assert all(abs(x) < 1e-9 for x in s0["WC_SERVICE"])


def test_wc_breakdown_sums_to_total():
    """El drill-down de cada partida WC: las componentes suman EXACTO el valor de
    la celda (check == total) para todas las partidas, y Deposits Received lista
    los anticipos de los meses futuros que lo forman."""
    p = _params()
    lf = lambda gi: f"M{gi}"
    fb = [10000.0] * 12
    s = wc_schedule(REV, COST, p, fb=fb)
    for key in ("WC_DEP_RECV", "WC_DEP_APPL", "WC_AR", "WC_AP", "WC_PROV",
                "WC_TAX", "WC_RENTTAX", "WC_SERVICE"):
        for t in (0, 5, 11):
            bd = wc_breakdown(REV, COST, p, key, t, lf, fb=fb)
            assert abs(bd["check"] - bd["total"]) < 0.02, f"{key}[{t}] no cuadra"
            assert abs(bd["total"] - round(s[key][t], 2)) < 0.02
    # Deposits Received de un mes lista anticipos de estadías futuras
    bd = wc_breakdown(REV, COST, p, "WC_DEP_RECV", 3, lf, fb=fb)
    assert any("Anticipo de estadía" in pt["label"] for pt in bd["parts"])


def test_capex_reduces_cash():
    """Projects/CapEx es SALIDA: un gasto positivo REBAJA la caja (no la favorece).
    Sin CapEx la caja final = opening; con 90.000 en enero baja a opening−90.000."""
    monthly = {m: {"TOTAL_REVENUES": 0.0, "TOTAL_OPEXP": 0.0,
                   "TOTAL_OVERHEAD": 0.0, "TOTAL_NON_OP": 0.0,
                   "NET_PROFIT": 0.0, "REV_FB": 0.0} for m in range(1, 13)}
    base = compute_cashflow_budget(monthly, {}, 100000.0)
    ending = {r["key"]: r for r in base["rows"]}["ENDING_CASH"]
    assert ending["values"][0] == 100000.0           # sin gasto, caja intacta

    capex = [90000.0] + [0.0] * 11
    cf = compute_cashflow_budget(monthly, {"CAPEX_PREV": capex}, 100000.0)
    rows = {r["key"]: r for r in cf["rows"]}
    assert rows["SUBTOTAL_CAPEX"]["values"][0] == 90000.0     # el subtotal muestra el gasto
    assert rows["ENDING_CASH"]["values"][0] == 10000.0       # PERO la caja baja 90.000


def test_fb_service_cross_year_nets_to_zero():
    """Con la ventana de cruce de año (prior_fb), enero paga el A&B de diciembre
    del año anterior → el servicio netea a 0 sobre un año de A&B constante."""
    p = _params(service_rate=0.10, service_lag=1)
    fb = [1000.0] * 12
    win = compute_wc_model(REV, COST, p, prior_rev=REV, prior_costs=COST,
                           fb_rev=fb, prior_fb=fb)
    assert abs(win["WC_SERVICE"][0]) < 1e-6      # enero: cobra y paga el dic anterior
    assert abs(sum(win["WC_SERVICE"])) < 1e-6    # steady state → neto 0
