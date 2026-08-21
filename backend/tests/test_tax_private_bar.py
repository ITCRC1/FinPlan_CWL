# -*- coding: utf-8 -*-
"""
EL PRIVATE BAR SE COBRA TODO CON TARJETA, Y NO SE CUENTA DOS VECES.

Decisión del owner (2026-08-12): el consumo del Private Bar se cobra entero con
tarjeta → `card_pct_private_bar = 1.00`.

Antes de tener línea propia caía en el residual «otros», al 60%. Y como esa
venta se codificaba dentro de A&B —que está al 70%—, sacar el `0121` de F&B le
había BAJADO el porcentaje sin que nada avisara. No mueve el EBT ni el impuesto
bruto: mueve la retención acumulada, que es crédito contra el impuesto, así que
sube el impuesto neto a pagar.

**La trampa que cuida la segunda prueba:** `other` es un RESIDUAL
(`total − las nombradas`), no una línea. Toda línea que se saque a porcentaje
propio hay que restarla del residual, o se cobra dos veces —una en su línea y
otra dentro de «otros»— y la retención sale inflada. Nada lo delataría:
`card_revenue` no tiene contra qué cuadrar y el total de ingresos no se toca.
"""
from app.engine.tax import calculate_tax

PARAMS = {"wh_rate": 0.025, "income_tax_rate": 0.30,
          "card_pct_rooms": 0.90, "card_pct_fb": 0.70, "card_pct_spa": 0.80,
          "card_pct_tours": 0.75, "card_pct_private_bar": 1.00,
          "card_pct_other": 0.60}


def _mes(month, rooms=0, fb=0, spa=0, tours=0, private_bar=0, total=None, ebt=0):
    total = total if total is not None else rooms + fb + spa + tours + private_bar
    return {"month": month, "lines": {
        "REV_ROOMS": rooms, "REV_FB": fb, "REV_SPA": spa, "REV_TOURS": tours,
        "REV_PRIVATE_BAR": private_bar, "TOTAL_REVENUES": total, "EBT": ebt}}


def test_el_private_bar_va_al_cien_por_ciento():
    """50k de bar, nada más: los 50k enteros son cobro con tarjeta."""
    monthly = [_mes(1, private_bar=50000, total=50000)] + [_mes(m) for m in range(2, 13)]
    t = calculate_tax(monthly, PARAMS)
    assert t["monthly"][0]["card_revenue"] == 50000.0
    assert t["cumulative_wh"] == 1250.0        # 50,000 × 2.5%


def test_no_se_cuenta_dos_veces_dentro_de_otros():
    """El residual tiene que EXCLUIR al Private Bar.

    Rooms 60k @90% = 54,000 · Private Bar 10k @100% = 10,000 ·
    resto 30k @60% = 18,000  →  82,000.
    Si el bar no se restara del residual, «otros» valdría 40k y daría 88,000.
    """
    monthly = [_mes(1, rooms=60000, private_bar=10000, total=100000)] + \
              [_mes(m) for m in range(2, 13)]
    t = calculate_tax(monthly, PARAMS)
    assert t["monthly"][0]["card_revenue"] == 82000.0


def test_sin_private_bar_nada_cambia():
    """Un escenario sin la línea da exactamente lo mismo que antes del cambio.

    Es la garantía de que agregar el porcentaje no movió ningún número viejo:
    rooms 60k @90% + resto 40k @60% = 78,000, igual que test_tax.py.
    """
    monthly = [_mes(1, rooms=60000, total=100000)] + [_mes(m) for m in range(2, 13)]
    t = calculate_tax(monthly, PARAMS)
    assert t["monthly"][0]["card_revenue"] == 78000.0


def test_el_default_es_cien_aunque_no_venga_el_parametro():
    """Un escenario viejo, sin el campo en sus params, igual cobra el bar al 100%."""
    viejos = {"wh_rate": 0.025, "card_pct_rooms": 0.90, "card_pct_other": 0.60,
              "card_pct_fb": 0.70, "card_pct_spa": 0.80, "card_pct_tours": 0.75}
    monthly = [_mes(1, private_bar=20000, total=20000)] + [_mes(m) for m in range(2, 13)]
    t = calculate_tax(monthly, viejos)
    assert t["monthly"][0]["card_revenue"] == 20000.0
