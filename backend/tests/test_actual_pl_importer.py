"""
Tests for app/importers/actual_pl_importer pure helpers (no Excel file needed).
The end-to-end parse is validated manually against the CWL working workbook
(Budget 2025W tab); see the Phase 9 notes.
Run: pytest tests/test_actual_pl_importer.py -v
"""
from app.importers.actual_pl_importer import (
    dept_code_for_name, _norm_account, VERSION_BLOCKS,
)
from app.importers.actual_workbook_loader import BLOCK_TO_SCENARIO, _is_all_zero


def test_dept_code_for_name_keywords():
    assert dept_code_for_name("Departamento de Habitaciones") == "0110"
    assert dept_code_for_name("Departamento de A&B") == "0120"
    assert dept_code_for_name("Departamento de Tours") == "0150"
    assert dept_code_for_name("Departamento de Transportation") == "0152"
    assert dept_code_for_name("Departamento de Lavanderia") == "0161"
    assert dept_code_for_name("Departamento de Cafeteria") == "0220"
    assert dept_code_for_name("Departamento de TI") == "0230"
    assert dept_code_for_name("Departamento de Administracion") == "0180"


def test_dept_code_for_name_unknown_is_blank():
    assert dept_code_for_name("Departamento Inventado XYZ") == ""
    assert dept_code_for_name(None) == ""


def test_norm_account():
    assert _norm_account("4000") == "4000"
    assert _norm_account(6020) == "6020"
    assert _norm_account(6020.0) == "6020"
    assert _norm_account("4900") == "4900"
    assert _norm_account("Gl Account") is None
    assert _norm_account(None) is None
    assert _norm_account("") is None
    assert _norm_account("123") is None      # not a 4xxx-9xxx USALI code


def test_version_blocks_cover_six_versions():
    assert set(VERSION_BLOCKS) == {
        "ACTUAL_2024", "ACTUAL_2025", "ACTUAL_2026",
        "FORECAST_2026", "FORECAST_APR_2026", "BUDGET_2026",
    }
    # ACTUAL 2026 is Jan-May only (5 months)
    assert VERSION_BLOCKS["ACTUAL_2026"][3] == 5


def test_block_to_scenario_covers_all_blocks():
    assert set(BLOCK_TO_SCENARIO) == set(VERSION_BLOCKS)
    assert BLOCK_TO_SCENARIO["ACTUAL_2024"] == ("ACTUAL", 2024, "actual")
    assert BLOCK_TO_SCENARIO["BUDGET_2026"][0] == "BUDGET"
    assert BLOCK_TO_SCENARIO["FORECAST_APR_2026"][0] == "FORECAST"


def test_is_all_zero():
    z = {m: 0 for m in ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]}
    assert _is_all_zero(z) is True
    z["mar"] = 5
    assert _is_all_zero(z) is False
