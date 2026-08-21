# -*- coding: utf-8 -*-
"""Un sub-departamento sin regla propia se rutea por su PADRE, no por descarte.

El reparto de lavanderia y cafeteria cae en sub-departamentos —0122 Cocina,
0123 Restaurante, 0132 Spa, 0182 Finance, 0183 Purchasing, 0186 Security— que
casi nunca tienen regla de mapeo para esas cuentas. El motor caia entonces al
ultimo recurso: cualquier regla que usara la cuenta. Como el 0110 aparecia de
primero en la tabla, $337,127.25 de costo repartido terminaban en OPEX_ROOMS:
la cocina, el restaurante, el spa, seguridad, finanzas y mercadeo, todos
cobrandose a Habitaciones.

Peor todavia: ese ultimo recurso depende del orden fisico de las filas en la
base, o sea que el resultado no era ni estable.
"""
from decimal import Decimal

import pytest

from app.engine import pl_engine


CATALOGO = [
    {"dept_code": "0110", "default_pl_group": "ROOMS", "parent_dept_code": ""},
    {"dept_code": "0113", "default_pl_group": "ROOMS", "parent_dept_code": "0110"},
    {"dept_code": "0120", "default_pl_group": "FB",    "parent_dept_code": ""},
    {"dept_code": "0122", "default_pl_group": "FB",    "parent_dept_code": "0120"},
    {"dept_code": "0123", "default_pl_group": "FB",    "parent_dept_code": "0120"},
    {"dept_code": "0130", "default_pl_group": "SPA",   "parent_dept_code": ""},
    {"dept_code": "0132", "default_pl_group": "SPA",   "parent_dept_code": "0130"},
    # nieto: 0124 cuelga de Cocina, que cuelga de A&B
    {"dept_code": "0124", "default_pl_group": "FB",    "parent_dept_code": "0122"},
]

# El 0110 va de primero a proposito: es el que ganaba por descarte.
MAPEOS = [
    {"account_code": "7685", "dept_code": "0110", "report_line_code": "OPEX_ROOMS",
     "active_status": "YES", "rollup_operator": "ADD"},
    {"account_code": "7685", "dept_code": "0120", "report_line_code": "OPEX_FB",
     "active_status": "YES", "rollup_operator": "ADD"},
    {"account_code": "7685", "dept_code": "0130", "report_line_code": "OPEX_SPA",
     "active_status": "YES", "rollup_operator": "ADD"},
]

LINEAS = [
    {"line_code": c, "line_name": c, "section": "OPERATING EXPENSES",
     "line_type": "MAPPED", "display_order": i, "calculation_logic": None,
     "active": True}
    for i, c in enumerate(["OPEX_ROOMS", "OPEX_FB", "OPEX_SPA"])
]


@pytest.fixture(autouse=True)
def _catalogo():
    pl_engine.set_dept_catalog(CATALOGO)
    yield
    pl_engine.reset_dept_catalog()


def _correr(filas):
    return pl_engine.calculate_pl_from_mapping(filas, MAPEOS, LINEAS)


def _monto(res, linea):
    for r in res:
        if r.line_code == linea:
            return Decimal(str(r.amount_usd))
    return Decimal("0")


def test_cocina_y_restaurante_van_a_ayb_no_a_habitaciones():
    """Este es el caso que costaba $337k mal ubicados."""
    res = _correr([
        {"dept_code": "0122", "account_code": "7685", "amount": Decimal("4033.98")},
        {"dept_code": "0123", "account_code": "7685", "amount": Decimal("2933.80")},
    ])
    assert _monto(res, "OPEX_FB") == Decimal("6967.78")
    assert _monto(res, "OPEX_ROOMS") == Decimal("0")


def test_el_spa_no_se_le_carga_a_habitaciones():
    res = _correr([{"dept_code": "0132", "account_code": "7685", "amount": Decimal("733.45")}])
    assert _monto(res, "OPEX_SPA") == Decimal("733.45")
    assert _monto(res, "OPEX_ROOMS") == Decimal("0")


def test_un_hijo_de_habitaciones_si_va_a_habitaciones():
    """El padre correcto tambien tiene que funcionar, no solo los que estaban mal."""
    res = _correr([{"dept_code": "0113", "account_code": "7685", "amount": Decimal("5500.87")}])
    assert _monto(res, "OPEX_ROOMS") == Decimal("5500.87")


def test_la_regla_exacta_le_gana_al_padre():
    """Si el departamento tiene su propia regla, esa manda."""
    res = _correr([{"dept_code": "0120", "account_code": "7685", "amount": Decimal("100")}])
    assert _monto(res, "OPEX_FB") == Decimal("100")


def test_sube_mas_de_un_nivel():
    """0124 → 0122 Cocina → 0120 A&B. Ninguno de los dos primeros tiene regla."""
    res = _correr([{"dept_code": "0124", "account_code": "7685", "amount": Decimal("50")}])
    assert _monto(res, "OPEX_FB") == Decimal("50")


def test_un_ciclo_en_el_catalogo_no_cuelga_el_calculo():
    """Un padre mal capturado no puede dejar el P&L dando vueltas para siempre."""
    pl_engine.set_dept_catalog([
        {"dept_code": "0110", "default_pl_group": "ROOMS", "parent_dept_code": ""},
        {"dept_code": "0991", "default_pl_group": "FB", "parent_dept_code": "0992"},
        {"dept_code": "0992", "default_pl_group": "FB", "parent_dept_code": "0991"},
    ])
    res = _correr([{"dept_code": "0991", "account_code": "7685", "amount": Decimal("10")}])
    # sin regla en toda la cadena: cae al ultimo recurso, pero TERMINA
    assert _monto(res, "OPEX_ROOMS") == Decimal("10")


def test_cadena_de_padres_corta_ciclos():
    pl_engine.set_dept_catalog([
        {"dept_code": "0991", "default_pl_group": "FB", "parent_dept_code": "0992"},
        {"dept_code": "0992", "default_pl_group": "FB", "parent_dept_code": "0991"},
    ])
    cadena = pl_engine._cadena_de_padres("0991")
    assert cadena == ["0992"]


def test_el_tab_de_control_resuelve_igual_que_el_motor():
    """No mas replicas escritas a mano.

    El tab de Control tenia su propia copia del lookup, marcada «replica
    EXACTA». Con el paso del padre agregado solo en el motor, la copia habria
    reportado FALLBACK y otra linea distinta a la que el P&L de verdad usa —
    justo la herramienta que existe para decirle al usuario donde cae cada dato.
    """
    from app.api.audit_api import _resolver

    control = _resolver(MAPEOS)
    motor = pl_engine.construir_resolvedor(MAPEOS)

    for dept in ["0122", "0123", "0132", "0113", "0120", "0124", "9999"]:
        regla, como = motor(dept, "7685")
        linea_c, como_c, _op, _prestado = control(dept, "7685")
        assert como_c == como, f"{dept}: control dice {como_c}, motor {como}"
        esperada = regla.get("report_line_code") if regla else None
        assert linea_c == esperada, f"{dept}: control manda a {linea_c}, motor a {esperada}"


def test_control_marca_cuando_hereda_del_padre():
    """El usuario tiene que poder distinguir «heredo del padre» (correcto) de
    «se resolvio por descarte» (hay que arreglar el mapeo)."""
    from app.api.audit_api import _resolver

    control = _resolver(MAPEOS)
    linea, como, _op, prestado = control("0122", "7685")
    assert (linea, como) == ("OPEX_FB", "parent")
    assert prestado == "0120"          # de quien heredo
