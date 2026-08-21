"""
Tests for Phase 4 — Payroll Checkbook.

Unit tests (no DB):
  - calc_sw: CRC salary conversion, USD passthrough, FTE=0
  - calc_base: all 7 concepts included
  - recalculate_entry: 6020 and 6021 always automatic
  - manual concepts survive recalc
  - FTE validation
  - build_fte_report: aggregation, FTE=0 still visible

Integration tests (require Codificacion Excel):
  - import_codificacion: 49 unique positions imported
  - all devengados depts present (0150, 0123, 0220, etc.)
  - October FTE defaults to 0.0
  - position names are clean strings
"""
import pytest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

from app.engine.payroll_calculator import (
    calc_sw, calc_base, recalculate_entry,
    build_fte_report, summarize_dept, total_entry,
    CCSS_RATE,
)
from app.models.payroll_position import PayrollPosition, get_fte
from app.models.payroll_concept_entry import PayrollConceptEntry


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_position(
    salary_amount=Decimal("650000"),
    salary_currency="CRC",
    fte_jan=Decimal("1.0"),
    fte_feb=Decimal("1.0"),
    fte_oct=Decimal("0.0"),
    dept_code="0150",
):
    pos = MagicMock(spec=PayrollPosition)
    pos.salary_amount = Decimal(str(salary_amount))
    pos.salary_currency = salary_currency
    pos.dept_code = dept_code
    pos.scenario_id = "test-scenario"
    fte_attrs = {
        "fte_jan": Decimal(str(fte_jan)),
        "fte_feb": Decimal(str(fte_feb)),
        "fte_mar": Decimal("1.0"),
        "fte_apr": Decimal("1.0"),
        "fte_may": Decimal("1.0"),
        "fte_jun": Decimal("1.0"),
        "fte_jul": Decimal("1.0"),
        "fte_aug": Decimal("1.0"),
        "fte_sep": Decimal("1.0"),
        "fte_oct": Decimal(str(fte_oct)),
        "fte_nov": Decimal("1.0"),
        "fte_dec": Decimal("1.0"),
    }
    for attr, val in fte_attrs.items():
        setattr(pos, attr, val)
    return pos


def make_entry(
    sw=Decimal("0"),
    overtime=Decimal("0"),
    day_off=Decimal("0"),
    working_holiday=Decimal("0"),
    commissions=Decimal("0"),
    vacations_taken=Decimal("0"),
    incentive_bonus=Decimal("0"),
    disabilities=Decimal("0"),
    cafeteria=Decimal("0"),
    housing=Decimal("0"),
    month=1,
    dept_code="0150",
):
    entry = MagicMock(spec=PayrollConceptEntry)
    entry.c6000_sw = Decimal(str(sw))
    entry.c6001_overtime = Decimal(str(overtime))
    entry.c6002_day_off = Decimal(str(day_off))
    entry.c6003_working_holiday = Decimal(str(working_holiday))
    entry.c6010_commissions = Decimal(str(commissions))
    entry.c6024_vacations_taken = Decimal(str(vacations_taken))
    entry.c6027_incentive_bonus = Decimal(str(incentive_bonus))
    entry.c6020_ccss = Decimal("0")
    entry.c6021_aguinaldo = Decimal("0")
    entry.c6004_disabilities = Decimal(str(disabilities))
    entry.c6022_occ_hazard = Decimal("0")
    entry.c6023_vacation_prov = Decimal("0")
    entry.c6025_cafeteria = Decimal(str(cafeteria))
    entry.c6026_severance = Decimal("0")
    entry.c6028_housing = Decimal(str(housing))
    entry.c6029_transport = Decimal("0")
    entry.c6030_other = Decimal("0")
    entry.month = month
    entry.dept_code = dept_code
    return entry


# ── Unit tests ─────────────────────────────────────────────────────────────────

class TestCalcSW:
    def test_crc_salary_converted_by_tc(self):
        pos = make_position(salary_amount="650000", salary_currency="CRC", fte_jan="1.0")
        tc = Decimal("530")
        sw = calc_sw(pos, 1, tc)
        expected = (Decimal("650000") / Decimal("530")).quantize(Decimal("0.01"))
        assert float(sw) == pytest.approx(float(expected), rel=0.001)

    def test_usd_salary_no_tc_needed(self):
        pos = make_position(salary_amount="2500", salary_currency="USD", fte_jan="1.0")
        sw = calc_sw(pos, 1, Decimal("530"))  # TC ignored for USD
        assert sw == pytest.approx(2500.0, rel=0.001)

    def test_fte_half_halves_sw(self):
        pos = make_position(salary_amount="1000", salary_currency="USD", fte_jan="0.5")
        sw = calc_sw(pos, 1, Decimal("530"))
        assert sw == pytest.approx(500.0, rel=0.001)

    def test_fte_zero_returns_zero(self):
        pos = make_position(salary_amount="650000", salary_currency="CRC", fte_oct="0.0")
        sw = calc_sw(pos, 10, Decimal("530"))  # October
        assert sw == Decimal("0")

    def test_crc_tc_zero_raises(self):
        pos = make_position(salary_amount="650000", salary_currency="CRC", fte_jan="1.0")
        with pytest.raises(ValueError, match="zero"):
            calc_sw(pos, 1, Decimal("0"))


