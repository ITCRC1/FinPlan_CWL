# -*- coding: utf-8 -*-
"""La plantilla tiene que ENSEÑAR todo lo que la subida va a pisar.

**El defecto (owner, 2026-10-06, quinto 409 de la misma subida).**

    cambiar ActualEntry.jun: 583.3333 -> 0 (diferencia 583.3333) · 7625 en 0230

El 7625 de Sistemas vive en el mayor (`ActualEntry`) y no en `opex_entries`.
`filas_de_la_clase` decidía por CLASE y todo o nada —«si la derivada trae aunque
sea una fila, manda ella entera»— así que el 7625 no salía en la plantilla. Al
volver a subirla, el archivo no lo traía y la carga lo ponía en cero.

**El todo-o-nada tenía su razón** y sigue teniéndola: mezclar las dos fuentes
duplica, porque el Spa vive en `0130` en el mayor y en `0140` en `opex_entries`
y sumarlas metía la misma plata dos veces con dos departamentos distintos.

La salida no es elegir una fuente: es comparar por LLAVE CONSOLIDADA. Las dos
filas del Spa caen en `(0140, 4201)` y la del mayor se descarta; el 7625 de
Sistemas no tiene con quién chocar y entra. Esta prueba fija las dos mitades —
que no duplique y que no esconda— porque arreglar una rompiendo la otra es el
viaje de ida y vuelta que este archivo lleva cuatro commits intentando cerrar.
"""
from decimal import Decimal

from app.api.scenarios_api import filas_de_la_clase


class _Fila:
    """Lo mínimo que `filas_de_la_clase` mira de una fila."""

    def __init__(self, dept_code, account_code, account_name=""):
        self.dept_code = dept_code
        self.account_code = account_code
        self.account_name = account_name

    def __repr__(self):                                  # para que el fallo se lea
        return f"{self.account_code}@{self.dept_code}"


def _llaves(filas):
    return {(f.dept_code, f.account_code) for f in filas}


def test_la_fila_que_solo_vive_en_el_mayor_sale_en_la_plantilla():
    """El caso del owner: 7625 en 0230, en el mayor y no en opex_entries."""
    derivadas = [_Fila("0110", "7065"), _Fila("0120", "7400")]
    mayor = [_Fila("0110", "7065"), _Fila("0120", "7400"), _Fila("0230", "7625")]
    salida = filas_de_la_clase(derivadas, mayor, "7")
    assert ("0230", "7625") in _llaves(salida)


def test_el_spa_no_entra_dos_veces():
    """0130 (mayor) y 0140 (derivada) son el MISMO lugar: una sola fila.

    Es el doble conteo que el todo-o-nada cuidaba. Si esta prueba se cae, la
    plantilla muestra la misma plata dos veces y al subirla se duplica.
    """
    derivadas = [_Fila("0140", "4201")]
    mayor = [_Fila("0130", "4201")]
    salida = filas_de_la_clase(derivadas, mayor, "4")
    assert len(salida) == 1
    assert salida[0].dept_code == "0140"          # manda la derivada


def test_la_derivada_manda_cuando_los_dos_tienen_la_misma_llave():
    derivadas = [_Fila("0110", "7065", "lo que digito el owner")]
    mayor = [_Fila("0110", "7065", "lo que trajo el mayor")]
    salida = filas_de_la_clase(derivadas, mayor, "7")
    assert len(salida) == 1
    assert salida[0].account_name == "lo que digito el owner"


def test_sin_tabla_derivada_manda_el_mayor_entero():
    """El respaldo de siempre: un escenario cuyo detalle llegó por otra puerta."""
    mayor = [_Fila("0110", "7065"), _Fila("0230", "7625")]
    salida = filas_de_la_clase([], mayor, "7")
    assert _llaves(salida) == {("0110", "7065"), ("0230", "7625")}


def test_solo_la_clase_pedida():
    derivadas = [_Fila("0110", "7065")]
    mayor = [_Fila("0110", "4000"), _Fila("0230", "7625"), _Fila("0110", "6000")]
    salida = filas_de_la_clase(derivadas, mayor, "7")
    assert _llaves(salida) == {("0110", "7065"), ("0230", "7625")}


def test_las_contrapartidas_siguen_fuera():
    """Las genera el motor y no se digitan: no van en una plantilla para digitar.

    Ya lo vigila `test_contrapartidas_sobreviven`; acá se comprueba que abrir la
    puerta a las filas del mayor no las dejó colarse de vuelta.
    """
    derivadas = [_Fila("0110", "4000")]
    mayor = [_Fila("0161", "4900", "Distribución"),
             _Fila("0220", "4901", "Distribución")]
    salida = filas_de_la_clase(derivadas, mayor, "4")
    assert _llaves(salida) == {("0110", "4000")}
    # Y tampoco por el camino del respaldo.
    assert filas_de_la_clase([], mayor, "4") == []
