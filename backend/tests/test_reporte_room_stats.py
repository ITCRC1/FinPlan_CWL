# -*- coding: utf-8 -*-
"""El reporte de Rooms Statistics: dos páginas, y el corte YTD que manda.

**El pedido (owner, 2026-10-25):** *«mete este reporte como un reporte
frecuente… que el reporte se genere según lo que diga el mes escogido… que sea
en PDF y en 2 páginas»*, y después *«deja esto para que siempre esté el mes
último que tiene actuales»*.
"""
import re

import pytest

from tests._rutas import FRONT, sin_comentarios

PAGINA = FRONT / "app" / "operation-insight" / "room-stats" / "page.tsx"
REPORTE = FRONT / "lib" / "reporteRoomStats.ts"


@pytest.fixture(scope="module")
def pag() -> str:
    assert PAGINA.exists(), f"no está {PAGINA}"
    return PAGINA.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rep() -> str:
    assert REPORTE.exists(), f"no está {REPORTE}"
    return REPORTE.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# El corte YTD
# ═══════════════════════════════════════════════════════════════════════════
def test_el_corte_NO_es_un_mes_escrito_a_mano(pag):
    """⚠️ El defecto que esto cierra, y por qué no se veía.

    El corte arrancaba en `useState(5)` — mayo, escrito a mano. Nunca se movió:
    en octubre, con actuales hasta setiembre, la pantalla abría en el YTD a
    mayo y el reporte salía con **cuatro meses de menos**. Nada falla: el
    cuadro es correcto, sólo que de otro corte. Hay que leer el rótulo para
    darse cuenta.
    """
    # ⚠️ Sobre el CÓDIGO, no sobre el archivo: el comentario de arriba nombra
    # `useState(5)` justamente para explicar por qué no va. Ver
    # `sin_comentarios`.
    assert "useState(5)" not in sin_comentarios(pag), (
        "el corte no puede ser un mes fijo: queda viejo solo y el reporte sale "
        "corto sin que nada avise")
    assert "setMonth(ultimoMesConDato(d))" in pag, (
        "al cargar el escenario, el corte va al último mes con dato")


def test_el_ultimo_mes_mira_MOVIMIENTO_y_no_disponibilidad(pag):
    """⚠️ Las noches DISPONIBLES existen los doce meses aunque no se haya
    cargado nada —son unidades × días—, así que mirarlas devolvería diciembre
    siempre y el corte quedaría peor que antes."""
    codigo = sin_comentarios(pag)
    cuerpo = codigo[codigo.index("function ultimoMesConDato"):][:700]
    assert "r.revenue !== 0" in cuerpo
    assert "r.nights_occupied !== 0" in cuerpo
    assert "nights_available" not in cuerpo, (
        "las noches disponibles no dicen si el mes tiene dato cargado")


def test_sin_ningun_mes_cargado_vale_enero(pag):
    """Un escenario recién creado no tiene movimiento. Una pantalla vacía es la
    verdad; inventar un corte es peor."""
    codigo = sin_comentarios(pag)
    cuerpo = codigo[codigo.index("function ultimoMesConDato"):][:700]
    assert "let ult = 1" in cuerpo


# ═══════════════════════════════════════════════════════════════════════════
# El reporte
# ═══════════════════════════════════════════════════════════════════════════
def test_son_DOS_paginas(rep):
    """Una sola, y el detalle mensual no cabe; tres, y deja de ser un reporte."""
    assert "@page { size: Letter landscape" in rep
    assert ".p2{page-break-before:always}" in rep
    # los seis bloques del detalle, en rejilla de dos columnas: a ancho
    # completo sólo entraban cuatro y se iba a tres páginas
    assert ".g2{display:grid;grid-template-columns:1fr 1fr" in rep
    for b in ("NIGHTS AVAILABLE", "NIGHTS OCCUPIED", "OCCUPANCY %",
              "REVENUE (USD)", "ADR (USD)", '"PAX"'):
        assert b in rep, f"falta el bloque {b}"


def test_el_reporte_NO_pide_nada_al_servidor(rep):
    """⚠️ La regla que ya estaba escrita en esta pantalla para el Excel mes a
    mes: *«agregar un endpoint habría creado una segunda fuente del mismo
    número»*. Un reporte que se trae su propio dato es un reporte que algún día
    dice algo distinto de la pantalla de la que cuelga."""
    assert "fetch(" not in rep and "api." not in rep, (
        "el reporte se arma con el dato que la pantalla ya tiene")


