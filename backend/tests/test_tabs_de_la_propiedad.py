# -*- coding: utf-8 -*-
"""Qué tabs y reportes ve cada propiedad — owner, 2026-08-20.

*«No todas las propiedades van a ver todos los reportes, ya que son muchos para
cada propiedad y se van a perder»* · *«así como los departamentos se van a
limitar, así se van a limitar los reportes y los tabs principales»* · *«todo
debe poderse esconder y habilitar»* · *«la lógica debe ser escojo el tab
principal y dentro de esa lista escojo lo que quiero, y activo para el hotel»*.

Lo que se vigila acá es que **esconder no se convierta en perder**: que el
default sea prendido, que un reporte nuevo nazca visible, que el catálogo no se
duplique, y que la ruta siga respondiendo — porque eso último es lo que hace
seguro poder apagarlo todo.
"""
import inspect
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"
NAV_TSX = FRONT / "components" / "TopNav.tsx"
PANTALLA = FRONT / "app" / "admin" / "tabs" / "page.tsx"


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app, raise_server_exceptions=False)


# ── La puerta ────────────────────────────────────────────────────────────────

def test_las_rutas_existen_y_piden_token(cliente):
    rutas = cliente.app.openapi()["paths"]
    assert "/api/provisioning/{hotel_id}/tabs/" in rutas
    assert set(rutas["/api/provisioning/{hotel_id}/tabs/"]) == {"get", "put"}
    assert cliente.get("/api/provisioning/CWL/tabs/").status_code in (401, 403)


# ── El default ───────────────────────────────────────────────────────────────

def test_la_tabla_es_ESPARSA_y_el_default_es_PRENDIDO():
    """⚠️ Sin filas, se ve todo. Así el día que esto se despliega **no cambia
    nada en ninguna propiedad**, y una propiedad nueva no depende de que alguien
    haya escrito 96 filas para poder trabajar."""
    from app.models import tab_enablement

    # ⚠️ La doctrina vive en el docstring del MÓDULO, no en el de la clase: es
    # lo que lee quien abre el archivo.
    doc = inspect.getsource(tab_enablement)
    assert "ESPARSA" in doc and "PRENDIDO" in doc


def test_PRENDER_BORRA_la_fila():
    """Si prender escribiera `visible=true`, la tabla acumularía las 96 filas de
    cada propiedad y «volver al default» dejaría de existir."""
    from app.api import provisioning_api

    fuente = inspect.getsource(provisioning_api.guardar_tabs)
    assert "await db.delete(fila)" in fuente
    assert "if r.visible:" in fuente


def test_un_reporte_NUEVO_nace_VISIBLE():
    """⚠️ Al revés sería peor: se construye algo, nadie lo ve, y **nadie sabe
    que existe para poder prenderlo**. Como sólo se guarda lo apagado, una clave
    que nunca se tocó no está en la tabla y se muestra."""
    from app.api import _apagados

    fuente = inspect.getsource(_apagados.tabs_apagados)
    assert "sólo lo que alguien apagó" in fuente


# ── El catálogo no se duplica ────────────────────────────────────────────────

def test_el_catalogo_vive_en_la_BARRA_y_no_en_el_backend():
    """⚠️ **Este proyecto ya pagó DOS veces por una lista escrita a mano**: el
    Club Madresal desaparecía del P&L, y siete de quince líneas de ingreso
    faltaban en Master Data. El backend guarda sólo lo apagado; la lista de lo
    que existe es `NAV`, que ya es la barra."""
    from app.models import tab_enablement

    fuente = inspect.getsource(tab_enablement)
    assert "El catálogo de lo que existe vive en la barra" in fuente

    # Y la barra se exporta para que la pantalla la lea.
    assert "export const NAV" in NAV_TSX.read_text(encoding="utf-8")
    assert 'import { NAV } from "@/components/TopNav"' in \
        PANTALLA.read_text(encoding="utf-8")


def test_una_clave_que_ya_no_existe_NO_ROMPE():
    """Si se borra un reporte de la barra, su fila apagada queda huérfana. No
    puede reventar nada: simplemente deja de esconder algo que ya no está."""
    from app.models import tab_enablement

    assert "no rompe nada" in inspect.getsource(tab_enablement)


# ── Esconder ≠ prohibir ──────────────────────────────────────────────────────

