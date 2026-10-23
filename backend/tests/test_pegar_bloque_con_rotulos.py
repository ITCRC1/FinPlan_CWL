# -*- coding: utf-8 -*-
"""Pegar desde Excel arrastrando sobre la tabla, no seleccionando el rectángulo.

Owner, 2026-10-22, sobre la grilla de pax (8 tipos × 12 meses): *«que se pueda
hacer copy paste fácilmente»*.

## Lo que fallaba

Pegar YA funcionaba — si uno seleccionaba exactamente el rectángulo de números.
Pero nadie copia así: se arrastra sobre la tabla de Excel y se lleva la columna
de nombres y la fila de meses.

Eso entraba como dato. «Treehouse king bed» no parsea, así que la primera
columna se llenaba de ceros y los doce números quedaban **corridos un lugar**:
enero recibía el valor de diciembre anterior y diciembre quedaba vacío. Con pax
—todos entre 1,8 y 1,9— el resultado se ve perfectamente plausible y nada
avisa.

## Dónde vive el arreglo

En `manejarPegado`, que es el enganche común de las **ocho** grillas que pegan,
y no en cada pantalla: todas se pegan desde la misma tabla y con los mismos
rótulos adelante. Es lo que ya decía el encabezado de `pegarGrilla.ts` —«toda
grilla de la app debería pegarse igual»— y evita que la novena nazca sin él.

## La regla, y por qué es conservadora

Se descarta una fila o una columna sólo si **ninguna** de sus celdas es un
número y **alguna** tiene texto. Una fila de puros números no se pierde nunca:
comerse un mes de datos es mucho peor que dejar pasar un rótulo, que el usuario
ve y borra.

⚠️ El defecto que esto casi repite: la primera versión probaba «es número» con
`Number.isFinite(numeroDeExcel(t))`, y `numeroDeExcel` devuelve **0** para lo
que no entiende, no `NaN`. Con eso «Enero» pasaba por número, el encabezado
nunca se descartaba y el bloque seguía entrando corrido. Lo atrapó la prueba
del caso real, no la lectura del código.
"""
import re

import pytest

from tests._rutas import FRONT

PEGAR = FRONT / "lib" / "pegarGrilla.ts"
GRILLA_PAX = FRONT / "app" / "revenue" / "pax" / "GrillaPax.tsx"


@pytest.fixture(scope="module")
def fuente() -> str:
    assert PEGAR.exists(), f"no está {PEGAR}"
    return PEGAR.read_text(encoding="utf-8")


def test_el_enganche_COMUN_recorta_los_rotulos(fuente):
    """Las ocho grillas lo heredan sin tocar ocho archivos."""
    cuerpo = fuente[fuente.index("export function manejarPegado"):]
    assert "recortarRotulos" in cuerpo[:800], (
        "`manejarPegado` tiene que recortar los rótulos; ponerlo en cada "
        "pantalla deja fuera a la que se escriba mañana")


def test_existe_el_recortador(fuente):
    assert "export function recortarRotulos" in fuente


def test_NO_usa_isFinite_sobre_numeroDeExcel(fuente):
    """⚠️ El defecto exacto que ya se cometió una vez.

    `numeroDeExcel("Enero")` devuelve **0**, no `NaN`. Probar con
    `Number.isFinite` da `true` para cualquier texto, el encabezado nunca se
    descarta y el bloque entra corrido una columna — sin que nada falle.

    ⚠️ Esta prueba mira el CÓDIGO, no el texto: el comentario de
    `recortarRotulos` nombra `isFinite` justamente para explicar por qué no se
    usa. Buscar la palabra suelta marcaba ese comentario como el defecto — el
    mismo error de leer «nan» dentro de «Maintenance».
    """
    cuerpo = fuente[fuente.index("export function recortarRotulos"):]
    codigo = re.sub(r"//[^\n]*|/\*.*?\*/", "", cuerpo, flags=re.S)
    assert "isFinite" not in codigo, (
        "`numeroDeExcel` devuelve 0 para texto: `Number.isFinite` lo da por "
        "número. Hay que mirar la FORMA del texto.")
    assert "\\d" in codigo, (
        "se espera una prueba por forma del texto (regex con dígitos)")


def test_una_fila_de_PUROS_NUMEROS_nunca_se_descarta(fuente):
    """El contrapeso. Comerse un mes de datos es peor que dejar pasar un
    rótulo: el rótulo se ve en la celda y se borra; el mes perdido no se ve."""
    cuerpo = fuente[fuente.index("export function recortarRotulos"):]
    assert "!celdas.some(esNumero)" in cuerpo, (
        "la condición tiene que exigir que NINGUNA celda sea número")
    assert "celdas.some(c =>" in cuerpo, (
        "y que ALGUNA tenga texto, para no descartar una fila vacía")


def test_no_se_come_la_unica_columna(fuente):
    """Una grilla de una sola columna de números quedaría en cero."""
    cuerpo = fuente[fuente.index("export function recortarRotulos"):]
    assert "b[0].length > 1" in cuerpo


def test_solo_mira_la_PRIMERA_fila_de_encabezado(fuente):
    """Dos filas de puro texto seguidas ya no son un encabezado sino otra cosa.
    Adivinar de más es peor que pegar de menos."""
    cuerpo = fuente[fuente.index("export function recortarRotulos"):]
    assert "b = b.slice(1)" in cuerpo
    assert "while" not in cuerpo.split("b = b.slice(1)")[0], (
        "el encabezado se recorta UNA vez, no en bucle")


def test_la_pantalla_DICE_que_se_puede_pegar():
    """⚠️ La mitad del problema no era el código.

    La pantalla rotulaba el bloque como «(digitar)» y el texto de ayuda nunca
    mencionaba el pegado: le estaba diciendo al usuario que tecleara 96 celdas
    a mano sobre una grilla que ya sabía pegarse.
    """
    t = GRILLA_PAX.read_text(encoding="utf-8")
    assert "(digitar)" not in t, "el rótulo no puede decir solo «digitar»"
    assert "pegar desde Excel" in t
    assert "Pegue un bloque desde Excel" in t, (
        "la ayuda tiene que explicar cómo, no solo que se puede")


def test_las_ocho_grillas_siguen_usando_el_enganche_comun():
    """Si una pantalla se pega por su cuenta, no hereda el arreglo.

    Es el modo de falla que este archivo existe para evitar, y ya pasó con
    `num()` de rack rates, que borraba todas las comas y metía un `2,1` como
    **21**.
    """
    usan = sorted(p.relative_to(FRONT).as_posix()
                  for p in FRONT.joinpath("app").rglob("*.tsx")
                  if "manejarPegado" in p.read_text(encoding="utf-8"))
    assert len(usan) >= 8, f"se esperaban al menos 8 grillas, hay {len(usan)}: {usan}"
    assert "app/revenue/pax/GrillaPax.tsx" in usan
