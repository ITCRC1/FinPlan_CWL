"""
Tests for Phase 6 OPEX importer.

Validation values cross-checked against GRAN TOTAL 2026 rows in Excel files:
  ROOMS Jan 2026 = 10859.484...
  F&B   Jan 2026 = 5360.0
  MAINT Jan 2026 = 18925.0
"""
import os
from decimal import Decimal
from pathlib import Path

import pytest

from tests._rutas import DATOS as BASE_DIR
SCENARIO_ID = "test-opex-scenario"
HOTEL_ID = "CWL"


@pytest.fixture(scope="module")
def entries():
    from app.importers.opex_importer import import_opex_for_scenario
    result = import_opex_for_scenario(SCENARIO_ID, HOTEL_ID, BASE_DIR)
    if not result:
        pytest.skip("Archivos Excel OPEX no presentes en este entorno (definir DATA_DIR para habilitar)")
    return result


def test_import_returns_entries(entries):
    assert len(entries) > 0, "No OPEX entries imported"


def test_rooms_jan_total(entries):
    """Sum of Jan values for dept 0110 should match GRAN TOTAL 2026 ~10859.48."""
    rooms = [e for e in entries if e.dept_code == "0110"]
    assert rooms, "No ROOMS entries imported"
    total_jan = sum(e.jan for e in rooms)
    assert abs(float(total_jan) - 10859.48) < 0.10, f"ROOMS Jan = {total_jan}"


def test_fb_jan_total(entries):
    """Sum of Jan values for dept 0120 should match GRAN TOTAL 2026 = 5360."""
    fb = [e for e in entries if e.dept_code == "0120"]
    assert fb, "No F&B entries imported"
    total_jan = sum(e.jan for e in fb)
    assert abs(float(total_jan) - 5360.0) < 0.01, f"F&B Jan = {total_jan}"


def test_maint_jan_total(entries):
    """Sum of Jan values for dept 0200 should match GRAN TOTAL 2026 = 18925."""
    maint = [e for e in entries if e.dept_code == "0200"]
    assert maint, "No MAINT entries imported"
    total_jan = sum(e.jan for e in maint)
    assert abs(float(total_jan) - 18925.0) < 0.01, f"MAINT Jan = {total_jan}"


def test_all_entries_have_valid_account_codes(entries):
    """Every entry should have a numeric account_code (7xxx)."""
    for e in entries:
        assert e.account_code.isdigit(), f"Non-numeric account_code: {e.account_code!r}"
        assert 7000 <= int(e.account_code) <= 8999, \
            f"Out-of-range account_code: {e.account_code}"


def test_no_entry_has_all_zero_months(entries):
    """Importer skips entirely-zero rows — every imported entry has at least one non-zero month."""
    for e in entries:
        month_sum = sum(e.get_month(m) for m in range(1, 13))
        assert month_sum > 0, f"All-zero entry: {e.dept_code}/{e.account_code}/{e.detail_code}"


def test_scenario_id_is_set(entries):
    """All entries must carry the scenario_id passed to the importer."""
    for e in entries:
        assert e.scenario_id == SCENARIO_ID


def test_hotel_id_is_set(entries):
    for e in entries:
        assert e.hotel_id == HOTEL_ID
