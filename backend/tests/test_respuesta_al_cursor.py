# -*- coding: utf-8 -*-
"""Toda superficie responde al cursor de la misma manera.

«Suavizar el movimiento» (owner, 2026-08-19). El menú ya se desliza y la
pantalla ya entra suave; faltaba lo que uno mira todo el día: la tabla.

⚠️ **Se midió antes de escribir una línea, y la medida cambió el enfoque.**
El spec que trajo el owner proponía un componente compartido más un hook. El
inventario dio **86 tablas escritas a mano y CERO componentes de tabla
compartidos** — el propio spec dice que con seis la capa no sirve hasta
unificarlas. Migrar 86 pantallas para poder resaltar una fila no se paga.

Así que va en CSS, y las 86 responden sin tocar ninguna.

⚠️ **Y por qué un velo (`box-shadow`) y no un `background`:** 73 filas fijan
su fondo EN LÍNEA —totales, variaciones, filas en rojo— y un estilo en línea le
gana a la hoja de estilos. Con `background`, el resaltado habría funcionado en
las tablas simples y NO en las más trabajadas, que son las que más se miran.
Nadie lo habría notado, porque en las otras se ve bien.
"""
import io
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
TEMAS = ["lino", "papel", "grafito", "hoy"]


def _css() -> str:
    return io.open(os.path.join(RAIZ, "app", "globals.css"), encoding="utf-8").read()


def test_el_resaltado_no_usa_background():
    """El invariante que hace que llegue a las 86."""
    css = _css()
    m = re.search(r"\.pag tbody tr:hover > td\s*\{([^}]*)\}", css)
    assert m, "se fue la regla de respuesta al cursor de las tablas"
    cuerpo = m.group(1)
    assert "box-shadow" in cuerpo, "el velo tiene que ser un box-shadow"
    assert not re.search(r"(^|[;\s])background\s*:", cuerpo), (
        "volvió el `background`: no va a aparecer en las 73 filas que fijan su "
        "fondo en línea, que son justo las más trabajadas")


def test_el_velo_existe_en_las_cuatro_paletas():
    """La trampa que ya mordió una vez con el color de marca: se ve bien en el
    tema propio y no existe en el del otro. Sin el token, la regla resuelve a
    `initial` y la tabla deja de responder — sin fallar en ningún lado."""
    css = _css()
    for tema in TEMAS:
        i = css.index(f'[data-tema="{tema}"]')
        bloque = css[i:css.index("}", i)]
        assert "--hover-velo:" in bloque, (
            f"[{tema}] no define --hover-velo: en ese tema la tabla no responde")
    # `:root` es Lino y es el que abre por defecto en una propiedad clonada.
    raiz = css[css.index(":root {"):css.index("[data-tema=\"lino\"]")]
    assert "--hover-velo:" in raiz, ":root se quedó sin el velo"


def test_el_velo_va_en_la_direccion_del_tema():
    """Un velo oscuro sobre un tema oscuro no se ve, y uno claro sobre un tema
    claro tampoco. Cada paleta necesita el suyo, en su dirección."""
    css = _css()
    claros, oscuros = {"lino", "papel"}, {"grafito", "hoy"}
    for tema in TEMAS:
        i = css.index(f'[data-tema="{tema}"]')
        bloque = css[i:css.index("}", i)]
        velo = re.search(r"--hover-velo:\s*rgba\((\d+)", bloque).group(1)
        if tema in claros:
            assert velo == "0", f"[{tema}] es claro: el velo tiene que ser oscuro"
        if tema in oscuros:
            assert velo == "255", f"[{tema}] es oscuro: el velo tiene que ser claro"


def test_no_se_toca_el_encabezado():
    """El encabezado no es una fila de datos, y además va pegado al hacer
    scroll: resaltarlo al pasar por encima no dice nada."""
    css = _css()
    m = re.search(r"(\.pag \w*\s*tbody tr:hover > td)", css)
    assert m and "tbody" in m.group(1), (
        "la regla dejó de estar acotada a `tbody`")


def test_en_tactil_se_apaga():
    """Sin cursor, un hover simulado se queda pegado en la última fila tocada."""
    css = _css()
    i = css.find("@media (hover: none)")
    assert i > 0, "no se desactiva en táctil"
    assert "tr:hover > td" in css[i:i + 200]


def test_se_respeta_quien_pidio_menos_movimiento():
    css = _css()
    i = css.find("prefers-reduced-motion")
    bloque = css[i:i + 400]
    assert "tbody tr:hover > td" in bloque, (
        "la fricción del velo quedó fuera de la regla de movimiento reducido")
