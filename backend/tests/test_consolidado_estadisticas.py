# -*- coding: utf-8 -*-
"""Estadísticas de habitaciones para el Excel en vivo (owner, 2026-11-11).

Se blinda que salgan del mismo armado que el encabezado del P&L y que cada
indicador nuevo se derive de los de siempre, no de otra fuente.
"""
import pathlib
from types import SimpleNamespace

from app.api import consolidado_api as ca

FUENTE = (pathlib.Path(__file__).resolve().parents[1] / "app" / "api"
          / "consolidado_api.py").read_text(encoding="utf-8")


def _cuerpo(nombre: str) -> str:
    i = FUENTE.index(f"async def {nombre}(")
    j = FUENTE.find("\n@router", i + 1)
    return FUENTE[i: j if j > 0 else len(FUENTE)]


KPIS = {"rooms_available": 930, "rooms_occupied": 465.0, "guests": 837.0,
        "occupancy_pct": 0.5, "adr": 400.0, "revpar": 300.0}
LINEAS = [SimpleNamespace(line_code="REV_ROOMS", amount_usd=190000.0),
          SimpleNamespace(line_code="TOTAL_REVENUES", amount_usd=279000.0)]


def test_indicadores_de_un_mes():
    i = ca.indicadores_del_periodo(KPIS, LINEAS, 31)
    assert i["units"] == 30.0
    assert i["rooms_available"] == 930 and i["rooms_occupied"] == 465.0
    assert i["occupancy_pct"] == 0.5
    assert i["adr_total"] == 279000.0 / 465.0
    assert i["revpar_rooms"] == 200.0          # ADR × ocupación
    assert i["revpar"] == 300.0                # el del P&L, sin recalcular


def test_el_adr_es_el_del_pl_y_no_la_linea_rev_rooms():
    """REV_ROOMS / ocupadas daría 408.6: incluye cancelaciones y no-shows que no
    ocupan habitación. El ADR viene de las estadísticas."""
    i = ca.indicadores_del_periodo(KPIS, LINEAS, 31)
    assert i["adr"] == 400.0
    assert i["rooms_revenue"] == 190000.0


def test_un_mes_sin_ocupacion_no_divide_por_cero():
    i = ca.indicadores_del_periodo({"rooms_available": 900}, [], 30)
    assert i["adr_total"] == 0.0 and i["units"] == 30.0


def test_acepta_las_lineas_del_anual_como_dict():
    i = ca.indicadores_del_periodo(KPIS, [{"line_code": "TOTAL_REVENUES", "amount_usd": 10.0}], 365)
    assert i["total_revenue"] == 10.0


def test_reusa_el_armado_del_pl_y_va_con_la_llave():
    cuerpo = _cuerpo("consolidado_estadisticas")
    assert "pl_api._monthly_results(" in cuerpo and "pl_api._aggregate(" in cuerpo
    assert "lector_del_consolidado" in cuerpo
    assert "_escoger_escenario(" in cuerpo


def test_trae_los_indicadores_que_pidio_el_owner():
    claves = [k for k, _n, _u in ca.INDICADORES]
    for k in ("units", "rooms_available", "rooms_occupied", "occupancy_pct",
              "adr", "adr_total", "revpar"):
        assert k in claves


def test_sin_adr_guardado_el_mes_usa_la_regla_del_anio():
    """Un ACTUAL no guarda ADR por mes: sin esto el mes daba 0 y el año no."""
    k = {**KPIS, "adr": 0.0}
    i = ca.indicadores_del_periodo(k, LINEAS, 31)
    assert i["adr"] == 190000.0 / 465.0
    assert i["revpar_rooms"] == i["adr"] * 0.5


def test_las_unidades_del_anio_cuentan_solo_meses_con_habitaciones():
    cuerpo = _cuerpo("consolidado_estadisticas")
    assert "dias_con_hab" in cuerpo
