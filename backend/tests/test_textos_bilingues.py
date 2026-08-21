# -*- coding: utf-8 -*-
"""Los textos que la API manda en respuestas 200, en los dos idiomas.

Hermano de `test_errores_bilingues`. Aquel cubre lo que viaja en una excepción;
esto, lo que viaja en un 200: el aviso al guardar, el resultado del chequeo, la
nota al pie. El frontend los pinta tal cual, así que en español se quedaban
aunque la app estuviera en inglés.

⚠️ **El modo de fallar es silencioso**: una clave mal escrita no rompe nada —
`t()` devuelve la clave y la pantalla muestra `chequeo.identidad_ok` como si
fuera un mensaje. Por eso esto mira el CÓDIGO, no solo el catálogo.
"""
from __future__ import annotations

import ast
import pathlib
import re

import pytest

from app.textos import TEXTOS, idioma_de, t

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
RESERVADOS = {"locale", "clave", "self"}


def _claves_usadas() -> set[str]:
    usadas = set()
    for p in APP.rglob("*.py"):
        try:
            arbol = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:                              # pragma: no cover
            continue
        for n in ast.walk(arbol):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == "t" and len(n.args) >= 2
                    and isinstance(n.args[1], ast.Constant)
                    and isinstance(n.args[1].value, str)):
                usadas.add(n.args[1].value)
    return usadas


def test_toda_clave_usada_existe():
    faltan = sorted(_claves_usadas() - set(TEXTOS))
    assert not faltan, (
        f"claves usadas que no están en TEXTOS: {faltan[:8]} — la pantalla "
        f"mostraría el nombre de la clave como si fuera el mensaje")


def test_todo_texto_tiene_los_dos_idiomas():
    incompletos = sorted(k for k, v in TEXTOS.items() if not v.get("es") or not v.get("en"))
    assert not incompletos, incompletos


@pytest.mark.parametrize("clave", sorted(TEXTOS))
def test_los_parametros_coinciden_entre_idiomas(clave):
    saca = lambda s: set(re.findall(r"\{(\w+)", s))
    assert saca(TEXTOS[clave]["es"]) == saca(TEXTOS[clave]["en"]), clave


@pytest.mark.parametrize("clave", sorted(TEXTOS))
def test_ningun_parametro_pisa_la_firma(clave):
    """`t(locale, clave, **params)`: un parámetro que se llame igual que uno de
    esos revienta al llamarse. No lo cacha ni el import ni la suite."""
    for idioma in ("es", "en"):
        choque = set(re.findall(r"\{(\w+)", TEXTOS[clave][idioma])) & RESERVADOS
        assert not choque, f"[{idioma}] '{clave}' usa {sorted(choque)}"


def test_el_texto_cambia_de_idioma():
    clave = next(k for k, v in TEXTOS.items() if v["es"] != v["en"] and "{" not in v["es"])
    assert t("es", clave) == TEXTOS[clave]["es"]
    assert t("en", clave) == TEXTOS[clave]["en"]


def test_una_clave_que_no_existe_no_revienta():
    assert t("es", "no.existe") == "no.existe"


def test_el_motor_no_usa_este_catalogo():
    """⚠️ `app/engine/` no puede enterarse del idioma. Lo suyo se resuelve al
    revés: emite una clave y el frontend traduce. Si el motor importara esto,
    volvería a decidir el idioma sin saberlo."""
    for p in (APP / "engine").rglob("*.py"):
        txt = p.read_text(encoding="utf-8")
        assert "app.textos" not in txt, f"{p.name} importa app/textos.py"


class _Req:
    def __init__(self, cab=None, lang=None):
        self.headers = {"accept-language": cab} if cab else {}
        self.query_params = {"lang": lang} if lang else {}


def test_el_idioma_sale_de_la_query_o_de_la_cabecera():
    """La query manda: las descargas van por `<a href>` y un href no manda
    cabeceras — sin esto el Excel sale en el idioma del navegador."""
    assert idioma_de(_Req("es", lang="en")) == "en"
    assert idioma_de(_Req("en")) == "en"
    assert idioma_de(_Req()) == "es"
