"""
Panorama fiscal (Fase D2) — retención de tarjetas + impuesto de renta.

Puro: recibe los montos por línea por mes + params, no toca DB.

Por mes: cobro con tarjeta = Σ(línea × card_pct) → retención = cobro × wh_rate.
Anual: impuesto bruto = max(0, EBT × tasa). Crédito = retención acumulada.
Impuesto neto = max(0, bruto − retención). Saldo a favor = max(0, retención − bruto).
"""


def _f(d: dict, code: str) -> float:
    return float(d.get(code, 0) or 0)


def calculate_tax(monthly: list[dict], params: dict) -> dict:
    wh_rate = float(params.get("wh_rate", 0.025) or 0)
    tax_rate = float(params.get("income_tax_rate", 0.30) or 0)
    p_rooms = float(params.get("card_pct_rooms", 0.90) or 0)
    p_fb = float(params.get("card_pct_fb", 0.70) or 0)
    p_spa = float(params.get("card_pct_spa", 0.80) or 0)
    p_tours = float(params.get("card_pct_tours", 0.75) or 0)
    p_private_bar = float(params.get("card_pct_private_bar", 1.00) or 0)
    p_other = float(params.get("card_pct_other", 0.60) or 0)

    monthly_wh = []
    cumulative = 0.0
    annual_ebt = 0.0
    annual_rev = 0.0
    for m in monthly:
        lines = m["lines"]
        # ⚠️ Las FAMILIAS completas, no la línea suelta. Desde que el ingreso
        # quedó partido (2026-08-14) `REV_ROOMS` es solo la cta 4000 y `REV_FB`
        # solo la comida: `REV_ROOMS_OTHER`, `REV_FB_BEV` y `REV_FB_MISC` caían
        # en el residual `other` y se cobraban al 60% en vez del 90% y el 70%
        # que les toca. La retención bajó sola, sin que nadie tocara la
        # parametría y sin nada contra qué cuadrarlo.
        #
        # El docstring de este archivo advertía la versión INVERSA del error
        # —sacar una línea a porcentaje propio y no restarla del residual—.
        # Este es el otro lado: se agregaron líneas a una familia y no se
        # sumaron a la familia.
        rooms = sum(_f(lines, c) for c in ("REV_ROOMS", "REV_ROOMS_OTHER"))
        fb = sum(_f(lines, c) for c in ("REV_FB", "REV_FB_BEV", "REV_FB_MISC"))
        spa = _f(lines, "REV_SPA")
        tours = _f(lines, "REV_TOURS")
        private_bar = _f(lines, "REV_PRIVATE_BAR")
        total = _f(lines, "TOTAL_REVENUES")
        # 'other' es un RESIDUAL, no una línea: es todo lo que no se nombró arriba.
        # Cada línea que se saca a porcentaje propio HAY que restarla acá, o se
        # cobra dos veces —una en su línea y otra dentro del residual— y la
        # retención sale inflada. Nada lo delataría: `card_revenue` no tiene
        # contra qué cuadrar y el total de ingresos no se toca.
        other = total - (rooms + fb + spa + tours + private_bar)
        card_rev = (rooms * p_rooms + fb * p_fb + spa * p_spa + tours * p_tours
                    + private_bar * p_private_bar + other * p_other)
        wh = card_rev * wh_rate
        cumulative += wh
        annual_ebt += _f(lines, "EBT")
        annual_rev += total
        monthly_wh.append({"month": m["month"], "card_revenue": round(card_rev, 2),
                           "withholding": round(wh, 2)})

    gross_tax = max(0.0, annual_ebt * tax_rate)
    net_tax = max(0.0, gross_tax - cumulative)
    credit_balance = max(0.0, cumulative - gross_tax)
    effective_rate = (net_tax / annual_rev) if annual_rev else 0.0
    return {
        "monthly": monthly_wh,
        "cumulative_wh": round(cumulative, 2),
        "annual_ebt": round(annual_ebt, 2),
        "annual_revenue": round(annual_rev, 2),
        "gross_income_tax": round(gross_tax, 2),
        "wh_credit": round(-cumulative, 2),
        "net_income_tax": round(net_tax, 2),
        "credit_balance": round(credit_balance, 2),
        "effective_tax_rate": round(effective_rate, 4),
    }
