"""
Tests for app/engine/pl_engine.py — pure P&L engine (no DB).
Run: pytest tests/test_pl_engine.py -v
"""
from decimal import Decimal
import pytest

from app.engine.pl_engine import (
    calculate_full_pl,
    ManualInputs,
    get_line,
    group_for_dept,
    aggregate_by_group,
    revenue_by_group,
)


# ─── Fixtures of synthetic data ───────────────────────────────────────────────

def base_revenue():
    return {
        "rooms": Decimal("319273"),
        "food": Decimal("80000"),
        "beverage": Decimal("27200"),
        "fnb_misc": Decimal("12011"),
        "spa": Decimal("6088"),
        "activities": Decimal("87645"),
        "transport": Decimal("40000"),
        "retail": Decimal("9000"),
        "laundry": Decimal("5000"),
        "innoceana": Decimal("3000"),
        "sustainability": Decimal("7918.41"),
    }


def base_payroll():
    return {
        "0110": Decimal("40000"),   # rooms
        "0120": Decimal("55000"),   # f&b
        "0180": Decimal("30000"),   # admin (overhead)
        "0200": Decimal("12000"),   # maintenance (overhead)
    }


def base_opex():
    return {
        "0110": Decimal("20000"),
        "0120": Decimal("25000"),
        "0180": Decimal("36000"),   # admin overhead
        "0190": Decimal("15000"),   # sales overhead
    }


def base_cos():
    return {
        "0120": Decimal("18000"),   # F&B food/bev cost
        "0150": Decimal("9000"),    # tours cost
    }


# ─── Mapping tests ────────────────────────────────────────────────────────────

def test_group_for_dept_known_and_fallback():
    assert group_for_dept("0110") == "ROOMS"
    assert group_for_dept("0120") == "FB"
    assert group_for_dept("0180") == "ADMIN"
    assert group_for_dept("9999") == "OTHER_OVERHEAD"  # unknown → fallback overhead


def test_aggregate_by_group_sums_depts():
    agg = aggregate_by_group({"0110": Decimal("10"), "0111": Decimal("5"), "0120": Decimal("7")})
    assert agg["ROOMS"] == Decimal("15")
    assert agg["FB"] == Decimal("7")


def test_revenue_by_group_collapses_fb():
    rev = revenue_by_group({"food": Decimal("100"), "beverage": Decimal("34"), "fnb_misc": Decimal("6")})
    assert rev["FB"] == Decimal("140")


# ─── Formula tests (mirror CLAUDE.md §17.9) ───────────────────────────────────

def test_total_revenue_sums_all_lines():
    pl = calculate_full_pl(
        revenue_by_line=base_revenue(),
        payroll_by_dept={}, cos_by_dept={}, opex_by_dept={},
    )
    expected = sum(base_revenue().values())
    assert abs(get_line(pl, "TOTAL_REVENUES") - expected) < Decimal("0.01")


def test_operating_exp_is_sum_of_three_plus_alloc():
    """Operating Expenses dept = Payroll + CoS + OpEx + Allocations."""
    alloc = {"0110": Decimal("1850")}  # cafetería charge to rooms
    pl = calculate_full_pl(
        revenue_by_line=base_revenue(),
        payroll_by_dept=base_payroll(),
        cos_by_dept=base_cos(),
        opex_by_dept=base_opex(),
        alloc_by_dept=alloc,
    )
    rooms_opexp = get_line(pl, "OPEXP_ROOMS")
    expected = Decimal("40000") + Decimal("0") + Decimal("20000") + Decimal("1850")
    assert abs(rooms_opexp - expected) < Decimal("0.01")


def test_gop_formula():
    """GOP = Total Operating Profit − Total Overhead."""
    pl = calculate_full_pl(
        revenue_by_line=base_revenue(),
        payroll_by_dept=base_payroll(),
        cos_by_dept=base_cos(),
        opex_by_dept=base_opex(),
    )
    gop = get_line(pl, "GOP")
    op_profit = get_line(pl, "TOTAL_OP_PROFIT")
    overhead = get_line(pl, "TOTAL_OVERHEAD")
    assert abs(gop - (op_profit - overhead)) < Decimal("0.01")


