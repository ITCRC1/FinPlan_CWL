# -*- coding: utf-8 -*-
"""Una llave de texto que no existe revienta la pantalla, y el typecheck no la ve.

`t("totalRevenue")` compila perfecto: para TypeScript devuelve un `string` y se
acabó. Si la llave no está en `messages/`, el error aparece **en tiempo de
ejecución**, cuando el usuario abre la pantalla.

Es el mismo patrón que mordió el 2026-10-06 por la mañana con la Auditoría del
mayor —la pantalla leía `data.por_grupo` y la respuesta no lo mandaba, así que
TODA subida buena terminaba en «esta pantalla no se pudo dibujar»— y me volvió a
morder por la tarde, escribiendo la bajada por mes de Room Stats: use
`t("totalRevenue")` y esa llave no existía. No lo encontró el typecheck: lo
encontré mirando a mano, y sólo porque venía con la mañana fresca.

Las dos mitades del contrato viven en archivos distintos —la pantalla en `.tsx`,
los textos en `messages/*.json`— y nada las mira juntas. Esta prueba las mira.

## Qué revisa y qué no

Resuelve el espacio de nombres de cada `useTranslations("x")` y comprueba sus
`t("llave")` **literales**, en los dos idiomas.

⚠️ Las llaves ARMADAS —`t(\\`tab.${p}\\`)`— no se pueden resolver leyendo el
código y se saltan a propósito. Inventar qué valores puede tomar la variable
daría falsos positivos, y una prueba que avisa de más se termina apagando.
"""
import json
import re

from tests._rutas import FRONT

#: `const tc = useTranslations("common")` → {"tc": "common"}
_USO = re.compile(
    r"\bconst\s+(\w+)\s*=\s*useTranslations\(\s*[\"'`]([^\"'`]*)[\"'`]\s*\)")


def _idiomas() -> dict[str, dict]:
    return {f.stem: json.loads(f.read_text(encoding="utf-8"))
            for f in (FRONT / "messages").glob("*.json")}


def _tiene(arbol: dict, espacio: str, llave: str) -> bool:
    cur = arbol
    for parte in (espacio.split(".") if espacio else []) + llave.split("."):
        if not isinstance(cur, dict) or parte not in cur:
            return False
        cur = cur[parte]
    return True


def _pantallas():
    return [f for f in FRONT.rglob("*.tsx") if ".next" not in f.parts]


def test_hay_pantallas_y_hay_idiomas():
    """Si los caminos cambian, esta prueba tiene que avisar — no pasar en verde
    mirando una carpeta vacía."""
    assert _pantallas()
    idiomas = _idiomas()
    assert set(idiomas) >= {"es", "en"}, sorted(idiomas)


def test_toda_llave_literal_existe_en_los_dos_idiomas():
    idiomas = _idiomas()
    faltan: list[str] = []
    for f in _pantallas():
        txt = f.read_text(encoding="utf-8")
        espacios = dict(_USO.findall(txt))
        if not espacios:
            continue
        for var, espacio in espacios.items():
            # Sólo las literales: `t("algo")`. Las armadas se saltan — ver el
            # encabezado.
            for llave in re.findall(rf"\b{var}\(\s*\"([A-Za-z0-9_.]+)\"", txt):
                for idioma, arbol in idiomas.items():
                    if not _tiene(arbol, espacio, llave):
                        faltan.append(
                            f"{f.relative_to(FRONT).as_posix()} · {idioma} · "
                            f"{espacio + '.' if espacio else ''}{llave}")
    assert not faltan, (
        "Estas pantallas piden un texto que no existe. En pantalla no sale el "
        "rótulo: sale un error, y el typecheck no lo ve.\n  "
        + "\n  ".join(sorted(set(faltan))))


def test_los_dos_idiomas_tienen_las_MISMAS_llaves():
    """Una llave en español y no en inglés deja la pantalla rota en un idioma.

    Se mira sólo lo que las pantallas usan de verdad: `messages/` guarda textos
    de pantallas viejas y exigir simetría total sería una limpieza, no un
    candado.
    """
    idiomas = _idiomas()
    es, en = idiomas["es"], idiomas["en"]
    desparejas: list[str] = []
    for f in _pantallas():
        txt = f.read_text(encoding="utf-8")
        for var, espacio in dict(_USO.findall(txt)).items():
            for llave in re.findall(rf"\b{var}\(\s*\"([A-Za-z0-9_.]+)\"", txt):
                completa = f"{espacio + '.' if espacio else ''}{llave}"
                if _tiene(es, espacio, llave) != _tiene(en, espacio, llave):
                    desparejas.append(completa)
    assert not desparejas, (
        "Estas llaves están en un idioma y no en el otro:\n  "
        + "\n  ".join(sorted(set(desparejas))))
