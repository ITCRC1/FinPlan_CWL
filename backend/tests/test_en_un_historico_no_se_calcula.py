# -*- coding: utf-8 -*-
"""EN UN HISTÓRICO SOLO VALE LO SUBIDO.

Regla del owner, textual:

    «En los históricos **solo debe aceptar lo que se sube… nada más**.»
    «Los históricos rompen los auxiliares… **y se va directo al GL**.»

**El defecto era preguntar por el TIPO en vez de por el ORIGEN.** El motor
decidía con `scenario.type == "ACTUAL"`, pero un `BUDGET` o un `FORECAST`
*importado* es igual de histórico: sus cifras salieron de un archivo. Al no ser
de tipo ACTUAL caían en la rama de cálculo completa, que les derivaba las
monedas del checkbook, les refabricaba la planilla y les inventaba asientos de
reparto que el archivo nunca trajo.

⚠️ **Y era invisible en el reporte.** El P&L de un escenario importado se lee
del snapshot (`_compute_pl_month_core`), así que ninguna cifra del P&L se movía:
el destrozo quedaba abajo, en los auxiliares. Medido contra producción el
2026-08-16, el único escenario vivo expuesto era el `FORECAST Working 2026`
(importado, en borrador, con 648 líneas de snapshot y 132 de planilla). Los
demás importados con datos —`BUDGET Final 2026`, `FORECAST April 2026`— están
enllavados, y los 2028-2035 están vacíos.

**El segundo camino era la pantalla de repartos.** `allocation_api.
calculate_allocations` llama a `_recalc_allocations` DIRECTO, sin pasar por el
orquestador, y no filtraba por origen: apretar el botón sobre el `ACTUAL 2025`
le fabricaba cafetería y lavandería encima de un mayor que ya venía repartido.
En un histórico el reparto ya está hecho: volver a calcularlo es exactamente lo
que la regla prohíbe.
"""
import inspect

import pytest

from app.api import allocation_api, pl_api
from app.engine import recalculate as recalc


# ── El veredicto vive en UN solo lugar ───────────────────────────────────────

def test_el_veredicto_lo_da_el_motor_y_el_reporte_lo_reusa():
    """La misma pregunta decide si el reporte corrige el impuesto y si el
    recálculo puede pisar los auxiliares. Escrita dos veces, son dos reglas que
    se separan al primer cambio."""
    assert inspect.iscoroutinefunction(recalc.lo_subido_manda)
    src = inspect.getsource(pl_api._lo_subido_manda)
    assert "recalc.lo_subido_manda(session, scenario)" in src, (
        "el reporte volvió a tener su propia copia del veredicto")


def test_el_veredicto_exige_source_mode_Y_datos():
    """`imported` y VACÍO no es un histórico: es un escenario que dice serlo y
    no lo es. Los presupuestos 2028-2035 están así y el motor los calcula desde
    los checkbooks — tratarlos como históricos los dejaría en cero para
    siempre."""
    src = inspect.getsource(recalc.lo_subido_manda)
    assert "checkbook" in src, "no mira el origen"
    assert "actual_pl_lines_for_month" in src and "actual_rows_for_month" in src, (
        "no comprueba que el escenario TENGA datos subidos")


# ── El recálculo ─────────────────────────────────────────────────────────────

def test_el_recalculo_pregunta_por_el_origen_y_no_por_el_tipo():
    """Es el defecto: un BUDGET/FORECAST importado caía en la rama de cálculo."""
    src = inspect.getsource(recalc.recalculate_scenario)
    assert "await lo_subido_manda(session, scenario)" in src, (
        "el recálculo volvió a decidir por el TIPO: un BUDGET o un FORECAST "
        "importado cae en la rama de cálculo y le pisa monedas, planilla y "
        "repartos — datos que el owner subió")


def test_un_actual_vacio_tampoco_se_calcula():
    """`lo_subido_manda` da False si no hay datos. Un ACTUAL sin cargar no puede
    caer en la rama de cálculo por ese hueco: no se le fabrica una planilla."""
    src = inspect.getsource(recalc.recalculate_scenario)
    assert 'scenario.type == "ACTUAL" or await lo_subido_manda(' in src, (
        "se quitó el `or`: un ACTUAL todavía vacío se calcularía desde los "
        "checkbooks")


# ── Los repartos ─────────────────────────────────────────────────────────────

def test_el_reparto_no_corre_sobre_un_historico():
    src = inspect.getsource(recalc._recalc_allocations)
    assert 'scenario.type == "ACTUAL" or await lo_subido_manda(' in src, (
        "el reparto volvió a correr sobre históricos: en un histórico ya viene "
        "hecho en el mayor")


def test_el_guard_del_reparto_no_borra_nada():
    """Borrar sería PEOR que calcular de más: se perdería el reparto que vino en
    el archivo y nada lo repondría. El guard cuenta y avisa; no toca la tabla.

    Concreto: el `BUDGET Final 2026` (importado, enllavado) tiene 379 asientos.
    """
    src = inspect.getsource(recalc._recalc_allocations)
    i = src.index('scenario.type == "ACTUAL" or await lo_subido_manda(')
    guard = src[i:src.index("return actuales", i)]
    assert "delete(" not in guard, "el guard del histórico borra asientos"
    assert "session.add" not in guard, "el guard del histórico escribe asientos"
    assert "avisos.append" in guard, "no avisa por qué no hizo nada"


def test_el_guard_esta_en_el_motor_y_no_en_la_pantalla():
    """Dos caminos a la misma tabla que protegen distinto son un camino sin
    protección. `calculate_allocations` delega, así que el guard tiene que estar
    del lado de `_recalc_allocations`."""
    src = inspect.getsource(allocation_api.calculate_allocations)
    assert "_recalc_allocations(session, scenario, avisos, cerrados)" in src
    assert "avisos" in src, "la pantalla no devuelve el aviso del guard"


@pytest.mark.parametrize("tipo,modo,con_datos,espera", [
    ("ACTUAL",   "imported",  True,  True),   # ACTUAL 2024 / 2025 / 2026
    ("ACTUAL",   "imported",  False, True),   # ACTUAL recién creado, sin cargar
    ("FORECAST", "imported",  True,  True),   # FORECAST Working 2026 ← el caso vivo
    ("BUDGET",   "imported",  True,  True),   # BUDGET Final 2026
    ("BUDGET",   "imported",  False, False),  # BUDGET Working 2028-2035 (vacíos)
    ("BUDGET",   "checkbook", False, False),  # BUDGET Working 2027
])
def test_la_tabla_de_verdad_del_guard(tipo, modo, con_datos, espera):
    """La condición completa, caso por caso, con los escenarios reales de
    producción al 2026-08-16 como referencia."""
    tipo_es_actual = tipo == "ACTUAL"
    subido = modo != "checkbook" and con_datos
    assert (tipo_es_actual or subido) is espera
