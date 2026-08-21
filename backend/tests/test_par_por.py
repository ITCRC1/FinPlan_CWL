"""
Tests for USALI per-room metrics (PAR/POR) — pl_engine.par_por.

Run: pytest tests/test_par_por.py -v

PAR = Per Available Room (amount / rooms_available)
POR = Per Occupied Room  (amount / rooms_occupied)
"""
from decimal import Decimal

from app.engine.pl_engine import par_por


def test_par_por_basic():
    par, por = par_por(Decimal("100000"), 4530, 2843)
    assert round(par, 2) == 22.08   # 100000 / 4530
    assert round(por, 2) == 35.17   # 100000 / 2843


def test_par_por_matches_ytd_rooms_line():
    # From the real YTD May 2026 report: Rooms revenue $1,706,130.10
    # over 4,530 available / 2,843 occupied → PAR $376.63, POR $600.12.
    par, por = par_por(Decimal("1706130.10"), 4530, 2843)
    assert round(par, 2) == 376.63
    assert round(por, 2) == 600.12


def test_par_por_zero_rooms_no_crash():
    # Closed period / empty scenario: divide-by-zero yields 0.0, never raises.
    assert par_por(Decimal("5000"), 0, 0) == (0.0, 0.0)
    par, por = par_por(Decimal("5000"), 100, 0)
    assert round(par, 2) == 50.0 and por == 0.0


def test_par_por_handles_none_and_floats():
    assert par_por(None, None, None) == (0.0, 0.0)
    par, por = par_por(1000.0, 100.0, 50.0)
    assert par == 10.0 and por == 20.0
