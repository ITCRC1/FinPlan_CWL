"""
Tests for the tax panorama engine (D2) — engine.tax.calculate_tax.

Run: pytest tests/test_tax.py -v
"""
from app.engine.tax import calculate_tax


def _m(month, rooms=0, fb=0, spa=0, tours=0, total=None, ebt=0):
    total = total if total is not None else rooms + fb + spa + tours
    return {"month": month, "lines": {
        "REV_ROOMS": rooms, "REV_FB": fb, "REV_SPA": spa, "REV_TOURS": tours,
        "TOTAL_REVENUES": total, "EBT": ebt}}


def test_withholding_by_card_pct():
    # Jan: rooms 100k @90%, fb 0, spa 0, tours 0, total 100k → card_rev 90k, wh 2.5% = 2250
    monthly = [_m(1, rooms=100000, total=100000, ebt=20000)] + [_m(m) for m in range(2, 13)]
    t = calculate_tax(monthly, {"wh_rate": 0.025, "income_tax_rate": 0.30,
        "card_pct_rooms": 0.90, "card_pct_fb": 0.70, "card_pct_spa": 0.80,
        "card_pct_tours": 0.75, "card_pct_other": 0.60})
    assert t["monthly"][0]["card_revenue"] == 90000.0
    assert t["monthly"][0]["withholding"] == 2250.0
    assert t["cumulative_wh"] == 2250.0


def test_other_revenue_uses_other_pct():
    # total 100k, rooms 60k @90%, rest 40k "other" @60% → 54k + 24k = 78k
    monthly = [_m(1, rooms=60000, total=100000)] + [_m(m) for m in range(2, 13)]
    t = calculate_tax(monthly, {"wh_rate": 0.025, "card_pct_rooms": 0.90, "card_pct_other": 0.60,
        "card_pct_fb": 0.70, "card_pct_spa": 0.80, "card_pct_tours": 0.75})
    assert t["monthly"][0]["card_revenue"] == 78000.0


def test_annual_liquidation_net_tax():
    # EBT 1,000,000 × 30% = 300,000 gross. Withholding small → net = gross - wh.
    monthly = [_m(m, rooms=50000, total=50000, ebt=1000000/12) for m in range(1, 13)]
    t = calculate_tax(monthly, {"wh_rate": 0.025, "income_tax_rate": 0.30,
        "card_pct_rooms": 0.90, "card_pct_other": 0.60, "card_pct_fb": 0.70,
        "card_pct_spa": 0.80, "card_pct_tours": 0.75})
    assert t["gross_income_tax"] == 300000.0
    # wh = 12 × (50000×0.9×0.025) = 12 × 1125 = 13500
    assert t["cumulative_wh"] == 13500.0
    assert t["net_income_tax"] == 286500.0      # 300000 - 13500
    assert t["credit_balance"] == 0.0


def test_credit_balance_when_loss():
    # Negative EBT → gross tax 0; withholding becomes a credit balance.
    monthly = [_m(m, rooms=40000, total=40000, ebt=-5000) for m in range(1, 13)]
    t = calculate_tax(monthly, {"wh_rate": 0.025, "card_pct_rooms": 0.90, "card_pct_other": 0.60,
        "card_pct_fb": 0.70, "card_pct_spa": 0.80, "card_pct_tours": 0.75})
    assert t["gross_income_tax"] == 0.0
    assert t["net_income_tax"] == 0.0
    assert t["credit_balance"] == t["cumulative_wh"]
