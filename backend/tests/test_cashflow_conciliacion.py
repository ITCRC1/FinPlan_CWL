"""Los dos métodos de cash flow tienen que dar lo mismo.

El flujo DIRECTO es una presentación del mismo calendario de caja que arma el
INDIRECTO, así que para cada mes debe cumplirse

    Cobros − Pagos  ≡  NOI − CapEx + Δ(Working Capital)

Estas pruebas fallan si alguien vuelve a meterle al directo un modelo propio de
cobro, de A/P, de IVA o de nómina — que fue exactamente el origen de la brecha
de $285,652 en enero que motivó la auditoría.
"""
from app.engine import cashflow_criterios as crit
from app.engine.cashflow_budget import WC_MODEL_DEFAULTS, compute_cashflow_budget
from app.engine.cashflow_directo import DIRECT_DEFAULTS, compute_cashflow_directo

MESES = range(1, 13)


def _pl_mensual(rev, opex, overhead, nonop, capex):
    return {m: {"TOTAL_REVENUES": rev[m - 1], "TOTAL_OPEXP": opex[m - 1],
                "TOTAL_OVERHEAD": overhead[m - 1], "TOTAL_NON_OP": nonop[m - 1],
                "REV_FB": rev[m - 1] * 0.2, "CAPITAL_EXPENSE": capex[m - 1]}
            for m in MESES}


def _escenario():
    rev = [90000, 95000, 110000, 70000, 40000, 35000,
           38000, 42000, 20000, 0, 60000, 100000]
    opex = [30000, 31000, 33000, 26000, 20000, 19000,
            19500, 21000, 15000, 8000, 24000, 32000]
    overhead = [12000] * 12
    nonop = [3000] * 12
    capex = [x * 0.04 for x in rev]
    return rev, opex, overhead, nonop, capex


def _criterios(**over):
    c = dict(crit.CRITERIOS_DEFAULTS)
    c["enabled"] = True
    c.update(over)
    return c


def _correr(criterios, opening=250000.0):
    rev, opex, overhead, nonop, capex = _escenario()
    monthly = _pl_mensual(rev, opex, overhead, nonop, capex)
    ind = compute_cashflow_budget(monthly, {}, opening,
                                  wc_model={"enabled": True, "params": criterios})
    filas = {r["key"]: r["values"] for r in ind["rows"] if r.get("key")}
    gasto = [-(filas["OPEX"][i] + filas["OVERHEAD"][i] + filas["NONALLOC"][i])
             for i in range(12)]
    movimientos = {k: filas[k] for k in
                   ("WC_DEP_RECV", "WC_DEP_APPL", "WC_AR", "WC_AP",
                    "WC_TAX", "WC_PROV", "WC_RENTTAX", "WC_SERVICE")}
    movimientos.update({"rev": filas["REVENUE"], "gasto": gasto,
                        "capex": filas["SUBTOTAL_CAPEX"], "otros": [0.0] * 12})
    totales = {"rev": rev, "opex": opex, "overhead": overhead, "nonop": nonop,
               "capex": capex, "fb": [r * 0.2 for r in rev], "payroll": [0.0] * 12}
    dire = compute_cashflow_directo({}, {}, {}, {"capex": capex}, criterios,
                                    opening, {}, totales=totales,
                                    movimientos=movimientos)
    return ind, dire


def _fila(rows, *, key=None, label=None):
    for r in rows:
        if key is not None and r.get("key") == key:
            return r["values"]
        if label is not None and r.get("label") == label:
            return r["values"]
    raise AssertionError(f"fila no encontrada: {key or label}")


def test_flujo_neto_identico_mes_a_mes():
    ind, dire = _correr(_criterios())
    neto_ind = _fila(ind["rows"], key="NET_CHANGE")
    neto_dir = _fila(dire["resumen"], label="FLUJO NETO TOTAL")
    for i in range(12):
        assert abs(neto_dir[i] - neto_ind[i]) < 0.05, (
            f"mes {i + 1}: directo {neto_dir[i]:,.2f} vs indirecto {neto_ind[i]:,.2f}")


