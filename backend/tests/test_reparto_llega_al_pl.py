# -*- coding: utf-8 -*-
"""El reparto tiene que llegar al P&L, y llegar completo.

Los repartos se calculaban, se guardaban en allocation_entries, se dibujaban
en su pantalla… y el P&L los ignoraba. La ruta que usa produccion
—calculate_budget_pl_from_mapping— nunca los leia: `alloc_by_dept` solo
alimentaba el motor viejo. El resultado era que lavanderia y cafeteria se
quedaban con TODO su costo en overhead y Habitaciones, A&B y Spa nunca
recibian su parte.

Repartir es mover el costo de sitio. Que «netee a cero» describe el total, no
el efecto: el efecto es justamente cambiar en que linea del P&L queda cada
colon.

Las dos mitades tienen que viajar juntas. Si el CARGO entra y el CREDITO se
cae —porque su cuenta no tiene regla de mapeo— el gasto total del hotel sube
por el monto repartido y nada lo avisa.
"""
from decimal import Decimal

import pytest

from app.engine import pl_engine


CATALOGO = [
    {"dept_code": "0110", "default_pl_group": "ROOMS", "parent_dept_code": ""},
    {"dept_code": "0120", "default_pl_group": "FB", "parent_dept_code": ""},
    {"dept_code": "0161", "default_pl_group": "LAUNDRY_OPS", "parent_dept_code": ""},
]

MAPEOS = [
    {"account_code": "7310", "dept_code": "0110", "report_line_code": "OPEX_ROOMS",
     "active_status": "YES", "rollup_operator": "ADD"},
    {"account_code": "7310", "dept_code": "0120", "report_line_code": "OPEX_FB",
     "active_status": "YES", "rollup_operator": "ADD"},
    {"account_code": "7310", "dept_code": "0161", "report_line_code": "OH_LAUNDRY",
     "active_status": "YES", "rollup_operator": "ADD"},
    # la regla del credito — la que agrega la migracion 079
    {"account_code": "4999", "dept_code": "0161", "report_line_code": "OH_LAUNDRY",
     "active_status": "YES", "rollup_operator": "ADD"},
]

LINEAS = [
    {"line_code": c, "line_name": c, "section": "OPERATING EXPENSES",
     "line_type": "MAPPED", "display_order": i, "calculation_logic": None,
     "active": True}
    for i, c in enumerate(["OPEX_ROOMS", "OPEX_FB", "OH_LAUNDRY"])
] + [
    {"line_code": "TOTAL_GASTO", "line_name": "TOTAL", "section": "OPERATING EXPENSES",
     "line_type": "CALCULATED", "display_order": 9,
     "calculation_logic": "OPEX_ROOMS + OPEX_FB + OH_LAUNDRY", "active": True},
]


@pytest.fixture(autouse=True)
def _catalogo():
    pl_engine.set_dept_catalog(CATALOGO)
    yield
    pl_engine.reset_dept_catalog()


def _monto(res, linea):
    for r in res:
        if r.line_code == linea:
            return Decimal(str(r.amount_usd))
    return Decimal("0")


# El costo original de lavanderia, antes de repartir.
COSTO_0161 = [{"dept_code": "0161", "account_code": "7310", "amount": Decimal("1000")}]

# Lo que produce el reparto: dos cargos y su credito.
REPARTO = [
    {"dept_code": "0110", "account_code": "7310", "amount": Decimal("700")},
    {"dept_code": "0120", "account_code": "7310", "amount": Decimal("300")},
    {"dept_code": "0161", "account_code": "4999", "amount": Decimal("-1000")},
]


def test_sin_el_reparto_lavanderia_se_queda_con_todo():
    """El estado que tenia el sistema: el reparto no llegaba."""
    res = pl_engine.calculate_pl_from_mapping(COSTO_0161, MAPEOS, LINEAS)
    assert _monto(res, "OH_LAUNDRY") == Decimal("1000")
    assert _monto(res, "OPEX_ROOMS") == Decimal("0")
    assert _monto(res, "OPEX_FB") == Decimal("0")


def test_con_el_reparto_el_costo_llega_a_quien_lo_consume():
    res = pl_engine.calculate_pl_from_mapping(COSTO_0161 + REPARTO, MAPEOS, LINEAS)
    assert _monto(res, "OPEX_ROOMS") == Decimal("700")
    assert _monto(res, "OPEX_FB") == Decimal("300")
    assert _monto(res, "OH_LAUNDRY") == Decimal("0")     # quedo aliviada


def test_el_gasto_total_no_se_mueve():
    """Repartir cambia DONDE queda el costo, no cuanto es. Si el total cambia,
    algo se perdio o se conto dos veces."""
    sin = pl_engine.calculate_pl_from_mapping(COSTO_0161, MAPEOS, LINEAS)
    con = pl_engine.calculate_pl_from_mapping(COSTO_0161 + REPARTO, MAPEOS, LINEAS)
    assert _monto(sin, "TOTAL_GASTO") == _monto(con, "TOTAL_GASTO") == Decimal("1000")


def test_si_el_credito_no_mapea_el_gasto_se_infla():
    """Este es el modo de falla que justifica la migracion 079.

    Sin regla para la 4999 el credito se cae, entran solo los cargos y el
    hotel aparece gastando el doble sin que nada lo avise.
    """
    sin_regla_credito = [m for m in MAPEOS if m["account_code"] != "4999"]
    res = pl_engine.calculate_pl_from_mapping(
        COSTO_0161 + REPARTO, sin_regla_credito, LINEAS)
    assert _monto(res, "TOTAL_GASTO") == Decimal("2000")   # inflado: 1000 de mas
