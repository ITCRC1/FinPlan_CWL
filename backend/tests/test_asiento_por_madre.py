# -*- coding: utf-8 -*-
"""El asiento de lavanderia se presenta por departamento MADRE.

El reparto se calcula por sub-departamento porque ahi viven los FTE, pero el
asiento salia con catorce renglones de 7685 —Front Desk, Reservation,
Housekeeping, Concierge, Kitchen, Restaurant, Spa, Management, Finance,
Purchasing, Security, Sales, Jornalero— y nadie cuadra eso a mano contra un
P&L que se lee por madre.

Los numeros son los reales del Budget Working 2027.
"""
from app.api.allocation_api import consolidar_a_la_madre


PADRES = {
    "0111": "0110", "0112": "0110", "0113": "0110", "0114": "0110",
    "0122": "0120", "0123": "0120",
    "0132": "0130",
    "0181": "0180", "0182": "0180", "0183": "0180", "0186": "0180",
}


def _anual(v):
    return round(sum(v), 2)


def test_los_uniformes_quedan_por_madre():
    uniform = {
        "0111": [1833.62 / 12] * 12,      # Front Desk
        "0112": [1100.17 / 12] * 12,      # Reservation
        "0113": [5500.87 / 12] * 12,      # Housekeeping
        "0114": [1833.62 / 12] * 12,      # Concierge
        "0122": [4033.98 / 12] * 12,      # Kitchen
        "0123": [2933.80 / 12] * 12,      # Restaurant
        "0132": [733.45 / 12] * 12,       # Spa
        "0181": [366.72 / 12] * 12,       # Management
        "0182": [1100.17 / 12] * 12,      # Finance
        "0183": [1100.17 / 12] * 12,      # Purchasing
        "0186": [1833.62 / 12] * 12,      # Security
        "0190": [2200.35 / 12] * 12,      # Sales — sin madre, queda igual
        "0205": [366.72 / 12] * 12,       # Jornalero — sin madre
    }
    out = consolidar_a_la_madre(uniform, PADRES)

    assert sorted(out) == ["0110", "0120", "0130", "0180", "0190", "0205"]
    assert _anual(out["0110"]) == 10268.28    # 1833.62+1100.17+5500.87+1833.62
    assert _anual(out["0120"]) == 6967.78     # Kitchen + Restaurant
    assert _anual(out["0130"]) == 733.45      # el 0132 subio al 0130
    assert _anual(out["0180"]) == 4400.68     # Mgmt+Finance+Purch+Security
    assert _anual(out["0190"]) == 2200.35     # sin madre: se queda
    assert _anual(out["0205"]) == 366.72


def test_no_se_pierde_ni_se_inventa_plata():
    """Consolidar es reagrupar, no recalcular: el total tiene que ser identico."""
    uniform = {d: [i + 1.5] * 12 for i, d in enumerate(PADRES)}
    antes = sum(sum(v) for v in uniform.values())
    despues = sum(sum(v) for v in consolidar_a_la_madre(uniform, PADRES).values())
    assert round(antes, 6) == round(despues, 6)


def test_el_linen_del_spa_sube_al_0130():
    """En la pantalla el linen salia a nombre del 0132, que no es el
    departamento con el que se lee el P&L."""
    out = consolidar_a_la_madre({"0132": [1558.58 / 12] * 12}, PADRES)
    assert list(out) == ["0130"]
    assert _anual(out["0130"]) == 1558.58


def test_mes_a_mes_no_solo_el_anual():
    out = consolidar_a_la_madre(
        {"0122": [100.0] + [0.0] * 11, "0123": [0.0, 50.0] + [0.0] * 10},
        PADRES,
    )
    assert out["0120"][0] == 100.0
    assert out["0120"][1] == 50.0
    assert out["0120"][2] == 0.0


def test_sube_mas_de_un_nivel():
    padres = {"0124": "0122", "0122": "0120"}
    out = consolidar_a_la_madre({"0124": [10.0] * 12}, padres)
    assert list(out) == ["0120"]


def test_un_ciclo_no_cuelga_la_pantalla():
    padres = {"0991": "0992", "0992": "0991"}
    out = consolidar_a_la_madre({"0991": [5.0] * 12}, padres)
    assert _anual(next(iter(out.values()))) == 60.0
