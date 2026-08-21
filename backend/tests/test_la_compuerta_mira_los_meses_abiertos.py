# -*- coding: utf-8 -*-
"""
LA COMPUERTA JUZGA SOLO LOS MESES QUE EL ESCENARIO REPORTA — Y DICE POR QUÉ.

**El modelo del owner (2026-08-16).** Cada escenario histórico tiene dos
fuentes con roles distintos: el **Detalle** (`actual_entries`, el mayor) es «la
forma de manejar reportes», y el **Resumen** (`actual_pl_lines`) es «la forma de
decir que el detalle está bien». *«Para mí ambos son importantes.»* El desacuerdo
entre las dos es la señal que él quiere ver, no algo que el motor deba resolver
solo.

## Defecto 1 — juzgaba meses que el reporte ni usa

`veredicto_del_detalle` comparaba los siete totales de control sobre los DOCE
meses, siempre. Pero un forecast con corte (`actuals_through`) **no reporta sus
meses cerrados**: `_compute_pl_month_core` se desvía al ACTUAL enlazado y ni
mira el resumen ni el detalle de este escenario.

Medido contra producción el 2026-08-16, el `FORECAST Working 2026` (corte=6):

    sobre 12 meses     → los 7 totales descuadrados
    sobre los meses 7–12 → ingreso, GOP, EBITDA, EBT e impuesto en CERO
                            diferencia; sobrevive solo un traslado real de
                            $1.303,00 de OPEX_LAUNDRY a overhead

O sea que el descuadre vivía casi entero en **mayo**, un mes cerrado que ese
forecast toma del Actual 2026. La compuerta estaba midiendo el dato equivocado.

## Defecto 2 — se replegaba en silencio

Elegía y no lo contaba. Por eso cuatro de los seis escenarios llegaron a estar
etiquetados al revés sobre cuál fuente manda, y nadie se enteró: el P&L salía y
cuadraba consigo mismo.

⚠️ **Ninguno de los dos arreglos mueve un número.** Verificado línea por línea
sobre los 20 escenarios: los seis históricos eligen hoy la misma fuente que
antes. Lo que cambia es qué evidencia se usa para decidir y que ahora se ve.
"""
import inspect

import pytest

from app.engine import recalculate as recalc


class _Esc:
    def __init__(self, tipo="FORECAST", corte=6):
        self.id = "x"
        self.type = tipo
        self.actuals_through = corte


@pytest.fixture
def con_actual_enlazado(monkeypatch):
    async def _hay(session, scenario):
        return object()
    monkeypatch.setattr(recalc, "linked_actual_scenario", _hay)


@pytest.fixture
def sin_actual_enlazado(monkeypatch):
    async def _no_hay(session, scenario):
        return None
    monkeypatch.setattr(recalc, "linked_actual_scenario", _no_hay)


# ── Qué meses son «propios» ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_un_forecast_con_corte_solo_juzga_sus_meses_abiertos(con_actual_enlazado):
    """El caso vivo: Working 2026, corte=6 → juzga julio a diciembre."""
    assert await recalc.meses_propios(None, _Esc("FORECAST", 6)) == list(range(7, 13))


@pytest.mark.asyncio
async def test_un_actual_juzga_el_ano_entero(con_actual_enlazado):
    """Un ACTUAL no se desvía a ningún lado: los doce meses son suyos."""
    assert await recalc.meses_propios(None, _Esc("ACTUAL", 0)) == list(range(1, 13))


@pytest.mark.asyncio
async def test_un_budget_juzga_el_ano_entero_aunque_traiga_corte(con_actual_enlazado):
    """El desvío del rolling forecast es SOLO para FORECAST. Un budget con
    `actuals_through` cargado igual reporta sus doce meses."""
    assert await recalc.meses_propios(None, _Esc("BUDGET", 6)) == list(range(1, 13))


@pytest.mark.asyncio
async def test_sin_actual_enlazado_el_forecast_vuelve_a_los_doce(sin_actual_enlazado):
    """Espeja la condición REAL de `_compute_pl_month_core`: sin ACTUAL
    enlazado el desvío no ocurre y esos meses los reporta el forecast con sus
    propias fuentes. Recortarlos igual dejaría la compuerta ciega justo donde
    el dato sí se usa."""
    assert await recalc.meses_propios(None, _Esc("FORECAST", 6)) == list(range(1, 13))


@pytest.mark.asyncio
async def test_un_forecast_sin_corte_juzga_el_ano_entero(con_actual_enlazado):
    assert await recalc.meses_propios(None, _Esc("FORECAST", 0)) == list(range(1, 13))


@pytest.mark.asyncio
async def test_un_forecast_cerrado_hasta_diciembre_no_juzga_nada(con_actual_enlazado):
    """Todo el año viene del Actual: no hay mes propio que juzgar, y el
    veredicto tiene que salir por «no hay detalle que evaluar», no por un
    descuadre inventado."""
    assert await recalc.meses_propios(None, _Esc("FORECAST", 12)) == []


# ── Que la compuerta la use, y que la decisión se vea ────────────────────────

@pytest.fixture(scope="module")
def fuente() -> str:
    return inspect.getsource(recalc.veredicto_del_detalle)


def test_el_veredicto_recorre_los_meses_propios_y_no_range_1_13(fuente):
    assert "meses_propios(session, scenario)" in fuente, (
        "el veredicto volvio a juzgar los doce meses siempre: un forecast con "
        "corte se descuadra por meses que su reporte ni usa")
    assert "for m in range(1, 13)" not in fuente


def test_el_veredicto_dice_por_que(fuente):
    """Sin motivo, la eleccion vuelve a ser silenciosa — que es el defecto."""
    assert '"motivo"' in fuente
    assert '"diferencias"' in fuente
    assert '"meses_evaluados"' in fuente


def test_la_compuerta_sigue_siendo_por_escenario_no_por_mes(fuente):
    """Decidir mes a mes deja el cuadro internamente incoherente: unos meses
    con el detalle y otros con el resumen, y `OPERATING_PROFIT` sumando solo
    parte del ano."""
    assert '("veredicto_detalle", scenario.id)' in fuente


def test_el_si_o_no_sale_del_mismo_veredicto():
    """Dos caminos para la misma decision serian dos verdades."""
    assert "veredicto_del_detalle" in inspect.getsource(recalc._el_detalle_cuadra)


def test_el_cuadre_publica_el_veredicto():
    from app.api import cuadre_api
    assert '"veredicto": veredicto' in inspect.getsource(cuadre_api.cuadre), (
        "la pantalla vuelve a mostrar cual manda sin la evidencia")
