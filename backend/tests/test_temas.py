# -*- coding: utf-8 -*-
"""Las paletas: una sola lista, y que el CSS defina todas.

**El modo de fallar es silencioso.** Si el backend acepta un tema que el CSS no
define, el usuario lo elige, se guarda bien, la petición devuelve 200 — y la
pantalla no cambia de color. No hay error en ningún lado: el CSS simplemente cae
al `:root` porque no existe ese `[data-tema]`. Nadie encuentra eso mirando logs.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.temas import TEMA_POR_DEFECTO, TEMAS

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"


def _css() -> str:
    return (FRONT / "app" / "globals.css").read_text(encoding="utf-8")


@pytest.mark.parametrize("tema", TEMAS)
def test_el_css_define_cada_tema(tema):
    assert f'[data-tema="{tema}"]' in _css(), (
        f"el backend acepta «{tema}» y el CSS no lo define: se guardaría bien y "
        f"la pantalla no cambiaría")


def test_el_frontend_conoce_los_mismos():
    txt = (FRONT / "lib" / "tema.ts").read_text(encoding="utf-8")
    m = re.search(r'export const TEMAS = \[(.*?)\] as const', txt, re.S)
    assert m, "no encontré la lista en lib/tema.ts"
    front = {t.strip().strip('"\'') for t in m.group(1).split(",") if t.strip()}
    assert front == set(TEMAS), (
        f"las dos listas se separaron — backend {sorted(TEMAS)} · "
        f"frontend {sorted(front)}")


def test_el_default_es_el_mismo_de_los_dos_lados():
    txt = (FRONT / "lib" / "tema.ts").read_text(encoding="utf-8")
    assert f'export const TEMA_POR_DEFECTO: Tema = "{TEMA_POR_DEFECTO}"' in txt


def test_el_default_existe():
    assert TEMA_POR_DEFECTO in TEMAS


@pytest.mark.parametrize("tema", TEMAS)
def test_cada_tema_trae_la_paleta_COMPLETA(tema):
    """⚠️ La condición del owner: «si cambia fondo también deben cambiar los
    colores de las letras para que se vea».

    Un tema al que le falte `--text-primary` hereda el del `:root`, y entonces
    queda el texto de una paleta sobre el fondo de otra. Se ve mal pero no
    falla, así que solo se cacha acá."""
    css = _css()
    i = css.index(f'[data-tema="{tema}"]')
    bloque = css[i:css.index("}", i)]
    for token in ("--bg-base", "--bg-surface", "--bg-header",
                  "--text-primary", "--text-secondary",
                  "--border-subtle", "--border-medium",
                  "--positive", "--negative", "--brand",
                  "--nav-fg", "--nav-fg-strong",
                  # La barra tiene tokens PROPIOS desde el 19-ago: en los temas
                  # claros va sobre fondo oscuro, y `--bg-header` no sirve
                  # porque lo comparte con los encabezados de las tablas —
                  # pintarlo negro se habría llevado todas las tablas.
                  "--nav-bg", "--nav-borde", "--nav-accent",
                  "--nav-chip-bg", "--nav-chip-fg"):
        assert token in bloque, f"a «{tema}» le falta {token}"


def _rgb(h): return [int(h[i:i + 2], 16) for i in (1, 3, 5)]


def _lum(h):
    c = [v / 255 for v in _rgb(h)]
    c = [v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4 for v in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]


def _razon(a, b):
    x, y = sorted((_lum(a), _lum(b)), reverse=True)
    return (x + .05) / (y + .05)


@pytest.mark.parametrize("tema", TEMAS)
def test_el_texto_se_lee_sobre_su_fondo(tema):
    """El contraste no es opinión: es la razón WCAG. 4.5 es el mínimo para
    texto normal. Esto es lo que impide que alguien agregue una paleta bonita
    e ilegible."""
    css = _css()
    i = css.index(f'[data-tema="{tema}"]')
    bloque = css[i:css.index("}", i)]
    val = lambda t: re.search(rf"{t}:\s*(#[0-9A-Fa-f]{{6}})", bloque).group(1)

    base, surf = val("--bg-base"), val("--bg-surface")
    for token, fondo, minimo in (
        ("--text-primary",   base, 4.5),
        ("--text-secondary", base, 4.5),
        ("--positive",       surf, 3.0),   # números grandes y en negrita
        ("--negative",       surf, 3.0),
        # La barra, contra SU fondo — no contra el de las tablas.
        ("--nav-fg",         val("--nav-bg"), 4.5),
        ("--nav-fg-strong",  val("--nav-bg"), 4.5),
        # El logo y el subrayado del tab activo, sobre la barra.
        ("--nav-accent",     val("--nav-bg"), 4.5),
        # ⚠️ El chip ES/EN necesita tokens aparte: `--nav-accent` es CLARO para
        # leerse sobre la barra oscura, y como fondo con letra blanca daría
        # 1.9:1. Reusar `--brand` tampoco servía: en Grafito da 3.7:1.
        ("--nav-chip-fg",    val("--nav-chip-bg"), 4.5),
        # ⚠️ `--brand` va a 3.0 y NO a 4.5 porque es color de BORDE y de
        # acento, nunca de texto. La barra «Ir a» lo intentó como texto y no
        # llegaba en los dos temas oscuros —4.11:1 en Grafito, 3.26:1 en Hoy—
        # aunque en Lino y Papel daba 6.6:1 y se veía perfecta. Es la trampa de
        # siempre: se prueba en el tema propio y se rompe en el del otro.
        # Quien quiera texto de marca necesita un token nuevo, no éste.
        ("--brand",          surf, 3.0),
    ):
        r = _razon(val(token), fondo)
        assert r >= minimo, (
            f"[{tema}] {token} sobre su fondo da {r:.2f}:1, "
            f"por debajo de {minimo}:1 — no se lee")
