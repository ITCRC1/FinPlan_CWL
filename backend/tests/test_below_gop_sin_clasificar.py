# -*- coding: utf-8 -*-
"""El below-GOP que no tiene línea propia se MUESTRA, no se pierde.

Medido el 2026-08-19: el desglose de gastos de propiedad quedaba corto contra
su propio total — **$15.654,92 en el Actual 2024** y **$9.600,00 en el Forecast
April** (exactamente 1.200 por mes de mayo a diciembre).

No era un error de cálculo. En los escenarios con meses reales el total
below-GOP **no se calcula: se DERIVA** de `GOP − EBITDA Before`, y `pl_engine`
lo documenta en su propio comentario: esa resta «captura montos que no están
guardados como línea propia». O sea que hay gasto real que no es alquiler, ni
honorario, ni seguro, ni la línea de otros — y al desglosar desaparecía.

El total siempre estuvo bien. Lo que faltaba era poder VER que una parte no
está clasificada. Por eso ahora es una fila con nombre: no inventa una
categoría, dice cuánto hay y que no se sabe de qué es. Si algún día se
clasifica, la fila baja sola a cero.
"""
import io
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..")


def _motor() -> str:
    p = os.path.join(RAIZ, "app", "engine", "cashflow_directo.py")
    return io.open(p, encoding="utf-8").read()


def test_el_total_de_propiedad_sale_del_pl_y_no_de_sus_partes():
    """Si se volviera a sumar los cuatro componentes, el bloque deja de cerrar
    contra su propio total y la plata sin clasificar se vuelve invisible otra
    vez — sin que falle nada."""
    src = _motor()
    assert 'nonop_pl = serie("nonop")' in src, (
        "el tab de propiedad volvió a calcular su total sumando componentes")
    assert re.search(r"nonop_prop\s*=\s*serie\(\"nonop\"\)", src), (
        "la fila «Gastos de propiedad» del tab de Proveedores volvió a sumar "
        "componentes: el bloque A queda corto contra su propio total")


def test_la_diferencia_es_una_fila_con_nombre():
    src = _motor()
    assert "sin_clasificar = [nonop_pl[i] - desglosado[i] for i in rng]" in src
    assert "Sin clasificar (está en el total, sin línea propia)" in src, (
        "se fue la fila que hace visible el below-GOP sin clasificar")


def test_la_fila_tiene_rotulo_y_ayuda_en_los_dos_idiomas():
    """Una fila del motor sin clave en el catálogo sale en blanco en inglés."""
    import json
    et = io.open(os.path.join(RAIZ, "app", "engine", "etiquetas_cashflow.py"),
                 encoding="utf-8").read()
    assert '"below_gop_sin_clasificar"' in et, (
        "la fila no está en el mapa de etiquetas: saldría sin traducir")
    for idioma in ("es", "en"):
        p = os.path.join(RAIZ, "..", "frontend", "messages", f"{idioma}.json")
        cat = json.load(io.open(p, encoding="utf-8"))
        assert "below_gop_sin_clasificar" in cat["cfdFila"], idioma
        assert "belowGopSinClasificar" in cat["cfdAyuda"], idioma


def test_el_motor_no_se_entera_del_idioma():
    """Regla del proyecto: el motor emite una CLAVE, la presentación traduce."""
    src = _motor()
    i = src.index("Sin clasificar (está en el total")
    bloque = src[i - 200:i + 300]
    assert 'ayuda="belowGopSinClasificar"' in bloque, (
        "la ayuda de esta fila tiene que viajar como clave, no como texto")
