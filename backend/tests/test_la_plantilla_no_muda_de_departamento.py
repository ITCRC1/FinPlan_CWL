# -*- coding: utf-8 -*-
"""Bajar la plantilla y subirla no mueve una cuenta de departamento.

Owner, 2026-10-06, bajando la plantilla de 12 meses y subiendola SIN TOCARLA:

    RevenueAccountEntry.jan: 6268.2590 → 0 (diferencia 6268.2590) · 4201 en 0130

El Spa se guarda en **0130** (Spa gerencia) y la plantilla lo exporta bajo
**0140** (Spa), que es su padre: `export_scenario_detail` llama a
`consolidate_dept` para que el archivo tenga un solo bloque de Spa. Pero el
import escribia literal lo que leia, asi que la cuenta se creaba en 0140 y la
fila de 0130 se quedaba en cero.

⚠️ **Lo que lo hace peligroso es el mes ABIERTO, no el cerrado.** En un mes
cerrado el candado lo frena —asi aparecio—. En un mes abierto no hay error: el
ingreso se muda de departamento en silencio, y como el P&L consolida los dos, el
total no cambia y nadie se entera. El Spa queda partido, con el ingreso en un
lado y la planilla en el otro.
"""
from app.api.scenarios_api import destinos_de_la_fila
from app.engine.pl_engine import consolidate_dept, consolidate_dept_raiz


class Fila:
    """Lo unico que el resolvedor mira."""

    def __init__(self, dept: str, code: str = "", outlet: str = ""):
        self.dept_code = dept
        self.account_code = code
        self.outlet = outlet


def _uno(by_key, dept, code):
    """El destino unico, o None. Lo que devolvia el resolvedor viejo.

    El de ahora devuelve LA LISTA de filas que esa linea del archivo alimenta
    (ver `test_el_viaje_redondo_es_nulo`); estas pruebas miran el caso de una.
    """
    dest = destinos_de_la_fila(by_key, dept, code)
    propia = [d for d in dest if d.dept_code == dept]
    otros = [d for d in dest if d.dept_code != dept]
    if propia or len(otros) != 1:
        return None
    return otros[0]


def test_el_spa_vuelve_al_departamento_donde_ya_vive():
    """El caso del owner, tal cual."""
    by_key = {("0130", "4201", ""): Fila("0130", "4201")}
    assert _uno(by_key, "0140", "4201").dept_code == "0130"


def test_una_cuenta_que_no_existe_se_crea_donde_dice_el_archivo():
    """Sin fila previa no hay nada que respetar: manda el archivo."""
    by_key = {("0130", "4201", ""): Fila("0130", "4201")}
    assert _uno(by_key, "0140", "4299") is None


def test_una_cuenta_que_ya_esta_en_su_departamento_no_se_toca():
    """Si la llave exacta existe, es ella y no hay nada que resolver."""
    by_key = {("0110", "4000", ""): Fila("0110", "4000")}
    assert _uno(by_key, "0110", "4000") is None
    assert [d.dept_code for d in destinos_de_la_fila(by_key, "0110", "4000")] == ["0110"]


def test_el_criterio_es_UN_escalon_igual_que_la_bajada():
    """Lo que cambio el 2026-10-06 por la tarde, y por que.

    Esto antes decia «con DOS hijos no se adivina» y dejaba la fila creada en el
    padre con las dos hijas en cero — no adivinar estaba bien, dejarlas en cero
    no: era borrar la misma plata por no elegir. Ahora la linea alimenta a TODAS
    las filas que la plantilla plego en ella y se reparte por lo que cada una ya
    tenia (ver `test_el_viaje_redondo_es_nulo`).

    Y el criterio pasa a ser UN escalon, el mismo que usa la bajada. Comparando
    con la cadena entera, el `0132` —que la plantilla baja como `0130`— no se
    reconocia con su propia linea y se iba a cero igual.
    """
    by_key = {("0130", "4201", ""): Fila("0130", "4201"),
              ("0132", "4201", ""): Fila("0132", "4201")}
    assert consolidate_dept_raiz("0130") == consolidate_dept_raiz("0132") == "0140"
    # La bajada escribe 0140 para el 0130 y 0130 para el 0132: dos lineas, y
    # cada una encuentra la suya.
    assert consolidate_dept("0130") == "0140" and consolidate_dept("0132") == "0130"
    assert [d.dept_code for d in destinos_de_la_fila(by_key, "0140", "4201")] == ["0130"]
    assert [d.dept_code for d in destinos_de_la_fila(by_key, "0130", "4201")] == ["0132"]


def test_no_cruza_entre_departamentos_sin_parentesco():
    """Rooms no es padre del Spa: una cuenta de 0130 no puede atraer a 0110."""
    by_key = {("0130", "4201", ""): Fila("0130", "4201")}
    assert destinos_de_la_fila(by_key, "0110", "4201") == []


def test_el_spa_de_verdad_cuelga_del_0140():
    """Si el catalogo cambiara esta jerarquia, el arreglo de arriba deja de
    aplicar y esta prueba lo dice antes que un numero raro en el P&L."""
    assert consolidate_dept_raiz("0130") == "0140"
