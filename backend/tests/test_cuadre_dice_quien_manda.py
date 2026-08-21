# -*- coding: utf-8 -*-
"""El Cuadre tiene que decir cuál hoja produce el P&L de HOY, no cuál debería.

**El defecto (medido en producción, 2026-08-15).** `/reports/cuadre/` etiquetaba
la fuente así: «resumen si el escenario es ACTUAL, detalle si no». El motor no
funciona así — `recalculate._detalle_fino_si_cuadra` usa el detalle del mayor
solo cuando sus SIETE totales del año coinciden con el resumen, y eso no depende
del tipo de escenario.

Medido contra los seis escenarios de 2026 y anteriores, la etiqueta mentía en
cuatro:

    ACTUAL actual 2024      decía resumen   el motor usa resumen   ✔
    ACTUAL actual 2025      decía resumen   el motor usa DETALLE   ✖
    ACTUAL actual 2026      decía resumen   el motor usa DETALLE   ✖
    BUDGET Final 2026       decía detalle   el motor usa RESUMEN   ✖
    FORECAST April 2026     decía detalle   el motor usa RESUMEN   ✖
    FORECAST Working 2026   decía detalle   el motor usa RESUMEN   ✖

Esta pantalla existe para que el owner sepa qué hoja corregir cuando las dos no
dicen lo mismo. Con la etiqueta al revés lo mandaba a corregir la otra.

No mueve ningún número del P&L: solo cambia lo que el reporte dice de sí mismo.
"""
import inspect

from app.api import cuadre_api


def test_le_pregunta_al_motor_cual_manda():
    """La decisión se le PIDE al motor. Cualquiera de las dos puertas sirve:
    `_el_detalle_cuadra` (el sí o no) o `veredicto_del_detalle` (el sí o no CON
    su motivo, que es lo que la pantalla usa desde el 2026-08-16). Lo que no
    puede volver es que el reporte la deduzca por su cuenta."""
    fuente = inspect.getsource(cuadre_api.cuadre)
    assert ("_el_detalle_cuadra" in fuente or "veredicto_del_detalle" in fuente), (
        "El Cuadre volvió a adivinar cuál hoja manda en vez de preguntárselo al "
        "motor. La etiqueta vuelve a mentir en cuanto un escenario cambie de "
        "lado, y nada avisa.")


def test_ya_no_adivina_por_tipo_de_escenario():
    """La heurística vieja no puede volver ni «por si acaso».

    Si alguien la reintroduce como respaldo, el reporte vuelve a tener dos
    verdades y gana la que se evalúe primero.
    """
    fuente = inspect.getsource(cuadre_api.cuadre)
    assert 'e.type == "ACTUAL"' not in fuente


def test_el_motor_sigue_exponiendo_la_decision():
    """El Cuadre depende de estas funciones: si se renombran, tiene que romper
    acá y no en silencio contra producción."""
    from app.engine import recalculate

    assert hasattr(recalculate, "_el_detalle_cuadra")
    assert inspect.iscoroutinefunction(recalculate._el_detalle_cuadra)
    assert hasattr(recalculate, "veredicto_del_detalle")
    assert inspect.iscoroutinefunction(recalculate.veredicto_del_detalle)


def test_la_pantalla_muestra_el_motivo_y_no_solo_la_etiqueta():
    """«Manda el resumen» sin la evidencia es la elección en silencio con otro
    nombre: el owner quiere VER el desacuerdo, no que se resuelva solo."""
    fuente = inspect.getsource(cuadre_api.cuadre)
    assert '"veredicto": veredicto' in fuente


def test_la_ruta_del_cuadre_existe_de_verdad():
    """**El módulo estaba escrito y la ruta no existía.** Hasta el 2026-08-16
    `cuadre_api` no se importaba ni se montaba en `main.py`: estas pruebas
    pasaban en verde contra una pantalla que en producción daba 404. Todo lo que
    esta pantalla dice sobre cuál hoja manda no le llegaba a nadie.

    Verde no significa aplicado."""
    from app.main import app

    # Se mira el esquema publicado, no `app.routes`: FastAPI 0.141 resuelve los
    # routers incluidos de forma perezosa, así que `app.routes` puede estar
    # vacío de rutas reales. El esquema es además lo que ve el de afuera.
    rutas = set(app.openapi()["paths"])
    assert "/api/reports/cuadre/{scenario_id}/" in rutas, (
        "el Cuadre volvió a quedar sin montar: la elección de fuente vuelve a "
        "ser invisible")
    assert "/api/reports/cuadre/" in rutas


def test_el_listado_puede_traer_el_veredicto_de_todos():
    """La pregunta real del owner no es «cuáles se pueden cuadrar» sino «cuál de
    los míos está reportando contra un control viejo». Va apagado por defecto
    porque el veredicto recorre el año de cada escenario."""
    from app.main import app

    par = app.openapi()["paths"]["/api/reports/cuadre/"]["get"].get("parameters", [])
    nombres = {p["name"]: p for p in par}
    assert "con_veredicto" in nombres
    assert nombres["con_veredicto"]["schema"].get("default") is False
