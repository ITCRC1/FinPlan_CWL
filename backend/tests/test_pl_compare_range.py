# -*- coding: utf-8 -*-
"""`/pl/compare-range/` — el rango arbitrario de meses (Q1..Q4) que pidió el
owner para el Performance Snapshot (`/operation-insight/summary`).

No agrega un endpoint con lógica nueva: filtra `monthly` al rango pedido y
llama al mismo `_aggregate_selected` que ya usan Mes/YTD/Full — por eso estos
tests solo fijan que el FILTRO de meses es el correcto (Q2 = abril, mayo,
junio; nunca enero ni julio), no que la agregación en sí funcione (eso ya lo
prueba `test_pl_ytd.py`).
"""
from app.api.pl_api import _aggregate_selected, _ebt_anual
from tests.test_pl_ytd import _month


def _rango(monthly, desde, hasta):
    sel = [m for m in monthly if desde <= m["month"] <= hasta]
    return _aggregate_selected(sel, ebt_anual=_ebt_anual(monthly))


def test_q2_toma_solo_abril_mayo_junio():
    monthly = [_month(m, 10000 * m, 900, 500) for m in range(1, 13)]
    q2 = _rango(monthly, 4, 6)
    rooms = next(l for l in q2["lines"] if l["line_code"] == "REV_ROOMS")
    assert rooms["amount_usd"] == (40000 + 50000 + 60000)   # abril+mayo+junio
    assert q2["kpis"]["rooms_available"] == 900 * 3
    assert q2["kpis"]["rooms_occupied"] == 500 * 3


def test_q1_no_arrastra_los_demas_meses():
    monthly = [_month(1, 100000, 930, 600), _month(2, 900000, 930, 600),
               _month(3, 100000, 930, 600), _month(4, 999999, 930, 600)]
    q1 = _rango(monthly, 1, 3)
    rooms = next(l for l in q1["lines"] if l["line_code"] == "REV_ROOMS")
    assert rooms["amount_usd"] == 100000 + 900000 + 100000   # NO 999999 de abril


def test_full_year_range_igual_al_agregado_de_los_doce_meses():
    """Rango 1..12 = lo mismo que `_aggregate(monthly, 12)` — la identidad que
    el front usa para NO pedir este endpoint cuando el período es Full Year."""
    from app.api.pl_api import _aggregate
    monthly = [_month(m, 10000 * m, 900, 500) for m in range(1, 13)]
    rango = _rango(monthly, 1, 12)
    full = _aggregate(monthly, 12)
    rooms_r = next(l for l in rango["lines"] if l["line_code"] == "REV_ROOMS")
    rooms_f = next(l for l in full["lines"] if l["line_code"] == "REV_ROOMS")
    assert rooms_r["amount_usd"] == rooms_f["amount_usd"]
