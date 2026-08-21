# -*- coding: utf-8 -*-
"""
EL POTE QUE SE REPARTE, ABIERTO POR CLASE DE CUENTA.

La pantalla mostraba el RESULTADO del reparto pero no de dónde salía el monto.
El owner pidió ver cuánto se va a repartir de la clase 5 (costo de ventas), la 6
(salarios) y la 7 (opex), por mes y con el total del año.

El criterio tiene que ser el MISMO que usa el motor: si el endpoint sumara algo
distinto a `_dept_total_cost`, la pantalla diría un número y el reparto otro.
"""
import inspect

from app.api import allocation_api
from app.engine import recalculate


def test_el_endpoint_usa_las_mismas_tres_fuentes_que_el_motor():
    motor = inspect.getsource(recalculate._dept_total_cost)
    vista = inspect.getsource(allocation_api.costo_a_repartir)
    for fn in ("opex_by_dept", "cos_by_dept", "payroll_by_dept"):
        assert fn in motor, f"el motor ya no usa {fn}: revisar el endpoint"
        assert fn in vista, (
            f"el endpoint no suma {fn}: la pantalla mostraría un pote distinto al "
            f"que el motor reparte")


def test_devuelve_las_tres_clases_con_12_meses():
    src = inspect.getsource(allocation_api.costo_a_repartir)
    for clase in ('"5"', '"6"', '"7"'):
        assert clase in src
    assert "range(1, 13)" in src
    assert "totales_mes" in src and "total" in src


def test_el_departamento_es_parametro_no_esta_fijo():
    """Sirve para 0220 (cafetería) y 0161 (lavandería), y para lo que venga."""
    sig = inspect.signature(allocation_api.costo_a_repartir)
    assert "dept" in sig.parameters
    assert sig.parameters["dept"].default == "0220"


# ── Un cero no siempre significa lo mismo ────────────────────────────────────
def test_dice_cuantas_lineas_hay_en_cada_clase():
    """Un total en cero puede ser «no hay lineas» (no aplica) o «hay lineas sin
    monto» (falta llenarlas). Sin esa distincion, el guion se lee como si la
    cuenta no estuviera llegando — que fue justo lo que paso con el OPEX de la
    lavanderia: sus 19 lineas existen y estan todas en cero.
    """
    import inspect
    from app.api import allocation_api
    src = inspect.getsource(allocation_api.costo_a_repartir)
    assert "lineas_cargadas" in src
    assert "donde" in src


def test_las_tres_clases_salen_siempre_aunque_no_apliquen():
    """El owner lo pidio explicito: en lavanderia no hay costo de ventas, pero la
    fila se queda igual para que se vea que se reviso."""
    import inspect
    from app.api import allocation_api
    src = inspect.getsource(allocation_api.costo_a_repartir)
    for clase in ('"5"', '"6"', '"7"'):
        assert clase in src


def test_apunta_a_donde_se_carga_cada_clase():
    import inspect
    from app.api import allocation_api
    src = inspect.getsource(allocation_api.costo_a_repartir)
    assert "OPEX por Departamento" in src
    assert "Planilla" in src
    assert "Cost of Sales" in src
