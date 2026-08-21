"""
Tests for the DB-driven P&L engine (account_mapping + report_line_config) and
the budget/forecast-from-checkbook path that feeds it.

Run: pytest tests/test_pl_mapping.py -v

These cover code paths that prod uses (calculate_pl_from_mapping) but that had
no unit coverage, plus the new checkbook → account → P&L loop
(calculate_budget_pl_from_mapping).
"""
from decimal import Decimal

from app.engine.pl_engine import (
    calculate_pl_from_mapping,
    calculate_budget_pl_from_mapping,
    revenue_seed_from_lines,
    payroll_account_for_column,
    ManualInputs,
    get_line,
)


# ─── Synthetic report_line_config (a representative slice of P&L_DETAIL_OWNERS) ─
def report_lines() -> list[dict]:
    def L(order, code, section, ltype, calc=None):
        return {"line_code": code, "line_name": code, "section": section,
                "line_type": ltype, "display_order": order,
                "calculation_logic": calc, "active": True}
    return [
        L(1, "REV_ROOMS", "REVENUES", "MAPPED"),
        L(2, "REV_FB", "REVENUES", "MAPPED"),
        L(3, "TOTAL_REVENUES", "REVENUES", "CALCULATED", "SUM(REV_*)"),
        L(4, "OPEX_ROOMS", "OPERATING EXPENSES", "MAPPED"),
        L(5, "OPEX_FB", "OPERATING EXPENSES", "MAPPED"),
        L(6, "TOTAL_OPERATING_EXPENSES", "OPERATING EXPENSES", "CALCULATED", "SUM(OPEX_*)"),
        L(7, "TOTAL_GOP", "GOP", "CALCULATED", "TOTAL_REVENUES - TOTAL_OPERATING_EXPENSES"),
        L(8, "RENT", "OWNER / NON-OP EXPENSES", "MAPPED"),
        L(9, "MGMT_FEE_3", "OWNER / NON-OP EXPENSES", "MAPPED"),
        L(9.5, "PROPERTY_INSURANCE", "OWNER / NON-OP EXPENSES", "MAPPED"),
        L(10, "TOTAL_NON_OP_EXPENSES", "OWNER / NON-OP EXPENSES", "CALCULATED",
          "RENT + MGMT_FEE_3 + PROPERTY_INSURANCE"),
        L(11, "EBITDA_BEFORE_CAPITAL", "EBITDA", "CALCULATED",
          "TOTAL_GOP - TOTAL_NON_OP_EXPENSES"),
        L(12, "EBT", "TAX / NET PROFIT", "CALCULATED", "EBITDA_BEFORE_CAPITAL"),
        L(13, "INCOME_TAXES", "TAX / NET PROFIT", "MAPPED"),
        L(14, "NET_PROFIT", "TAX / NET PROFIT", "CALCULATED", "EBT - INCOME_TAXES"),
    ]


def mappings() -> list[dict]:
    def M(acct, dept, line):
        return {"account_code": acct, "dept_code": dept,
                "report_line_code": line, "active_status": "YES",
                "rollup_operator": "ADD"}
    return [
        M("6000", "0110", "OPEX_ROOMS"),
        M("7065", "0110", "OPEX_ROOMS"),
        M("6000", "0120", "OPEX_FB"),   # same account, different dept → different line
        M("8000", "", "RENT"),          # below-GOP mini checkbook (NonOpEntry)
        M("8015", "", "PROPERTY_INSURANCE"),
    ]


# ─── helper-level ──────────────────────────────────────────────────────────────
def test_payroll_account_for_column():
    assert payroll_account_for_column("c6000_sw") == "6000"
    assert payroll_account_for_column("c6021_aguinaldo") == "6021"
    assert payroll_account_for_column("c6030_other") == "6030"
    assert payroll_account_for_column("garbage") == ""


def test_revenue_seed_uses_report_line_config_codes():
    seeds = revenue_seed_from_lines({
        "rooms": Decimal("100"),
        "food": Decimal("10"), "beverage": Decimal("5"), "fnb_misc": Decimal("2"),
        "transport": Decimal("7"),
        "sustainability": Decimal("3"),
    })
    assert seeds["REV_ROOMS"] == Decimal("100")
    # El A&B va PARTIDO desde el 2026-08-14. El checkbook siempre tuvo las tres
    # separadas y antes se colapsaban en `REV_FB`, lo que dejaba `REV_FB_BEV` y
    # `REV_FB_MISC` en cero en todo presupuesto — y comparar Actual contra Budget
    # linea por linea daba una variacion falsa del tamano de toda la bebida.
    assert seeds["REV_FB"] == Decimal("10")            # solo comida
    assert seeds["REV_FB_BEV"] == Decimal("5")
    assert seeds["REV_FB_MISC"] == Decimal("2")
    # Lo que de verdad importa: partirlo no puede PERDER nada.
    assert sum(seeds[c] for c in ("REV_FB", "REV_FB_BEV", "REV_FB_MISC")) == Decimal("17")
    assert seeds["REV_TRANSPORTATION"] == Decimal("7")  # NOT REV_TRANSPORT
    assert seeds["REV_SUSTAINABILITY"] == Decimal("3")  # ahora línea propia (antes se fusionaba en REV_MISC_OTHER)


