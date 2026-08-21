"""
Tests for the ACTUALS P&L path — app/engine/pl_engine.build_actual_inputs
+ calculate_full_pl with real (NonOpActuals) non-operating amounts.
Run: pytest tests/test_actuals_pl.py -v
"""
from decimal import Decimal

from app.engine.pl_engine import (
    build_actual_inputs,
    calculate_full_pl,
    get_line,
    revenue_line_for_account,
    nonop_bucket_for_account,
    NonOpActuals,
)


# ─── account classification ───────────────────────────────────────────────────

def test_revenue_line_for_account_ranges():
    assert revenue_line_for_account("4000") == "rooms"
    assert revenue_line_for_account("4110") == "food"      # F&B → FB group
    assert revenue_line_for_account("4205") == "spa"
    assert revenue_line_for_account("4400") == "activities"
    assert revenue_line_for_account("4700") == "laundry"
    assert revenue_line_for_account("4880") == "sustainability"
    assert revenue_line_for_account("4999") is None        # allocation, not revenue
    assert revenue_line_for_account("6000") is None         # not revenue


def test_nonop_bucket_for_account():
    assert nonop_bucket_for_account("8000") == "rent"
    assert nonop_bucket_for_account("8015") == "properties_insurance"
    assert nonop_bucket_for_account("8040") == "depreciation"
    assert nonop_bucket_for_account("8060") == "income_tax"
    assert nonop_bucket_for_account("8999") == "bank_interest"  # unmapped fallback


# ─── build_actual_inputs ──────────────────────────────────────────────────────

def test_build_actual_inputs_routes_by_class():
    rows = [
        {"account_code": "4000", "dept_code": "0110", "amount": Decimal("100000")},
        {"account_code": "4110", "dept_code": "0120", "amount": Decimal("40000")},
        {"account_code": "5101", "dept_code": "0120", "amount": Decimal("12000")},
        {"account_code": "6000", "dept_code": "0110", "amount": Decimal("25000")},
        {"account_code": "7065", "dept_code": "0110", "amount": Decimal("8000")},
        {"account_code": "4999", "dept_code": "0161", "amount": Decimal("-5000")},
        {"account_code": "8040", "dept_code": "0180", "amount": Decimal("3000")},
        {"account_code": "9700", "dept_code": "0161", "amount": Decimal("999")},  # stat, ignored
    ]
    inp = build_actual_inputs(rows)
    assert inp["revenue_by_line"]["rooms"] == Decimal("100000")
    assert inp["revenue_by_line"]["food"] == Decimal("40000")
    assert inp["cos_by_dept"]["0120"] == Decimal("12000")
    assert inp["payroll_by_dept"]["0110"] == Decimal("25000")
    assert inp["opex_by_dept"]["0110"] == Decimal("8000")
    assert inp["alloc_by_dept"]["0161"] == Decimal("-5000")
    assert inp["nonop"].depreciation == Decimal("3000")
    # 9xxx never enters the P&L inputs
    assert all("9700" not in str(v) for v in inp.values())


# ─── full actuals P&L ─────────────────────────────────────────────────────────

def test_actual_pl_gop_is_revenue_minus_costs():
    rows = [
        {"account_code": "4000", "dept_code": "0110", "amount": Decimal("300000")},
        {"account_code": "4110", "dept_code": "0120", "amount": Decimal("100000")},
        {"account_code": "5101", "dept_code": "0120", "amount": Decimal("30000")},
        {"account_code": "6000", "dept_code": "0110", "amount": Decimal("50000")},
        {"account_code": "7065", "dept_code": "0180", "amount": Decimal("20000")},  # overhead
    ]
    inp = build_actual_inputs(rows)
    pl = calculate_full_pl(**inp)
    total_rev = get_line(pl, "TOTAL_REVENUES")
    assert total_rev == Decimal("400000")
    all_costs = Decimal("30000") + Decimal("50000") + Decimal("20000")
    assert abs(get_line(pl, "GOP") - (total_rev - all_costs)) < Decimal("0.01")


def test_actual_income_tax_is_real_not_computed():
    """Actuals use the recorded 8060 tax, not 30% of EBT."""
    rows = [
        {"account_code": "4000", "dept_code": "0110", "amount": Decimal("200000")},
        {"account_code": "8060", "dept_code": "0180", "amount": Decimal("7777")},
    ]
    inp = build_actual_inputs(rows)
    pl = calculate_full_pl(**inp)
    assert get_line(pl, "INCOME_TAXES") == Decimal("7777")
    # Net = EBT - real tax
    ebt = get_line(pl, "EBT")
    assert abs(get_line(pl, "NET_PROFIT") - (ebt - Decimal("7777"))) < Decimal("0.01")


def test_actual_nonop_uses_real_mgmt_fee():
    """Mgmt fee for actuals = recorded 8005 amount, not revenue × %."""
    rows = [
        {"account_code": "4000", "dept_code": "0110", "amount": Decimal("500000")},
        {"account_code": "8005", "dept_code": "0180", "amount": Decimal("12345")},
    ]
    pl = calculate_full_pl(**build_actual_inputs(rows))
    assert get_line(pl, "MGMT_FEE") == Decimal("12345")  # not 500000 × 3%