def test_gop_equals_revenue_minus_all_costs():
    """Integrity: GOP must equal Total Revenue − all operating/overhead costs."""
    pay, cos, opx = base_payroll(), base_cos(), base_opex()
    pl = calculate_full_pl(
        revenue_by_line=base_revenue(),
        payroll_by_dept=pay, cos_by_dept=cos, opex_by_dept=opx,
    )
    total_rev = get_line(pl, "TOTAL_REVENUES")
    all_costs = sum(pay.values()) + sum(cos.values()) + sum(opx.values())
    assert abs(get_line(pl, "GOP") - (total_rev - all_costs)) < Decimal("0.01")


def test_allocations_net_zero_do_not_change_gop():
    """Allocations shift per-dept profit but net to zero → GOP unchanged."""
    args = dict(
        revenue_by_line=base_revenue(),
        payroll_by_dept=base_payroll(),
        cos_by_dept=base_cos(),
        opex_by_dept=base_opex(),
    )
    pl_no_alloc = calculate_full_pl(**args)
    # cafetería 0220 distributes 5000 to rooms+f&b, credits itself -5000
    alloc = {"0110": Decimal("3000"), "0120": Decimal("2000"), "0220": Decimal("-5000")}
    pl_alloc = calculate_full_pl(**args, alloc_by_dept=alloc)
    assert abs(get_line(pl_no_alloc, "GOP") - get_line(pl_alloc, "GOP")) < Decimal("0.01")


def test_mgmt_fee_uses_total_revenue():
    """Management Fee = Total Revenue × % configured."""
    manual = ManualInputs(mgmt_fee_pct_3=Decimal("0.03"))
    pl = calculate_full_pl(
        revenue_by_line=base_revenue(),
        payroll_by_dept={}, cos_by_dept={}, opex_by_dept={},
        manual=manual,
    )
    total_rev = get_line(pl, "TOTAL_REVENUES")
    mgmt_fee = get_line(pl, "MGMT_FEE")
    assert abs(mgmt_fee - total_rev * Decimal("0.03")) < Decimal("0.01")


def test_mgmt_fee_changes_when_revenue_changes():
    manual = ManualInputs(mgmt_fee_pct_3=Decimal("0.03"))
    low = calculate_full_pl(revenue_by_line={"rooms": Decimal("100000")},
                            payroll_by_dept={}, cos_by_dept={}, opex_by_dept={}, manual=manual)
    high = calculate_full_pl(revenue_by_line={"rooms": Decimal("200000")},
                             payroll_by_dept={}, cos_by_dept={}, opex_by_dept={}, manual=manual)
    assert get_line(high, "MGMT_FEE") > get_line(low, "MGMT_FEE")


def test_net_profit_formula():
    """Net Profit = EBT − Income Taxes."""
    manual = ManualInputs(rent=Decimal("5000"), depreciation=Decimal("3000"))
    pl = calculate_full_pl(
        revenue_by_line=base_revenue(),
        payroll_by_dept=base_payroll(),
        cos_by_dept=base_cos(),
        opex_by_dept=base_opex(),
        manual=manual,
    )
    ebt = get_line(pl, "EBT")
    tax = get_line(pl, "INCOME_TAXES")
    net = get_line(pl, "NET_PROFIT")
    assert abs(net - (ebt - tax)) < Decimal("0.01")


def test_income_tax_zero_when_negative_ebt():
    """No tax on losses."""
    manual = ManualInputs(rent=Decimal("999999"))  # force a loss
    pl = calculate_full_pl(
        revenue_by_line={"rooms": Decimal("1000")},
        payroll_by_dept={}, cos_by_dept={}, opex_by_dept={},
        manual=manual,
    )
    assert get_line(pl, "EBT") < 0
    assert get_line(pl, "INCOME_TAXES") == Decimal("0")


def test_income_tax_is_30pct_of_positive_ebt():
    manual = ManualInputs(income_tax_rate=Decimal("0.30"))
    pl = calculate_full_pl(
        revenue_by_line={"rooms": Decimal("100000")},
        payroll_by_dept={}, cos_by_dept={}, opex_by_dept={},
        manual=manual,
    )
    ebt = get_line(pl, "EBT")
    assert ebt > 0
    assert abs(get_line(pl, "INCOME_TAXES") - ebt * Decimal("0.30")) < Decimal("0.01")
