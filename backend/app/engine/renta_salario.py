"""Impuesto al salario (renta al trabajo) de Costa Rica — cálculo POR PERSONA.

El impuesto es progresivo por tramos y **mensual**, así que no se puede sacar con
un porcentaje plano sobre la planilla: dos hoteles con la misma masa salarial
pagan distinto según cómo esté repartida. Una plantilla de muchos salarios bajos
puede quedar entera exenta mientras que unos pocos sueldos altos concentran toda
la retención. Por eso hay que recorrer empleado por empleado y mes por mes.

La base gravable es el ingreso del mes de esa persona: salario, horas extra,
día libre, feriado trabajado, comisiones, vacaciones tomadas y bonificaciones —
los mismos siete conceptos que forman la base de cotización (`calc_base`).

Los tramos vienen en COLONES y la planilla del sistema está en dólares, así que
la conversión usa el tipo de cambio del mes. Un tramo aplicado sobre el monto en
dólares daría cualquier cosa.

Puro: sin DB, sin FastAPI.
"""
from __future__ import annotations

# Tramos vigentes 2026 (₡ por mes). Cada tramo cobra su tasa SOBRE EL EXCESO del
# piso, no sobre el total: alguien que gana ₡1,000,000 paga 10% de ₡82,000, no
# 10% de ₡1,000,000.
TRAMOS_CR_2026: list[dict] = [
    {"desde": 0,         "hasta": 918_000,   "tasa": 0.00},
    {"desde": 918_000,   "hasta": 1_347_000, "tasa": 0.10},
    {"desde": 1_347_000, "hasta": 2_364_000, "tasa": 0.15},
    {"desde": 2_364_000, "hasta": 4_727_000, "tasa": 0.20},
    {"desde": 4_727_000, "hasta": None,      "tasa": 0.25},
]

# La CCSS obrera se resta de la base antes de aplicar los tramos: la ley permite
# deducir las cotizaciones obligatorias a la seguridad social. Es un criterio
# editable porque si el owner prefiere calcular sobre el bruto, el número cambia.
DEDUCIR_CCSS_POR_DEFECTO = True


def normalizar_tramos(crudo) -> list[dict]:
    """Sanea los tramos que vengan de la configuración. Devuelve la tabla oficial
    si lo que llega no sirve — mejor el default vigente que un cálculo mudo."""
    if not isinstance(crudo, (list, tuple)) or not crudo:
        return [dict(t) for t in TRAMOS_CR_2026]
    out = []
    for t in crudo:
        if not isinstance(t, dict):
            continue
        try:
            desde = float(t.get("desde") or 0)
            hasta = t.get("hasta")
            hasta = float(hasta) if hasta not in (None, "") else None
            tasa = float(t.get("tasa") or 0)
        except (TypeError, ValueError):
            continue
        out.append({"desde": desde, "hasta": hasta, "tasa": tasa})
    if not out:
        return [dict(t) for t in TRAMOS_CR_2026]
    return sorted(out, key=lambda t: t["desde"])


def impuesto_mensual(base_crc: float, tramos: list[dict] | None = None) -> float:
    """Impuesto del mes en colones para una base gravable en colones."""
    if base_crc <= 0:
        return 0.0
    tabla = normalizar_tramos(tramos)
    total = 0.0
    for t in tabla:
        if base_crc <= t["desde"]:
            break
        techo = t["hasta"] if t["hasta"] is not None else base_crc
        gravado = min(base_crc, techo) - t["desde"]
        if gravado > 0:
            total += gravado * t["tasa"]
    return total


def tramo_de(base_crc: float, tramos: list[dict] | None = None) -> int:
    """En qué tramo cae la base (1..n). Sirve para mostrarlo en pantalla."""
    tabla = normalizar_tramos(tramos)
    for i, t in enumerate(tabla):
        techo = t["hasta"]
        if techo is None or base_crc <= techo:
            return i + 1
    return len(tabla)


def retencion_persona(base_usd: float, tc: float, tramos: list[dict] | None = None,
                      ccss_obrera_rate: float = 0.0,
                      deducir_ccss: bool = DEDUCIR_CCSS_POR_DEFECTO) -> dict:
    """Retención de un empleado en un mes.

    `base_usd` = ingreso gravable del mes (salario + extras + comisiones +
    vacaciones tomadas + bonificaciones). Devuelve el detalle en colones y en
    dólares, más el tramo, para que la pantalla pueda mostrar de dónde sale.
    """
    tc = float(tc or 0)
    if tc <= 0 or base_usd <= 0:
        return {"base_usd": round(max(0.0, base_usd), 2), "base_crc": 0.0,
                "ccss_obrera_crc": 0.0, "gravable_crc": 0.0,
                "tramo": 1, "impuesto_crc": 0.0, "impuesto_usd": 0.0,
                "tasa_efectiva": 0.0}
    base_crc = base_usd * tc
    ccss_crc = base_crc * float(ccss_obrera_rate or 0) if deducir_ccss else 0.0
    gravable = max(0.0, base_crc - ccss_crc)
    imp_crc = impuesto_mensual(gravable, tramos)
    return {
        "base_usd": round(base_usd, 2),
        "base_crc": round(base_crc, 2),
        "ccss_obrera_crc": round(ccss_crc, 2),
        "gravable_crc": round(gravable, 2),
        "tramo": tramo_de(gravable, tramos),
        "impuesto_crc": round(imp_crc, 2),
        "impuesto_usd": round(imp_crc / tc, 2),
        "tasa_efectiva": round(imp_crc / base_crc, 6) if base_crc else 0.0,
    }


def resumen_tramos(tramos: list[dict] | None = None) -> list[dict]:
    """La tabla lista para mostrar, con la etiqueta de cada tramo."""
    tabla = normalizar_tramos(tramos)
    out = []
    for i, t in enumerate(tabla):
        if t["tasa"] == 0:
            etiqueta = f"Hasta ₡{t['hasta']:,.0f}: exento"
        elif t["hasta"] is None:
            etiqueta = (f"Más de ₡{t['desde']:,.0f}: {t['tasa'] * 100:.0f}% "
                        f"sobre el exceso")
        else:
            etiqueta = (f"De ₡{t['desde'] + 1:,.0f} a ₡{t['hasta']:,.0f}: "
                        f"{t['tasa'] * 100:.0f}% sobre el exceso de ₡{t['desde']:,.0f}")
        out.append({**t, "n": i + 1, "etiqueta": etiqueta})
    return out
