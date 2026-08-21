"""Cash Flow — MÉTODO DIRECTO (replica del modelo Excel del owner "Flujo de Caja
MD" + auxiliares). Puro. Devuelve el DETALLE COMPLETO por línea/departamento como
el Excel (cada ingreso con su IVA, OPEX por depto, nómina por depto, sub-filas de
gastos propiedad, IVA por concepto) + el resumen del flujo directo.

Recibe datos POR LÍNEA/DEPTO (dicts {etiqueta: [12]}), no agregados — la API los
arma del P&L.

Portado de Luz de Mono (engine/cashflow_direct.py). El formato es idéntico; el
enlace a los datos reales del P&L de CWL se hace en la API que lo alimenta.
"""
from __future__ import annotations


def _mul(a, k):
    return [x * k for x in a]


def _lag(a, n=1):
    return [(a[i - n] if i - n >= 0 else 0.0) for i in range(12)]


DIRECT_DEFAULTS = {
    "iva_rate": 0.13,
    "credit_pct": 0.0,        # % del ingreso cobrado a 1 mes (crédito); resto contado
    "card_pct": 0.70,         # % del cobro por tarjeta
    "card_renta_ret": 0.025,  # retención renta sobre cobro tarjeta
    "card_iva_ret": 0.025,    # retención IVA sobre cobro tarjeta (crédito mes sig.)
    "card_comision": 0.0,     # ya está en el P&L (7120): cobrarla acá era doble conteo
    "ap_same_pct": 0.60,      # proveedores: % pagado el mismo mes (resto mes sig.)
    "honorarios_pct": 0.05,   # honorarios adm = % de ventas (mes sig.)
    "ccss_rate": 0.2683,      # CCSS patronal
    "retencion_rate": 0.0,    # retención de renta empleados
    "seguros_pay_months": [6, 12],
    "iva_lag": 1,
    "aguinaldo_pay_month": 12,
}


def _p(params, k):
    v = (params or {}).get(k)
    return v if v is not None else DIRECT_DEFAULTS.get(k)


# Ayuda por fila: {label: (de_donde, formula)}. La llena `ayuda_cashflow.py` y se
# adjunta a cada fila para que la pantalla pueda explicar de dónde sale el número
# cuando el usuario hace clic. Un cuadro financiero sin trazabilidad obliga a
# preguntar; con esto la respuesta está al lado del número.
from app.engine.ayuda_cashflow import AYUDA
from app.engine.etiquetas_cashflow import ETIQUETAS


def _row(label, values, kind="data", key=None, editable=False, saldo=None,
         ayuda=None, label_params=None):
    # Los SALDOS no se suman: el del año es el de un mes puntual. La columna
    # «Año» del saldo inicial mostraba la suma de los doce saldos mensuales
    # —$18,978,959 cuando la caja inicial son $250,000— y el saldo final
    # arrastraba el mismo error. `saldo` dice qué mes vale: 0 = enero (inicial),
    # -1 = diciembre (final).
    anual = round(values[saldo], 2) if (saldo is not None and values) else round(sum(values), 2)
    d = {"label": label, "values": [round(v, 2) for v in values],
         "full_year": anual, "kind": kind}
    # El rótulo sigue viajando —es el respaldo y lo que usan las filas por
    # departamento, que se rotulan con DATO de la base— y además viaja su clave
    # cuando es una etiqueta fija de la pantalla. La pantalla prefiere el
    # catálogo y cae al `label` si no hay clave. Ver `etiquetas_cashflow.py`.
    lk = ETIQUETAS.get(label.strip())
    if lk:
        d["label_key"] = lk
        # Los datos del rótulo viajan aparte: una TASA metida en el texto
        # («IVA COBRADO 13%») miente el día que alguien la mueve, y `iva_rate`
        # es un criterio editable.
        if label_params:
            d["label_params"] = label_params
    if key:
        d["key"] = key
    if editable:
        d["editable"] = True
    # ⚠️ Sale la CLAVE, no el texto. El motor no se entera del idioma —regla del
    # proyecto, vigilada por `tests/test_i18n_locale.py`— y la explicación en
    # español dentro de la respuesta lo violaba de hecho: con la app en inglés
    # la ayuda salía en español igual. El texto vive en el catálogo del
    # frontend (`cfdAyuda`), como el `line_code` del P&L.
    clave = ayuda or AYUDA.get(label.strip()) or AYUDA.get(label)
    if clave:
        d["ayuda"] = {"clave": clave}
    return d


