"""
Tests for per-room-type revenue detail (A3) — revenue_calculator.room_type_breakdown.

Run: pytest tests/test_room_type_breakdown.py -v
"""
from decimal import Decimal
from types import SimpleNamespace

from app.engine.revenue_calculator import room_type_breakdown


def rc(rt_id, net_rate, pax=2):
    return SimpleNamespace(room_type_id=rt_id, net_rate=Decimal(str(net_rate)),
                           pax_per_room=Decimal(str(pax)))


def ob(rt_id, occ):
    return SimpleNamespace(room_type_id=rt_id, rooms_occupied=Decimal(str(occ)))


def test_breakdown_matches_real_treehouse_jan():
    # Treehouse king: 5 units, 129 occupied nights in January, net ~757.68.
    rows = room_type_breakdown(
        month=1,
        rate_cards=[rc("TH", 757.68)],
        occ_budgets=[ob("TH", 129)],
        room_type_units={"TH": 5},
    )
    r = rows[0]
    assert r["nights_available"] == 155          # 5 units × 31 days
    assert r["nights_occupied"] == 129.0
    assert round(r["occupancy_pct"], 3) == 0.832  # 129/155
    assert round(r["revenue"], 2) == 97740.72     # 129 × 757.68
    assert round(r["adr"], 2) == 757.68
    assert r["pax"] == 258.0                       # 129 × 2


def test_breakdown_missing_rate_or_occ_is_zero():
    rows = room_type_breakdown(
        month=2,  # 28 days
        rate_cards=[],          # no rate card
        occ_budgets=[],         # no occupancy
        room_type_units={"X": 3},
    )
    r = rows[0]
    assert r["nights_available"] == 84   # 3 × 28
    assert r["nights_occupied"] == 0.0
    assert r["revenue"] == 0.0
    assert r["adr"] == 0.0
    assert r["occupancy_pct"] == 0.0


def test_breakdown_preserves_unit_order():
    rows = room_type_breakdown(
        month=1,
        rate_cards=[rc("A", 100), rc("B", 200)],
        occ_budgets=[ob("A", 10), ob("B", 20)],
        room_type_units={"B": 1, "A": 1},  # B first
    )
    assert [r["room_type_id"] for r in rows] == ["B", "A"]