class TestCalcBase:
    def test_base_includes_all_7_concepts(self):
        entry = make_entry(
            sw="1000", overtime="150", day_off="50",
            working_holiday="30", commissions="200",
            vacations_taken="80", incentive_bonus="100"
        )
        base = calc_base(entry)
        assert base == Decimal("1610")

    def test_base_sw_only(self):
        entry = make_entry(sw="1226.42")
        base = calc_base(entry)
        assert base == Decimal("1226.42")

    def test_base_zero_when_all_zero(self):
        entry = make_entry()
        assert calc_base(entry) == Decimal("0")


class TestRecalculateEntry:
    def test_6020_is_base_times_ccss_rate(self):
        pos = make_position(salary_amount="1000", salary_currency="USD", fte_jan="1.0")
        entry = make_entry(sw="1000", overtime="150", incentive_bonus="100")
        # base = 1250
        recalculate_entry(entry, pos, 1, Decimal("530"))
        base = Decimal("1250")
        expected_ccss = (base * CCSS_RATE).quantize(Decimal("0.01"))
        assert entry.c6020_ccss == expected_ccss
        assert float(entry.c6020_ccss) == pytest.approx(float(expected_ccss), rel=0.001)

    def test_6021_is_base_divided_by_12(self):
        pos = make_position(salary_amount="1200", salary_currency="USD", fte_jan="1.0")
        entry = make_entry(sw="1200")
        recalculate_entry(entry, pos, 1, Decimal("530"))
        expected_agu = (Decimal("1200") / Decimal("12")).quantize(Decimal("0.01"))
        assert entry.c6021_aguinaldo == pytest.approx(float(expected_agu), rel=0.001)
        assert entry.c6021_aguinaldo == pytest.approx(100.0, rel=0.001)

    def test_manual_concepts_preserved_after_recalc(self):
        pos = make_position(salary_amount="800000", salary_currency="CRC", fte_jan="1.0")
        entry = make_entry(disabilities="50", cafeteria="30", housing="200")
        recalculate_entry(entry, pos, 1, Decimal("530"))
        # Manual fields must not change
        assert entry.c6004_disabilities == Decimal("50")
        assert entry.c6025_cafeteria == Decimal("30")
        assert entry.c6028_housing == Decimal("200")

    def test_fte_zero_means_sw_zero_means_ccss_zero(self):
        pos = make_position(salary_amount="650000", salary_currency="CRC", fte_oct="0.0")
        entry = make_entry(month=10)
        recalculate_entry(entry, pos, 10, Decimal("530"))
        assert entry.c6000_sw == Decimal("0")
        assert entry.c6020_ccss == Decimal("0")
        assert entry.c6021_aguinaldo == Decimal("0")

    def test_custom_rates_override_defaults(self):
        """Params por escenario: un ccss_rate / aguinaldo_divisor custom se aplica."""
        pos = make_position(salary_amount="1000", salary_currency="USD", fte_jan="1.0")
        entry = make_entry(sw="1000")  # base = 1000
        recalculate_entry(entry, pos, 1, Decimal("530"),
                          ccss_rate=Decimal("0.30"), aguinaldo_divisor=Decimal("13"))
        assert entry.c6020_ccss == Decimal("300.00")            # 1000 × 0.30
        assert entry.c6021_aguinaldo == (Decimal("1000") / Decimal("13")).quantize(Decimal("0.01"))

    def test_default_rates_unchanged(self):
        """Sin params → mismos resultados históricos (sin regresión)."""
        pos = make_position(salary_amount="1000", salary_currency="USD", fte_jan="1.0")
        entry = make_entry(sw="1000")
        recalculate_entry(entry, pos, 1, Decimal("530"))
        assert entry.c6020_ccss == Decimal("268.30")            # 1000 × 0.2683
        assert entry.c6021_aguinaldo == Decimal("83.33")        # 1000 / 12

    def test_ccss_based_on_all_7_base_concepts(self):
        """CCSS is 26.83% of BASE, not just SW. Tests the full base formula."""
        pos = make_position(salary_amount="1000", salary_currency="USD", fte_jan="1.0")
        entry = make_entry(
            sw="1000", overtime="150", day_off="50",
            working_holiday="30", commissions="200",
            vacations_taken="80", incentive_bonus="100"
        )
        # base = 1610
        recalculate_entry(entry, pos, 1, Decimal("530"))
        expected = (Decimal("1610") * Decimal("0.2683")).quantize(Decimal("0.01"))
        assert float(entry.c6020_ccss) == pytest.approx(float(expected), rel=0.001)
        # Sanity: should be ~431.97, NOT 268.30 (which would be only SW)
        assert float(entry.c6020_ccss) > 400.0


