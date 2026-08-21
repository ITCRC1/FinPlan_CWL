"""Tests de la capa de traducción canónica del P&L (canonicalize_pl_lines).
Garantiza que es ADITIVA: ningún monto cambia, solo se agregan códigos canónicos
(report_line_config) con la sección correcta, para que todos los escenarios sean
comparables en el Full P&L."""
from decimal import Decimal
from app.engine.pl_engine import (
    calculate_full_pl, add_pl_aliases, canonicalize_pl_lines, _MOTOR_TO_CANON,
)


def _motor_lines():
    return add_pl_aliases(calculate_full_pl(
        revenue_by_line={"rooms": Decimal("1000"), "food": Decimal("500"),
                         "spa": Decimal("300")},
        payroll_by_dept={"0110": Decimal("200"), "0180": Decimal("150")},
        cos_by_dept={"0120": Decimal("80")},
        opex_by_dept={"0110": Decimal("100"), "0200": Decimal("60")},
    ))


def test_additive_no_value_changes():
    """Todos los códigos previos conservan EXACTAMENTE su valor."""
    lines = _motor_lines()
    before = {ln.line_code: ln.amount_usd for ln in lines}
    after = {ln.line_code: ln.amount_usd for ln in canonicalize_pl_lines(lines)}
    for code, val in before.items():
        assert after.get(code) == val, f"{code}: {val} → {after.get(code)}"


def test_canonical_codes_added():
    codes = {ln.line_code for ln in canonicalize_pl_lines(_motor_lines())}
    for c in ("OPEX_ROOMS", "PROFIT_ROOMS", "OPERATING_PROFIT",
              "TOTAL_OPERATING_EXPENSES", "TOTAL_GOP"):
        assert c in codes, f"falta el código canónico {c}"


def test_canonical_sections():
    by = {ln.line_code: ln for ln in canonicalize_pl_lines(_motor_lines())}
    assert by["TOTAL_REVENUES"].section == "REVENUES"
    assert by["TOTAL_OPERATING_EXPENSES"].section == "OPERATING EXPENSES"
    assert by["OPERATING_PROFIT"].section == "OPERATING PROFIT"
    assert by["TOTAL_OVERHEAD_EXPENSES"].section == "OVERHEAD EXPENSES"
    assert by["TOTAL_GOP"].section == "GOP"
    assert by["NET_PROFIT"].section == "TAX / NET PROFIT"


def test_canonical_value_matches_source():
    """El código canónico agregado tiene el mismo valor que su origen motor."""
    lines = _motor_lines()
    by = {ln.line_code: ln.amount_usd for ln in lines}
    canon = {ln.line_code: ln.amount_usd for ln in canonicalize_pl_lines(lines)}
    for motor_code, (canon_code, _sec) in _MOTOR_TO_CANON.items():
        if motor_code in by and canon_code != motor_code:
            assert canon[canon_code] == by[motor_code], \
                f"{canon_code} ({canon[canon_code]}) != {motor_code} ({by[motor_code]})"


def test_idempotent():
    """Aplicar dos veces no cambia nada (escenarios ya canónicos no se afectan)."""
    once = canonicalize_pl_lines(_motor_lines())
    t1 = {ln.line_code: ln.amount_usd for ln in once}
    twice = canonicalize_pl_lines(once)
    t2 = {ln.line_code: ln.amount_usd for ln in twice}
    assert t1 == t2
    # no duplica códigos
    codes = [ln.line_code for ln in twice]
    assert len(codes) == len(set(codes)), "canonicalize duplicó códigos"


def test_totals_preserved():
    lines = _motor_lines()
    before = {ln.line_code: ln.amount_usd for ln in lines}
    after = {ln.line_code: ln.amount_usd for ln in canonicalize_pl_lines(lines)}
    for code in ("TOTAL_REVENUES", "GOP", "TOTAL_GOP", "EBITDA_BEFORE_CAPITAL", "NET_PROFIT"):
        if code in before:
            assert after[code] == before[code], f"total {code} cambió"