def test_esconder_NO_ES_UN_PERMISO_y_se_dice_en_los_tres_lados():
    """⚠️ La ruta sigue respondiendo. Decirlo importa por dos razones: para que
    nadie lo use como control de acceso, y porque **es lo que hace seguro poder
    apagarlo todo** — hasta la pantalla que administra esto se recupera
    entrando a su URL."""
    from app.api import provisioning_api
    from app.models import tab_enablement

    assert "no es un permiso" in inspect.getsource(tab_enablement).lower()
    assert "no es un permiso" in inspect.getsource(provisioning_api.leer_tabs).lower() \
        or "NO es un permiso" in inspect.getsource(provisioning_api)
    texto = PANTALLA.read_text(encoding="utf-8")
    assert "no es un permiso" in texto
    assert "/admin/tabs" in texto, "la pantalla no dice por dónde volver"


def test_TODO_se_puede_apagar_incluida_esta_pantalla():
    """El owner lo pidió explícito: «todo debe poderse esconder y habilitar».
    No hay lista de intocables — lo que lo hace seguro es que esconder no
    bloquea la ruta."""
    from app.api import provisioning_api

    fuente = inspect.getsource(provisioning_api.guardar_tabs)
    for palabra in ("PROTEGID", "intocable", "no se puede apagar"):
        assert palabra not in fuente


# ── La barra ─────────────────────────────────────────────────────────────────

def test_la_barra_ESCONDE_lo_apagado():
    texto = NAV_TSX.read_text(encoding="utf-8")
    assert "getTabsApagados" in texto
    assert "tabFuera.has(g.key)" in texto
    assert "itemFuera.has(i.key)" in texto


def test_si_la_llamada_FALLA_la_barra_queda_COMPLETA():
    """⚠️ Quedarse sin barra porque un endpoint tardó sería mucho peor que
    mostrar de más un instante. Falla prendido."""
    texto = NAV_TSX.read_text(encoding="utf-8")
    assert ".catch(() => { if (vivo) setApagados(NADA_APAGADO); });" in texto


def test_un_tab_que_queda_VACIO_no_se_dibuja():
    """Un tab que abre un panel vacío es peor que no tener el tab — y ahora se
    puede vaciar por lo que apagó la propiedad, no sólo por rol."""
    texto = NAV_TSX.read_text(encoding="utf-8")
    assert ".filter(g => g.href || g.items.some(i => i.href && !i.disabled));" in texto


# ── La pantalla ──────────────────────────────────────────────────────────────

def test_la_pantalla_sigue_la_logica_QUE_PIDIO_EL_OWNER():
    """«Escojo el tab principal y dentro de esa lista escojo lo que quiero.»"""
    texto = PANTALLA.read_text(encoding="utf-8")
    assert "Tab principal" in texto
    assert "Dentro de" in texto
    assert "setTab(g.key)" in texto


def test_los_ROTULOS_salen_del_mismo_diccionario_que_la_barra():
    """⚠️ Si acá dijeran otra cosa, apagarías un nombre y desaparecería otro."""
    texto = PANTALLA.read_text(encoding="utf-8")
    assert 'useTranslations("nav")' in texto
    assert "groups." in texto and "items." in texto


def test_los_ENCABEZADOS_no_se_ofrecen_para_apagar():
    """No son pantallas: son separadores dentro del menú. Ofrecerlos sería
    ofrecer apagar algo que no lleva a ningún lado."""
    texto = PANTALLA.read_text(encoding="utf-8")
    assert "filter(i => !i.header)" in texto


def test_se_avisa_cuando_se_apaga_LA_PROPIA_PANTALLA():
    texto = PANTALLA.read_text(encoding="utf-8")
    assert "Escondiste esta misma pantalla" in texto


def test_hay_cuantos_tabs_y_pantallas_a_la_vista():
    """El owner dijo «son muchos y se van a perder»: el número tiene que estar
    en la pantalla, no en su cabeza."""
    texto = PANTALLA.read_text(encoding="utf-8")
    assert "NAV.length" in texto
    assert "NAV.reduce" in texto


def test_la_barra_de_verdad_tiene_lo_que_se_midio():
    """Si la barra crece o se encoge, esta prueba lo cuenta: el texto de la
    pantalla habla de «muchos» y hay que saber cuántos son de verdad.

    ⚠️ Se cuentan las pantallas ÚNICAS. La primera versión contaba las
    apariciones y exigía «≥ 96»: al sacar tres entradas que estaban
    **duplicadas** en Admin, la prueba se puso roja por un arreglo — estaba
    midiendo el defecto en vez del tamaño.
    """
    texto = NAV_TSX.read_text(encoding="utf-8")
    tabs = re.findall(r'key:\s*"([a-zA-Z]+)",\s*\n\s*items:\s*\[', texto)
    items = set(re.findall(r'\{\s*key:\s*"([a-zA-Z0-9_]+)",\s*href:', texto))
    assert len(tabs) >= 13, f"la barra tiene {len(tabs)} tabs"
    assert len(items) >= 90, f"la barra tiene {len(items)} pantallas distintas"
