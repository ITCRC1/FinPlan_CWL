# -*- coding: utf-8 -*-
"""Los selectores del §5 — base, período y temporada.

Owner, 2026-08-20: *«esto tiene que ser flexible para escoger versiones, lo veo
muy básico; los meses más dinámicos: YTD, full year, todos los meses»*.

El spec §5 los pide independientes y combinables. Hasta ese día sólo existían
mes y temporada, y la base estaba clavada en `cfg_parametros.escenario_base`.
"""
import inspect
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import costos_grupos_resumen_api as api
from app.engine import costos_grupos as cg
from app.main import app


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app, raise_server_exceptions=False)


def _mes(m: int, ocupadas: str = "100", rev: str = "1000") -> cg.MesDeCostos:
    temporada = {12: "ALTA", 1: "ALTA", 2: "ALTA", 3: "ALTA", 4: "ALTA",
                 5: "MEDIA", 6: "MEDIA", 7: "MEDIA", 8: "MEDIA", 11: "MEDIA",
                 9: "BAJA", 10: "BAJA"}[m]
    return cg.MesDeCostos(
        mes=m, temporada=temporada, dias_abiertos=30,
        revenue_por_dept={"REV_ROOMS": Decimal(rev)},
        hab_ocupadas=Decimal(ocupadas))


DOCE = [_mes(m) for m in range(1, 13)]


# ── Los tres selectores llegan a la puerta ───────────────────────────────────

@pytest.mark.parametrize("ruta", ["/api/costos-grupos/resumen/",
                                  "/api/costos-grupos/fully-loaded/"])
def test_las_dos_pantallas_aceptan_base_y_periodo(cliente, ruta):
    q = {p["name"] for p in cliente.app.openapi()["paths"][ruta]["get"]["parameters"]
         if p.get("in") == "query"}
    assert {"escenario_id", "periodo", "mes", "temporada"} <= q, ruta


# ── Período ──────────────────────────────────────────────────────────────────

def test_ano_completo_toma_los_doce():
    sel, etiqueta = api._filtrar(DOCE, SimpleNamespace(actuals_through=0),
                                 "full", None, None)
    assert len(sel) == 12
    assert etiqueta == "año completo"


def test_un_mes_toma_uno_solo():
    sel, etiqueta = api._filtrar(DOCE, SimpleNamespace(actuals_through=0),
                                 "mes", 7, None)
    assert [m.mes for m in sel] == [7]
    assert "mes 7" in etiqueta


def test_el_YTD_sale_del_CORTE_del_escenario_y_no_del_calendario():
    """⚠️ **El defecto que esto evita.** Un YTD que llegara hasta «hoy»
    incluiría meses SIN DATO, y el costo quedaría dividido entre ocupación que
    todavía no ocurrió: todos los unitarios bajarían sin que nada avise. El
    corte es el del escenario, igual que el rolling forecast.
    """
    sel, etiqueta = api._filtrar(DOCE, SimpleNamespace(actuals_through=5),
                                 "ytd", None, None)
    assert [m.mes for m in sel] == [1, 2, 3, 4, 5]
    assert "YTD" in etiqueta and "5" in etiqueta


def test_sin_corte_el_YTD_cae_al_ultimo_mes_CON_DATO():
    """Un presupuesto no tiene `actuals_through`. Tomar los doce diría «YTD» de
    un año que no pasó."""
    meses = [_mes(m) for m in range(1, 5)] + [
        cg.MesDeCostos(mes=m, temporada="MEDIA", dias_abiertos=30)
        for m in range(5, 13)]
    sel, _ = api._filtrar(meses, SimpleNamespace(actuals_through=0),
                          "ytd", None, None)
    assert [m.mes for m in sel] == [1, 2, 3, 4]


def test_periodo_y_temporada_se_cruzan_por_INTERSECCION():
    """Lo pide el §5. «YTD × ALTA» son los meses de alta transcurridos."""
    sel, etiqueta = api._filtrar(DOCE, SimpleNamespace(actuals_through=6),
                                 "ytd", None, "ALTA")
    assert [m.mes for m in sel] == [1, 2, 3, 4]
    assert "ALTA" in etiqueta


def test_una_combinacion_VACIA_se_dice_en_vez_de_devolver_ceros():
    """⚠️ «Julio × ALTA» no existe. Un cero que en realidad es «no hay meses» se
    lee como «no hay costo», que es lo contrario."""
    sel, etiqueta = api._filtrar(DOCE, SimpleNamespace(actuals_through=0),
                                 "mes", 7, "ALTA")
    assert sel == []
    for fn in (api.resumen, api.fully_loaded):
        fuente = inspect.getsource(fn)
        assert '"vacio": True' in fuente
        assert "no hay meses en" in fuente


