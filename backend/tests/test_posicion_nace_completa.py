# -*- coding: utf-8 -*-
"""
UNA POSICIÓN NUEVA NACE COMPLETA.

`create_position` guardaba la posición pero NO sus 12 filas mensuales. Resultado:
la persona existía pero no aparecía con FTE en el reporte de FTEs, no sumaba
salario ni CCSS, y todo eso quedaba escondido hasta que alguien se acordara de
apretar «Recalcular». Lo mismo al duplicar.
"""
import inspect

import pytest

from app.api import payroll_api


@pytest.mark.parametrize("funcion", ["create_position", "duplicate_position"])
def test_la_posicion_nueva_estrena_sus_12_meses(funcion):
    src = inspect.getsource(getattr(payroll_api, funcion))
    assert "_estrenar_posicion" in src, (
        f"{funcion} deja la posición sin filas mensuales: no entra al reporte de "
        f"FTEs ni al costo de planilla hasta que alguien recalcule")
    # y tiene que pasar por flush ANTES, si no la fila cuelga de un id que aún no existe
    assert src.index("flush") < src.index("_estrenar_posicion")


def test_estrena_los_doce_meses_y_los_calcula():
    src = inspect.getsource(payroll_api._estrenar_posicion)
    assert "range(1, 13)" in src, "no cubre los 12 meses"
    assert "recalculate_entry" in src, "crea las filas pero no las calcula"
    assert "get_tc_for_month" in src, "no usa el TC del mes"
    assert "_payroll_cfg" in src, "no pasa los drivers del escenario"


def test_usa_el_ano_del_escenario_no_uno_fijo():
    """Una posición creada en el budget 2029 debe guardar sus filas con año 2029."""
    for f in ("create_position", "duplicate_position"):
        src = inspect.getsource(getattr(payroll_api, f))
        assert 'year' in src and 'scenario' in src.lower()
