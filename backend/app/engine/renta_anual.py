"""Impuesto sobre la renta de la empresa — liquidación anual.

Se paga el 30% sobre la utilidad antes de impuesto, y contra ese monto se
acreditan las retenciones que le practicaron al hotel durante el año: el 2.5%
que el adquirente retiene sobre los cobros con tarjeta.

De ahí salen dos resultados distintos y el signo importa:

  · **A pagar** — el impuesto supera las retenciones. Es una salida de caja real
    en el mes de la liquidación.
  · **Saldo a favor** — las retenciones superaron al impuesto. NO es una entrada
    de caja: es un crédito que se arrastra al período siguiente. Por eso al flujo
    solo baja el caso a pagar, y el crédito queda informado.

Puro: sin DB, sin FastAPI.
"""
from __future__ import annotations

TASA_RENTA_CR = 0.30
MES_PAGO_POR_DEFECTO = 3   # la liquidación se paga en marzo del año siguiente


def _pl(monthly: dict, code: str) -> float:
    """Suma anual de una línea del P&L mensual {mes: {codigo: monto}}."""
    return sum(float((monthly.get(m, {}) or {}).get(code, 0) or 0)
               for m in range(1, 13))


def renta_liquidacion(monthly: dict, criterios: dict | None = None,
                      creditos_tarjeta: float = 0.0) -> dict:
    """Liquidación anual del impuesto sobre la renta.

    `monthly` = {mes: {line_code: monto}} del P&L. `criterios` puede traer
    `renta_tasa`, `renta_pasa_flujo`, `renta_mes_pago` y `card_renta_ret`.
    """
    c = criterios or {}
    tasa = float(c.get("renta_tasa", TASA_RENTA_CR) or 0)
    mes = min(12, max(1, int(c.get("renta_mes_pago", MES_PAGO_POR_DEFECTO) or 3)))
    # El impuesto que se calcula sobre la utilidad de ESTE año se paga en marzo
    # del año SIGUIENTE: no es caja de este flujo. Lo que sí sale este año es la
    # liquidación del año ANTERIOR, que es otro cálculo y otro P&L. Por eso el
    # monto que baja al flujo se carga a mano.
    pago_manual = float(c.get("renta_pago_manual", 0) or 0)

    # La utilidad antes de impuesto. Si el escenario no emite EBT se reconstruye
    # con la utilidad neta más el impuesto que el propio P&L ya calculó, para no
    # quedarse en cero por una diferencia de vocabulario.
    ebt = _pl(monthly, "EBT")
    if abs(ebt) < 0.005:
        ebt = _pl(monthly, "NET_PROFIT") + _pl(monthly, "INCOME_TAXES")

    impuesto = max(0.0, ebt * tasa)      # sobre pérdida no se paga renta
    # Crédito: la retención de Renta sobre los cobros con tarjeta que ya le
    # descontaron al hotel durante el año. La calcula el modelo de capital de
    # trabajo (partida WC_RENTTAX) y entra por parámetro para no recalcularla acá
    # con otra base — sería otra fuente de verdad para el mismo número.
    creditos = float(creditos_tarjeta or 0)
    neto = impuesto - creditos

    return {
        "tasa": tasa,
        "ebt": round(ebt, 2),
        "impuesto_bruto": round(impuesto, 2),
        "creditos_tarjeta": round(creditos, 2),
        "neto": round(neto, 2),
        "a_pagar": round(max(0.0, neto), 2),
        "saldo_a_favor": round(max(0.0, -neto), 2),
        "mes_pago": mes,
        "pago_manual": round(pago_manual, 2),
        # Lo que EFECTIVAMENTE baja al flujo: el monto cargado a mano. Un saldo a
        # favor no se carga nunca — un crédito no es caja que entra.
        "pasa_al_flujo": round(max(0.0, pago_manual), 2),
    }
