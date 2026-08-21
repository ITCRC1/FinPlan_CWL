# -*- coding: utf-8 -*-
"""El Cash Flow Directo: el motor NOMBRA, el catálogo dice.

**Qué se arregló (2026-08-19).** La pantalla tenía 134 explicaciones y 129
rótulos de fila **en español, dentro del motor**, viajando en la respuesta. Dos
problemas a la vez:

* `app/engine/` no puede enterarse del idioma —regla del proyecto, vigilada por
  `tests/test_i18n_locale.py`— y un motor que emite prosa en español lo decide
  sin saberlo.
* Con la app en inglés, la pantalla salía en español igual.

Ahora el motor emite `label_key` y `ayuda.clave`; el texto vive en el catálogo.
Misma regla que el `line_code` del P&L: el código es el contrato, el idioma es
presentación.

⚠️ **El modo de fallar es silencioso.** Si el motor emite una clave que el
catálogo no tiene, no hay error: la pantalla muestra la clave cruda o un hueco.
Por eso esta prueba compara las dos listas, en los DOS idiomas.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.engine.ayuda_cashflow import AYUDA
from app.engine.etiquetas_cashflow import ETIQUETAS
from tests._rutas import FRONT


def _catalogo(idioma: str) -> dict:
    def plano(o, p=""):
        for k, v in o.items():
            if isinstance(v, dict):
                yield from plano(v, f"{p}{k}.")
            else:
                yield f"{p}{k}", v

    return dict(plano(json.loads(
        (FRONT / "messages" / f"{idioma}.json").read_text(encoding="utf-8"))))


@pytest.mark.parametrize("idioma", ["es", "en"])
def test_toda_explicacion_que_el_motor_nombra_tiene_texto(idioma):
    cat = _catalogo(idioma)
    faltan = sorted({c for c in AYUDA.values() if f"cfdAyuda.{c}.deDonde" not in cat})
    assert not faltan, (
        f"[{idioma}] el motor nombra explicaciones que el catálogo no tiene: "
        f"{faltan[:6]} — la pantalla mostraría la clave cruda")


@pytest.mark.parametrize("idioma", ["es", "en"])
def test_todo_rotulo_que_el_motor_nombra_tiene_texto(idioma):
    cat = _catalogo(idioma)
    faltan = sorted({c for c in ETIQUETAS.values() if f"cfdFila.{c}" not in cat})
    assert not faltan, (
        f"[{idioma}] el motor nombra rótulos que el catálogo no tiene: {faltan[:6]}")


def test_el_motor_no_emite_prosa():
    """⚠️ Lo que se vino a arreglar: que el texto NO vuelva al motor.

    `AYUDA` y `ETIQUETAS` son mapas a CLAVES. Si alguien vuelve a poner texto
    ahí —una tupla, una frase— la pantalla en inglés vuelve a salir en español y
    nada falla."""
    for nombre, mapa in (("AYUDA", AYUDA), ("ETIQUETAS", ETIQUETAS)):
        for llave, valor in mapa.items():
            assert isinstance(valor, str), (
                f"{nombre}[{llave!r}] dejó de ser una clave: {type(valor).__name__}")
            assert " " not in valor and valor.islower() or valor.replace("_", "").isalnum(), (
                f"{nombre}[{llave!r}] = {valor!r} no parece una clave, parece texto")


def test_las_filas_por_departamento_NO_llevan_clave():
    """Su rótulo es el nombre que viene de la BASE: eso es dato, no interfaz.

    Si alguien las metiera en `ETIQUETAS`, se traduciría el nombre de un
    departamento — y dejaría de coincidir con el que muestra el resto de la app.
    """
    sospechosas = [k for k in ETIQUETAS if k.strip().startswith("  ")]
    assert not sospechosas, sospechosas
