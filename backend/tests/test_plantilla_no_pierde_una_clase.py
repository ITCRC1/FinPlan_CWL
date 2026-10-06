# -*- coding: utf-8 -*-
"""La plantilla del Detalle no puede salir sin una clase que el mayor SÍ tiene.

**El defecto (medido en producción, 2026-08-15).** El `FORECAST Working 2026`
—la versión con la que el sistema abre para forecast— tenía 279 filas de detalle
GL en `actual_entries` y las tablas derivadas VACÍAS: cero de ingreso, cero de
costo, cero de below-GOP y cero de planilla. Solo `opex_entries` tenía filas.

Su plantilla del Detalle salía así:

    clase 4 (ingreso)      $0        el mayor tiene   $5.216.806,03
    clase 5 (costo)        $0        el mayor tiene     $713.702,26
    clase 6 (planilla)     $0        el mayor tiene   $2.235.541,21
    clase 7 (opex)  $1.552.223       el mayor tiene   $1.552.223,38  ✔
    clase 8 (below) $0               el mayor tiene     $931.584,31

**Por qué importa tanto.** Bajar-corregir-subir es la norma de trabajo del owner,
y el reemplazo completo borra el detalle del escenario y lo reinserta desde el
archivo. Con una plantilla así, ese viaje se lleva por delante $9,1 millones de
movimiento que la plantilla nunca mostró — y el P&L sigue cuadrando consigo
mismo, así que la diferencia solo aparece meses después comparando contra el
auxiliar. Es exactamente el patrón de los $196 mil de las contrapartidas y el de
los $40.613 del Actual 2024.

**La causa.** Las cuatro tablas derivadas + la planilla sintética las escribe UN
solo camino, `POST /scenarios/import-gl-detail/`. Nada las deriva de
`actual_entries`. Un escenario cuyo detalle llegó por otra puerta queda con el
mayor completo y las derivadas vacías, y ningún reporte lo dice.
"""
import pytest

from app.api.scenarios_api import filas_de_la_clase
from app.models.actual_entry import ActualEntry
from app.models.opex_entry import OpexEntry


def _gl(dept, code, name=""):
    return ActualEntry(scenario_id="s", hotel_id="CWL", dept_code=dept,
                       account_code=code, account_name=name)


MAYOR = [
    _gl("0110", "4000", "Rooms"),
    _gl("0140", "4201", "Massage Spa"),
    _gl("0120", "5110", "Food Cost"),
    _gl("0110", "6000", "Salary and Wages"),
    _gl("0110", "7065", "Cleaning Supplies"),
    _gl("0250", "8005", "Owners Fee"),
    # Las dos contrapartidas de allocation, tal cual están en producción.
    _gl("0161", "4900", "Distribución"),
    _gl("0220", "4901", "Distribución"),
]


@pytest.mark.parametrize("clase,esperado", [
    ("4", ["4000", "4201"]),      # sin las contrapartidas
    ("5", ["5110"]),
    ("6", ["6000"]),
    ("7", ["7065"]),
    ("8", ["8005"]),
])
def test_sin_tabla_derivada_la_clase_sale_del_mayor(clase, esperado):
    """El caso del FORECAST Working 2026: la derivada vacía, el mayor completo."""
    filas = filas_de_la_clase([], MAYOR, clase)
    assert [f.account_code for f in filas] == esperado


def test_las_contrapartidas_no_entran_al_respaldo():
    """`4900`/`4901` las genera el motor de repartos: no se digitan.

    Si el respaldo las ofreciera, alguien podría llenarlas en la plantilla y el
    reparto se contaría dos veces — con el P&L cuadrando igual.
    """
    filas = filas_de_la_clase([], MAYOR, "4")
    assert {f.account_code for f in filas} == {"4000", "4201"}


def test_la_misma_plata_no_entra_dos_veces():
    """El Spa vive en el `0130` en el mayor y en el `0140` en `opex_entries`.

    Sumar las dos metería la misma cuenta dos veces, con dos departamentos, y el
    archivo devolvería el doble del gasto del Spa. Por eso la llave con la que se
    comparan las dos fuentes lleva el departamento YA CONSOLIDADO: las dos filas
    caen en `(0140, 7065)` y la del mayor se descarta.
    """
    mayor = [_gl("0130", "7065", "Cleaning Supplies")]
    derivada = [OpexEntry(scenario_id="s", hotel_id="CWL", dept_code="0140",
                          account_code="7065", account_name="Cleaning Supplies")]
    filas = filas_de_la_clase(derivada, mayor, "7")
    assert len(filas) == 1
    assert filas[0].dept_code == "0140"          # manda la derivada


def test_la_cuenta_que_la_derivada_NO_tiene_sale_igual():
    """Lo que cambió el 2026-10-06, y por qué.

    Esto antes era al revés: una sola fila derivada y mandaba ella ENTERA. El
    argumento era que no se puede distinguir un hueco de una fila que el sistema
    movió de departamento — cierto, y por eso la llave se consolida: una fila
    movida de 0130 a 0140 SÍ se reconoce (la prueba de arriba) y se descarta.

    Lo que quedaba sin reconocer era el hueco, y costaba plata. Owner,
    2026-10-06: *«cambiar ActualEntry.jun: 583.3333 → 0 · 7625 en 0230»*. El 7625
    de Sistemas está en el mayor y no en `opex_entries`; la plantilla no lo
    mostraba y la subida lo ponía en cero. En un mes abierto eso pasaba en
    silencio y le movía el GOP.

    Entre enseñar de más y borrar sin avisar, se enseña de más.
    """
    derivada = [OpexEntry(scenario_id="s", hotel_id="CWL", dept_code="0180",
                          account_code="7999", account_name="Otra")]
    filas = filas_de_la_clase(derivada, MAYOR, "7")
    assert {f.account_code for f in filas} == {"7999", "7065"}


def test_sin_mayor_y_sin_derivadas_no_truena():
    """Un escenario en blanco tiene que bajar su plantilla igual."""
    assert filas_de_la_clase([], [], "4") == []


def test_el_endpoint_usa_el_respaldo():
    """Que la función esté REALMENTE cableada en la descarga.

    Sin esto, alguien podría dejarla definida y sin usar, y todo lo de arriba
    seguiría en verde mientras la plantilla vuelve a salir sin ingreso.
    """
    import inspect

    from app.api import scenarios_api

    fuente = inspect.getsource(scenarios_api.export_scenario_detail)
    assert "filas_de_la_clase" in fuente, (
        "La descarga de la plantilla ya no usa el respaldo por clase: un "
        "escenario con el mayor cargado y las derivadas vacías vuelve a bajar "
        "sin ingreso, sin costo, sin planilla y sin below-GOP.")
    # Y que el mayor se siga leyendo: sin `gl_rows` el respaldo no tiene de dónde.
    assert "gl_rows" in fuente
