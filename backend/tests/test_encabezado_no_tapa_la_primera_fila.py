# -*- coding: utf-8 -*-
"""El encabezado de una tabla no puede taparle la primera fila.

**El defecto (owner, 2026-08-14: «favor revisar... no se ve bien»).** El CSS de
la app pega el encabezado de TODA tabla debajo del nav:

    thead th { position: sticky; top: var(--nav-h); }

Eso es correcto cuando la tabla scrollea con la página. Pero un `<div>` con
`overflow-x: auto` se vuelve contexto de scroll en **los dos ejes** —la spec
fuerza `overflow-y` a `auto` cuando el otro eje no es `visible`—, así que el
encabezado deja de resolver contra el viewport y resuelve contra el contenedor:
`top: 44px` lo empuja 44px **hacia abajo dentro de la caja** y le come la primera
fila. Pasa aunque nadie scrollee y aunque la tabla entre entera en pantalla.

Estaban así 20 contenedores en 9 pantallas —Month-End, allocations, control,
tipo de cambio— y ninguna prueba lo veía: el navegador no da error, el dato está
bien, y la fila tapada solo se nota mirando.

La convención de la app es `fin-sticky` (contenedor con scroll propio y
`max-height`) o `fin-scroll-x` (solo horizontal, sin tocar el alto).
"""
import re

from tests._rutas import FRONT

#: Un contenedor de scroll necesita una de estas para que el encabezado se pegue
#: a SU tope (`top: 0`) en vez de al del nav.
CLASES_QUE_ARREGLAN = ("fin-sticky", "fin-scroll-x")

#: Cuántos caracteres después del `<div>` se busca la tabla. Suficiente para el
#: `<table>` y sus estilos; corto para no cazar una tabla de otra sección.
CERCA = 900

ABRE_DIV_CON_SCROLL = re.compile(r'<div\b[^>]*overflowX:\s*"auto"[^>]*>')


def _contenedores_sin_clase() -> list[str]:
    malos = []
    for archivo in sorted(FRONT.joinpath("app").rglob("*.tsx")):
        texto = archivo.read_text(encoding="utf-8")
        if "<table" not in texto:
            continue
        for m in ABRE_DIV_CON_SCROLL.finditer(texto):
            tag = m.group(0)
            if any(c in tag for c in CLASES_QUE_ARREGLAN):
                continue
            if "<table" not in texto[m.end():m.end() + CERCA]:
                continue
            linea = texto[:m.start()].count("\n") + 1
            malos.append(f"{archivo.relative_to(FRONT).as_posix()}:{linea}")
    return malos


def test_hay_pantallas_que_revisar():
    """La prueba tiene que estar mirando algo de verdad.

    Sin esto, un cambio de rutas o de convención la dejaría en verde sin haber
    abierto un solo archivo — que es como este repo ya tuvo 60 pruebas que no
    protegían nada.
    """
    tsx = list(FRONT.joinpath("app").rglob("*.tsx"))
    assert len(tsx) > 50, f"solo {len(tsx)} pantallas: las rutas no resuelven"
    assert any("<table" in a.read_text(encoding="utf-8") for a in tsx)


def test_ningun_contenedor_con_scroll_deja_el_encabezado_flotando():
    malos = _contenedores_sin_clase()
    assert not malos, (
        "Estos <div> scrollean y no declaran `fin-sticky` ni `fin-scroll-x`, asi "
        "que su encabezado se va 44px hacia abajo y tapa la primera fila:\n  "
        + "\n  ".join(malos))


def test_la_clase_existe_en_el_css_y_pega_el_encabezado_arriba():
    """De nada sirve poner la clase si el CSS no la define: quedaria un nombre
    decorativo y el encabezado seguiria tapando la fila."""
    css = FRONT.joinpath("app", "globals.css").read_text(encoding="utf-8")
    for clase in CLASES_QUE_ARREGLAN:
        assert f".{clase} thead th" in css, f"falta la regla de .{clase}"
        regla = css.split(f".{clase} thead th")[1].split("}")[0]
        assert "top: 0" in regla, f".{clase} no pega el encabezado al tope"