def test_los_totales_llegan_CALCULADOS(rep, pag):
    """La pantalla ya resuelve el YTD, el «Other Rooms Revenue» —que no tiene
    noches ni ADR pero sí plata— y el orden por ingreso. Rehacer esa aritmética
    acá sería la segunda fuente por la puerta de atrás."""
    for campo in ("total:", "occTotal", "adrTotal", "insight", "otherRevenue"):
        assert campo in rep, f"el reporte tiene que recibir {campo}"
    assert "total: tot, occTotal, adrTotal, insight, otherRevenue" in pag


def test_el_other_revenue_SALE_en_la_tabla(rep):
    """Ya desapareció callado una vez del KPI y del Excel. Si el total incluye
    esa plata y la tabla no la muestra, las filas no suman al TOTAL y el que
    revisa no encuentra la diferencia."""
    assert "Other Rooms Revenue" in rep
    assert "d.otherRevenue" in rep


def test_lo_que_viene_del_DATO_se_escapa(rep):
    """Los nombres de categoría los escribe un usuario en Master Data. Un `&`
    en «Bar & Grill» rompe el HTML en silencio: la página sale a medias y no
    hay error en ningún lado."""
    assert "function esc(" in rep
    assert 'replace(/&/g, "&amp;")' in rep
    for campo in ("f.room_type_name", "d.insight", "escenario"):
        assert re.search(rf"esc\(\s*{re.escape(campo)}", rep), (
            f"{campo} sale sin escapar")


def test_el_reporte_NO_usa_una_ventana_emergente(pag):
    """⚠️ El defecto que esto cierra, y por qué el primer arreglo era peor.

    La primera versión usaba `window.open`. El navegador la bloqueó y el botón
    no hizo nada. Yo había puesto un aviso —«permita las ventanas emergentes»—
    y eso es resolver el síntoma pidiéndole al usuario que baje una defensa del
    navegador para usar un botón de su propio sistema. El enfoque era el malo,
    no el mensaje.
    """
    codigo = sin_comentarios(pag)
    assert "window.open" not in codigo, (
        "una ventana emergente la bloquea el navegador; el reporte va en un "
        "iframe mismo-origen, que no se bloquea")


def test_imprime_SOLO_el_reporte(pag):
    """`contentWindow.print()` imprime el contenido del iframe, no la pantalla
    que está detrás. Llamar a `window.print()` a secas sacaría el tablero de la
    app con su menú y sus botones."""
    codigo = sin_comentarios(pag)
    cuerpo = codigo[codigo.index("function abrirReportePdf"):][:2200]
    assert "marco.srcdoc = html" in cuerpo, (
        "`srcdoc` deja el documento en el mismo origen; sin eso "
        "`contentWindow` no se deja tocar")
    assert "v.print()" in cuerpo
    assert "window.print()" not in cuerpo


def test_el_print_espera_a_que_el_documento_cargue(pag):
    """Dispararlo antes imprime una hoja a medio dibujar."""
    cuerpo = sin_comentarios(pag)
    cuerpo = cuerpo[cuerpo.index("function abrirReportePdf"):][:2200]
    assert "marco.onload" in cuerpo
    assert cuerpo.index("marco.onload") < cuerpo.index("v.print()")


def test_el_iframe_se_retira(pag):
    """Uno por reporte, y se quedan. ⚠️ `afterprint` no llega en todos los
    navegadores, así que el temporizador es la red — no el camino principal."""
    cuerpo = sin_comentarios(pag)
    cuerpo = cuerpo[cuerpo.index("function abrirReportePdf"):][:2200]
    assert "afterprint" in cuerpo
    assert "setTimeout(limpiar" in cuerpo


@pytest.mark.parametrize("archivo", ["es.json", "en.json"])
def test_los_rotulos_estan_en_los_dos_idiomas(archivo):
    import json
    d = json.loads((FRONT / "messages" / archivo).read_text(encoding="utf-8"))
    rs = d["roomStats"]
    for k in ("reportePdf", "reportePdfTitle", "reporteFallo"):
        assert k in rs, f"{archivo}: falta roomStats.{k}"
        assert rs[k].strip(), f"{archivo}: roomStats.{k} vacío"
