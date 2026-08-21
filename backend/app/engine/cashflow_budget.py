"""Cash Flow Budget — estructura tipo "FULL YEAR CASH FLOW BUDGET" del usuario.

Bloque **Operating Performance** se jala del P&L (Revenue / Operating Expenses /
Overhead / Non Allocated → Net Operating Income = EBITDA antes de capital).
Los bloques **Projects/CapEx**, **Balance Sheet/Working Capital** y **Other Cash
Movements** son líneas de entrada (el usuario las carga/pega por mes). Se
calculan los subtotales, Net Change in Cash y el roll Beginning/Ending Cash.

Puro: recibe P&L mensual por línea + inputs + caja inicial; no toca DB.
"""
from __future__ import annotations

# El rótulo en español viaja con su CLAVE al lado: el motor nombra y la pantalla
# traduce. Ver `etiquetas_cashflow_budget.py` — misma regla que el flujo directo.
from app.engine.etiquetas_cashflow_budget import clave as _clave_fila

# Operating Performance — jalado del P&L. (key, label, pl_code, signo de display)
PL_ROWS = [
    ("REVENUE",  "Revenue",                 "TOTAL_REVENUES", 1),
    ("OPEX",     "Operating Expenses",      "TOTAL_OPEXP",   -1),
    ("OVERHEAD", "Overhead Expenses",       "TOTAL_OVERHEAD", -1),
    ("NONALLOC", "Non Allocated Expenses",  "TOTAL_NON_OP",  -1),
]
# Filas de CapEx que salen del P&L en vez de tecleadas. El P&L ya calcula
# CAPITAL_EXPENSE = CAPITAL_RESERVE (% del revenue) + LARGE_CAPEX, y el flujo
# directo lo lee desde siempre; esto pone al Budget de acuerdo con los dos.
CAPEX_DESDE_PL = {"CAPEX_LARGE": "CAPITAL_EXPENSE"}

CAPEX_ROWS = [
    ("CAPEX_PREV",  "Capital Expenditures – Previously Approved"),
    ("CAPEX_NEW",   "Capital Expenditures – New"),
    ("CAPEX_SMALL", "Capital – Small Projects"),
    ("CAPEX_LARGE", "Large Improvement Budget 4%"),
]
WC_ROWS = [
    ("WC_DEP_RECV", "Deposits Received"),
    ("WC_DEP_APPL", "Deposits Applied"),
    ("WC_AP",       "Accounts Payable / Other Payables"),
    ("WC_AR",       "Accounts Receivable"),
    ("WC_TAX",      "Tax credits/debits"),
    ("WC_PROV",     "Provisions and reserves"),
    ("WC_RENTTAX",  "Rent Taxes not Paid"),
    ("WC_SERVICE",  "Servicio F&B por pagar (10% empleados)"),
]
OTHER_ROWS = [
    ("OTH_RENTA",   "Impuesto de renta (liquidación anual)"),
    ("OTH_CONTRIB", "Contributions / Distributions"),
    ("OTH_OTHER",   "Other"),
    ("OTH_FX",      "Exchange rate variations"),
    ("OTH_HOUSE",   "House Ledger"),
    ("OTH_ADJUST",  "Ajuste manual"),   # plug editable — corrección manual de caja (en caso de)
]
INPUT_ROWS = CAPEX_ROWS + WC_ROWS + OTHER_ROWS
INPUT_KEYS = {k for k, _ in INPUT_ROWS}

# Modo 'days' (DSO/DPO): base de cálculo y signo de caja por partida.
# A/R = activo sobre ventas (signo −1); A/P = pasivo sobre costos (+1).
DAYS_BASE = {
    "WC_AR": ("sales", -1),
    "WC_AP": ("costs", 1),
}


# Mapeo partida WC → líneas del Balance Sheet (Summary) + signo de caja
# (activo ↑ = salida −1; pasivo ↑ = entrada +1).
WC_BALANCE_MAP = {
    "WC_AR":      (["a/r - travel agencies", "guest ledger"], -1),
    "WC_AP":      (["total a/p"], 1),
    "WC_TAX":     (["taxes payable"], 1),
    # «Capital reserves» NO va acá: esa línea es la reserva de reposición (el 4%
    # del revenue), no una provisión de planilla. Mezclarlas hacía que el
    # aguinaldo se posteara contra la reserva de capital.
    "WC_PROV":    (["other current liabilities", "payroll provisions"], 1),
    "WC_DEP_RECV": (["deposits (guests)"], 1),   # solo neto disponible (Recibidos−Aplicados)
    # WC_DEP_APPL y WC_RENTTAX no tienen línea de balance limpia → sin hint de calibración
}


# ── Modelo de timing de Working Capital (replica del modelo del usuario) ──────
# Descompone el revenue por tipo de pago con su timing y hace rodar los saldos
# de Depósitos / A/R / A/P / Accrued / IVA. Parámetros calibrables por escenario.
# Mezcla por mes (Ene..Dic). NRR y Credit constantes; Flex/Stay varían:
# Feb/May/Ago/Nov = 20/60 (temporada baja), resto 30/50 (del modelo del usuario).
_DEFAULT_FLEX = [0.30, 0.20, 0.30, 0.30, 0.20, 0.30, 0.30, 0.20, 0.30, 0.30, 0.20, 0.30]
WC_MODEL_DEFAULTS = {
    "enabled": False,
    # Mezcla de pago del revenue — NRR/Credit escalares; Flex por mes (Stay = 1−NRR−Credit−Flex)
    "mix_nrr": 0.10, "mix_credit": 0.10, "mix_flex": list(_DEFAULT_FLEX),
    # Timing (meses): NRR cobra 2M antes, Flex 1M antes, Credit +1M (queda en A/R)
    "lead_nrr": 2, "lead_flex": 1, "lag_credit": 1,
    # Retención de anticipos (cancelaciones/ajustes): % retenido del depósito recibido
    # ese mes; se libera y devuelve al huésped el mes siguiente. Reduce WC_DEP_RECV.
    "retention": 0.05,
    # Tarjeta
    "card_pct": 0.70, "card_iva_ret": 0.025, "card_renta_ret": 0.025,
    # bank_comm (2.7%) eliminado — ya está en P&L como CC Commissions (7120),
    # reduce el NOI y por lo tanto el flujo de caja; no debe duplicarse en WC.
    # Servicio F&B (10% de ley CR) — PASS-THROUGH puro: NO es ingreso del hotel
    # (el revenue de A&B del P&L NO lo incluye), es plata de los empleados. Se
    # COBRA con la venta de A&B (entra) y se PAGA a los empleados `service_lag`
    # meses después (sale) → pasivo "Servicio por pagar". service_rate sobre el
    # revenue de A&B (REV_FB).
    "service_rate": 0.10, "service_lag": 1,
    # IVA
    "iva_rate": 0.13,
    # A/P proveedores: % pagado el mismo mes (resto el siguiente)
    "ap_same_pct": 0.60,
    # Planilla tercerizada: el externo factura un "cobro de planilla con IVA", así
    # que la planilla SÍ lleva crédito de IVA y es A/P (entra a la base del modelo).
    # Si es planilla interna → False (sin IVA, fuera de la base de A/P e IVA).
    "payroll_outsourced": True,
    # Aguinaldo
    "aguinaldo_monthly": 8300.0, "aguinaldo_pay_month": 12,
    # Proyección año 2 (meses 13–24): crecimiento sobre el año 1
    "growth_y2": 0.07,
    # NOTA: los saldos iniciales se quitaron — el Balance Sheet proyectado ANCLA en
    # el último balance real subido (project_full_balance_sheet), así que un opening
    # paramétrico era redundante y solo distorsionaba (doble conteo). La proyección
    # interna de 6 líneas arranca en 0 y solo aporta los Δ mensuales.
}
# Partidas WC que el modelo de timing calcula (las demás siguen su driver/manual)
WC_MODEL_KEYS = ["WC_DEP_RECV", "WC_DEP_APPL", "WC_AR", "WC_AP", "WC_PROV", "WC_TAX"]


def aguinaldo_series(p: dict) -> list[float] | None:
    """Aguinaldo provisionado por mes según la PLANILLA real, si el escenario la
    tiene. Viaja dentro de los params para que lo vean por igual el cálculo, el
    desglose del modal y el balance proyectado — si solo lo viera el cálculo, el
    drill-down explicaría el número con otra cifra.
    None → se usa el monto fijo de los Criterios (respaldo)."""
    ser = p.get("aguinaldo_series")
    if not isinstance(ser, (list, tuple)) or len(ser) < 12:
        return None
    vals = [_ff(v) for v in ser[:12]]
    return vals if any(abs(v) > 0.005 for v in vals) else None


