"""
Tests for the YTD / Full Year aggregator (A2) — pl_api._aggregate.

Run: pytest tests/test_pl_ytd.py -v
"""
from decimal import Decimal

from app.engine.pl_engine import PLLineResult
from app.api.pl_api import _aggregate, _aggregate_selected, _apply_tax_correction


def _month(m, rooms_rev, rooms_avail, rooms_occ, ebt=0.0, tax=0.0, adr=None):
    lines = [
        PLLineResult("REV_ROOMS", "Rooms", "REVENUES", Decimal(str(rooms_rev))),
        PLLineResult("EBT", "EBT", "TOTALS", Decimal(str(ebt))),
        PLLineResult("INCOME_TAXES", "Income Taxes", "TOTALS", Decimal(str(tax))),
        PLLineResult("NET_PROFIT", "Net Profit", "TOTALS", Decimal(str(ebt - tax))),
    ]
    kpis = {"rooms_available": rooms_avail, "rooms_occupied": rooms_occ, "guests": 0.0}
    if adr is not None:
        kpis["adr"] = adr
    return {"month": m, "kpis": kpis, "lines": lines}


def test_ytd_sums_lines_and_kpis():
    monthly = [
        _month(1, 100000, 930, 600),
        _month(2, 120000, 840, 650),
        _month(3, 110000, 930, 620),
    ] + [_month(m, 0, 0, 0) for m in range(4, 13)]

    agg = _aggregate(monthly, 3)  # YTD through March
    rooms = next(l for l in agg["lines"] if l["line_code"] == "REV_ROOMS")
    assert rooms["amount_usd"] == 330000.0
    assert agg["kpis"]["rooms_available"] == 2700
    assert agg["kpis"]["rooms_occupied"] == 1870
    # Sin ADR en las estadísticas cae a la derivación de la línea (ver
    # test_adr_sale_de_las_estadisticas para el camino normal).
    assert round(agg["kpis"]["adr"], 2) == round(330000 / 1870, 2)
    assert round(rooms["par"], 2) == round(330000 / 2700, 2)
    assert round(rooms["por"], 2) == round(330000 / 1870, 2)


def test_full_year_is_through_12():
    monthly = [_month(m, 10000, 100, 50) for m in range(1, 13)]
    agg = _aggregate(monthly, 12)
    rooms = next(l for l in agg["lines"] if l["line_code"] == "REV_ROOMS")
    assert rooms["amount_usd"] == 120000.0
    assert agg["kpis"]["rooms_available"] == 1200


def test_tax_correction_applied_to_aggregate():
    # EBT positive, no GL tax posting → 30% applied.
    monthly = [_month(1, 0, 100, 50, ebt=100000, tax=0.0)] + \
              [_month(m, 0, 0, 0) for m in range(2, 13)]
    agg = _aggregate(monthly, 12)
    tax = next(l for l in agg["lines"] if l["line_code"] == "INCOME_TAXES")
    assert tax["amount_usd"] == 30000.0


def test_single_month_is_not_cumulative():
    # The compare endpoint's "month" column = just that month, not YTD.
    monthly = [
        _month(1, 100000, 930, 600),
        _month(2, 120000, 840, 650),
        _month(3, 110000, 930, 620),
    ] + [_month(m, 0, 0, 0) for m in range(4, 13)]
    feb = _aggregate_selected([m for m in monthly if m["month"] == 2])
    rooms = next(l for l in feb["lines"] if l["line_code"] == "REV_ROOMS")
    assert rooms["amount_usd"] == 120000.0          # February alone
    assert feb["kpis"]["rooms_available"] == 840


def test_tax_correction_skips_when_real_posting():
    amounts = {"EBT": 100000.0, "INCOME_TAXES": -5000.0, "NET_PROFIT": 105000.0}
    _apply_tax_correction(amounts)
    assert amounts["INCOME_TAXES"] == -5000.0  # real GL credit preserved


def test_adr_sale_de_las_estadisticas_no_de_la_linea():
    """El ADR NO se deriva de REV_ROOMS cuando hay estadísticas cargadas.

    El owner abrió el room revenue en 4000 Room Revenue + 4001 Cancellations +
    4002 No Show, y las tres consolidan en REV_ROOMS. Un no-show no ocupa
    habitación: si el ADR saliera de la línea consolidada, subiría solo — y en
    silencio, porque el ADR no tiene contra qué cuadrar.

    Acá REV_ROOMS trae 200,000 (con cancelaciones y no-show adentro) pero el ADR
    cargado dice 100: el agregado tiene que respetar el 100, no dar 200,000/1000.
    """
    monthly = [
        _month(1, 120000, 900, 600, adr=100.0),
        _month(2,  80000, 900, 400, adr=100.0),
    ]
    agg = _aggregate(monthly, 2)
    assert agg["kpis"]["rooms_occupied"] == 1000
    assert round(agg["kpis"]["adr"], 2) == 100.00        # no 200.00
    # y RevPAR mantiene la identidad ADR x ocupación
    assert round(agg["kpis"]["revpar"], 4) == round(100.0 * 1000 / 1800, 4)


def test_el_adr_agregado_pondera_por_noches_ocupadas():
    """Un mes lleno no puede pesar lo mismo que uno casi vacío."""
    monthly = [
        _month(1, 0, 900, 900, adr=100.0),   # mes lleno, ADR 100
        _month(2, 0, 900, 100, adr=300.0),   # mes flojo, ADR 300
    ]
    agg = _aggregate(monthly, 2)
    esperado = (100.0 * 900 + 300.0 * 100) / 1000        # 120, no 200
    assert round(agg["kpis"]["adr"], 2) == round(esperado, 2)
