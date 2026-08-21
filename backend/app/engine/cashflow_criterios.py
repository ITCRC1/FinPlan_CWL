"""Criterios del Cash Flow — FUENTE ÚNICA para los dos métodos.

El sistema tenía dos tablas de defaults independientes (`WC_MODEL_DEFAULTS` en el
indirecto y `DIRECT_DEFAULTS` en el directo) y una herencia parcial de cinco
parámetros entre pantallas. El mismo concepto tenía dos valores:

    ap_same_pct     0.60 (indirecto)  vs  0.70 (directo)
    card_iva_ret    0.025             vs  0.0
    card_renta_ret  0.025             vs  0.0
    card_comision   fuera del modelo  vs  0.0195
    payroll_outsourced  True          vs  no existía (se comportaba como False)

y seis criterios de la hoja de Criterios (retención de anticipos, servicio F&B y
su rezago, planilla tercerizada, aguinaldo y su mes de pago) no llegaban al
directo. Además el interruptor «Modelo de timing ACTIVO» apagaba solo el
indirecto.

Este módulo declara **un default por concepto** y resuelve los criterios
efectivos de un escenario. Los dos motores consumen la misma resolución a través
de `vista_indirecto` / `vista_directo`, que solo traducen nombres — no deciden
nada. `divergencias()` reporta cualquier criterio compartido que haya quedado
distinto, para que la brecha nunca vuelva a abrirse en silencio.

Puro: sin DB, sin FastAPI. El cargador con sesión vive en
`app/api/_cashflow_criterios.py`.
"""
from __future__ import annotations

# Un default por CONCEPTO. Donde los dos motores traían valores distintos, gana
# el criterio declarado por el owner (ver comentarios).
CRITERIOS_DEFAULTS: dict = {
    # ── Interruptor ──────────────────────────────────────────────────────────
    # Apaga el modelo de timing en LOS DOS métodos. Antes solo apagaba el
    # indirecto: el directo leía los params sin mirar este flag, así que con el
    # modelo apagado una pantalla cobraba con la matriz y la otra no.
    "enabled": False,

    # ── Cobro ────────────────────────────────────────────────────────────────
    "retention": 0.05,          # retención de anticipos (se libera al mes sig.)
    "card_pct": 0.70,           # % del cobro que entra por tarjeta
    "card_iva_ret": 0.025,      # retención de IVA sobre el cobro con tarjeta
    "card_renta_ret": 0.025,    # retención de Renta sobre el cobro con tarjeta
    # La comisión bancaria YA está en el P&L (cuenta 7120, CC Commissions) y por
    # lo tanto ya bajó el NOI. El directo la volvía a restar: era doble conteo.
    "card_comision": 0.0,

    # ── Servicio F&B 10% de ley (pass-through a empleados) ───────────────────
    "service_rate": 0.10,
    "service_lag": 1,

    # ── IVA · A/P ────────────────────────────────────────────────────────────
    "iva_rate": 0.13,
    # 60/40 es el criterio que declaró el owner en la hoja de Criterios. El 0.70
    # del directo era un residuo del port desde Luz de Mono.
    "ap_same_pct": 0.60,
    "payroll_outsourced": True,
    "iva_lag": 1,               # meses hasta liquidar el IVA al gobierno

    # ── Aguinaldo ────────────────────────────────────────────────────────────
    "aguinaldo_monthly": 8300.0,   # respaldo si el escenario no tiene planilla
    "aguinaldo_pay_month": 12,

    # ── Derivación de la matriz (solo si no hay matriz explícita) ────────────
    "mix_nrr": 0.10, "mix_credit": 0.10,
    "mix_flex": [0.30, 0.20, 0.30, 0.30, 0.20, 0.30,
                 0.30, 0.20, 0.30, 0.30, 0.20, 0.30],
    "lead_nrr": 2, "lead_flex": 1, "lag_credit": 1,

    # ── Proyección del balance ───────────────────────────────────────────────
    "growth_y2": 0.07,

    # ── Nómina (los usa el directo para desglosar; el indirecto la trae del P&L) ──
    "ccss_rate": 0.2683,        # carga PATRONAL (la paga el hotel, va al costo)
    # Deducción OBRERA de CCSS: 5.50% SEM + 4.17% IVM + 1.00% Banco Popular. La
    # paga el empleado — el hotel la retiene del salario y la remite. No es costo
    # adicional: sale de adentro del bruto. El sistema no la tenía en ningún lado
    # (los 17 conceptos de planilla son todos costo patronal), así que la planilla
    # neta se venía calculando restándole al salario la carga PATRONAL, que no es
    # una deducción del empleado.
    "ccss_obrera_rate": 0.1067,
    "retencion_rate": 0.0,      # retención de renta al empleado (por tramos)

    # ── Impuesto sobre la renta de la empresa (liquidación anual) ────────────
    "renta_tasa": 0.30,
    # La liquidación de ESTE año se paga en marzo del SIGUIENTE, así que no es
    # caja de este flujo. Lo que sale este año es la del año anterior, y ese
    # monto se carga a mano.
    "renta_pago_manual": 0.0,
    "renta_mes_pago": 3,

    # ── Legado del directo, solo activo sin matriz de timing ─────────────────
    "credit_pct": 0.0,
}

# Claves que solo tienen sentido en un método. Todo lo demás es COMPARTIDO y
# tiene que valer exactamente lo mismo en los dos.
SOLO_INDIRECTO = frozenset({"mix_nrr", "mix_credit", "mix_flex",
                            "lead_nrr", "lead_flex", "lag_credit", "growth_y2"})