class TestFTEReport:
    def _make_positions(self):
        positions = []
        depts = ["0150", "0113", "0111"]
        for dept in depts:
            for i in range(2):
                pos = make_position(dept_code=dept, fte_jan="1.0", fte_oct="0.0")
                pos.dept_code = dept
                positions.append(pos)
        return positions

    def test_fte_zero_still_visible_in_report(self):
        pos = make_position(fte_oct="0.0")
        pos.dept_code = "0150"
        report = build_fte_report([pos])
        # October appears with 0.0 — position is not hidden
        assert "0150" in report.by_dept
        assert report.by_dept["0150"][10] == Decimal("0.0")

    def test_totals_aggregate_all_depts(self):
        positions = self._make_positions()
        report = build_fte_report(positions)
        # 3 depts × 2 positions = 6 FTE in Jan
        assert float(report.totals[1]) == pytest.approx(6.0)
        # October = 0 for all
        assert float(report.totals[10]) == pytest.approx(0.0)

    def test_annual_avg_is_sum_over_12(self):
        pos = make_position(fte_oct="0.0")
        pos.dept_code = "0150"
        report = build_fte_report([pos])
        # 11 months at 1.0 + 1 month at 0.0 = 11/12
        expected = Decimal("11") / Decimal("12")
        assert float(report.annual_avg["0150"]) == pytest.approx(float(expected), rel=0.001)


class TestSummarizeDept:
    def test_totals_sum_across_positions(self):
        # Use MagicMock entries directly — summarize_dept only reads attributes
        e1 = make_entry(sw="1000", overtime="100", month=1, dept_code="0150")
        e2 = make_entry(sw="900", overtime="50", month=1, dept_code="0150")
        s = summarize_dept([e1, e2], "0150", 1, 2026)
        assert s.c6000 == Decimal("1900")
        assert s.c6001 == Decimal("150")
        assert s.base == Decimal("2050")


# ── Integration tests (require Excel file) ────────────────────────────────────

from tests._rutas import DATOS
CODIFICACION_PATH = DATOS / "Codificacion Planilla 11 de febrero 0850am (enviado).xlsx"


@pytest.mark.skipif(
    not CODIFICACION_PATH.exists(),
    reason="Codificacion Planilla Excel not found",
)
class TestCodificacionImporter:
    def _import(self):
        from app.importers.codificacion_importer import import_codificacion
        return import_codificacion(str(CODIFICACION_PATH), "test-scenario", "CWL")

    def test_imports_49_unique_positions(self):
        positions = self._import()
        assert len(positions) == 49

    def test_all_expected_depts_present(self):
        positions = self._import()
        dept_codes = {p.dept_code for p in positions}
        expected = {"0150", "0123", "0122", "0220", "0182", "0113", "0161",
                    "0200", "0132", "0152", "0230", "0183", "0114", "0190",
                    "0181", "0111", "0112", "0186"}
        for dept in expected:
            assert dept in dept_codes, f"Dept {dept} missing from imported positions"

    def test_october_fte_defaults_to_zero(self):
        positions = self._import()
        assert all(p.fte_oct == Decimal("0.0") for p in positions)

    def test_other_months_fte_is_one(self):
        positions = self._import()
        assert all(p.fte_jan == Decimal("1.0") for p in positions)
        assert all(p.fte_dec == Decimal("1.0") for p in positions)

    def test_salary_amount_zero_vacante(self):
        """All imported positions are templates — no salary amounts yet."""
        positions = self._import()
        assert all(p.salary_amount == Decimal("0") for p in positions)
        assert all(p.employee_name == "VACANTE" for p in positions)

    def test_position_names_are_strings(self):
        positions = self._import()
        assert all(isinstance(p.position_name, str) for p in positions)
        assert all(len(p.position_name) > 0 for p in positions)

    def test_tours_has_captain_de_barco(self):
        positions = self._import()
        tours = [p for p in positions if p.dept_code == "0150"]
        names = [p.position_name for p in tours]
        assert any("CAPITAN" in n.upper() for n in names), f"Captain not found in: {names}"

    def test_scenario_id_assigned(self):
        positions = self._import()
        assert all(p.scenario_id == "test-scenario" for p in positions)

    def test_dept_codes_zero_padded(self):
        """All dept_codes must be exactly 4 chars (zero-padded)."""
        positions = self._import()
        assert all(len(p.dept_code) == 4 for p in positions)
