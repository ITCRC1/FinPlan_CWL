# -*- coding: utf-8 -*-
"""Nivel 3 · los reportes de Opera entre sí — pendiente 22.

Destrabado por el owner el 2026-08-20: *«todos serán XML de Opera»*. El §5 del
spec lo llama *«lo que distingue "los archivos están" de "los datos sirven"»*.

Lo que se vigila acá es que el chequeo **pueda fallar** y que **no ladre por
cosas que no son errores**: un cuadre que sólo puede dar verde no es un cuadre,
y uno que grita todos los meses se aprende a ignorar.
"""
import inspect
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.guillermo import cuadre_opera as co
from app.main import app


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app, raise_server_exceptions=False)


# ── Los tres estados ─────────────────────────────────────────────────────────

def test_dos_reportes_que_coinciden_CUADRAN():
    p = co._comparar(6, "Country Mix", Decimal("3403"), "Channel Mix",
                     Decimal("3403"))
    assert p.estado == co.CUADRA and p.motivo == ""


def test_una_diferencia_de_verdad_NO_CUADRA_y_dice_los_dos_numeros():
    """⚠️ «No cuadra» sin los dos números obliga a ir a buscarlos: el aviso
    tiene que alcanzar para saber qué mirar."""
    p = co._comparar(6, "Country Mix", Decimal("3403"), "Channel Mix",
                     Decimal("3180"))
    assert p.estado == co.NO_CUADRA
    assert "3,403.00" in p.motivo and "3,180.00" in p.motivo
    assert "223.00" in p.motivo
    assert p.diferencia == Decimal("223")


def test_FALTA_UN_LADO_no_es_descuadre():
    """⚠️ Si el Channel Mix de junio no se subió, el veredicto es «no se puede
    verificar». Marcarlo como descuadre mandaría a buscar un error que no
    existe; marcarlo verde diría que coinciden sin haber comparado."""
    p = co._comparar(6, "Country Mix", Decimal("3403"), "Channel Mix", None)
    assert p.estado == co.SIN_VERIFICAR
    assert "Channel Mix" in p.motivo
    assert p.diferencia == Decimal("0")


def test_media_noche_de_diferencia_es_REDONDEO_y_no_descuadre():
    """Las noches llevan dos decimales porque una estadía puede repartirse.
    Ladrar por 0,3 noches llenaría la cola de ruido."""
    p = co._comparar(6, "A", Decimal("100"), "B", Decimal("100.4"))
    assert p.estado == co.CUADRA
    p = co._comparar(6, "A", Decimal("100"), "B", Decimal("101"))
    assert p.estado == co.NO_CUADRA


# ── Lo que NO se compara, y por qué ──────────────────────────────────────────

def test_solo_entran_las_filas_que_VINIERON_DEL_XML():
    """⚠️ **El defecto que esto evita.** Un mix planificado a mano no es un
    reporte de Opera: contra el On the Books sería **plan contra realidad**, que
    es otra conversación. Marcarlo descuadre llenaría la cola de diferencias que
    no son errores."""
    fuente = inspect.getsource(co._por_mes)
    assert 'modelo.origen == "xml"' in fuente
    assert "solo_xml" in inspect.getsource(co.cuadre_de_opera)


def test_contra_el_OTB_solo_los_meses_CERRADOS():
    """⚠️ El On the Books son reservas: para un mes futuro es parcial por
    definición, así que va a dar menos que el forecast SIEMPRE. Compararlos
    daría un descuadre garantizado todos los meses, y no significaría nada."""
    fuente = inspect.getsource(co.cuadre_de_opera)
    assert "if mes <= corte:" in fuente
    assert "actuals_through" in fuente


def test_el_OTB_se_pide_por_HOTEL_Y_ANO_no_por_escenario():
    """El OTB se llavea por `hotel_id` desde la migración 126: se sube una vez y
    se ve desde cualquier escenario. Pedirlo por `scenario_id` devolvería vacío
    y todo saldría «sin verificar» sin que nadie entendiera por qué."""
    fuente = inspect.getsource(co._otb_por_mes)
    assert "OtbDailyOcc.hotel_id == hotel_id" in fuente
    assert "OtbDailyOcc.year == anio" in fuente
    # ⚠️ El docstring SÍ menciona `scenario_id` para explicar por qué no se usa;
    # lo que no puede aparecer es en la consulta.
    cuerpo = fuente.split('"""')[-1]
    assert "scenario_id" not in cuerpo


def test_el_RESUMEN_del_canal_se_verifica_contra_SU_DETALLE():
    """⚠️ El modelo dice que el resumen se deriva del detalle y «no puede
    discrepar». Se comprueba igual: una invariante que nadie verifica deja de
    serlo el día que alguien escribe el resumen por otro lado."""
    fuente = inspect.getsource(co.cuadre_de_opera)
    assert "Channel Mix (resumen)" in fuente
    assert "Channel Mix (detalle)" in fuente


# ── El veredicto del escenario ───────────────────────────────────────────────

def _resumen(pares):
    return co.ResumenOpera(escenario="X/2026/Y", pares=pares)


def test_CERO_COMPARACIONES_no_es_cuadra():
    """⚠️ Pintarlo verde diría que los reportes coinciden cuando nadie comparó
    nada. Es la misma regla de tres estados de `cuadre.py`."""
    r = _resumen([co.Par(1, "A", "B", None, None, co.SIN_VERIFICAR, "x")])
    assert r.verificados == 0
    assert r.estado == co.SIN_VERIFICAR


def test_un_solo_descuadre_tine_todo_el_escenario():
    r = _resumen([
        co.Par(1, "A", "B", Decimal("1"), Decimal("1"), co.CUADRA, ""),
        co.Par(2, "A", "B", Decimal("1"), Decimal("9"), co.NO_CUADRA, "x"),
    ])
    assert r.estado == co.NO_CUADRA
    assert len(r.descuadres) == 1


def test_todo_comparado_y_sin_diferencias_CUADRA():
    r = _resumen([co.Par(1, "A", "B", Decimal("1"), Decimal("1"), co.CUADRA, "")])
    assert r.estado == co.CUADRA


# ── La cola y la puerta ──────────────────────────────────────────────────────

def test_la_ronda_deja_los_descuadres_EN_LA_COLA():
    from app.guillermo import ronda_control

    assert "opera_no_cuadra" in ronda_control.TIPOS
    fuente = inspect.getsource(ronda_control.ronda_de_control)
    assert "resumen_opera" in fuente


def test_la_nota_lleva_ESCENARIO_PAR_Y_MES():
    """⚠️ Sin el mes, dos meses distintos del mismo par se pisarían entre sí y
    en la cola quedaría uno solo."""
    from app.guillermo import ronda_control

    fuente = inspect.getsource(ronda_control.ronda_de_control)
    assert "mes {par.mes}" in fuente
    assert "{par.izquierda} vs {par.derecha}" in fuente


def test_la_ruta_existe_y_pide_token(cliente):
    rutas = cliente.app.openapi()["paths"]
    assert "/api/guillermo/cuadre-opera/" in rutas
    assert cliente.get("/api/guillermo/cuadre-opera/").status_code in (401, 403)


def test_la_respuesta_explica_EL_CRITERIO():
    """Quien vea un descuadre tiene que poder saber qué se comparó sin abrir el
    código."""
    from app.api import guillermo_api

    fuente = inspect.getsource(guillermo_api.cuadre_opera)
    assert '"criterio"' in fuente
    assert "mismo" in fuente and "XML" in fuente