# Filas MANUALES editables del resumen (Capital + Financiamiento + ajustes).
# sign: +1 = salida (resta al flujo), -1 = entrada (suma al flujo).
MANUAL_ROWS = [
    ("CAPITAL", [
        ("CAP_CAPEX", "Inversión / CapEx adicional", 1),
        ("CAP_RESERVA", "Reserva de reposición (FF&E)", 1),
        ("CAP_OTRO", "Otra inversión de capital", 1),
    ]),
    ("FINANCIAMIENTO", [
        ("FIN_PRESTAMO", "Préstamos recibidos (+)", -1),
        ("FIN_SERVICIO", "Servicio de deuda (amortización)", 1),
        ("FIN_INTERES", "Intereses", 1),
        ("FIN_DISTRIB", "Distribuciones / retiros", 1),
    ]),
    ("AJUSTES", [
        ("ADJ_ENTRADA", "Otras entradas manuales (+)", -1),
        ("ADJ_SALIDA", "Otras salidas manuales", 1),
    ]),
]
MANUAL_KEYS = {k for _, rows in MANUAL_ROWS for k, _, _ in rows}


def compute_cashflow_directo(revenue_lines: dict, opex_lines: dict, payroll_lines: dict,
                             prop: dict, params: dict | None = None,
                             opening_cash: float = 0.0, manual: dict | None = None,
                             totales: dict | None = None,
                             ventana: dict | None = None,
                             movimientos: dict | None = None) -> dict:
    """Flujo de caja por el método DIRECTO — cobros menos pagos.

    El cálculo NO es propio: sale de `wc_schedule_ventana`, el mismo calendario
    de capital de trabajo que usa el flujo indirecto. Este módulo solo lo
    PRESENTA al derecho —de la venta al cobro, del gasto al pago— en vez de
    presentarlo como ajustes sobre el resultado.

    Que los dos métodos den lo mismo deja así de ser una coincidencia que hay que
    perseguir con parámetros: es una identidad. Para cada mes,

        Cobros − Pagos  ≡  NOI − CapEx + Δ(Working Capital)

    porque los dos lados se arman con las mismas series. Lo que quede de
    diferencia son las filas MANUALES de cada pantalla, y esas se ven.

    Antes este motor tenía su propio modelo de cobro, su propia base de A/P, su
    propio IVA y su propia nómina reconstruida. De ahí salían las trece
    divergencias de la auditoría: no era un parámetro mal puesto, eran dos
    modelos distintos del mismo hotel.
    """
    from app.engine.cashflow_budget import wc_schedule_ventana, wc_cost_base

    p = params or {}
    manual = manual or {}
    tot = totales or {}
    v = ventana or {}

    def man(key):
        val = manual.get(key) or []
        return [float(val[i]) if i < len(val) and val[i] is not None else 0.0 for i in range(12)]

    iva = float(_p(p, "iva_rate"))
    rng = range(12)

    def total(d):
        return [sum(d[l][i] for l in d) for i in rng]

    def serie(clave, respaldo=None):
        s = tot.get(clave)
        if isinstance(s, list) and len(s) >= 12:
            return [float(x or 0) for x in s[:12]]
        return list(respaldo) if respaldo else [0.0] * 12

    # ── Devengado del P&L: la MISMA base que el indirecto ────────────────────
    # Ingreso = TOTAL_REVENUES · Costo = TOTAL_OPEXP + TOTAL_OVERHEAD + TOTAL_NON_OP.
    # El costo incluye la planilla completa, el alquiler, el honorario de
    # administración, el seguro y los otros gastos below-GOP: todo lo que el P&L
    # reconoce arriba del EBITDA. El modelo viejo armaba esta base sumando
    # líneas sueltas y dejaba el bloque non-op afuera.
    R = serie("rev", total(revenue_lines))
    C = [serie("opex")[i] + serie("overhead")[i] + serie("nonop")[i] for i in rng]
    capex = serie("capex", prop.get("capex"))
    fb = serie("fb")
    planilla = serie("payroll")

    # ── El calendario de caja, compartido ────────────────────────────────────
    C_modelo = wc_cost_base(C, planilla, p)
    s = wc_schedule_ventana(
        R, C_modelo, p,
        prior_rev=v.get("prior_rev"), prior_costs=v.get("prior_costs"),
        next_rev=v.get("next_rev"), next_costs=v.get("next_costs"),
        fb_rev=fb, prior_fb=v.get("prior_fb"), next_fb=v.get("next_fb"))

    iva_out, iva_in, iva_ret = s["iva_out"], s["iva_in"], s["iva_ret"]
    payable_prev = s["payable_prev"]

    # ── Los movimientos que MANDAN son los del flujo indirecto ───────────────
    # El calendario de arriba explica el detalle (cuánto es depósito, cuánto
    # IVA), pero la caja sale de las partidas finales de la otra pantalla. Eso
    # importa porque esas partidas no siempre vienen del modelo: en los meses
    # cerrados salen del Balance Sheet real, pueden estar pisadas a mano celda
    # por celda, o venir de un driver. Tomando el resultado final, los dos
    # métodos coinciden en TODOS los escenarios y no solo cuando el modelo de
    # timing está activo.
    mov = movimientos or {}

    def mv(clave, respaldo):
        val = mov.get(clave)
        if isinstance(val, list) and len(val) >= 12:
            return [float(x or 0) for x in val[:12]]
        return list(respaldo)

    dep_recv = mv("WC_DEP_RECV", s["WC_DEP_RECV"])
    dep_appl = mv("WC_DEP_APPL", s["WC_DEP_APPL"])
    ar_mov = mv("WC_AR", s["WC_AR"])
    ap_mov = mv("WC_AP", s["WC_AP"])
    prov_mov = mv("WC_PROV", s["WC_PROV"])
    renttax = mv("WC_RENTTAX", s["WC_RENTTAX"])
    servicio = mv("WC_SERVICE", s["WC_SERVICE"])
    wc_tax = mv("WC_TAX", s["WC_TAX"])
    if mov.get("gasto"):
        C = [float(x or 0) for x in mov["gasto"][:12]]
    if mov.get("rev"):
        R = [float(x or 0) for x in mov["rev"][:12]]
    if mov.get("capex"):
        capex = [float(x or 0) for x in mov["capex"][:12]]
    otros_mov = mv("otros", [0.0] * 12)
    renta_mov = mv("renta", [0.0] * 12)   # negativo = salida en su mes de pago

    cn = tot.get("conceptos") or {}

    def cs(clave):
        v = cn.get(clave)
        return [float(x or 0) for x in v[:12]] if isinstance(v, list) and len(v) >= 12 else [0.0] * 12

    # Retenciones que el adquirente descuenta al liquidar la tarjeta: la de IVA
    # y la de Renta, 2.5% cada una. No son pagos del hotel — son plata que no
    # llega — así que se restan del cobro, no se muestran como salidas.
    retenciones_tarjeta = [iva_ret[i] - renttax[i] for i in rng]

    # ═══ COBROS ═════════════════════════════════════════════════════════════
    # La venta del mes no es el cobro del mes: el huésped deja un depósito meses
    # antes y salda al llegar. Estas cuatro piezas suman exactamente el cobro
    # operativo del modelo.
    cobro_op = [R[i] + dep_recv[i] + dep_appl[i] + ar_mov[i] for i in rng]
    # ── Servicio 10% de A&B: las dos patas, no el neto ───────────────────────
    # Es el 10% de ley sobre la venta de A&B: se le cobra al huésped y se le paga
    # a los empleados el mes siguiente. Mostrar el NETO daba números negativos en
    # los meses en que A&B baja —el pago del mes pasado supera el cobro de este—
    # y un 10% de una venta no puede ser negativo. Ahora entra por un lado y sale
    # por el otro, cada uno con su signo natural.
    servicio_cobrado = [max(0.0, s["svc_collected"][i]) for i in rng]
    # La salida se despeja del neto para que el efecto de caja siga siendo el
    # mismo aunque el movimiento venga del balance real y no del modelo.
    servicio_pagado = [servicio_cobrado[i] - servicio[i] for i in rng]

    entradas = [cobro_op[i] + iva_out[i] + servicio_cobrado[i]
                - retenciones_tarjeta[i] for i in rng]
    # El IVA se abre en sus cuatro piezas para poder auditarlo, pero el efecto
    # de caja que manda es el de la otra pantalla. Este renglón absorbe la
    # diferencia cuando el movimiento no viene del modelo (mes cerrado con
    # balance real, celda pisada a mano). Con el modelo como fuente vale 0.
    ajuste_iva = [wc_tax[i] - (iva_out[i] - iva_in[i] - iva_ret[i] - payable_prev[i])
                  for i in rng]

    # ═══ PAGOS ══════════════════════════════════════════════════════════════
    # Proveedores: el devengado del mes menos lo que queda por pagar. Es
    # idéntico a pagar `ap%` del mes y el resto el mes siguiente, pero arrastra
    # solo la cola del año anterior: enero paga el 40% de la factura de
    # diciembre pasado, que el modelo viejo se saltaba.
    pago_prov = [C[i] - ap_mov[i] for i in rng]

    # ── Planilla y proveedores, separados ────────────────────────────────────
    # Los dos se pagan con el mismo calendario de cuentas por pagar, pero son
    # cosas distintas y la junta las lee distinto. El pago del mes se reparte
    # según lo que le toca a cada uno CON SU PROPIO REZAGO —una parte del mes y
    # el resto del anterior— y no según el peso del mes corriente, que daría un
    # reparto equivocado cuando la planilla es plana y el gasto estacional.
    #
    # Se reparte el pago TOTAL en vez de calcular cada uno por su cuenta: así la
    # suma cierra exacta aunque el movimiento venga del balance real de un mes
    # cerrado y no del modelo.
    ap_same = float(_p(p, "ap_same_pct"))

    def _devengado_efectivo(serie_costo):
        return [ap_same * serie_costo[i]
                + (1 - ap_same) * (serie_costo[i - 1] if i > 0 else serie_costo[0])
                for i in rng]

    plan_ef = _devengado_efectivo(planilla)
    tot_ef = _devengado_efectivo(C)
    peso_planilla = [(plan_ef[i] / tot_ef[i]) if abs(tot_ef[i]) > 0.005 else 0.0
                     for i in rng]
    pago_planilla = [pago_prov[i] * peso_planilla[i] for i in rng]
    pago_proveedores = [pago_prov[i] - pago_planilla[i] for i in rng]
    # Aguinaldo: se PROVISIONA cada mes contra el balance y se PAGA entero en su
    # mes. En el flujo solo tiene que verse la salida: mostrar la provisión como
    # un «pago negativo» los otros once meses no es un movimiento de caja, es el
    # reverso de un gasto que todavía no se pagó.
    #
    # Por eso el pago de planilla se rebaja en la provisión del mes —esa plata no
    # sale— y el aguinaldo aparece con su salida sola en diciembre. El total del
    # año es idéntico: lo que se resta mes a mes es lo que sale de golpe al final.
    provision_aguinaldo = [max(0.0, prov_mov[i]) for i in rng]
    pago_aguinaldo = [max(0.0, -prov_mov[i]) for i in rng]
    # Retención de Renta sobre el cobro con tarjeta: sale de caja, es saldo a favor.
    pago_ret_renta = [-renttax[i] for i in rng]
    # IVA: lo cobrado entra con la venta, lo pagado a proveedores sale, la
    # retención de tarjeta la adelanta Hacienda, y el saldo del mes anterior se
    # remite. Las cuatro piezas suman el efecto de caja del IVA del modelo.
    remesa_iva = [payable_prev[i] for i in rng]
    # El resumen no lleva seis líneas de impuestos. La reconciliación completa
    # vive en el tab de IVA y de ahí baja UN solo renglón: lo que efectivamente
    # se le entrega a Hacienda en el mes (retenciones de tarjeta + remesa),
    # neto del ajuste al movimiento real. El IVA cobrado y el pagado no van
    # sueltos: viajan dentro del cobro a clientes y del pago a proveedores,
    # que es como se mueven en la realidad.
    # SOLO IVA. La retención de Renta de tarjeta no va acá: es un anticipo del
    # impuesto sobre la renta, no del IVA, y se acredita contra la liquidación
    # anual. Se paga durante el año igual, pero pertenece al bloque de renta.
    # LO QUE SE LE PAGA A HACIENDA es la remesa, nada más. Las retenciones de
    # tarjeta —IVA y Renta, 2.5% cada una— NO son pagos que el hotel hace: el
    # adquirente se las descuenta al liquidar, así que van NETAS DEL COBRO. Antes
    # salían como dos renglones de salida, y como las dos tasas son iguales
    # mostraban el mismo monto todos los meses: parecía la misma plata contada
    # dos veces (no lo era, pero se leía así).
    impuestos_hacienda = [remesa_iva[i] - ajuste_iva[i] for i in rng]
    # El impuesto sobre la renta va aparte: es otro tributo, con su propia
    # liquidación anual y su propio interruptor. Meterlo con el IVA escondería
    # justamente lo que el owner quiere poder prender y apagar.
    # Renta: DOS cosas distintas, y mezclarlas confunde.
    #
    #  · El ANTICIPO es la retención que el adquirente le practica al hotel sobre
    #    los cobros con tarjeta. No se paga ni se acumula: se descuenta en el
    #    momento de liquidar, así que el hotel recibe 97.5% en vez de 100% cada
    #    mes. Es caja que no entra, mes a mes.
    #  · La LIQUIDACIÓN es el impuesto del año, y ese sí sale una sola vez, en
    #    marzo del año siguiente.
    anticipos_renta = pago_ret_renta
    pago_renta = [-renta_mov[i] for i in rng]
    cobro_con_iva = [cobro_op[i] + iva_out[i] - retenciones_tarjeta[i] for i in rng]
    pago_con_iva = [pago_prov[i] + iva_in[i] for i in rng]
    iva_planilla = [iva_in[i] * peso_planilla[i] for i in rng]
    planilla_con_iva = [pago_planilla[i] + iva_planilla[i] - provision_aguinaldo[i]
                        for i in rng]
    proveedores_con_iva = [(pago_prov[i] - pago_planilla[i])
                           + (iva_in[i] - iva_planilla[i]) for i in rng]

    # ── Lo que va a la CCSS ──────────────────────────────────────────────────
    # La cuota patronal la paga el hotel encima del salario; la obrera se le
    # retiene al empleado. Las dos se depositan en la Caja, así que en el flujo
    # van juntas y a la vista: es de los desembolsos más grandes del mes y
    # estaba escondido adentro del pago de planilla.
    obrera_rate_ = float(_p(p, "ccss_obrera_rate") or 0)
    ccss_devengado = [cs("ccss_patronal")[i] + cs("bruto")[i] * obrera_rate_
                      for i in rng]
    pago_ccss = _devengado_efectivo(ccss_devengado)
    planilla_neta_pago = [planilla_con_iva[i] - pago_ccss[i] for i in rng]
    salidas_op = [planilla_neta_pago[i] + pago_ccss[i] + pago_aguinaldo[i]
                  + proveedores_con_iva[i] + servicio_pagado[i]
                  + impuestos_hacienda[i] + pago_renta[i]
                  - otros_mov[i] for i in rng]

    flujo_operativo = [entradas[i] - salidas_op[i] for i in rng]

    # ═══ AUX-INGRESOS ═══════════════════════════════════════════════════════
    iva_por_linea = {l: _mul(revenue_lines[l], iva) for l in revenue_lines}
    aux_ingresos = [_row("A. VENTA DEVENGADA (sin IVA)", [0] * 12, "section")]
    for l in revenue_lines:
        aux_ingresos.append(_row(f"  {l}", revenue_lines[l], ayuda=AYUDA.get("*REV")))
    aux_ingresos.append(_row("TOTAL VENTA DEVENGADA", R, "sub"))
    aux_ingresos.append(_row("B. IVA COBRADO", [0] * 12, "section",
                             label_params={"tasa": f"{iva:.0%}"}))
    for l in revenue_lines:
        aux_ingresos.append(_row(f"  IVA {l}", iva_por_linea[l],
                                 ayuda=AYUDA.get("*REVIVA")))
    aux_ingresos.append(_row("TOTAL IVA COBRADO", iva_out, "sub"))
    aux_ingresos += [
        _row("C. DE LA VENTA AL COBRO", [0] * 12, "section"),
        _row("  Venta devengada del mes", R),
        _row("  (+) Depósitos recibidos por estadías futuras", dep_recv),
        _row("  (−) Depósitos aplicados a la estadía del mes", dep_appl),
        _row("  (±) Movimiento de cuentas por cobrar", ar_mov),
        _row("  = COBRO OPERATIVO", cobro_op, "sub"),
        _row("D. OTROS COBROS", [0] * 12, "section"),
        _row("  IVA cobrado a clientes", iva_out),
        _row("  Servicio 10% A&B cobrado al huésped", servicio_cobrado),
        _row("  (se le paga a los empleados el mes siguiente)", _mul(servicio_pagado, -1)),
        _row("▶ TOTAL ENTRADAS DE CAJA", entradas, "total_strong"),
    ]

    # ═══ AUX-NÓMINA (informativo) ═══════════════════════════════════════════
    # La nómina YA está dentro del costo devengado del P&L, con CCSS patronal y
    # aguinaldo adentro. Este cuadro es el detalle de qué la compone; su caja no
    # se suma aparte. El modelo viejo la reconstruía —base imponible × (1+CCSS)
    # + 1/12— y la volvía a pagar por su cuenta: el aguinaldo salía dos veces.
    bruto = cs("bruto")
    ccss_pat, aguin_c, ins_c = cs("ccss_patronal"), cs("aguinaldo"), cs("ins")
    vac_c, ces_c, incap_c = cs("vacaciones"), cs("cesantia"), cs("incapacidades")
    cafe_c, transp_c = cs("cafeteria"), cs("transporte")
    viv_c, otros_c = cs("vivienda"), cs("otros")

    # Deducciones AL EMPLEADO. El hotel las retiene del salario y las remite: no
    # son costo adicional, salen de adentro del bruto. Esto no estaba en ningún
    # lado —los 17 conceptos de planilla son todos costo patronal— y por eso la
    # «neta» anterior se calculaba restándole al salario la CCSS PATRONAL, que es
    # plata que el hotel paga ENCIMA del salario, no algo que se le descuente al
    # empleado. La neta salía mal y las cargas sociales no se mostraban.
    obrera_rate = float(_p(p, "ccss_obrera_rate") or 0)
    ded_ccss = _mul(bruto, obrera_rate)
    # La renta al salario NO es un porcentaje plano: es progresiva por tramos y
    # se calcula persona por persona (ver el tab de Retenciones). Acá llega ya
    # calculada. Si no viene, se cae al porcentaje plano de los criterios.
    ded_renta = cs("renta")
    if not any(abs(x) > 0.005 for x in ded_renta):
        ded_renta = _mul(bruto, float(_p(p, "retencion_rate") or 0))
    ded_total = [ded_ccss[i] + ded_renta[i] for i in rng]
    neta = [bruto[i] - ded_total[i] for i in rng]

    cargas = [ccss_pat[i] + ins_c[i] + aguin_c[i] + vac_c[i] + ces_c[i] + incap_c[i]
              for i in rng]
    beneficios = [cafe_c[i] + transp_c[i] + viv_c[i] + otros_c[i] for i in rng]
    costo_total = [bruto[i] + cargas[i] + beneficios[i] for i in rng]

    aux_nomina = [_row("A. COSTO DE PLANILLA POR DEPARTAMENTO", [0] * 12, "section")]
    for l in payroll_lines:
        aux_nomina.append(_row(f"  {l}", payroll_lines[l], ayuda=AYUDA.get("*NOMINA")))
    aux_nomina += [
        _row("TOTAL COSTO DE PLANILLA", total(payroll_lines) if payroll_lines
             else [0.0] * 12, "sub"),

        _row("B. DEL BRUTO A LA NETA (lo que recibe el empleado)", [0] * 12, "section"),
        _row("  Salario bruto (base imponible)", bruto),
        _row(f"  (−) CCSS obrera {obrera_rate * 100:.2f}%", _mul(ded_ccss, -1),
             ayuda=AYUDA.get("*CCSSOBRERA")),
        _row("  (−) Retención de renta al salario (por tramos)", _mul(ded_renta, -1)),
        _row("  Total deducciones al empleado", _mul(ded_total, -1)),
        _row("▶ PLANILLA NETA A PAGAR AL EMPLEADO", neta, "total_strong"),

        # A dónde va cada pedazo del salario bruto. El bruto no se paga entero al
        # empleado: una parte se retiene y la remite el hotel.
        _row("B2. A DÓNDE VA EL SALARIO BRUTO", [0] * 12, "section"),
        _row("  Al empleado (neto en la mano)", neta),
        _row("  A la CCSS (cotización obrera retenida)", ded_ccss),
        _row("  A Hacienda (retención de renta al salario)", ded_renta),
        _row("= SALARIO BRUTO", bruto, "sub"),

        _row("C. CARGAS SOCIALES PATRONALES (encima del bruto)", [0] * 12, "section"),
        _row("  CCSS patronal", ccss_pat),
        _row("  INS — riesgos del trabajo", ins_c),
        _row("  Aguinaldo (provisión)", aguin_c),
        _row("  Vacaciones (provisión)", vac_c),
        _row("  Cesantía (provisión)", ces_c),
        _row("  Incapacidades", incap_c),
        _row("TOTAL CARGAS SOCIALES", cargas, "sub"),

        _row("D. OTROS BENEFICIOS", [0] * 12, "section"),
        _row("  Cafetería", cafe_c),
        _row("  Transporte", transp_c),
        _row("  Vivienda", viv_c),
        _row("  Otros", otros_c),
        _row("TOTAL BENEFICIOS", beneficios, "sub"),

        _row("E. RESUMEN", [0] * 12, "section"),
        _row("  Salario bruto", bruto),
        _row("  (+) Cargas sociales patronales", cargas),
        _row("  (+) Otros beneficios", beneficios),
        _row("▶ COSTO TOTAL DE PLANILLA (al P&L)", costo_total, "total_strong"),
        _row("  La deducción obrera se retiene y se remite: la caja paga el costo total",
             [0] * 12),
    ]

    # ═══ AUX-PROVEEDORES ════════════════════════════════════════════════════
    # ⚠️ Del P&L, no la suma de sus cuatro componentes. En los escenarios con
    # meses reales hay below-GOP que no está guardado como línea propia (ver el
    # tab de propiedad, más abajo): sumando componentes, este renglón quedaba
    # corto y el bloque A no cerraba contra su propio total — $15.654,92 en el
    # Actual 2024. Acá va UNA línea que representa el bloque entero, así que
    # tiene que traer el bloque entero.
    nonop_prop = serie("nonop")
    aux_prov = [_row("A. COSTO DEVENGADO DEL MES", [0] * 12, "section")]
    for l in opex_lines:
        aux_prov.append(_row(f"  {l}", opex_lines[l], ayuda=AYUDA.get("*OPEX")))
    # El bloque de propiedad va en UNA línea, no abierto en cuatro: el detalle
    # vive en su propio tab y repetirlo acá se lee como si el gasto estuviera
    # contado dos veces. No lo está —departamentos 3,650,127 + propiedad 281,920
    # = 3,932,047, el costo del P&L— pero verlo dos veces da esa impresión.
    aux_prov += [
        _row("  Gastos de propiedad (ver su tab)", nonop_prop),
        _row("TOTAL COSTO DEVENGADO", C, "sub"),
        _row("B. DEL GASTO AL PAGO", [0] * 12, "section"),
        _row("  (±) Movimiento de cuentas por pagar", ap_mov),
        _row("  Pago total del mes (sin IVA)", pago_prov, "sub"),
        _row("C. CÓMO SE REPARTE EL PAGO", [0] * 12, "section"),
        _row("  Planilla", pago_planilla),
        _row("  Proveedores", pago_proveedores),
        _row("▶ TOTAL PAGADO (sin IVA)", pago_prov, "total_strong"),
    ]

    # ═══ AUX-GASTOS PROPIEDAD ═══════════════════════════════════════════════
    # Alquiler, honorarios, seguros y otros salen del P&L y se pagan con el
    # MISMO criterio que el resto de los proveedores. Antes cada uno tenía su
    # propia regla acá —el honorario a mes vencido, el seguro semestral— y una
    # regla distinta en el indirecto, para el mismo gasto.
    rent = list(prop.get("rent") or [0.0] * 12)
    honor = list(prop.get("honorarios") or [0.0] * 12)
    seguros = list(prop.get("seguros") or [0.0] * 12)
    otros = list(prop.get("otros") or [0.0] * 12)
    # ⚠️ El TOTAL es el del P&L, NO la suma de las cuatro filas de arriba, y la
    # diferencia entre ambos es una fila propia.
    #
    # En los escenarios con meses reales el total below-GOP no se calcula: se
    # DERIVA de `GOP − EBITDA Before` (ver `pl_engine`, que lo documenta), y esa
    # resta «captura montos que no están guardados como línea propia». O sea que
    # hay plata below-GOP real que no es alquiler, ni honorario, ni seguro, ni
    # la línea de otros — y al desglosar desaparecía sin dejar rastro.
    #
    # Medido el 2026-08-19: $15.654,92 en el Actual 2024 (varía mes a mes, es
    # del mayor) y $9.600,00 en el Forecast April (exactamente 1.200 por mes de
    # mayo a diciembre). El total siempre estuvo bien; lo que faltaba era poder
    # ver que una parte no está clasificada.
    #
    # Mostrarlo como fila es lo honesto: no inventa una categoría, dice cuánto
    # hay y que no se sabe de qué es. Si algún día se clasifica, esta fila baja
    # sola a cero.
    nonop_pl = serie("nonop")
    desglosado = [rent[i] + honor[i] + seguros[i] + otros[i] for i in rng]
    sin_clasificar = [nonop_pl[i] - desglosado[i] for i in rng]
    nonop_tot = nonop_pl
    aux_gp = [
        _row("A. GASTOS DE PROPIEDAD DEVENGADOS (below-GOP)", [0] * 12, "section"),
        _row("  Alquiler", rent),
        _row("  Honorarios de administración", honor),
        _row("  Seguros de la propiedad", seguros),
        _row("  Otros gastos", otros),
        _row("  Sin clasificar (está en el total, sin línea propia)", sin_clasificar,
             ayuda="belowGopSinClasificar"),
        _row("TOTAL GASTOS DE PROPIEDAD", nonop_tot, "sub"),
        _row("B. CÓMO SE PAGAN", [0] * 12, "section"),
        _row("  Entran al mismo calendario de proveedores", nonop_tot),
        _row("  (se ven dentro de «Pago a proveedores y planilla»)", [0] * 12),
        _row("C. INVERSIÓN", [0] * 12, "section"),
        _row("  CapEx del presupuesto (del P&L)", capex),
        _row("▶ TOTAL PROPIEDAD + INVERSIÓN", [nonop_tot[i] + capex[i] for i in rng],
             "total_strong"),
    ]

    # ═══ AUX-IVA ════════════════════════════════════════════════════════════
    # Arrastre del saldo a favor. Si el saldo sube, el mes GENERÓ crédito; si
    # baja, el crédito se APLICÓ contra el impuesto. Siempre cierra:
    # final = inicial + generado − aplicado.
    credito_fin = s["iva_credito"]
    credito_ini = _lag(credito_fin)
    credito_gen = [max(0.0, credito_fin[i] - credito_ini[i]) for i in rng]
    credito_apl = [max(0.0, credito_ini[i] - credito_fin[i]) for i in rng]

    # Este cuadro es donde se reconcilia el impuesto. El resumen del flujo solo
    # recibe el total del bloque C.
    aux_iva = [
        _row("A. IVA DEL MES (devengado)", [0] * 12, "section"),
        _row("  IVA cobrado a clientes (+)", iva_out),
        _row("  IVA pagado a proveedores (−)", _mul(iva_in, -1)),
        _row("  Retención de IVA de tarjeta (−)", _mul(iva_ret, -1)),
        _row("= POSICIÓN DEL MES (débito − crédito)", s["iva_obligacion"], "sub"),

        _row("B. AUXILIAR DEL SALDO A FAVOR", [0] * 12, "section"),
        _row("  Saldo inicial (viene del mes anterior)", credito_ini, saldo=0),
        _row("  (+) Crédito generado en el mes", credito_gen),
        _row("  (−) Crédito aplicado contra el impuesto", _mul(credito_apl, -1)),
        _row("  = SALDO A FAVOR FINAL", s["iva_credito"], "sub", saldo=-1),

        _row("C. LIQUIDACIÓN", [0] * 12, "section"),
        _row("  A declarar este mes (nunca negativo)", s["iva_net"], "sub"),
        _row("  Remesa a Hacienda de lo declarado el mes anterior", remesa_iva),
        _row("  Ajuste al movimiento real de la otra pantalla", ajuste_iva),
        _row("  Efecto neto del IVA en caja", s["WC_TAX"], "sub"),

        _row("D. LO QUE BAJA AL FLUJO", [0] * 12, "section"),
        _row("  Remesa de IVA a Hacienda", remesa_iva),
        _row("  (−) Ajuste al movimiento real", _mul(ajuste_iva, -1)),
        _row("▶ REMESA DE IVA (una línea en el Resumen)",
             impuestos_hacienda, "total_strong"),

        _row("E. MEMO — el IVA que viaja dentro de otras líneas", [0] * 12, "section"),
        _row("  El IVA cobrado va dentro de «Cobro a clientes»", iva_out),
        _row("  El IVA pagado va dentro de «Pago a proveedores»", iva_in),
        _row("  Retención de IVA de tarjeta (va neta del cobro)", iva_ret),
        _row("  Retención de RENTA de tarjeta (va neta del cobro)", anticipos_renta),
        _row("  Las dos son 2.5%: el adquirente las descuenta al liquidar",
             [0] * 12),
    ]

    # ═══ RESUMEN ════════════════════════════════════════════════════════════
    def sec_impact(section):
        rows_for = next(rows for name, rows in MANUAL_ROWS if name == section)
        return [sum(man(k)[i] * sg for k, _, sg in rows_for) for i in rng]

    cap_imp = sec_impact("CAPITAL")
    fin_imp = sec_impact("FINANCIAMIENTO")
    adj_imp = sec_impact("AJUSTES")
    flujo_neto = [flujo_operativo[i] - capex[i] - cap_imp[i] - fin_imp[i] - adj_imp[i]
                  for i in rng]

    # El saldo RUEDA, y si queda negativo se muestra negativo. Antes había un
    # renglón «Financiamiento Requerido» que inyectaba caja automáticamente para
    # que el saldo nunca bajara de cero: un flujo proyectado tiene que poder
    # mostrar el hueco, y además esa inyección hacía incomparables los saldos
    # con el otro método desde el primer mes en rojo. El requerimiento se sigue
    # informando, pero ya no se suma.
    saldo_ini, saldo_fin, requerido = [0.0] * 12, [0.0] * 12, [0.0] * 12
    bal = float(opening_cash or 0)
    for i in rng:
        saldo_ini[i] = bal
        saldo_fin[i] = bal + flujo_neto[i]
        requerido[i] = max(0.0, -saldo_fin[i])
        bal = saldo_fin[i]

    resumen = [
        _row("▶ ENTRADAS DE EFECTIVO", [0] * 12, "section"),
        _row("Cobro a clientes (con IVA, neto de retenciones de tarjeta)", cobro_con_iva),
        _row("Servicio 10% A&B cobrado al huésped", servicio_cobrado),
        _row("TOTAL ENTRADAS", entradas, "sub"),
        _row("▶ SALIDAS DE EFECTIVO", [0] * 12, "section"),
        _row("Pago de planilla neta (a empleados)", planilla_neta_pago),
        _row("Pago a la CCSS (cuota patronal + obrera)", pago_ccss),
        _row("Pago de aguinaldo (se provisiona y sale en su mes)", pago_aguinaldo),
        _row("Pago a proveedores (con IVA)", proveedores_con_iva),
        _row("Servicio 10% A&B pagado a empleados", servicio_pagado),
        _row("Remesa de IVA a Hacienda (ver tab Impuestos)", impuestos_hacienda),
        _row("Impuesto de renta — liquidación (sale una vez)", pago_renta),
        _row("Otros movimientos de caja", _mul(otros_mov, -1)),
        _row("TOTAL SALIDAS OPERATIVAS", salidas_op, "total"),
        _row("FLUJO OPERATIVO", flujo_operativo, "total_strong"),
        _row("▶ INVERSIÓN", [0] * 12, "section"),
        _row("CapEx del presupuesto (del P&L)", capex),
    ]
    _titles = {"CAPITAL": "▶ INVERSIÓN DE CAPITAL ADICIONAL (manual)",
               "FINANCIAMIENTO": "▶ PRÉSTAMOS E INTERESES (manual)",
               "AJUSTES": "▶ AJUSTES MANUALES"}
    for section, rows_for in MANUAL_ROWS:
        resumen.append(_row(_titles[section], [0] * 12, "section"))
        for k, lbl, sg in rows_for:
            resumen.append(_row("  " + lbl, man(k), "input", key=k, editable=True))
        resumen.append(_row("  Subtotal " + section.title(), sec_impact(section), "sub"))
    resumen += [
        _row("FLUJO NETO TOTAL", flujo_neto, "total_strong"),
        _row("▶ POSICIÓN DE CAJA", [0] * 12, "section"),
        _row("Saldo Inicial de Caja", saldo_ini, "cash", saldo=0),
        _row("SALDO FINAL DE CAJA", saldo_fin, "total_strong", saldo=-1),
        _row("(informativo) Financiamiento requerido", requerido, "cash"),
    ]

    return {
        "opening_cash": round(float(opening_cash or 0), 2),
        "resumen": resumen, "aux_ingresos": aux_ingresos, "aux_nomina": aux_nomina,
        "aux_proveedores": aux_prov, "aux_gastos_propiedad": aux_gp, "aux_iva": aux_iva,
        "identidad": {
            "noi": [round(R[i] - C[i], 2) for i in rng],
            "capex": [round(x, 2) for x in capex],
            "wc": [round(dep_recv[i] + dep_appl[i] + ar_mov[i] + ap_mov[i]
                         + wc_tax[i] + prov_mov[i] + renttax[i] + servicio[i], 2)
                   for i in rng],
            "flujo_neto_operativo": [round(flujo_operativo[i] - capex[i], 2) for i in rng],
        },
    }