# ─── mapping engine ──────────────────────────────────────────────────────────
def test_dept_specific_attribution():
    """Account 6000 in dept 0110 → Rooms; in dept 0120 → F&B (not collapsed)."""
    rows = [
        {"account_code": "6000", "dept_code": "0110", "amount": Decimal("1000")},
        {"account_code": "6000", "dept_code": "0120", "amount": Decimal("800")},
    ]
    res = calculate_pl_from_mapping(rows, mappings(), report_lines())
    assert get_line(res, "OPEX_ROOMS") == Decimal("1000")
    assert get_line(res, "OPEX_FB") == Decimal("800")


def test_seed_amounts_feed_revenue():
    res = calculate_pl_from_mapping(
        [], mappings(), report_lines(),
        seed_amounts={"REV_ROOMS": Decimal("10000"), "REV_FB": Decimal("2000")},
    )
    assert get_line(res, "TOTAL_REVENUES") == Decimal("12000")


# ─── budget/forecast from checkbooks (the new loop) ──────────────────────────
def test_budget_pl_full_chain():
    """
    checkbook rollup (operating 6xxx/7xxx as account rows) + below-GOP lines
    seeded by report_line_code (NonOpEntry) + revenue seeds + mgmt-fee driver
    + two-pass income tax.
    """
    acct_rows = [
        # operating expenses (account rows → mapping engine)
        {"account_code": "6000", "dept_code": "0110", "amount": Decimal("1000")},
        {"account_code": "7065", "dept_code": "0110", "amount": Decimal("500")},
        {"account_code": "6000", "dept_code": "0120", "amount": Decimal("800")},
    ]
    # below-GOP mini checkbooks summed by report_line_code (3 insurance lines → 300)
    extra_seeds = {"RENT": Decimal("300"), "PROPERTY_INSURANCE": Decimal("300")}
    res = calculate_budget_pl_from_mapping(
        acct_rows, mappings(), report_lines(),
        revenue_by_line={"rooms": Decimal("10000"), "food": Decimal("2000")},
        manual=ManualInputs(
            mgmt_fee_pct_3=Decimal("0.03"),
            mgmt_fee_pct_5=Decimal("0"),
            income_tax_rate=Decimal("0.30"),
        ),
        extra_seeds=extra_seeds,
    )
    assert get_line(res, "TOTAL_REVENUES") == Decimal("12000")
    assert get_line(res, "OPEX_ROOMS") == Decimal("1500")     # 1000 + 500
    assert get_line(res, "OPEX_FB") == Decimal("800")
    assert get_line(res, "TOTAL_OPERATING_EXPENSES") == Decimal("2300")
    assert get_line(res, "TOTAL_GOP") == Decimal("9700")
    assert get_line(res, "RENT") == Decimal("300")
    assert get_line(res, "PROPERTY_INSURANCE") == Decimal("300")  # 120 + 80 + 100
    assert get_line(res, "MGMT_FEE_3") == Decimal("360")      # 12000 × 3%
    assert get_line(res, "TOTAL_NON_OP_EXPENSES") == Decimal("960")  # 300+360+300
    assert get_line(res, "EBT") == Decimal("8740")            # 9700 − 960
    assert get_line(res, "INCOME_TAXES") == Decimal("2622")   # 8740 × 30%
    assert get_line(res, "NET_PROFIT") == Decimal("6118")     # 8740 − 2622


def test_budget_pl_no_tax_when_loss():
    """Negative EBT → income tax is 0, never negative."""
    acct_rows = [
        {"account_code": "6000", "dept_code": "0110", "amount": Decimal("50000")},
    ]
    res = calculate_budget_pl_from_mapping(
        acct_rows, mappings(), report_lines(),
        revenue_by_line={"rooms": Decimal("1000")},
        manual=ManualInputs(income_tax_rate=Decimal("0.30")),
    )
    assert get_line(res, "EBT") < 0
    assert get_line(res, "INCOME_TAXES") == Decimal("0")
    assert get_line(res, "NET_PROFIT") == get_line(res, "EBT")
