# -*- coding: utf-8 -*-
"""Cuando el mayor empieza a postear el reparto, la contrapartida vieja cede.

## Lo que paso

Hasta agosto 2026 Integrity NO posteaba el reparto de Cafeteria y Lavanderia.
FinPlan lo sostenia a mano —`4900`/`4901`, -196.326,17 en el año— y por eso esas
filas SOBREVIVEN a cada carga: el archivo no podia traerlas, asi que pisarlas
era borrarlas.

Agosto fue el primer mes en que el mayor SI las trae (`4999-0220`,
`4999-0161`). Sostener ademas la vieja deja el credito dos veces, y la
verificacion de cierre bloqueo por **US$16.974,00** — el reparto del mes,
exacto.

Owner, 2026-09-15: «todo sera tal como revise el pre cierre».

## La regla ahora

La contrapartida vieja sobrevive SALVO que el archivo traiga una para ese
departamento y ese mes. Enero a julio no se mueven: ahi el mayor no la postea.
"""
import inspect

from app.importers.gl_detail_importer import (parse_gl_detail,
                                              contrapartidas_del_archivo)
from tests.test_gl_allocation import FILAS_CON_REPARTO, _plantilla


def test_el_archivo_declara_que_departamentos_traen_contrapartida():
    blk = parse_gl_detail(_plantilla(FILAS_CON_REPARTO))[0]
    assert contrapartidas_del_archivo(blk) == {"0220": {1}, "0161": {1}}


def test_anotarlas_no_las_suma_a_ningun_total():
    """Se anotan para decidir quien cede, no para entrar al P&L. Si entraran,
    volveriamos al doble conteo por la otra punta."""
    blk = parse_gl_detail(_plantilla(FILAS_CON_REPARTO))[0]
    cuentas = {r["account_code"] for k in ("revenue", "costs", "opex", "belowgop")
               for r in blk.get(k, [])}
    assert "4999" not in cuentas


def test_en_pre_cierre_la_lista_va_VACIA():
    """Ahi la contrapartida no se salta: entra como gasto y netea sola. Si
    devolviera algo, el espejo borraria la contrapartida vieja del Actual — y el
    espejo no escribe el Actual."""
    blk = parse_gl_detail(_plantilla(FILAS_CON_REPARTO), en_overhead=True)[0]
    assert contrapartidas_del_archivo(blk) == {}


def test_el_que_calcula_y_el_que_escribe_dicen_lo_mismo():
    """Su propio docstring lo exige: «esto tiene que decir EXACTAMENTE lo que
    hace el escritor». Si se separan, la puerta bloquea una carga correcta o
    deja pasar una mala."""
    from app.api import scenarios_api
    calc = inspect.getsource(scenarios_api._filas_que_sobreviven)
    escritor = inspect.getsource(scenarios_api.import_gl_detail)
    assert "trae_contrapartida" in calc
    assert "contrapartidas_del_archivo(blk)" in escritor, (
        "el escritor tambien tiene que mirar que trae el archivo")
    assert "cede_ae" in escritor


def test_solo_ceden_los_meses_que_el_archivo_trae():
    """Enero a julio no traen 4999: sus contrapartidas no se pueden tocar."""
    calc = inspect.getsource(
        __import__("app.api.scenarios_api", fromlist=["x"])._filas_que_sobreviven)
    assert "m in cede and m in tocados" in calc, (
        "sin el cruce contra los meses del archivo, una carga de agosto "
        "borraria las contrapartidas de todo el año")