SOLO_DIRECTO = frozenset({"ccss_rate", "ccss_obrera_rate",
                          "retencion_rate", "credit_pct",
                          "tramos_renta", "renta_deduce_ccss",
                          "renta_tasa", "renta_pago_manual", "renta_mes_pago"})
COMPARTIDOS = frozenset(CRITERIOS_DEFAULTS) - SOLO_INDIRECTO - SOLO_DIRECTO

# Valores DERIVADOS: se calculan en cada carga y no son configuración. Si se
# persisten, congelan el escenario (fue exactamente lo que pasó: guardar la
# pantalla del directo grababa la matriz heredada, y desde ese momento la
# condición `if "timing_matrix" not in params` no se cumplía nunca más y la
# pantalla dejaba de seguir a la hoja de Criterios).
DERIVADOS = frozenset({"timing_matrix", "timing_matrix_prev", "timing_matrix_next",
                       "rev_prev", "rev_next", "aguinaldo_series", "honorarios_pct"})

# Marca opcional dentro de los params del directo: lista de criterios compartidos
# que esa pantalla pisa a propósito. Sin la marca, un valor guardado ahí se trata
# como eco del default viejo y NO pisa el criterio compartido.
MARCA_OVERRIDE = "_overrides_explicitos"

# Defaults viejos del motor directo — se conservan solo para reconocer ecos.
_DIRECT_LEGACY = {
    "iva_rate": 0.13, "credit_pct": 0.0, "card_pct": 0.70, "card_renta_ret": 0.0,
    "card_iva_ret": 0.0, "card_comision": 0.0195, "ap_same_pct": 0.70,
    "honorarios_pct": 0.05, "ccss_rate": 0.2683, "retencion_rate": 0.0,
    "seguros_pay_months": [6, 12], "iva_lag": 1, "aguinaldo_pay_month": 12,
}


def _mismo(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_mismo(x, y) for x, y in zip(a, b))
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return a == b


def resolver(wc_enabled: bool | None = None,
             wc_params: dict | None = None,
             directo_params: dict | None = None,
             extras: dict | None = None) -> dict:
    """Criterios efectivos del escenario. Precedencia, de menor a mayor:

        CRITERIOS_DEFAULTS  <  extras  <  wc_params  <  overrides del directo

    `wc_params` es la hoja de Criterios: manda sobre todo lo compartido.
    `directo_params` solo gana en dos casos: claves de `SOLO_DIRECTO`, o claves
    listadas en `_overrides_explicitos`. Un valor guardado en la pantalla del
    directo que coincide con el default viejo del motor se descarta como eco.
    `extras` trae lo que se calcula al vuelo (aguinaldo real de la planilla,
    ventas de años vecinos, honorarios del P&L).
    """
    c = dict(CRITERIOS_DEFAULTS)
    wcp = dict(wc_params or {})
    dp = dict(directo_params or {})

    for k, v in (extras or {}).items():
        if v is not None:
            c[k] = v

    for k, v in wcp.items():
        if k.startswith("_") or v is None:
            continue
        c[k] = v

    explicitos = set(dp.get(MARCA_OVERRIDE) or [])
    for k, v in dp.items():
        if k.startswith("_") or k in DERIVADOS or v is None:
            continue          # los derivados JAMÁS se leen de lo guardado
        if k in SOLO_DIRECTO or k in explicitos:
            c[k] = v
            continue
        # Compartido sin marca: solo se respeta si NO es el eco de un default viejo
        # y la hoja de Criterios no dice nada sobre esa clave.
        if k not in wcp and k in _DIRECT_LEGACY and not _mismo(v, _DIRECT_LEGACY[k]):
            c[k] = v

    if wc_enabled is not None:
        c["enabled"] = bool(wc_enabled)
    return c


def vista_indirecto(c: dict) -> dict:
    """Params tal como los espera `engine/cashflow_budget`. Solo traduce."""
    return dict(c)


def vista_directo(c: dict) -> dict:
    """Params tal como los espera `engine/cashflow_directo`. Solo traduce."""
    return dict(c)


def divergencias(c: dict, wc_params: dict | None, directo_params: dict | None) -> list[dict]:
    """Criterios COMPARTIDOS que quedaron distintos entre las dos pantallas.

    Alimenta el panel de conciliación y el test de regresión: si esta lista no
    está vacía, los dos métodos están calculando con criterios distintos y
    cualquier brecha de caja es, en parte, ruido de configuración.
    """
    wcp, dp = dict(wc_params or {}), dict(directo_params or {})
    explicitos = set(dp.get(MARCA_OVERRIDE) or [])
    out = []
    for k in sorted(COMPARTIDOS):
        if k not in wcp or k not in dp:
            continue
        if _mismo(wcp[k], dp[k]):
            continue
        out.append({
            "clave": k,
            "criterios": wcp[k],
            "directo": dp[k],
            "efectivo": c.get(k),
            "motivo": ("override explícito de la pantalla del directo"
                       if k in explicitos else
                       "valor viejo guardado en la pantalla del directo — se ignora"),
        })
    return out


def avisos_matriz(matriz) -> list[dict]:
    """Filas de la matriz de timing que no reparten exactamente el 100% de la
    venta. No se normaliza en silencio: el número malo está en los Criterios y
    hay que arreglarlo ahí, no taparlo en el motor."""
    out = []
    for i, fila in enumerate(matriz or []):
        s = sum(float(x or 0) for x in fila)
        if abs(s - 1.0) > 0.0005:
            out.append({"mes": i + 1, "suma": round(s, 4)})
    return out