# ── Base ─────────────────────────────────────────────────────────────────────

def test_elegir_otra_base_NO_MUEVE_el_parametro_configurado():
    """⚠️ **Lo que esto protege.** `escenario_base` es una decisión del owner
    —«los costos salen del Forecast Working 2026, que es la realidad»— y gobierna
    los Pisos y la Golden Rate que se usan para negociar. El selector es un
    filtro de LECTURA: mirar otro escenario no puede reescribir el que manda.
    """
    fuente = inspect.getsource(api._base_elegida)
    assert "db.add" not in fuente and "commit" not in fuente
    assert "CfgParametro" not in fuente


def test_la_respuesta_dice_CUAL_es_la_base_configurada():
    """Sin esto, leer un piso calculado sobre otro escenario parece el piso
    oficial — y ése es el número con el que se firma un contrato."""
    for fn in (api.resumen, api.fully_loaded):
        fuente = inspect.getsource(fn)
        assert '"base_configurada"' in fuente, fn.__name__
        assert '"es_base"' in fuente, fn.__name__


def test_sin_escenario_elegido_manda_el_configurado():
    fuente = inspect.getsource(api._base_elegida)
    assert "if not escenario_id:" in fuente
    assert "return base, base, True" in fuente


@pytest.mark.asyncio
async def test_un_escenario_INEXISTENTE_da_404_con_el_id():
    """Y no un 500 ni un cuadro vacío que se lea como «este escenario no tiene
    costos»."""
    from fastapi import HTTPException

    class _Vacia:
        async def execute(self, stmt):
            return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: None))

    async def _base(db, hotel):
        return SimpleNamespace(id="base", type="FORECAST", year=2026,
                               version="Working")

    import app.engine.costos_grupos as _cg
    original = _cg.escenario_base
    _cg.escenario_base = _base
    try:
        with pytest.raises(HTTPException) as e:
            await api._base_elegida(_Vacia(), "no-existe")
        assert e.value.status_code == 404
        assert "no-existe" in e.value.detail
    finally:
        _cg.escenario_base = original


# ── Elegir CUÁLES meses (owner, 2026-08-20) ─────────────────────────────────
#
# «Que los meses estén desplegados y yo escojo los que quiero que salgan».

def test_se_pueden_elegir_MESES_SUELTOS():
    sel, etiqueta = api._filtrar(DOCE, SimpleNamespace(actuals_through=0),
                                 "full", None, None, {2, 6, 11})
    assert [m.mes for m in sel] == [2, 6, 11]
    # Y la etiqueta los nombra: «meses 2,6,11» no se lee de un vistazo.
    assert etiqueta == "Feb · Jun · Nov"


def test_la_lista_de_meses_MANDA_sobre_el_periodo():
    """⚠️ Si «año completo» le ganara a las casillas marcadas, la pantalla
    mostraría los doce meses con tres casillas prendidas — y no habría forma de
    saber cuál de los dos se está mirando."""
    sel, _ = api._filtrar(DOCE, SimpleNamespace(actuals_through=5),
                          "ytd", None, None, {8, 9})
    assert [m.mes for m in sel] == [8, 9]


def test_los_meses_elegidos_se_cruzan_con_la_temporada():
    sel, etiqueta = api._filtrar(DOCE, SimpleNamespace(actuals_through=0),
                                 "full", None, "ALTA", {1, 2, 6, 7})
    assert [m.mes for m in sel] == [1, 2]
    assert "ALTA" in etiqueta


@pytest.mark.parametrize("crudo,esperado", [
    ("1,2,3", {1, 2, 3}),
    (" 4 , 5 ", {4, 5}),
    ("1,1,1", {1}),
    ("", set()), (None, set()),
])
def test_el_parser_de_meses(crudo, esperado):
    assert api.meses_pedidos(crudo) == esperado


@pytest.mark.parametrize("basura", ["13", "0", "-1", "julio", "1.5"])
def test_un_mes_QUE_NO_EXISTE_no_entra(basura):
    """⚠️ Si un «13» entrara, el filtro devolvería un cuadro vacío que se lee
    como «ese mes no tuvo costo» — que es lo contrario de «ese mes no existe»."""
    assert api.meses_pedidos(basura) == set()


def test_sin_meses_elegidos_manda_el_periodo():
    """Ninguna casilla marcada = «lo que diga el Período». Si la lista vacía se
    tomara como «ningún mes», la pantalla abriría sin datos."""
    sel, etiqueta = api._filtrar(DOCE, SimpleNamespace(actuals_through=0),
                                 "full", None, None, set())
    assert len(sel) == 12 and etiqueta == "año completo"
