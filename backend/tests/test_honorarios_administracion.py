# -*- coding: utf-8 -*-
"""Honorarios de administración: el porcentaje es un driver, no la verdad.

El fee y los royalties salen de una fórmula (% del ingreso) **solo cuando el
porcentaje está configurado**. Sin porcentaje, manda lo que el owner haya
digitado en el mini-checkbook de below-GOP.

Antes la fórmula corría después de los seeds del checkbook y asignaba con `=`:
el honorario digitado quedaba pisado, y sin porcentaje lo pisaba con CERO.

Ver `alembic/versions/095_honorarios_una_regla_por_cuenta.py`.
"""
from decimal import Decimal

from app.engine.pl_engine import ManualInputs, calculate_budget_pl_from_mapping

REPORT_LINES = [
    {"display_order": 10, "line_code": "REV_ROOMS", "line_name": "Rooms",
     "section": "REVENUES", "line_type": "MAPPED", "active": True},
    {"display_order": 30, "line_code": "TOTAL_REVENUES", "line_name": "Total",
     "section": "REVENUES", "line_type": "CALCULATED",
     "calculation_logic": "SUM(REV_*)", "active": True},
    {"display_order": 83, "line_code": "RENT", "line_name": "Rent",
     "section": "OWNER / NON-OP EXPENSES", "line_type": "MAPPED", "active": True},
    {"display_order": 84, "line_code": "MGMT_FEE_3", "line_name": "Mgmt fee",
     "section": "OWNER / NON-OP EXPENSES", "line_type": "MAPPED", "active": True},
    {"display_order": 85, "line_code": "MGMT_FEE_5_ROYALTIES", "line_name": "Royalties",
     "section": "OWNER / NON-OP EXPENSES", "line_type": "MAPPED", "active": True},
    {"display_order": 87, "line_code": "TOTAL_RENT_MGMT_FEES", "line_name": "Total",
     "section": "OWNER / NON-OP EXPENSES", "line_type": "CALCULATED",
     "calculation_logic": "RENT + MGMT_FEE_3 + MGMT_FEE_5_ROYALTIES", "active": True},
]
REVENUE = {"rooms": Decimal("1000000")}


def _pl(manual: ManualInputs, extra=None) -> dict:
    lines = calculate_budget_pl_from_mapping(
        [], [], REPORT_LINES, revenue_by_line=REVENUE, manual=manual,
        extra_seeds=extra,
    )
    return {l.line_code: l.amount_usd for l in lines}


def test_con_porcentaje_manda_la_formula():
    v = _pl(ManualInputs(mgmt_fee_pct_3=Decimal("0.03"),
                         mgmt_fee_pct_5=Decimal("0.05")))
    assert v["MGMT_FEE_3"] == Decimal("30000")
    assert v["MGMT_FEE_5_ROYALTIES"] == Decimal("50000")


def test_sin_porcentaje_no_se_inventa_nada():
    v = _pl(ManualInputs())
    assert v["MGMT_FEE_3"] == Decimal("0")
    assert v["MGMT_FEE_5_ROYALTIES"] == Decimal("0")


def test_sin_porcentaje_respeta_el_honorario_digitado():
    """El bug: la fórmula pisaba con cero lo que el owner había digitado."""
    v = _pl(ManualInputs(), extra={"MGMT_FEE_3": Decimal("12345")})
    assert v["MGMT_FEE_3"] == Decimal("12345")
    assert v["TOTAL_RENT_MGMT_FEES"] == Decimal("12345")


def test_con_porcentaje_el_porcentaje_gana_y_no_se_suma_dos_veces():
    """Configurar el % es decir «calculámelo»: no se apila sobre lo digitado."""
    v = _pl(ManualInputs(mgmt_fee_pct_3=Decimal("0.03")),
            extra={"MGMT_FEE_3": Decimal("12345")})
    assert v["MGMT_FEE_3"] == Decimal("30000")


def test_las_dos_lineas_se_quedan_abiertas_y_el_total_las_junta():
    v = _pl(ManualInputs(mgmt_fee_pct_3=Decimal("0.03"),
                         mgmt_fee_pct_5=Decimal("0.05")),
            extra={"RENT": Decimal("2000")})
    assert v["TOTAL_RENT_MGMT_FEES"] == Decimal("82000")
