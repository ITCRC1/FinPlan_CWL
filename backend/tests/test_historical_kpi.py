"""
Tests de la Fase 3 — Historical KPIs (actuals 2024/2025).

Valores de referencia (Budget2026_Revenue_CORCO.xlsx → hoja 'Rooms'):
  2024 Enero: available=930, occupied=429, guests=711, occ≈46.13%, ADR≈359.84, rev≈154,371.56
  2025 Enero: available=930, occupied=454, rev≈214,971.95, ADR≈473.51
  RevPAR = revenue / rooms_available  (derivado, no está en el Excel)
"""
import pytest
from decimal import Decimal
from pathlib import Path

from app.importers.historical_kpi_importer import import_historical_kpi

from tests._rutas import DATOS
EXCEL_PATH = DATOS / "Budget2026_Revenue_CORCO.xlsx"

pytestmark = pytest.mark.skipif(not EXCEL_PATH.exists(), reason="Excel file not available")


def _by(records, year, month):
    return next(r for r in records if r.year == year and r.month == month)


def test_imports_two_years_full():
    recs = import_historical_kpi(EXCEL_PATH, "CWL")
    assert len(recs) == 24  # 2 years × 12 months
    assert {r.year for r in recs} == {2024, 2025}
    assert sorted({r.month for r in recs}) == list(range(1, 13))
    assert all(r.hotel_id == "CWL" and r.room_type_id == 0 for r in recs)
    assert all(r.source == "ACTUAL_IMPORT" for r in recs)


def test_jan_2024_values():
    r = _by(import_historical_kpi(EXCEL_PATH, "CWL"), 2024, 1)
    assert r.rooms_available == 930
    assert r.rooms_occupied == Decimal("429")
    assert r.guests == Decimal("711")
    assert float(r.occupancy_pct) == pytest.approx(0.4613, abs=0.001)
    assert float(r.adr_usd) == pytest.approx(359.84, abs=0.5)
    assert float(r.revenue_usd) == pytest.approx(154371.56, rel=0.001)


def test_jan_2025_values():
    r = _by(import_historical_kpi(EXCEL_PATH, "CWL"), 2025, 1)
    assert r.rooms_available == 930
    assert r.rooms_occupied == Decimal("454")
    assert float(r.revenue_usd) == pytest.approx(214971.95, rel=0.001)
    assert float(r.adr_usd) == pytest.approx(473.51, abs=0.5)


def test_revpar_is_revenue_over_available():
    r = _by(import_historical_kpi(EXCEL_PATH, "CWL"), 2024, 1)
    expected = Decimal("154371.56") / Decimal("930")
    assert float(r.revpar_usd) == pytest.approx(float(expected), rel=0.001)


def test_adr_consistent_with_revenue_over_occupied():
    """ADR del Excel debe cuadrar con revenue / rooms_occupied."""
    r = _by(import_historical_kpi(EXCEL_PATH, "CWL"), 2025, 1)
    derived = r.revenue_usd / r.rooms_occupied
    assert float(r.adr_usd) == pytest.approx(float(derived), rel=0.005)