def test_account_4900_treated_as_allocation():
    """The CWL books use 4900 'Distribución' for redistribution, not revenue."""
    rows = [
        {"account_code": "4701", "dept_code": "0161", "amount": Decimal("422.50")},
        {"account_code": "4900", "dept_code": "0161", "amount": Decimal("-2690.35")},
        {"account_code": "7320", "dept_code": "0161", "amount": Decimal("2690.35")},
    ]
    inp = build_actual_inputs(rows)
    # 4900 must NOT inflate laundry revenue
    assert inp["revenue_by_line"]["laundry"] == Decimal("422.50")
    assert inp["alloc_by_dept"]["0161"] == Decimal("-2690.35")
    # laundry operating expense nets to zero (cost + allocation credit)
    pl = calculate_full_pl(**inp)
    assert get_line(pl, "OPEXP_LAUNDRY") == Decimal("0")


def test_cafeteria_dept_excluded_from_actuals():
    """Dept 0220 (cafetería) is dropped — its cost is already in dept payroll (6025)."""
    rows = [
        {"account_code": "4000", "dept_code": "0110", "amount": Decimal("100000")},
        {"account_code": "6025", "dept_code": "0110", "amount": Decimal("500")},   # cafe benefit in dept
        {"account_code": "6000", "dept_code": "0220", "amount": Decimal("11916")}, # cafe pool — excluded
        {"account_code": "7400", "dept_code": "0220", "amount": Decimal("3000")},  # excluded
    ]
    inp = build_actual_inputs(rows)
    # nothing from dept 0220 leaks into the P&L inputs
    assert "0220" not in inp["payroll_by_dept"]
    assert "0220" not in inp["opex_by_dept"]
    pl = calculate_full_pl(**inp)
    # GOP = 100000 revenue − 500 (the 6025 in rooms); cafetería pool excluded
    assert abs(get_line(pl, "GOP") - Decimal("99500")) < Decimal("0.01")


def test_revenue_grouped_by_department_not_account_range():
    """Transport revenue in the Tours dept range must still land in TRANSPORT."""
    rows = [
        {"account_code": "4400", "dept_code": "0150", "amount": Decimal("48000")},   # tours dept
        {"account_code": "4400", "dept_code": "0152", "amount": Decimal("14820")},   # transport dept, same acct
    ]
    inp = build_actual_inputs(rows)
    assert inp["revenue_by_line"]["activities"] == Decimal("48000")
    assert inp["revenue_by_line"]["transport"] == Decimal("14820")


def test_mgmt_fee_no_phantom_by_default():
    """No manual inputs → NO phantom mgmt fee (default pct is 0, not 0.03)."""
    from app.engine.pl_engine import ManualInputs
    assert ManualInputs().mgmt_fee_pct_3 == Decimal("0")
    pl = calculate_full_pl(
        revenue_by_line={"rooms": Decimal("100000")},
        payroll_by_dept={}, cos_by_dept={}, opex_by_dept={},
    )
    assert get_line(pl, "MGMT_FEE") == Decimal("0")
    assert get_line(pl, "TOTAL_NON_OP") == Decimal("0")


def test_mgmt_fee_pct_is_opt_in():
    """Budget path still computes mgmt fee as revenue × % when a pct is set."""
    from app.engine.pl_engine import ManualInputs
    pl = calculate_full_pl(
        revenue_by_line={"rooms": Decimal("100000")},
        payroll_by_dept={}, cos_by_dept={}, opex_by_dept={},
        manual=ManualInputs(mgmt_fee_pct_3=Decimal("0.03")),
    )
    assert abs(get_line(pl, "MGMT_FEE") - Decimal("3000")) < Decimal("0.01")


def test_actual_pl_from_lines_derives_total_non_op():
    """Imported snapshot stores components + EBITDA Before but a blank
    TOTAL_NON_OP → derive it = GOP − EBITDA Before so the waterfall reconciles."""
    from app.engine.pl_engine import actual_pl_from_lines
    lines = actual_pl_from_lines({
        "GOP": Decimal("912212.11"),
        "EBITDA_BEFORE": Decimal("636468.98"),
        "RENT": Decimal("14032"),
        "MGMT_FEE": Decimal("169445.74"),
        # TOTAL_NON_OP intentionally absent
    })
    non_op = get_line(lines, "TOTAL_NON_OP")
    assert abs(non_op - Decimal("275743.13")) < Decimal("0.01")
    # reconciles: GOP − TOTAL_NON_OP == EBITDA Before
    assert abs(get_line(lines, "GOP") - non_op - get_line(lines, "EBITDA_BEFORE")) < Decimal("0.01")


def test_actual_pl_from_lines_respects_stored_total():
    """When the snapshot DOES store TOTAL_NON_OP, keep it (no derivation)."""
    from app.engine.pl_engine import actual_pl_from_lines
    lines = actual_pl_from_lines({
        "GOP": Decimal("100000"),
        "EBITDA_BEFORE": Decimal("70000"),
        "TOTAL_NON_OP": Decimal("25000"),
    })
    assert get_line(lines, "TOTAL_NON_OP") == Decimal("25000")
