"""Regresión del department_catalog: el motor leyendo el catálogo debe dar
EXACTAMENTE lo mismo que con sus constantes (byte-por-byte). Es la red de
seguridad del refactor (constantes → catálogo)."""
from decimal import Decimal

from app.engine.pl_engine import (
    group_for_dept, consolidate_dept, calculate_full_pl, build_actual_inputs,
    set_dept_catalog, reset_dept_catalog,
    OPERATING_DEPT_GROUPS, OVERHEAD_DEPT_GROUPS, CHECKBOOK_DEPT_CONSOLIDATION,
)
from app.seed_department_catalog import build_rows


ALL_DEPTS = sorted(
    set().union(*OPERATING_DEPT_GROUPS.values(), *OVERHEAD_DEPT_GROUPS.values())
    | set(CHECKBOOK_DEPT_CONSOLIDATION)
    | {r["dept_code"] for r in build_rows()}
    | {"280", "0205", "9999", "", "test-probe"}   # account-based, fallback, unknown
)


def test_group_and_consolidation_identical():
    """Cada dept_code resuelve al MISMO grupo y MISMO padre con constantes vs catálogo."""
    reset_dept_catalog()
    before_g = {d: group_for_dept(d) for d in ALL_DEPTS}
    before_c = {d: consolidate_dept(d) for d in ALL_DEPTS}
    set_dept_catalog(build_rows())
    try:
        for d in ALL_DEPTS:
            assert group_for_dept(d) == before_g[d], (d, group_for_dept(d), before_g[d])
            assert consolidate_dept(d) == before_c[d], (d, consolidate_dept(d), before_c[d])
    finally:
        reset_dept_catalog()


def test_full_pl_identical():
    """Un P&L completo (cubre revenue/payroll/opex/overhead/misc) idéntico al centavo."""
    rows = [
        {"account_code": "4000", "dept_code": "0110", "amount": Decimal("100000")},
        {"account_code": "4100", "dept_code": "0120", "amount": Decimal("50000")},
        {"account_code": "4200", "dept_code": "0130", "amount": Decimal("12000")},
        {"account_code": "4880", "dept_code": "280", "amount": Decimal("35000")},
        {"account_code": "4810", "dept_code": "280", "amount": Decimal("2000")},
        {"account_code": "6000", "dept_code": "0161", "amount": Decimal("10000")},
        {"account_code": "6000", "dept_code": "0123", "amount": Decimal("4000")},
        {"account_code": "7000", "dept_code": "0200", "amount": Decimal("8000")},
        {"account_code": "7000", "dept_code": "0205", "amount": Decimal("330")},
    ]
    reset_dept_catalog()
    before = {l.line_code: l.amount_usd for l in calculate_full_pl(**build_actual_inputs(rows))}
    set_dept_catalog(build_rows())
    try:
        after = {l.line_code: l.amount_usd for l in calculate_full_pl(**build_actual_inputs(rows))}
        assert before == after, {k: (before[k], after.get(k)) for k in before if before[k] != after.get(k)}
    finally:
        reset_dept_catalog()