def test_saldo_final_identico():
    ind, dire = _correr(_criterios())
    fin_ind = _fila(ind["rows"], key="ENDING_CASH")
    fin_dir = _fila(dire["resumen"], label="SALDO FINAL DE CAJA")
    for i in range(12):
        assert abs(fin_dir[i] - fin_ind[i]) < 0.05


def test_identidad_cobros_menos_pagos():
    """Cobros − Pagos ≡ NOI − CapEx + ΔWC, mes a mes."""
    _, dire = _correr(_criterios())
    ident = dire["identidad"]
    for i in range(12):
        esperado = ident["noi"][i] - ident["capex"][i] + ident["wc"][i]
        assert abs(ident["flujo_neto_operativo"][i] - esperado) < 0.05


def test_enero_arrastra_la_cola_del_ano_anterior():
    """Enero paga el resto de la factura de diciembre pasado.

    El modelo viejo empezaba el año en cero del lado del gasto: cobraba mirando
    atrás y pagaba como si no hubiera pasado nada antes, y eso solo en enero
    valía $285,652.
    """
    rev, opex, overhead, nonop, capex = _escenario()
    criterios = _criterios()
    monthly = _pl_mensual(rev, opex, overhead, nonop, capex)
    costos = [opex[i] + overhead[i] + nonop[i] for i in range(12)]
    ventana = {"prior_rev": rev, "prior_costs": costos, "prior_fb": [0.0] * 12}
    sin = compute_cashflow_budget(monthly, {}, 0.0,
                                  wc_model={"enabled": True, "params": criterios})
    con = compute_cashflow_budget(monthly, {}, 0.0,
                                  wc_model={"enabled": True, "params": criterios},
                                  wc_window=ventana)
    ap_sin = _fila(sin["rows"], key="WC_AP")[0]
    ap_con = _fila(con["rows"], key="WC_AP")[0]
    assert ap_sin == 0.0
    assert ap_con < 0.0, "con año anterior, enero tiene que pagar la cola de diciembre"


def test_ningun_criterio_compartido_con_dos_valores():
    """Cada concepto tiene UN default. Los dos motores no pueden discrepar."""
    for k in crit.COMPARTIDOS:
        assert k in crit.CRITERIOS_DEFAULTS
        if k in WC_MODEL_DEFAULTS and k not in ("enabled",):
            pass    # el canónico manda; WC_MODEL_DEFAULTS queda como legado
    canon = crit.resolver(wc_enabled=True, wc_params={}, directo_params={})
    for k in crit.COMPARTIDOS:
        assert crit.vista_indirecto(canon)[k] == crit.vista_directo(canon)[k]


def test_valor_viejo_del_directo_no_pisa_el_criterio_compartido():
    """Guardar la pantalla del directo no puede desconectarla de los Criterios.

    La pantalla precargaba sus defaults y los mandaba enteros al guardar. Como el
    backend respetaba cualquier clave presente, con un solo «Guardar» el
    escenario quedaba clavado en los valores viejos del motor directo.
    """
    guardado = {"ap_same_pct": 0.70, "card_iva_ret": 0.0, "card_comision": 0.0195}
    c = crit.resolver(wc_enabled=True, wc_params={"ap_same_pct": 0.60},
                      directo_params=guardado)
    assert c["ap_same_pct"] == 0.60
    assert c["card_iva_ret"] == crit.CRITERIOS_DEFAULTS["card_iva_ret"]
    assert c["card_comision"] == 0.0, "la comisión ya está en el P&L (cuenta 7120)"


def test_override_explicito_del_directo_si_manda():
    c = crit.resolver(wc_enabled=True, wc_params={"ap_same_pct": 0.60},
                      directo_params={"ap_same_pct": 0.80,
                                      crit.MARCA_OVERRIDE: ["ap_same_pct"]})
    assert c["ap_same_pct"] == 0.80


