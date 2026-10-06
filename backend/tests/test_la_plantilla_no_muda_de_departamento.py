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
from app.api.scenarios_api import _donde_ya_vive
from app.engine.pl_engine import consolidate_dept_raiz


class Fila:
    """Lo unico que el resolvedor mira."""

    def __init__(self, dept: str):
        self.dept_code = dept


def test_el_spa_vuelve_al_departamento_donde_ya_vive():
    """El caso del owner, tal cual."""
    by_key = {("0130", "4201"): Fila("0130")}
    assert _donde_ya_vive(by_key, "0140", "4201").dept_code == "0130"


def test_una_cuenta_que_no_existe_se_crea_donde_dice_el_archivo():
    """Sin fila previa no hay nada que respetar: manda el archivo."""
    assert _donde_ya_vive({("0130", "4201"): Fila("0130")}, "0140", "4299") is None


def test_una_cuenta_que_ya_esta_en_su_departamento_no_se_toca():
    """El resolvedor solo entra cuando la clave exacta no existe; aun asi, un
    departamento que no es padre de nadie no debe resolver a nada."""
    assert _donde_ya_vive({("0110", "4000"): Fila("0110")}, "0110", "4000") is None


def test_con_DOS_hijos_no_se_adivina():
    """Elegir uno de dos moveria plata con una moneda al aire. Se deja que la
    fila se cree donde dice el archivo, que es el comportamiento de siempre."""
    by_key = {("0130", "4201"): Fila("0130"), ("0132", "4201"): Fila("0132")}
    assert consolidate_dept_raiz("0130") == consolidate_dept_raiz("0132") == "0140"
    assert _donde_ya_vive(by_key, "0140", "4201") is None


def test_no_cruza_entre_departamentos_sin_parentesco():
    """Rooms no es padre del Spa: una cuenta de 0130 no puede atraer a 0110."""
    assert _donde_ya_vive({("0130", "4201"): Fila("0130")}, "0110", "4201") is None


def test_el_spa_de_verdad_cuelga_del_0140():
    """Si el catalogo cambiara esta jerarquia, el arreglo de arriba deja de
    aplicar y esta prueba lo dice antes que un numero raro en el P&L."""
    assert consolidate_dept_raiz("0130") == "0140"
