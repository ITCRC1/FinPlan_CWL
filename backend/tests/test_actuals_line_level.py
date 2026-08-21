"""
Tests for line-level actuals (macro P&L) — pl_engine.actual_pl_from_lines.
Uses the real May 2026 Actual figures from
data/raw/Actual P&L May 2026.pdf as a validation fixture.
Run: pytest tests/test_actuals_line_level.py -v
"""
from decimal import Decimal

from app.engine.pl_engine import actual_pl_from_lines, standard_pl_template, get_line


def D(x) -> Decimal:
    return Decimal(str(x))


# Real May 2026 Actuals (col "Actual 2026") from the P&L PDF.
MAY_2026_ACTUAL = {
    "REV_ROOMS": D("119456.11"),
    "REV_FB": D("46252.90"),
    "REV_SPA": D("1886.14"),
    "REV_TOURS": D("47996.41"),
    "REV_RETAIL": D("2792.61"),
    "REV_TRANSPORT": D("14820.69"),
    "REV_LAUNDRY": D("422.50"),
    "REV_INNOCEANA": D("0.00"),
    "REV_SUSTAINABILITY": D("11026.63"),
    "TOTAL_REVENUES": D("244654.00"),
    "OPEXP_ROOMS": D("48423.11"),
    "OPEXP_FB": D("51591.83"),
    "OPEXP_SPA": D("2138.64"),
    "OPEXP_TOURS": D("37454.71"),
    "OPEXP_RETAIL": D("1876.77"),
    "OPEXP_TRANSPORT": D("16102.94"),
    "OPEXP_LAUNDRY": D("0.00"),
    "OPEXP_INNOCEANA": D("0.00"),
    "TOTAL_OPEXP": D("157588.00"),
    "TOTAL_OP_PROFIT": D("87066.00"),
    "OVH_ADMIN": D("61073.87"),
    "OVH_SALES": D("71867.35"),
    "OVH_MAINTENANCE": D("19879.18"),
    "OVH_IT": D("3323.07"),
    "OVH_UTILITIES": D("28813.09"),
    "TOTAL_OVERHEAD": D("185664.26"),
    "GOP": D("-98598.25"),
    "TOTAL_NON_OP": D("17604.67"),
    "EBITDA_BEFORE": D("-116202.92"),
    "CAPITAL_EXPENSE": D("9786.16"),
    "EBITDA_AFTER": D("-125989.08"),
    "FINANCIAL_EXPENSES": D("-256.86"),
    "TOTAL_DEPRECIATIONS": D("28002.44"),
    "EBT": D("-153734.67"),
    "INCOME_TAXES": D("0.00"),
    "NET_PROFIT": D("-153734.67"),
}


def test_actual_pl_returns_stored_values():
    pl = actual_pl_from_lines(MAY_2026_ACTUAL)
    assert get_line(pl, "TOTAL_REVENUES") == D("244654.00")
    assert get_line(pl, "GOP") == D("-98598.25")
    assert get_line(pl, "NET_PROFIT") == D("-153734.67")


def test_actual_lines_are_marked_not_calculated():
    pl = actual_pl_from_lines(MAY_2026_ACTUAL)
    net = next(ln for ln in pl if ln.line_code == "NET_PROFIT")
    assert net.is_calculated is False


def test_may_2026_internal_consistency():
    """The PDF figures must tie: GOP = OpProfit − Overhead; Net = EBT − Tax."""
    a = MAY_2026_ACTUAL
    assert abs((a["TOTAL_OP_PROFIT"] - a["TOTAL_OVERHEAD"]) - a["GOP"]) < D("0.02")
    assert abs((a["GOP"] - a["TOTAL_NON_OP"]) - a["EBITDA_BEFORE"]) < D("0.02")
    assert abs((a["EBITDA_BEFORE"] - a["CAPITAL_EXPENSE"]) - a["EBITDA_AFTER"]) < D("0.02")
    assert abs((a["EBT"] - a["INCOME_TAXES"]) - a["NET_PROFIT"]) < D("0.02")


def test_total_revenues_equals_sum_of_revenue_lines():
    a = MAY_2026_ACTUAL
    rev_sum = sum(v for k, v in a.items() if k.startswith("REV_"))
    assert abs(rev_sum - a["TOTAL_REVENUES"]) < D("0.02")


def test_template_covers_all_provided_line_codes():
    """Every line_code we load must exist in the engine's standard template."""
    template_codes = {ln.line_code for ln in standard_pl_template()}
    missing = set(MAY_2026_ACTUAL) - template_codes
    assert not missing, f"line codes not in template: {missing}"