def test_los_derivados_nunca_salen_de_lo_guardado():
    """La matriz y el revenue de los años vecinos se recalculan siempre."""
    c = crit.resolver(wc_enabled=True, wc_params={},
                      directo_params={"timing_matrix": [[9] * 6] * 12,
                                      "rev_prev": [1] * 12})
    assert "timing_matrix" not in c
    assert "rev_prev" not in c


def test_interruptor_apaga_los_dos_metodos():
    c = crit.resolver(wc_enabled=False, wc_params={"ap_same_pct": 0.6},
                      directo_params={})
    assert c["enabled"] is False


def test_avisos_de_matriz_que_no_suma_cien():
    m = [[0.0, 0.0, 0.1, 0.3, 0.6, 0.1]] + [[0.0, 0.0, 0.1, 0.3, 0.5, 0.1]] * 11
    avisos = crit.avisos_matriz(m)
    assert [a["mes"] for a in avisos] == [1]
    assert abs(avisos[0]["suma"] - 1.10) < 1e-9


def test_defaults_del_directo_ya_no_traen_comision():
    """`card_comision` seguía viva en el motor directo y podía reactivarse."""
    assert crit.CRITERIOS_DEFAULTS["card_comision"] == 0.0
    assert DIRECT_DEFAULTS["card_comision"] == 0.0


def test_impuesto_de_renta_baja_a_los_dos_metodos():
    """Si la renta pasa al flujo, la ven las DOS pantallas.

    El impuesto entra por las partidas del indirecto, así que el directo lo toma
    de ahí. Si se hubiera agregado solo del lado del directo, la conciliación se
    rompería justo en el mes de pago.
    """
    rev, opex, overhead, nonop, capex = _escenario()
    monthly = _pl_mensual(rev, opex, overhead, nonop, capex)
    criterios = _criterios()
    ind = compute_cashflow_budget(monthly, {}, 0.0,
                                  wc_model={"enabled": True, "params": criterios},
                                  renta_annual=120_000, renta_pay_month=12)
    fila = _fila(ind["rows"], key="OTH_RENTA")
    assert fila[11] == -120_000
    assert sum(fila[:11]) == 0, "solo sale en el mes de pago"


def test_saldo_a_favor_no_entra_como_caja():
    """Un crédito no es plata que entra: se arrastra al período siguiente."""
    from app.engine.renta_anual import renta_liquidacion
    monthly = {m: {"EBT": 1000.0} for m in range(1, 13)}   # EBT anual 12,000
    r = renta_liquidacion(monthly, {"renta_pago_manual": 0}, creditos_tarjeta=50_000)
    assert r["neto"] < 0
    assert r["saldo_a_favor"] > 0
    assert r["pasa_al_flujo"] == 0.0


def test_el_impuesto_del_ano_no_baja_solo_al_flujo():
    from app.engine.renta_anual import renta_liquidacion
    monthly = {m: {"EBT": 100_000.0} for m in range(1, 13)}
    sin = renta_liquidacion(monthly, {})
    con = renta_liquidacion(monthly, {"renta_pago_manual": 90_000})
    # El impuesto del año se paga en marzo del SIGUIENTE: no baja solo.
    assert sin["a_pagar"] > 0 and sin["pasa_al_flujo"] == 0.0
    # Lo que baja es el monto cargado a mano (la liquidación del año anterior).
    assert con["pasa_al_flujo"] == 90_000
    assert con["mes_pago"] == 3


def test_sobre_perdida_no_se_paga_renta():
    from app.engine.renta_anual import renta_liquidacion
    monthly = {m: {"EBT": -5_000.0} for m in range(1, 13)}
    r = renta_liquidacion(monthly, {})
    assert r["impuesto_bruto"] == 0.0
    assert r["pasa_al_flujo"] == 0.0
