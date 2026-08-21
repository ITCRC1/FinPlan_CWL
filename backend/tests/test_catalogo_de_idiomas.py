# -*- coding: utf-8 -*-
"""El catálogo de idiomas no puede tener agujeros.

Un `t("loQueSea")` sin entrada en el catálogo **no rompe nada**: next-intl
renderiza el nombre de la clave. La pantalla queda diciendo `accountDescription`
en vez de «Descripción de la cuenta», y eso solo se descubre mirándola.

Peor todavía: una clave que existe en `es.json` y falta en `en.json` deja la app
funcionando perfecta en español y con basura en inglés — o sea, se descubre
recién cuando la ve el que la pidió.

Estas dos pruebas cierran las dos puertas:
  1. Toda clave usada en el código existe en los dos idiomas.
  2. Los dos catálogos tienen exactamente las mismas claves.
"""
import json
import pathlib
import re

import pytest

from tests._rutas import FRONT
MSGS = FRONT / "messages"
APP = FRONT / "app"
COMP = FRONT / "components"

# `const t = useTranslations("ns")` → alias: namespace
DECL = re.compile(r'const\s+(\w+)\s*=\s*useTranslations\(\s*"([^"]+)"\s*\)')


def _catalogo(idioma: str) -> dict:
    return json.loads((MSGS / f"{idioma}.json").read_text(encoding="utf-8"))


def _plano(d: dict, pre: str = "") -> set[str]:
    out: set[str] = set()
    for k, v in d.items():
        if isinstance(v, dict):
            out |= _plano(v, f"{pre}{k}.")
        else:
            out.add(pre + k)
    return out


def _usos() -> set[tuple[str, str, str]]:
    """(archivo, namespace, clave) de cada t("...") del frontend."""
    usos = set()
    for carpeta in (APP, COMP):
        if not carpeta.exists():
            continue
        # ⚠️ `.ts` TAMBIÉN, no solo `.tsx`. Esta guarda miraba únicamente los
        # `.tsx`, y por eso `reports/junta/secciones.ts` y `versiones.ts`
        # vivieron con 23 textos en español a mano —los títulos y las preguntas
        # de cada lámina del reporte al directorio, los encabezados más grandes
        # de esa presentación— sin que nada los señalara. Ni el build, ni el
        # tipado, ni esta prueba los veían.
        for p in [*carpeta.rglob("*.tsx"), *carpeta.rglob("*.ts")]:
            s = p.read_text(encoding="utf-8")
            ns_por_alias = dict((a, n) for a, n in DECL.findall(s))
            if not ns_por_alias:
                continue
            alias = "|".join(re.escape(a) for a in ns_por_alias)
            for m in re.finditer(r"\b(" + alias + r")(?:\.rich|\.raw)?\(\s*\"([^\"]+)\"", s):
                usos.add((p.name, ns_por_alias[m.group(1)], m.group(2)))
    return usos


@pytest.mark.skipif(not MSGS.exists(), reason="no está el frontend")
def test_ninguna_clave_usada_apunta_al_vacio():
    """Si esto falla, la pantalla muestra el nombre de la clave como si fuera
    texto. No hay error, no hay pantalla en blanco: solo un rótulo que dice
    `accountDescription`."""
    catalogos = {i: _plano(_catalogo(i)) for i in ("es", "en")}
    faltan = []
    for arch, ns, clave in sorted(_usos()):
        entera = f"{ns}.{clave}"
        for idioma, claves in catalogos.items():
            if entera not in claves:
                faltan.append(f"{idioma}: {entera}  (en {arch})")
    assert not faltan, "claves usadas que no existen en el catálogo:\n  " + "\n  ".join(faltan)


@pytest.mark.skipif(not MSGS.exists(), reason="no está el frontend")
def test_los_dos_idiomas_tienen_las_mismas_claves():
    """Una clave que está solo en español deja la app impecable en español y con
    el nombre de la clave en inglés — se descubre recién cuando la ve el que la
    pidió."""
    es, en = _plano(_catalogo("es")), _plano(_catalogo("en"))
    solo_es = sorted(es - en)
    solo_en = sorted(en - es)
    assert not solo_es and not solo_en, (
        f"solo en es.json: {solo_es}\nsolo en en.json: {solo_en}")


@pytest.mark.skipif(not MSGS.exists(), reason="no está el frontend")
def test_ninguna_traduccion_esta_vacia():
    for idioma in ("es", "en"):
        cat = _catalogo(idioma)

        def revisar(d, pre=""):
            for k, v in d.items():
                if isinstance(v, dict):
                    revisar(v, f"{pre}{k}.")
                elif isinstance(v, str):
                    assert v.strip(), f"{idioma}: {pre}{k} está vacía"

        revisar(cat)