def _gp(p: dict, k: str):
    v = p.get(k, WC_MODEL_DEFAULTS.get(k))
    return v if v is not None else WC_MODEL_DEFAULTS.get(k)


# Offsets de cobro relativos al mes de estadía — la MATRIZ de timing editable por
# mes (4m antes … 1m después). Generaliza las cajas NRR/Flex/Stay/Credit: el
# usuario programa, por mes, qué % entra en cada offset (clave para Dic/Oct/Nov).
WC_TIMING_OFFSETS = (-4, -3, -2, -1, 0, 1)


def _ff(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def effective_timing_matrix(p: dict) -> list[list[float]]:
    """Matriz 12×6 (mes de estadía 0..11 × offset WC_TIMING_OFFSETS, fracciones).
    Si el escenario trae 'timing_matrix' explícita la usa; si no, la DERIVA del
    modelo de cajas (NRR 2M antes / Flex 1M antes / Stay mismo mes / Credit +1M)
    → reproduce EXACTO el comportamiento previo (backward-compatible)."""
    n = len(WC_TIMING_OFFSETS)
    tm = p.get("timing_matrix")
    if isinstance(tm, (list, tuple)) and len(tm) >= 12:
        return [[_ff(row[i]) if i < len(row) else 0.0 for i in range(n)]
                for row in tm[:12]]
    flex_arr = _gp(p, "mix_flex")
    if not isinstance(flex_arr, (list, tuple)) or len(flex_arr) < 12:
        flex_arr = _DEFAULT_FLEX
    nrr = _ff(_gp(p, "mix_nrr")); credit = _ff(_gp(p, "mix_credit"))
    ln = int(_ff(_gp(p, "lead_nrr"))); lf = int(_ff(_gp(p, "lead_flex")))
    lc = int(_ff(_gp(p, "lag_credit")))
    idx = {o: i for i, o in enumerate(WC_TIMING_OFFSETS)}
    out = []
    for m in range(12):
        r = [0.0] * n
        flex_m = _ff(flex_arr[m])
        if -ln in idx: r[idx[-ln]] += nrr
        if -lf in idx: r[idx[-lf]] += flex_m
        if lc in idx:  r[idx[lc]]  += credit
        r[idx[0]] = max(0.0, 1.0 - nrr - credit - flex_m)   # Stay = resto
        out.append(r)
    return out


def cobros_por_timing(R: list[float], p: dict,
                      R_prev: list[float] | None = None,
                      R_next: list[float] | None = None) -> list[float]:
    """Ventas por mes → COBROS por mes, con la matriz 12×6 de timing.

    Es la misma matriz que usa el cash flow indirecto (`effective_timing_matrix`),
    expuesta aparte para que el MÉTODO DIRECTO cobre igual. Tener dos modelos de
    cobro en el mismo sistema garantizaba que dieran caja distinta para el mismo
    escenario.

    LOS AÑOS VECINOS IMPORTAN, y no se puede resolver dando la vuelta al año:

      · Los depósitos que entran a fin de 2027 son de estadías de 2028 → hacen
        falta los primeros meses del AÑO SIGUIENTE (`R_next`).
      · El saldo a crédito de diciembre de 2026 se cobra en enero de 2027 → hace
        falta el cierre del AÑO ANTERIOR (`R_prev`).
      · Los depósitos de las estadías de enero a abril de 2027 entraron en 2026:
        NO son caja de 2027 y no deben aparecer.

    Por eso `sum(cobros) != sum(ventas)` y está bien que así sea: esa diferencia
    es capital de trabajo. (La primera versión de esto trataba el año como
    cíclico y cobraba en diciembre de 2027 el depósito de enero de 2027 — el
    mismo año. Cerraba la suma a costa de inventar el dato.)

    Sin `R_next`/`R_prev` esos tramos quedan fuera, que es lo honesto: mejor un
    cobro que falta y se ve, que uno inventado con la venta del mes equivocado.
    """
    M = effective_timing_matrix(p)
    N = len(R)
    out = [0.0] * N

    # Los años vecinos pueden tener su PROPIA regla de cobro. Si el escenario no
    # la trae, usan la del año en curso — que es lo que se venía haciendo y deja
    # los números donde estaban.
    def matriz_vecina(clave: str, meses: range) -> list[list[float]]:
        crudo = (p or {}).get(clave)
        base = [list(f) for f in M]
        if isinstance(crudo, (list, tuple)):
            for k, mes in enumerate(meses):
                if k < len(crudo) and isinstance(crudo[k], (list, tuple)):
                    fila = crudo[k]
                    base[mes] = [_ff(fila[i]) if i < len(fila) else 0.0
                                 for i in range(len(WC_TIMING_OFFSETS))]
        return base

    # Del año ANTERIOR solo llegan acá los últimos 6 meses; del SIGUIENTE, los
    # primeros 6. Más allá de eso ningún offset alcanza a cruzar el año.
    M_prev = matriz_vecina("timing_matrix_prev", range(6, 12))
    M_next = matriz_vecina("timing_matrix_next", range(0, 6))

    def aplicar(ventas: list[float], desfase: int, matriz: list[list[float]]) -> None:
        """`desfase` = 0 este año, −12 el anterior, +12 el siguiente."""
        for t, v in enumerate(ventas):
            if not v:
                continue
            for i, off in enumerate(WC_TIMING_OFFSETS):
                m = t + desfase + off
                if 0 <= m < N:
                    out[m] += matriz[t % 12][i] * v

    aplicar(R, 0, M)
    if R_prev:
        aplicar(list(R_prev), -12, M_prev)
    if R_next:
        aplicar(list(R_next), 12, M_next)
    return out


def cobros_desglosados(R: list[float], p: dict,
                       R_prev: list[float] | None = None,
                       R_next: list[float] | None = None) -> dict[str, list[float]]:
    """Igual que `cobros_por_timing`, pero abierto en sus tres piezas.

    Un solo número neto no se puede auditar: no se sabe cuánto es depósito,
    cuánto saldo del mes y cuánto crédito de meses pasados. Devuelve:

      · `estadia` — la venta del propio mes que se cobra en el mes (offset 0)
      · `depositos` — anticipos por estadías FUTURAS (offsets negativos)
      · `credito` — saldo de estadías YA pasadas (offset +1)

    Las tres suman exactamente lo mismo que `cobros_por_timing`.
    """
    M = effective_timing_matrix(p)
    N = len(R)
    out = {"estadia": [0.0] * N, "depositos": [0.0] * N, "credito": [0.0] * N}

    def matriz_vecina(clave: str, meses: range) -> list[list[float]]:
        crudo = (p or {}).get(clave)
        base = [list(f) for f in M]
        if isinstance(crudo, (list, tuple)):
            for k, mes in enumerate(meses):
                if k < len(crudo) and isinstance(crudo[k], (list, tuple)):
                    fila = crudo[k]
                    base[mes] = [_ff(fila[i]) if i < len(fila) else 0.0
                                 for i in range(len(WC_TIMING_OFFSETS))]
        return base

    fuentes = [(R, 0, M)]
    if R_prev:
        fuentes.append((list(R_prev), -12, matriz_vecina("timing_matrix_prev", range(6, 12))))
    if R_next:
        fuentes.append((list(R_next), 12, matriz_vecina("timing_matrix_next", range(0, 6))))

    for ventas, desfase, matriz in fuentes:
        for t, v in enumerate(ventas):
            if not v:
                continue
            for i, off in enumerate(WC_TIMING_OFFSETS):
                m = t + desfase + off
                if not (0 <= m < N):
                    continue
                caja = matriz[t % 12][i] * v
                clave = "estadia" if off == 0 else ("depositos" if off < 0 else "credito")
                out[clave][m] += caja
    return out


def wc_schedule(R: list[float], C: list[float], p: dict,
                fb: list[float] | None = None) -> dict:
    """Calendario mensual del modelo de timing sobre N meses (replica el modelo
    del usuario + reglas CR). R=ventas, C=costos operativos, fb=revenue de A&B
    (para el 10% de servicio de ley, pass-through a empleados).
    Devuelve todas las líneas (movimientos y saldos) por mes."""
    N = len(R)
    g = lambda k: float(_gp(p, k))

    # ── Matriz de timing: mes de estadía × offset de cobro (4m antes … +1m) ──────
    M = effective_timing_matrix(p)                 # 12×6 fracciones (suma 1.0 por fila)
    OFF = WC_TIMING_OFFSETS
    oi = {o: i for i, o in enumerate(OFF)}
    stay = [M[t % 12][oi[0]] * R[t] for t in range(N)]
    credit = [(M[t % 12][oi[1]] if 1 in oi else 0.0) * R[t] for t in range(N)]
    # compat de display: porción a 2M antes (≈NRR) y 1M antes (≈Flex)
    nrr = [(M[t % 12][oi[-2]] if -2 in oi else 0.0) * R[t] for t in range(N)]
    flex = [(M[t % 12][oi[-1]] if -1 in oi else 0.0) * R[t] for t in range(N)]

    # ── Depósitos: cobros adelantados (offsets < 0) de estadías futuras ──────────
    # Retención: % del depósito recibido que se retiene ese mes (cancelaciones/
    # ajustes); se libera y devuelve al huésped el mes siguiente → efecto neto ≈ 0
    # en el largo plazo pero altera el timing mensual de la caja.
    received_gross = [0.0] * N
    for S in range(N):
        row = M[S % 12]
        for i, o in enumerate(OFF):
            if o < 0:
                t = S + o
                if 0 <= t < N:
                    received_gross[t] += R[S] * row[i]
    ret_pct = g("retention")
    ret_held = [ret_pct * received_gross[t] for t in range(N)]
    ret_release = [0.0] + [ret_held[t - 1] for t in range(1, N)]
    received = [received_gross[t] - ret_held[t] + ret_release[t] for t in range(N)]
    # Aplicación = anticipos (offsets<0) consumidos al hospedarse este mes
    adv = [sum(M[t % 12][i] for i, o in enumerate(OFF) if o < 0) for t in range(N)]
    applied = [adv[t] * R[t] for t in range(N)]
    # ── A/R: crédito (offset +1) cobrado el mes siguiente ──
    ar_collected = [credit[t - 1] if t - 1 >= 0 else 0.0 for t in range(N)]
    ar_move = [ar_collected[t] - credit[t] for t in range(N)]
    # ── A/P proveedores: Δ del saldo diferido (resto del % mismo mes) ──
    nxt = 1.0 - g("ap_same_pct")
    deferred = [nxt * C[t] for t in range(N)]
    ap_move = [0.0] + [deferred[t] - deferred[t - 1] for t in range(1, N)]
    # ── Aguinaldo: +mensual; se cancela todo en el mes de pago ──
    # Sale de la PLANILLA real si el escenario la tiene; el $8,300 fijo de los
    # Criterios queda solo como respaldo. Con la nómina de Budget 2027 el real es
    # ~$12,340/mes ($148,115 al año contra $99,600): la salida de diciembre estaba
    # 49% subestimada. Y como la provisión se cancela contra sí misma, el anual da
    # 0.00 y la fila parecía apagada — por eso nadie lo notaba.
    pm = int(g("aguinaldo_pay_month"))
    ser = aguinaldo_series(p)
    if ser:
        prov = [ser[t % 12] - (sum(ser) if ((t % 12) + 1) == pm else 0.0) for t in range(N)]
    else:
        ag = g("aguinaldo_monthly")
        prov = [ag - (ag * 12 if ((t % 12) + 1) == pm else 0.0) for t in range(N)]
    # ── IVA: efecto de caja = variación del saldo de IVA por pagar (float) ──────
    # El IVA se COBRA en ventas y se PAGA en compras durante el mes (queda en caja
    # hasta liquidar al mes siguiente); la retención de tarjeta adelanta crédito de
    # IVA. Como el neto remitido cada mes es el saldo del mes anterior, el efecto de
    # caja neto es Δ(IVA por pagar) — simétrico. (payable<0 = crédito, se respeta.)
    iva_rate = g("iva_rate")
    iva_out = [iva_rate * R[t] for t in range(N)]          # IVA débito (ventas)
    iva_in = [iva_rate * C[t] for t in range(N)]           # IVA crédito (compras)
    # ── Tarjeta: retenciones sobre el cobro operativo del mes ──
    cash_op = [received[t] + stay[t] + ar_collected[t] for t in range(N)]
    card_base = [g("card_pct") * cash_op[t] for t in range(N)]
    iva_ret = [g("card_iva_ret") * card_base[t] for t in range(N)]      # saldo a favor IVA (mes sig.)
    renta_ret = [g("card_renta_ret") * card_base[t] for t in range(N)]  # saldo a favor Renta anual
    # El saldo a favor NO se cobra: se ARRASTRA. Hacienda no devuelve el crédito
    # en efectivo (salvo trámites especiales); se aplica contra el impuesto de
    # los meses siguientes hasta agotarlo. El modelo anterior hacía
    # `wc_tax = Δ(payable)` con payable pudiendo ser negativo, y restar un
    # negativo es sumar caja: en los meses de crédito —temporada baja, octubre
    # con el lodge cerrado— aparecía una ENTRADA de plata que nunca ocurre.
    #
    # Ahora el crédito se acumula y solo se remite cuando la posición vuelve a
    # ser deudora.
    obligacion = [iva_out[t] - iva_in[t] - iva_ret[t] for t in range(N)]
    a_remitir = [0.0] * N        # lo que se declara este mes y se paga al siguiente
    credito = [0.0] * N          # saldo a favor que queda arrastrándose
    acum = 0.0
    for t in range(N):
        neto = obligacion[t] - acum
        if neto >= 0:
            a_remitir[t] = neto
            acum = 0.0
        else:
            a_remitir[t] = 0.0
            acum = -neto
        credito[t] = acum
    # Caja del mes: entra el IVA de las ventas, sale el de las compras y la
    # retención de tarjeta, y se remite lo declarado el mes ANTERIOR.
    wc_tax = [obligacion[t] - (a_remitir[t - 1] if t > 0 else 0.0)
              for t in range(N)]
    iva_net = a_remitir          # saldo por pagar del mes (nunca negativo)
    # Renta: la retención de tarjeta es saldo a favor (cash retenido) → salida, recuperable
    wc_renttax = [-renta_ret[t] for t in range(N)]
    # ── Servicio F&B (10% de ley CR) — pass-through a empleados ──────────────────
    # NO es ingreso del hotel (el revenue de A&B NO lo incluye). Se COBRA con la
    # venta de A&B (entra a caja) y se PAGA a los empleados `service_lag` meses
    # después (sale). El movimiento de caja = cobrado − pagado = Δ del pasivo
    # "Servicio por pagar". Sin fb → todo 0 (backward-compatible).
    srate = g("service_rate")
    slag = int(g("service_lag"))
    fbv = [_ff(x) for x in (fb or [])]
    if len(fbv) < N:
        fbv = (fbv + [0.0] * N)[:N]
    svc_collected = [srate * fbv[t] for t in range(N)]
    svc_paid = [svc_collected[t - slag] if t - slag >= 0 else 0.0 for t in range(N)]
    wc_service = [svc_collected[t] - svc_paid[t] for t in range(N)]

    return {
        "nrr": nrr, "flex": flex, "stay": stay, "credit": credit,
        "received": received, "applied": applied, "ar_collected": ar_collected,
        "WC_DEP_RECV": received, "WC_DEP_APPL": [-applied[t] for t in range(N)],
        "WC_AR": ar_move, "WC_AP": ap_move, "WC_PROV": prov,
        "WC_TAX": wc_tax, "WC_RENTTAX": wc_renttax, "WC_SERVICE": wc_service,
        "iva_out": iva_out, "iva_in": iva_in, "iva_net": iva_net,
        "iva_obligacion": obligacion, "iva_credito": credito,
        "card_base": card_base, "iva_ret": iva_ret, "renta_ret": renta_ret,
        "deferred": deferred,
        "svc_collected": svc_collected, "svc_paid": svc_paid,
    }


def wc_cost_base(costs: list[float], payroll: list[float] | None, p: dict) -> list[float]:
    """Base de costos para A/P e IVA-crédito del modelo WC. Si la planilla es
    tercerizada (payroll_outsourced=True, default), entra entera (factura con IVA);
    si es interna (False), se resta porque no lleva IVA ni va a A/P de proveedor."""
    outsourced = bool(p.get("payroll_outsourced", WC_MODEL_DEFAULTS["payroll_outsourced"]))
    if outsourced or not payroll:
        return list(costs)
    return [max(0.0, costs[i] - (payroll[i] if i < len(payroll) else 0.0))
            for i in range(len(costs))]


_WC_KEYS = ("WC_DEP_RECV", "WC_DEP_APPL", "WC_AR", "WC_AP", "WC_PROV", "WC_TAX", "WC_RENTTAX", "WC_SERVICE")


def wc_breakdown(R: list[float], C: list[float], p: dict, key: str, t: int,
                 label_fn, fb: list[float] | None = None) -> dict:
    """Descompone la celda WC[key][t] (índice GLOBAL t dentro de la ventana) en
    sus componentes: qué meses/conceptos la forman. `label_fn(idx)` → etiqueta
    de calendario (p.ej. 'Oct-26'). Devuelve {'total', 'parts':[{label,amount}]}.
    Sirve para auditar de dónde sale cada monto del modelo (drill-down)."""
    N = len(R)
    g = lambda k: float(_gp(p, k))
    M = effective_timing_matrix(p)
    OFF = WC_TIMING_OFFSETS
    s = wc_schedule(R, C, p, fb=fb)
    parts: list[dict] = []
    def add(label, amt, clave=None, params=None, memo=False):
        # El componente viaja con su `label` (respaldo, el texto de siempre) y
        # con `label_key` + `label_params`: el motor NOMBRA y la pantalla arma la
        # frase en el idioma del usuario (`cfbParte` en el catálogo). Los meses y
        # los montos van como PARÁMETROS, nunca concatenados acá: el plural y el
        # orden de las palabras cambian entre idiomas y solo el catálogo los sabe.
        # ⚠️ `memo=True` pasa el filtro del monto. El filtro existe para que un
        # componente en cero no ensucie el desglose — pero un MEMO va en cero a
        # propósito: informa un saldo que se arrastra, no una partida de caja.
        # Sin esta salida, «Saldo a favor que se arrastra» se agregaba y se
        # descartaba en el mismo renglón: no se mostró nunca.
        if memo or abs(amt) > 1e-6:
            p = {"label": label, "amount": round(amt, 2)}
            if clave:
                p["label_key"] = clave
                p["label_params"] = params or {}
            parts.append(p)

    if key == "WC_DEP_RECV":
        # Anticipos (offsets<0) de estadías futuras S que se cobran ESTE mes (S+o=t)
        for S in range(N):
            row = M[S % 12]
            for i, o in enumerate(OFF):
                if o < 0 and S + o == t:
                    add(f"Anticipo de estadía {label_fn(S)} ({-o}m antes)", R[S] * row[i],
                        "anticipo_de_estadia", {"mes": label_fn(S), "meses": -o})
        def gross(tt):
            if tt < 0 or tt >= N:
                return 0.0
            tot = 0.0
            for S in range(N):
                row = M[S % 12]
                for i, o in enumerate(OFF):
                    if o < 0 and S + o == tt:
                        tot += R[S] * row[i]
            return tot
        rp = g("retention")
        add("Retención retenida este mes (−)", -rp * gross(t),
            "retencion_retenida_este_mes")
        add("Retención liberada del mes anterior (+)", rp * gross(t - 1),
            "retencion_liberada_del_mes_anterior")
        total = s["received"][t]
    elif key == "WC_DEP_APPL":
        row = M[t % 12]
        for i, o in enumerate(OFF):
            if o < 0:
                add(f"Anticipo consumido (cobrado {-o}m antes) — estadía {label_fn(t)}",
                    -R[t] * row[i],
                    "anticipo_consumido", {"meses": -o, "mes": label_fn(t)})
        total = s["WC_DEP_APPL"][t]
    elif key == "WC_AR":
        credit = s["credit"]
        if t - 1 >= 0:
            add(f"Cobro del crédito de {label_fn(t-1)} (+)", credit[t - 1],
                "cobro_del_credito", {"mes": label_fn(t - 1)})
        add(f"Nuevo crédito a cobrar de {label_fn(t)} (−)", -credit[t],
            "nuevo_credito_a_cobrar", {"mes": label_fn(t)})
        total = s["WC_AR"][t]
    elif key == "WC_AP":
        # El modelo arranca A/P en 0 en el primer mes de la ventana (mes base, sin Δ).
        deferred = s["deferred"]
        if t >= 1:
            add(f"Diferido a pagar de {label_fn(t)} (+, queda por pagar)", deferred[t],
                "diferido_a_pagar", {"mes": label_fn(t)})
            add(f"Pago del diferido de {label_fn(t-1)} (−)", -deferred[t - 1],
                "pago_del_diferido", {"mes": label_fn(t - 1)})
        total = s["WC_AP"][t]
    elif key == "WC_PROV":
        pm = int(g("aguinaldo_pay_month"))
        ser = aguinaldo_series(p)
        if ser:
            add("Provisión de aguinaldo del mes (+, de la planilla)", ser[t % 12],
                "provision_aguinaldo_del_mes_planilla")
            if ((t % 12) + 1) == pm:
                add("Pago del aguinaldo (−, todo el acumulado)", -sum(ser),
                    "pago_del_aguinaldo")
        else:
            ag = g("aguinaldo_monthly")
            add("Provisión mensual de aguinaldo (+, monto fijo de Criterios)", ag,
                "provision_mensual_aguinaldo_criterios")
            if ((t % 12) + 1) == pm:
                add("Pago del aguinaldo (−, todo el acumulado)", -ag * 12,
                    "pago_del_aguinaldo")
        total = s["WC_PROV"][t]
    elif key == "WC_TAX":
        add(f"IVA débito (ventas) de {label_fn(t)} (+)", s["iva_out"][t],
            "iva_debito_ventas", {"mes": label_fn(t)})
        add(f"IVA crédito (compras) de {label_fn(t)} (−)", -s["iva_in"][t],
            "iva_credito_compras", {"mes": label_fn(t)})
        add("Retención IVA de tarjeta (−)", -s["iva_ret"][t],
            "retencion_iva_de_tarjeta")
        if t - 1 >= 0:
            add(f"Remesa a Hacienda de lo declarado en {label_fn(t-1)}",
                -s["iva_net"][t - 1],
                "remesa_a_hacienda_de_lo_declarado", {"mes": label_fn(t - 1)})
        if s["iva_credito"][t] > 0.005:
            add(f"(memo) Saldo a favor que se arrastra: {s['iva_credito'][t]:,.0f}", 0.0,
                "memo_saldo_a_favor_que_se_arrastra",
                {"monto": f"{s['iva_credito'][t]:,.0f}"}, memo=True)
        total = s["WC_TAX"][t]
    elif key == "WC_RENTTAX":
        add("Retención de Renta sobre tarjeta (saldo a favor, −)", -s["renta_ret"][t],
            "retencion_de_renta_sobre_tarjeta")
        total = s["WC_RENTTAX"][t]
    elif key == "WC_SERVICE":
        add(f"Cobro del 10% de servicio A&B de {label_fn(t)} (+)", s["svc_collected"][t],
            "cobro_del_10_de_servicio_ab", {"mes": label_fn(t)})
        lag = int(g("service_lag"))
        if t - lag >= 0:
            add(f"Pago a empleados (servicio de {label_fn(t-lag)}) (−)", -s["svc_paid"][t],
                "pago_a_empleados_servicio", {"mes": label_fn(t - lag)})
        total = s["WC_SERVICE"][t]
    else:
        total = float(s.get(key, [0.0] * N)[t]) if t < N else 0.0

    return {"total": round(total, 2), "parts": parts,
            "check": round(sum(x["amount"] for x in parts), 2)}


def wc_schedule_ventana(revenue: list[float], costs: list[float], p: dict,
                        prior_rev=None, prior_costs=None,
                        next_rev=None, next_costs=None,
                        fb_rev=None, prior_fb=None, next_fb=None) -> dict:
    """`wc_schedule` corrido sobre la ventana [año anterior + año + siguiente] y
    recortado al año — TODAS las series, no solo las 7 partidas de la pantalla.

    El flujo DIRECTO se arma con esto. Antes tenía su propio cálculo de cobros,
    pagos e IVA en paralelo, y esa duplicación era la razón de fondo por la que
    los dos métodos daban caja distinta para el mismo escenario: no era un
    parámetro mal puesto, eran dos modelos. Ahora el directo es una PRESENTACIÓN
    de este mismo calendario, así que la conciliación es exacta por construcción
    y cualquier diferencia que aparezca es de las filas manuales, no del modelo.

    Además de las series del año devuelve `payable_prev`: el saldo de IVA por
    pagar del mes ANTERIOR a cada mes del año, para que enero pueda remitir el
    IVA de diciembre del año pasado en vez de arrancar en cero.
    """
    def _arr(x):
        return [float(v) for v in (x or [])]

    pr, prc = _arr(prior_rev), _arr(prior_costs)
    nr, nrc = _arr(next_rev), _arr(next_costs)
    if len(prc) != len(pr):
        prc = (prc + [0.0] * len(pr))[:len(pr)]
    if len(nrc) != len(nr):
        nrc = (nrc + [0.0] * len(nr))[:len(nr)]
    pfb, fb, nfb = _arr(prior_fb), _arr(fb_rev), _arr(next_fb)
    if len(pfb) != len(pr):
        pfb = (pfb + [0.0] * len(pr))[:len(pr)]
    if len(nfb) != len(nr):
        nfb = (nfb + [0.0] * len(nr))[:len(nr)]

    n = len(revenue)
    R = pr + list(revenue) + nr
    C = prc + list(costs) + nrc
    FB = pfb + (fb if fb else [0.0] * n) + nfb
    off = len(pr)
    s = wc_schedule(R, C, p, fb=FB)

    out = {k: (v[off:off + n] if isinstance(v, list) else v) for k, v in s.items()}
    # Saldo de IVA por pagar del mes anterior a cada mes del año. En el primer
    # mes de la ventana no hay anterior y vale 0; con año previo cargado, enero
    # sí arrastra el saldo real de diciembre.
    remitir = s["iva_net"]
    out["payable_prev"] = [(remitir[off + t - 1] if off + t - 1 >= 0 else 0.0)
                           for t in range(n)]
    return out


def compute_wc_model(revenue: list[float], costs: list[float], p: dict,
                     prior_rev: list[float] | None = None, prior_costs: list[float] | None = None,
                     next_rev: list[float] | None = None, next_costs: list[float] | None = None,
                     fb_rev: list[float] | None = None,
                     prior_fb: list[float] | None = None, next_fb: list[float] | None = None) -> dict:
    """Devuelve {row_key: [12]} para las 7 partidas WC desde el modelo de timing.

    Si se pasan ventas de años ADYACENTES (prior/next), corre la matriz sobre la
    VENTANA combinada [prior + este año + next] y devuelve la tajada de ESTE año →
    CONTINUIDAD de WC en el cruce de año: los anticipos de estadías de ene/feb del
    año siguiente caen en oct-dic de este año (y viceversa, este enero ya no los
    duplica porque entraron el año pasado). Sin prior/next = comportamiento 12m
    aislado de siempre (backward-compatible)."""
    def _arr(x): return [float(v) for v in (x or [])]
    pr, prc = _arr(prior_rev), _arr(prior_costs)
    nr, nrc = _arr(next_rev), _arr(next_costs)
    if len(prc) != len(pr): prc = (prc + [0.0] * len(pr))[:len(pr)]
    if len(nrc) != len(nr): nrc = (nrc + [0.0] * len(nr))[:len(nr)]
    R = pr + list(revenue) + nr
    C = prc + list(costs) + nrc
    off = len(pr)
    # A&B (revenue) por la misma ventana, para el 10% de servicio pass-through.
    pfb, fb, nfb = _arr(prior_fb), _arr(fb_rev), _arr(next_fb)
    if pfb and len(pfb) != len(pr): pfb = (pfb + [0.0] * len(pr))[:len(pr)]
    if nfb and len(nfb) != len(nr): nfb = (nfb + [0.0] * len(nr))[:len(nr)]
    if not pfb: pfb = [0.0] * len(pr)
    if not nfb: nfb = [0.0] * len(nr)
    FB = pfb + (fb if fb else [0.0] * len(revenue)) + nfb
    s = wc_schedule(R, C, p, fb=FB)
    return {k: s[k][off:off + len(revenue)] for k in _WC_KEYS}


# Mapeo de líneas del Balance Sheet (Summary) → partida del modelo + naturaleza.
# Cada delta del modelo se coloca en UNA línea; Caja es el plug que cuadra.
_BS_LINE_MAP = [
    ("a/r - travel agencies", "AR", "asset"),
    ("($) - banks", "CASH", "asset"),
    ("deposits (guests)", "DEPOSITS", "liab"),
    ("a/p - usd vendors", "AP", "liab"),
    ("taxes payable", "IVA", "liab"),
    ("capital reserves", "RESERVA", "liab"),
    ("other current liabilities", "ACCRUED", "liab"),
    ("payroll provisions", "ACCRUED", "liab"),
    ("service charge", "SERVICE", "liab"),
    ("servicio por pagar", "SERVICE", "liab"),
    ("10% servicio", "SERVICE", "liab"),
    ("ytd profit", "NETPROFIT", "equity"),
    ("ytd p&l", "NETPROFIT", "equity"),
]
# Activo fijo. Viene NETO (sin línea de depreciación acumulada), así que la
# depreciación del período se le resta a las líneas depreciables en proporción a
# su saldo, y el CapEx se le suma a mobiliario y equipo.
_BS_DEPRECIABLE = ("building", "edificio", "furniture", "mobiliario", "equip",
                   "vehicle", "vehículo", "vehiculo")
_BS_CAPEX_DESTINO = ("furniture", "mobiliario", "equip")

_BS_GRAND = {"total assets": "ASSET", "total liabilities": "LIABILITY",
             "capital & liab": "LIAB+EQ", "total liabilities and equity": "LIAB+EQ"}


def _bs_match(label: str):
    low = label.strip().lower()
    for key, src, nat in _BS_LINE_MAP:
        if low.startswith(key) or key in low:
            return src, nat
    return None, None


def project_full_balance_sheet(anchor_lines: list[dict], deltas: dict,
                               net_profit: list[float], horizon: int) -> dict:
    """Proyecta el Balance Sheet COMPLETO (estructura del subido) `horizon`
    meses. anchor_lines = último balance real [{label,section,is_total,usd}].
    deltas = {'AR','DEPOSITS','AP','IVA','ACCRUED','RENTA': [horizon]} (Δ saldo).
    Caja = plug que cuadra (net_profit + Δpasivos − Δactivos no-caja). Recalcula
    los totales por sección. Cuadra Total assets = Capital & Liab. cada mes."""
    base = [dict(l) for l in anchor_lines]
    # delta por línea para cada mes
    cols = []  # lista de dicts {label: usd} por mes (saldo proyectado)
    cur = {i: float(base[i]["usd"]) for i in range(len(base))}

    # ── Activo fijo ──────────────────────────────────────────────────────────
    # Antes quedaba CONGELADO: ni el CapEx sumaba ni la depreciación restaba. Y
    # como la utilidad neta que alimenta el patrimonio SÍ viene después de
    # depreciación, el balance bajaba el patrimonio sin bajar ningún activo — la
    # caja, que es el plug que cuadra, terminaba absorbiendo una salida que en la
    # realidad no ocurre. La depreciación no es caja.
    depreciables = [i for i, ln in enumerate(base)
                    if not ln["is_total"] and ln.get("section") == "ASSET"
                    and any(k in ln["label"].strip().lower() for k in _BS_DEPRECIABLE)]
    peso_total = sum(max(0.0, float(base[i]["usd"])) for i in depreciables)
    pesos = {i: (max(0.0, float(base[i]["usd"])) / peso_total if peso_total else 0.0)
             for i in depreciables}
    destino_capex = next(
        (i for i in depreciables
         if any(k in base[i]["label"].strip().lower() for k in _BS_CAPEX_DESTINO)),
        depreciables[0] if depreciables else None)
    idx_reserva = next((i for i, ln in enumerate(base)
                        if not ln["is_total"]
                        and ln["label"].strip().lower().startswith("capital reserve")), None)
    def gd(k, t):
        a = deltas.get(k, [])
        return a[t] if t < len(a) else 0.0
    for t in range(horizon):
        npft = net_profit[t] if t < len(net_profit) else 0.0
        dvals = {"AR": gd("AR", t), "DEPOSITS": gd("DEPOSITS", t), "AP": gd("AP", t),
                 "IVA": gd("IVA", t), "ACCRUED": gd("ACCRUED", t), "RENTA": gd("RENTA", t),
                 "SERVICE": gd("SERVICE", t), "NETPROFIT": npft, "RESERVA": 0.0}
        # Reserva de reposición: se aparta el 4% del revenue contra un pasivo y
        # el CapEx ejecutado la consume, hasta donde alcance. Mientras la reserva
        # se acumule sin gastarse, el pasivo crece — y con él el activo total.
        # Va ANTES del bucle: si se calcula después, el delta llega tarde y la
        # línea nunca se mueve.
        if idx_reserva is not None:
            aporte = gd("RESERVA", t)
            saldo = cur[idx_reserva] + aporte
            uso = min(max(0.0, gd("CAPEX", t)), max(0.0, saldo))
            dvals["RESERVA"] = aporte - uso
        # aplicar a líneas detalle; sumar solo lo que ATERRIZA en una línea
        applied_asset = applied_liab = applied_eq = 0.0
        cash_idx = None
        for i, ln in enumerate(base):
            if ln["is_total"]:
                continue
            src, nat = _bs_match(ln["label"])
            if src == "CASH":
                cash_idx = i
                continue
            if src and src in dvals:
                v = dvals[src]
                cur[i] += v
                if nat == "asset":
                    applied_asset += v
                elif nat == "liab":
                    applied_liab += v
                elif nat == "equity":
                    applied_eq += v
        # CapEx: entra al activo fijo. Depreciación: sale, repartida entre las
        # líneas depreciables según su peso (la tierra no se deprecia). Las dos
        # pasan por el plug de caja, así que el CapEx la baja y la depreciación
        # la devuelve — que es justo lo que corresponde: no es un desembolso.
        capex_t = gd("CAPEX", t)
        deprec_t = gd("DEPREC", t)
        if destino_capex is not None and capex_t:
            cur[destino_capex] += capex_t
            applied_asset += capex_t
            # El P&L DEDUCE el CapEx antes del EBT (EBITDA − capex − depreciación
            # = EBT), así que la utilidad neta que alimenta el patrimonio ya lo
            # descontó. Si acá se capitaliza además como activo, la caja —que es
            # el plug— lo pagaría DOS VECES. Se revierte el gasto contra el
            # patrimonio: el CapEx incrementa el activo y sale de caja una sola
            # vez. La depreciación no necesita esto: baja el activo y baja la
            # utilidad, que es lo correcto.
            applied_eq += capex_t
            for i, ln in enumerate(base):
                if not ln["is_total"] and _bs_match(ln["label"])[0] == "NETPROFIT":
                    cur[i] += capex_t
                    break
        if deprec_t:
            for i, w in pesos.items():
                cur[i] -= deprec_t * w
            applied_asset -= deprec_t

        # caja = plug que cuadra (solo con deltas aterrizados)
        if cash_idx is not None:
            cur[cash_idx] += applied_liab + applied_eq - applied_asset
        # recalcular totales (grand = suma de sección; subtotal = bloque corrido)
        running = 0.0
        sect_assets = sum(cur[i] for i, ln in enumerate(base)
                          if not ln["is_total"] and ln["section"] == "ASSET")
        sect_liab = sum(cur[i] for i, ln in enumerate(base)
                        if not ln["is_total"] and ln["section"] == "LIABILITY")
        sect_eq = sum(cur[i] for i, ln in enumerate(base)
                      if not ln["is_total"] and ln["section"] == "EQUITY")
        for i, ln in enumerate(base):
            if not ln["is_total"]:
                running += cur[i]
                continue
            low = ln["label"].strip().lower()
            grand = next((g for g in _BS_GRAND if low.startswith(g) or g in low), None)
            if grand == "total assets":
                cur[i] = sect_assets
            elif grand == "total liabilities":
                cur[i] = sect_liab
            elif grand and _BS_GRAND[grand] == "LIAB+EQ":
                cur[i] = sect_liab + sect_eq
            else:
                cur[i] = running     # subtotal de bloque
            running = 0.0
        cols.append({i: round(cur[i], 2) for i in range(len(base))})

    lines = []
    for i, ln in enumerate(base):
        lines.append({"label": ln["label"], "section": ln.get("section", ""),
                      "is_total": ln["is_total"], "indent": ln.get("indent", 0),
                      "anchor": round(float(ln["usd"]), 2),
                      "values": [cols[t][i] for t in range(horizon)]})
    return {"horizon": horizon, "lines": lines}


def project_balance_sheet(revenue: list[float], costs: list[float], p: dict,
                          months: int = 24, fb: list[float] | None = None) -> dict:
    """Balance Sheet PROYECTADO a `months` meses + WC variance, desde el modelo.
    Extiende el año 1 (revenue/costs) al año 2 con crecimiento growth_y2."""
    n1 = len(revenue)
    gy2 = float(_gp(p, "growth_y2"))
    def ext(a):
        out = list(a)
        while len(out) < months:
            out.append(a[len(out) % n1] * (1 + gy2))   # fallback: crecer por growth_y2
        return out[:months]
    # Si ya viene la serie completa (revenue real de años adyacentes), se usa tal
    # cual; si viene 1 año, se extiende por growth_y2 (fallback).
    R = list(revenue)[:months] if len(revenue) >= months else ext(revenue)
    C = list(costs)[:months] if len(costs) >= months else ext(costs)
    fb_in = list(fb) if fb else [0.0] * n1
    FB = fb_in[:months] if len(fb_in) >= months else ext(fb_in)
    s = wc_schedule(R, C, p, fb=FB)

    def roll(opening, deltas):
        bal, out = float(opening), []
        for d in deltas:
            bal += d
            out.append(round(bal, 2))
        return out

    # Saldos arrancan en 0: la proyección real ancla en el balance subido y solo
    # usa los Δ mensuales de abajo; estos balances son auxiliares/informativos.
    dep_bal = roll(0.0, [s["received"][t] - s["applied"][t] for t in range(months)])
    ar_bal = roll(0.0, [s["credit"][t] - s["ar_collected"][t] for t in range(months)])
    ap_bal = roll(0.0, s["WC_AP"])
    accr_bal = roll(0.0, s["WC_PROV"])
    iva_bal = roll(0.0, [s["WC_TAX"][t] for t in range(months)])
    renta_bal = roll(0.0, s["renta_ret"])
    svc_bal = roll(0.0, s["WC_SERVICE"])

    lines = [
        {"key": "DEPOSITS", "label": "Depósitos de huéspedes", "kind": "liability", "balance": dep_bal,
         "delta": [round(s["received"][t] - s["applied"][t], 2) for t in range(months)]},
        {"key": "AR", "label": "Cuentas por cobrar (A/R)", "kind": "asset", "balance": ar_bal,
         "delta": [round(s["credit"][t] - s["ar_collected"][t], 2) for t in range(months)]},
        {"key": "AP", "label": "Cuentas por pagar (A/P)", "kind": "liability", "balance": ap_bal,
         "delta": [round(x, 2) for x in s["WC_AP"]]},
        {"key": "ACCRUED", "label": "Provisión aguinaldo", "kind": "liability", "balance": accr_bal,
         "delta": [round(x, 2) for x in s["WC_PROV"]]},
        {"key": "IVA", "label": "IVA por pagar / crédito", "kind": "liability", "balance": iva_bal,
         "delta": [round(s["WC_TAX"][t], 2) for t in range(months)]},
        {"key": "RENTA", "label": "Crédito de Renta (retención tarjeta)", "kind": "asset", "balance": renta_bal,
         "delta": [round(x, 2) for x in s["renta_ret"]]},
        {"key": "SERVICE", "label": "Servicio F&B por pagar (10% empleados)", "kind": "liability", "balance": svc_bal,
         "delta": [round(x, 2) for x in s["WC_SERVICE"]]},
    ]
    # El rótulo sigue viajando (respaldo) y la clave se le suma cuando existe.
    for ln in lines:
        lk = _clave_fila(ln["label"])
        if lk:
            ln["label_key"] = lk
    return {"months": months, "lines": lines,
            "wc_movements": {k: [round(v, 2) for v in s[k]] for k in
                             ("WC_DEP_RECV", "WC_DEP_APPL", "WC_AR", "WC_AP", "WC_PROV", "WC_TAX", "WC_RENTTAX", "WC_SERVICE")}}


def _pl(monthly: dict, m: int, code: str) -> float:
    return float((monthly.get(m, {}) or {}).get(code, 0) or 0)


def compute_wc_calibration(balances: dict, revenue_by_month: dict, year: int) -> dict:
    """`balances` = {(year,month): {label_lower: usd}}. Calcula, por partida WC,
    el movimiento de caja YTD (Δ saldo × signo) y el % implícito sobre las
    ventas brutas del mismo período → guía para fijar el criterio."""
    def bal_at(ym, labels):
        d = balances.get(ym)
        if not d:
            return None
        tot, found = 0.0, False
        for lab in labels:
            for k, v in d.items():
                if k.startswith(lab):
                    tot += float(v or 0); found = True; break
        return tot if found else None

    months = sorted(m for (y, m) in balances if y == year)
    out = {}
    for key, (labels, sign) in WC_BALANCE_MAP.items():
        ytd = sales = 0.0
        n = 0
        for m in months:
            prev = (year, m - 1) if m > 1 else (year - 1, 12)
            b1, b0 = bal_at((year, m), labels), bal_at(prev, labels)
            if b1 is None or b0 is None:
                continue
            ytd += sign * (b1 - b0)
            sales += float(revenue_by_month.get(m, 0) or 0)
            n += 1
        out[key] = {"ytd": round(ytd, 2), "ytd_sales": round(sales, 2),
                    "implied_pct": (ytd / sales if sales else None), "months": n}
    return out


def wc_actuals_from_balances(balances: dict, year: int, through_month: int) -> dict:
    """Movimiento REAL de Working Capital por mes (1..through) desde los Δ del
    Balance Sheet. `balances` = {(year,month): {label_lower: usd}}. Devuelve
    {month: {row_key: cash_move}} con convención de caja (+ = entrada), usando
    WC_BALANCE_MAP (mismo mapeo/signos que la calibración). Solo emite un mes si
    hay balance del mes Y del anterior. Deposits sale NETO en WC_DEP_RECV (el
    balance no separa Recibidos/Aplicados) → WC_DEP_APPL y WC_RENTTAX = 0."""
    def bal_at(ym, labels):
        d = balances.get(ym)
        if not d:
            return None
        tot, found = 0.0, False
        for lab in labels:
            for k, v in d.items():
                if k.startswith(lab):
                    tot += float(v or 0); found = True; break
        return tot if found else None

    out: dict[int, dict] = {}
    for m in range(1, max(0, int(through_month)) + 1):
        prev = (year, m - 1) if m > 1 else (year - 1, 12)
        row, ok = {}, False
        for key, (labels, sign) in WC_BALANCE_MAP.items():
            b1, b0 = bal_at((year, m), labels), bal_at(prev, labels)
            if b1 is None or b0 is None:
                continue
            row[key] = sign * (b1 - b0)
            ok = True
        if ok:
            row.setdefault("WC_DEP_APPL", 0.0)
            row.setdefault("WC_RENTTAX", 0.0)
            out[m] = row
    return out


def _vals(inputs: dict, key: str) -> list[float]:
    raw = inputs.get(key) or []
    return [float(raw[i]) if i < len(raw) and raw[i] is not None else 0.0 for i in range(12)]


def _norm_label(s) -> str:
    return " ".join(str(s or "").strip().lower().split())


def overrides_from_version_rows(version_rows, months, allowed_keys=None):
    """Mapea las filas de una versión CONGELADA (por label → row_key de WC_ROWS)
    y arma el dict de overrides {row_key: {mes(str): valor}} para los `months`
    dados (1..12). Solo partidas de Working Capital por defecto — los signos del
    WC son compatibles entre la versión congelada y el modelo en vivo (a
    diferencia de CapEx, que invierte el signo). Devuelve (overrides, mapped,
    skipped) para reportar qué líneas se copiaron y cuáles no calzaron."""
    label_to_key = {_norm_label(lbl): k for k, lbl in WC_ROWS}
    allowed = set(allowed_keys) if allowed_keys else set(label_to_key.values())
    months = [m for m in months if 1 <= m <= 12]
    overrides: dict = {}
    mapped: list = []
    skipped: list = []
    for r in (version_rows or []):
        if r.get("is_total"):
            continue
        key = label_to_key.get(_norm_label(r.get("label")))
        sect = _norm_label(r.get("section"))
        is_wc_section = "working capital" in sect or "balance sheet" in sect
        if not key or key not in allowed:
            if is_wc_section and r.get("label"):
                skipped.append(r.get("label"))
            continue
        vals = r.get("values") or []
        cell = {}
        for m in months:
            if m - 1 < len(vals) and vals[m - 1] is not None:
                cell[str(m)] = round(float(vals[m - 1]), 2)
        if cell:
            overrides[key] = {**overrides.get(key, {}), **cell}
            mapped.append(r.get("label"))
    return overrides, mapped, skipped


def compute_cashflow_budget(monthly: dict, inputs: dict, opening_cash: float,
                            drivers: dict | None = None, wc_model: dict | None = None,
                            payroll: list[float] | None = None,
                            wc_actuals: dict | None = None,
                            cash_actuals: dict | None = None,
                            wc_window: dict | None = None,
                            wc_overrides: dict | None = None,
                            distributions_annual: float = 0.0,
                            renta_annual: float = 0.0,
                            renta_pay_month: int = 12) -> dict:
    """`monthly` = {month: {pl_code: amount}}. `inputs` = {row_key: [12 valores]}.
    `drivers` = {row_key: {'mode': 'manual'|'pct_sales', 'pct': float}} → si la
    partida es 'pct_sales', su valor mensual = pct × ventas brutas del mes
    (Revenue del P&L); si no, usa los valores manuales de `inputs`.
    `payroll` = planilla mensual (12); solo se usa para SACARLA de la base del
    modelo cuando la planilla NO es tercerizada (sin IVA, ver payroll_outsourced).
    Devuelve secciones con filas (values[12] + full_year) listas para render."""
    MONTHS = range(1, 13)
    drivers = drivers or {}
    revenue = [_pl(monthly, m, "TOTAL_REVENUES") for m in MONTHS]
    # revenue de A&B (REV_FB) — base del 10% de servicio de ley (pass-through).
    fb_rev = [_pl(monthly, m, "REV_FB") for m in MONTHS]
    # costos operativos (magnitud positiva) — base para A/P (modo días) e IVA.
    costs = [_pl(monthly, m, "TOTAL_OPEXP") + _pl(monthly, m, "TOTAL_OVERHEAD")
             + _pl(monthly, m, "TOTAL_NON_OP") for m in MONTHS]
    # modelo de timing WC (si está activo, calcula las partidas)
    wc_on = bool(wc_model and wc_model.get("enabled"))
    wc_params = (wc_model or {}).get("params", {})
    model_costs = wc_cost_base(costs, payroll, wc_params)
    ww = wc_window or {}
    wc_vals = compute_wc_model(
        revenue, model_costs, wc_params,
        prior_rev=ww.get("prior_rev"), prior_costs=ww.get("prior_costs"),
        next_rev=ww.get("next_rev"), next_costs=ww.get("next_costs"),
        fb_rev=fb_rev, prior_fb=ww.get("prior_fb"), next_fb=ww.get("next_fb"),
    ) if wc_on else {}

    def row(section, key, label, values, kind, editable=False, driver=None):
        d = {"section": section, "key": key, "label": label,
             "kind": kind, "editable": editable,
             "values": [round(v, 2) for v in values],
             "full_year": round(sum(values), 2)}
        # El `label` sigue siendo el respaldo; la clave viaja al lado cuando el
        # rótulo es una etiqueta fija de la pantalla (`cfbFila` en el catálogo).
        lk = _clave_fila(label)
        if lk:
            d["label_key"] = lk
        if driver is not None:
            md = driver.get("mode", "manual")
            d["mode"] = md
            d["pct"] = driver.get("pct")
            d["lag"] = driver.get("lag", 0)
            d["driven"] = md == "model" or (md in ("pct_sales", "days", "lead_lag") and driver.get("pct") is not None)
        return d

    def _days_series(key, days):
        base, sign = DAYS_BASE.get(key, ("sales", -1))
        b = costs if base == "costs" else revenue
        f = days / 30.0
        out = [0.0] * 12
        for i in range(1, 12):
            out[i] = sign * (b[i] - b[i - 1]) * f   # Δ del nivel × días/30 (Ene=0)
        return out

    def _leadlag_series(pct, lag):
        out = [0.0] * 12
        for i in range(12):
            j = i - int(lag)
            out[i] = pct * (revenue[j] if 0 <= j < 12 else 0.0)
        return out

    def input_values(key):
        """Devuelve (values[12], driver_info) según el modo del driver."""
        drv = drivers.get(key) or {"mode": "manual", "pct": None, "lag": 0}
        mode, pct, lag = drv.get("mode"), drv.get("pct"), drv.get("lag", 0)
        if pct is not None:
            if mode == "pct_sales":
                return [float(pct) * revenue[i] for i in range(12)], drv
            if mode == "days":
                return _days_series(key, float(pct)), drv
            if mode == "lead_lag":
                return _leadlag_series(float(pct), lag), drv
        return _vals(inputs, key), drv

    # Overrides manuales por celda (máxima precedencia: pisan modelo/real/input).
    # {row_key: {mes(1..12 como str o int): valor}}. Típicamente la COPIA de los
    # reales Ene–May de la versión congelada → esas celdas quedan fijas y editables.
    wc_overrides = wc_overrides or {}
    def _ovr(key, vals):
        ov = wc_overrides.get(key) or {}
        oms = []
        for mk, val in ov.items():
            try:
                m = int(mk)
            except (TypeError, ValueError):
                continue
            if 1 <= m <= 12 and val is not None:
                vals[m - 1] = float(val)
                oms.append(m)
        return vals, sorted(oms)

    rows = []

    # 1. OPERATING PERFORMANCE (del P&L) ──────────────────────────────────────
    # Se permite OVERRIDE por celda (p.ej. Non Allocated Expenses / below-GOP en
    # los meses cerrados Ene–May, donde el P&L forecast no lo tiene cargado). El
    # override pisa el valor del P&L y NOI lo refleja.
    op_vals = {}
    for key, label, code, sign in PL_ROWS:
        vals = [sign * _pl(monthly, m, code) for m in MONTHS]
        vals, oms = _ovr(key, vals)
        op_vals[key] = vals
        rr = row("Operating Performance", key, label, vals, "auto")
        if oms:
            rr["override_months"] = oms
        rows.append(rr)
    total_exp = [op_vals["OPEX"][i] + op_vals["OVERHEAD"][i] + op_vals["NONALLOC"][i] for i in range(12)]
    rows.append(row("Operating Performance", "TOTAL_EXPENSES", "Total Expenses", total_exp, "subtotal"))
    noi = [op_vals["REVENUE"][i] + total_exp[i] for i in range(12)]
    rows.append(row("Operating Performance", "NET_OPERATING_INCOME", "Subtotal #1 Net Operating Income", noi, "subtotal_strong"))

    # 2. PROJECTS / CAPEX ──────────────────────────────────────────────────────
    # La fila del 4% ahora SALE DEL P&L (CAPITAL_EXPENSE = reserva de capital +
    # capex mayor). Antes eran cuatro casillas tecleadas en cero: el mismo hotel
    # invertía $239,894 en el flujo directo —que sí lee CAPITAL_EXPENSE— y $0 acá,
    # y la fila se llamaba "4%" sin calcular ningún 4%.
    #
    # Queda NO editable pero con override por mes, como las de Working Capital:
    # el presupuesto arranca donde lo pone el revenue, y el gasto real —que nunca
    # es lineal— se re-perfila mes a mes sin perder de dónde salió el total.
    capex_subtotal = [0.0] * 12
    for key, label in CAPEX_ROWS:
        code = CAPEX_DESDE_PL.get(key)
        if code:
            vals = [_pl(monthly, m, code) for m in MONTHS]
            drv, editable = {"mode": "model", "pct": None}, False
        else:
            vals, drv = input_values(key)
            editable = True
        vals, oms = _ovr(key, vals)
        capex_subtotal = [capex_subtotal[i] + vals[i] for i in range(12)]
        rr = row("Projects / CapEx", key, label, vals, "input", editable=editable, driver=drv)
        if oms:
            rr["override_months"] = oms
        rows.append(rr)
    rows.append(row("Projects / CapEx", "SUBTOTAL_CAPEX", "Subtotal #2 Projects", capex_subtotal, "subtotal_strong"))

    # 3. BALANCE SHEET / WORKING CAPITAL (modelo de timing / input / driver) ───
    # En meses cerrados con balance real (wc_actuals) se usa el MOVIMIENTO REAL;
    # el modelo/driver solo aplica a los meses abiertos.
    wc_actuals = wc_actuals or {}
    actual_months = sorted(m for m in wc_actuals if 1 <= m <= 12)
    wc_subtotal = [0.0] * 12
    for key, label in WC_ROWS:
        if wc_on and key in wc_vals:
            vals, drv = list(wc_vals[key]), {"mode": "model", "pct": None}
            editable = False
        else:
            v, drv = input_values(key)
            vals, editable = list(v), True
        for m in actual_months:                       # superponer el real del balance
            if key in wc_actuals[m]:
                vals[m - 1] = float(wc_actuals[m][key])
        if actual_months:
            editable = False                          # los meses reales no se editan
        vals, oms = _ovr(key, vals)                   # override manual gana sobre todo
        r = row("Balance Sheet / Working Capital", key, label, vals, "input", editable=editable, driver=drv)
        r["actual_months"] = actual_months            # cuáles columnas son reales (cerradas)
        if oms:
            r["override_months"] = oms                # celdas con override manual (editables)
        rows.append(r)
        wc_subtotal = [wc_subtotal[i] + vals[i] for i in range(12)]
    rows.append(row("Balance Sheet / Working Capital", "SUBTOTAL_WC", "Subtotal #3 Balance Sheet Changes", wc_subtotal, "subtotal_strong"))

    # 4. OTHER CASH MOVEMENTS (input) ─────────────────────────────────────────
    other_subtotal = [0.0] * 12
    for key, label in OTHER_ROWS:
        vals, drv = input_values(key)
        # Las distribuciones a dueños YA existen como parámetro del escenario y las
        # usa el flujo indirecto; esta pantalla nunca las consultaba, así que el
        # dueño podía tenerlas cargadas y este reporte las ignoraba. Si la fila no
        # tiene nada tecleado, arranca del parámetro (sale en su mes de pago).
        # Impuesto de renta: la liquidación anual, en su mes de pago. Entra por
        # acá —y no como una línea propia del método directo— para que los dos
        # flujos vean la misma salida. Solo pasa si da A PAGAR: un saldo a favor
        # no es una entrada de caja, es un crédito que se arrastra.
        if key == "OTH_RENTA" and renta_annual > 0 and not any(vals):
            m = min(12, max(1, int(renta_pay_month or 12)))
            vals = [(-float(renta_annual) if i == m - 1 else 0.0) for i in range(12)]
            drv = {"mode": "model", "pct": None}
        if key == "OTH_CONTRIB" and distributions_annual and not any(vals):
            # En diciembre, igual que el flujo indirecto — así los dos reportes
            # dicen lo mismo sobre la misma plata.
            vals = [(-float(distributions_annual) if i == 11 else 0.0) for i in range(12)]
            drv = {"mode": "model", "pct": None}
        vals, oms = _ovr(key, vals)
        other_subtotal = [other_subtotal[i] + vals[i] for i in range(12)]
        rr = row("Other Cash Movements", key, label, vals, "input", editable=True, driver=drv)
        if oms:
            rr["override_months"] = oms
        rows.append(rr)

    # 4b. AJUSTE A CAJA REAL (meses cerrados) ─────────────────────────────────
    # En meses con caja real conocida (del Balance Sheet) la caja final se ANCLA
    # al banco real: recon = real − (cálculo bottom-up). Captura lo no modelado
    # (impuestos pagados, intereses, deuda, distribuciones, CapEx real). Meses
    # abiertos = 0 (forecast puro, arrancando desde la última caja real).
    cash_actuals = cash_actuals or {}
    # CapEx/Projects es SALIDA de caja: un gasto (valor positivo) REBAJA el efectivo
    # → se RESTA. (Un negativo = reverso/crédito → suma de vuelta.)
    bottomup = [noi[i] - capex_subtotal[i] + wc_subtotal[i] + other_subtotal[i] for i in range(12)]
    recon = [0.0] * 12
    cash_months = sorted(m for m in cash_actuals if 1 <= m <= 12)
    if cash_months:
        prev = float(opening_cash or 0)
        for i in range(12):
            base_end = prev + bottomup[i]
            if (i + 1) in cash_actuals:
                recon[i] = float(cash_actuals[i + 1]) - base_end
            prev = base_end + recon[i]
        rr = row("Other Cash Movements", "OTH_RECON",
                 "Ajuste a caja real (meses cerrados)", recon, "input", editable=False)
        rr["actual_months"] = cash_months
        rows.append(rr)
        other_subtotal = [other_subtotal[i] + recon[i] for i in range(12)]

    # 5. CASH FLOW ────────────────────────────────────────────────────────────
    # CapEx/Projects es SALIDA → se RESTA (un gasto positivo rebaja la caja).
    net_change = [noi[i] - capex_subtotal[i] + wc_subtotal[i] + other_subtotal[i] for i in range(12)]
    beginning, ending = [0.0] * 12, [0.0] * 12
    bal = float(opening_cash or 0)
    for i in range(12):
        beginning[i] = bal
        ending[i] = bal + net_change[i]
        bal = ending[i]
    rows.append(row("Cash Flow", "NET_CHANGE", "Net Change in Cash", net_change, "total"))
    # Beginning/Ending: full_year = enero inicial / diciembre final (no suma)
    rb = row("Cash Flow", "BEGINNING_CASH", "Beginning Cash", beginning, "total")
    rb["full_year"] = round(beginning[0], 2)
    rows.append(rb)
    re = row("Cash Flow", "ENDING_CASH", "Ending Cash", ending, "total_strong")
    re["full_year"] = round(ending[11], 2)
    rows.append(re)

    return {"opening_cash": round(float(opening_cash or 0), 2), "rows": rows}
