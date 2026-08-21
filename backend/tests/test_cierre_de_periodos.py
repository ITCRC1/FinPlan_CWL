# -*- coding: utf-8 -*-
"""Cierre de períodos — owner, 2026-08-20.

*«Debería haber un tab en admin para cerrar períodos y dar a entender qué meses
son actuales y qué meses son forecast»* · *«yo subo y cierro el mes para indicar
que los actuales vienen del GL y el forecast viene de los checkbooks»*.

Lo que se vigila acá son las tres formas en que esta pantalla podría mentir:
decir «cerrado» sin escenario ACTUAL enlazado, decir «cerrado» sobre un mes sin
dato, y dejar abrir un mes —que mueve el P&L— como si fuera un cambio de vista.
"""
import inspect

import pytest
from fastapi.testclient import TestClient

from app.api import cierre_periodos_api as cp
from app.main import app


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app, raise_server_exceptions=False)


# ── La puerta ────────────────────────────────────────────────────────────────

def test_las_rutas_existen_y_piden_token(cliente):
    rutas = cliente.app.openapi()["paths"]
    assert "/api/scenarios/{scenario_id}/cierre/" in rutas
    assert set(rutas["/api/scenarios/{scenario_id}/cierre/"]) == {"get", "patch"}
    assert cliente.get("/api/scenarios/x/cierre/").status_code in (401, 403)


# ── Lo que la pantalla NO puede suponer ──────────────────────────────────────

def test_CERRADO_exige_las_dos_cosas_corte_Y_actual_enlazado():
    """⚠️ **El defecto que esto evita.** El desvío del motor
    (`recalculate.py:757`) pide que el mes esté dentro del corte **y** que
    exista un ACTUAL enlazado. Si falta el enlace, el corte avanza igual y el
    P&L vuelve a leer el checkbook **sin avisar**: el forecast diría «junio ya
    cerró» mostrando el plan.
    """
    fuente = inspect.getsource(cp.leer_cierre)
    assert "real = cerrado and actual is not None" in fuente
    assert "NO hay escenario ACTUAL enlazado" in fuente


def test_un_mes_cerrado_SIN_DATO_se_avisa():
    """⚠️ Que el ACTUAL exista no significa que junio tenga líneas. Cerrar hasta
    junio con junio vacío no da error: da un mes en CERO, que se lee como «el
    hotel no vendió»."""
    fuente = inspect.getsource(cp.leer_cierre)
    assert "reportar CERO" in fuente
    assert "tiene_dato" in fuente


def test_el_dato_se_busca_en_el_RESUMEN_y_en_el_DETALLE():
    """Un escenario puede traer uno y no el otro, y cualquiera alcanza para que
    el mes reporte. Mirar sólo uno diría «no hay dato» de un mes que sí lo
    tiene."""
    fuente = inspect.getsource(cp._con_dato)
    assert "actual_pl_lines_for_month" in fuente
    assert "actual_rows_for_month" in fuente


def test_un_monto_en_CERO_no_cuenta_como_dato():
    """Filas cargadas con todo en cero son un mes vacío con otra cara."""
    assert 'any(f.get("amount") for f in filas)' in inspect.getsource(cp._con_dato)


# ── Abrir mueve números ──────────────────────────────────────────────────────

def test_ABRIR_un_mes_exige_confirmacion_explicita():
    """⚠️ Bajar el corte devuelve esos meses al checkbook —al plan— y con ellos
    cambian el P&L, el cash flow y todo lo que cuelga. No es un cambio de
    vista."""
    fuente = inspect.getsource(cp.mover_corte)
    assert "cambio.corte < antes and not cambio.confirmar_apertura" in fuente
    assert "cierre.apertura_sin_confirmar" in fuente


def test_el_rechazo_NOMBRA_los_meses_que_se_reabren():
    """«¿Confirmás?» a secas no dice qué se pierde de vista, y lo que se pierde
    es la realidad."""
    fuente = inspect.getsource(cp.mover_corte)
    assert "MESES[m] for m in range(cambio.corte + 1, antes + 1)" in fuente


def test_CERRAR_no_pide_confirmacion():
    """Cerrar es el camino normal —se sube el GL y se cierra el mes— y pedir
    confirmación en lo que se hace todos los meses enseña a confirmar sin
    leer."""
    fuente = inspect.getsource(cp.mover_corte)
    # La guarda es sólo para bajar el corte.
    assert "cambio.corte < antes" in fuente
    assert "cambio.corte > antes" not in fuente


def test_solo_el_FORECAST_tiene_corte():
    fuente = inspect.getsource(cp.mover_corte)
    assert 'sc.type != FORECAST' in fuente
    assert "cierre.solo_forecast" in fuente


def test_el_corte_solo_puede_ir_de_0_a_12():
    fuente = inspect.getsource(cp.mover_corte)
    assert "0 <= cambio.corte <= 12" in fuente


# ── Lo que el owner necesita entender ────────────────────────────────────────

def test_la_respuesta_dice_QUE_MES_SALE_DE_DONDE():
    """Es el pedido textual: «dar a entender qué meses son actuales y qué meses
    son forecast»."""
    fuente = inspect.getsource(cp.leer_cierre)
    assert '"fuente"' in fuente
    assert "el GL (escenario ACTUAL)" in fuente
    assert "el checkbook de este escenario" in fuente


def test_se_dice_que_el_CHECKBOOK_de_un_mes_cerrado_NO_SE_BORRA():
    """⚠️ Sigue guardado y sigue editable — pero editarlo no mueve el P&L
    mientras el mes esté cerrado. Es un no-op silencioso, y ésta es la pantalla
    donde se explica."""
    fuente = inspect.getsource(cp.leer_cierre)
    assert "NO se borra" in fuente
    assert "no mueve el P&L" in fuente


def test_se_dice_cual_forecast_AVANZA_SOLO():
    """Sólo el marcado como Current avanza el corte al importar. Los
    reforecasts y snapshots son fotos de una decisión: creer que también
    avanzan haría pensar que un snapshot se desactualizó."""
    assert '"avanza_solo"' in inspect.getsource(cp.leer_cierre)


def test_el_candado_del_escenario_TAMBIEN_cubre_esto():
    """Un escenario enllavado no puede moverse el corte: `PATCH .../cierre/`
    lleva `scenario_id`, así que la dependencia global lo frena. La excepción
    del candado es sólo `/status/`."""
    from app import candado

    assert candado.PERMITIDAS == ("/status/",)
    assert "scenario_id" in candado.LLAVES
