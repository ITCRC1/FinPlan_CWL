# -*- coding: utf-8 -*-
"""Las perillas del botón «Llenar desde drivers» se guardan, y el «% que no consume».

## De dónde sale (2026-11-09)

Dos pedidos del owner el mismo día, que resultaron ser el mismo problema.

**Uno.** Sobre el recuadro «noches por estadía»: *«puse 2.80 de estadía
promedio porque hay gente que viene sola y hay gente que viene más días… pero
no vi que el cálculo de revenue cambiara»*. No cambiaba por tres razones, y la
tercera era un defecto: **los nueve recuadros de esa fila no se guardaban en
ningún lado**. Eran estado del navegador. Se escribía 2,80, se recargaba la
pantalla y volvía a 3 — el valor del paquete, que además es un ENTERO
(`int(base["nights"])` en `engine/tarifas_del_paquete.py`), así que un promedio
de estadía con decimales no tenía dónde vivir.

**Dos.** Quiere **bajar el presupuesto 2027 para dejarse un saldo a favor**, y
pidió un «% que no consume» como el que ya existía para Sustainability: *«este
solo aplica a sustainability… sería hacer una para todos los demás»*. Un
recuadro global, no uno por línea.

Agregar la perilla número diez sin arreglar lo primero era invitar a escribir un
supuesto de presupuesto y perderlo al recargar. Por eso van juntas.

## Lo que cuida

* **El viaje redondo.** Se guardan las diez y vuelven las diez. Si la columna no
  existe, si el JSON se serializa mal o si el modelo no la declara, esto se cae.
* **Que guardar las perillas NO le borre el master al escenario.** Es el camino
  caro: `scenario_master` es la misma fila que lleva los meses cerrados, el pax
  y las unidades, y el endpoint viejo (`POST /master/`) **escribe los tres**.
  Reusarlo desde el Revenue Checkbook —que no conoce ninguno— le habría dejado
  el escenario sin unidades y abierto en octubre, con el P&L cuadrando consigo
  mismo.
* **Que una perilla sola no pise a las otras nueve.**
* **Que el «% que no consume» aplique a las CUATRO líneas de consumo** (Food,
  Beverage, Tours y Transporte) y **no** a Rooms ni a Sustainability. Esa parte
  vive en el front y se vigila leyendo el código, igual que
  `test_tarifa_neta_en_el_front.py`: lo que hay que impedir no es una cuenta mal
  hecha, es que mañana la fórmula se escriba de nuevo sin el factor.
"""
import json

import pytest
import pytest_asyncio

from ._rutas import FRONT, sin_comentarios

pytest.importorskip("aiosqlite")

#: Las diez perillas, con un valor distinto cada una: si el endpoint mezclara
#: dos claves, con valores iguales la prueba pasaría igual.
DIEZ = {
    "food": 101.5, "tours": 102.5, "transport": 103.5,
    "nights_per_stay": 2.8, "bev_ratio": 26.0,
    "retail_pct": 3.5, "innoceana_pct": 1.25,
    "sust_rate": 12.0, "sust_non_pay": 10.0,
    "no_consume_pct": 10.0,
}


@pytest_asyncio.fixture
async def base():
    """Base en memoria con `scenarios`, `hotels` y `scenario_master`.

    Las tres: el endpoint busca el escenario antes de tocar el master, y
    `scenarios` tiene FK contra `hotels`.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.hotel import Hotel
    from app.models.scenario import Scenario
    from app.models.scenario_master import ScenarioMaster

    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as c:
        for m in (Hotel, Scenario, ScenarioMaster):
            await c.run_sync(lambda s, m=m: m.__table__.create(s))
    hacer = async_sessionmaker(eng, expire_on_commit=False)
    async with hacer() as db:
        yield db
    await eng.dispose()


async def _escenario(db, *, locked=False, master=None):
    from app.models.hotel import Hotel
    from app.models.scenario import Scenario
    from app.models.scenario_master import ScenarioMaster

    db.add(Hotel(id="CWL", name="Corcovado Wilderness Lodge",
                 short_name="Corcovado", rooms=30))
    sc = Scenario(id="sc-1", hotel_id="CWL", year=2027, type="BUDGET",
                  version="Working", status="locked" if locked else "draft")
    db.add(sc)
    if master is not None:
        db.add(ScenarioMaster(scenario_id="sc-1", **master))
    await db.commit()
    return sc


async def _put(db, tarifas, sid="sc-1"):
    from app.api.revenue_api import DriverRatesBody, put_scenario_driver_rates

    return await put_scenario_driver_rates(sid, DriverRatesBody(tarifas=tarifas), db)


async def _get(db, sid="sc-1"):
    from app.api.revenue_api import get_scenario_driver_rates

    return await get_scenario_driver_rates(sid, db)


# ── El viaje redondo ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sin_guardar_nada_el_get_dice_que_no_hay(base):
    """Vacío no es un error: significa «nadie las tocó», y la pantalla se cae al
    paquete del escenario y después a la semilla del hotel."""
    await _escenario(base)
    d = await _get(base)
    assert d["guardadas"] is False
    assert d["tarifas"] == {}


@pytest.mark.asyncio
async def test_las_diez_se_guardan_y_vuelven_iguales(base):
    await _escenario(base)
    await _put(base, DIEZ)
    d = await _get(base)
    assert d["guardadas"] is True
    assert d["tarifas"] == pytest.approx(DIEZ)


@pytest.mark.asyncio
async def test_las_noches_con_decimales_sobreviven(base):
    """El caso que lo motivó: 2,80 no se puede redondear a 3 en el camino.

    El paquete entrega las noches como ENTERO. Si esta columna hiciera lo mismo,
    el recuadro volvería a 3 y el defecto seguiría ahí con una capa más."""
    await _escenario(base)
    await _put(base, {"nights_per_stay": 2.8})
    assert (await _get(base))["tarifas"]["nights_per_stay"] == pytest.approx(2.8)


@pytest.mark.asyncio
async def test_una_perilla_sola_no_borra_las_otras_nueve(base):
    """La pantalla manda la fila entera, pero si mañana manda una sola, las
    demás no se pierden."""
    await _escenario(base)
    await _put(base, DIEZ)
    await _put(base, {"no_consume_pct": 15.0})
    t = (await _get(base))["tarifas"]
    assert t["no_consume_pct"] == pytest.approx(15.0)
    assert t["food"] == pytest.approx(DIEZ["food"])
    assert len(t) == len(DIEZ)


@pytest.mark.asyncio
async def test_una_clave_que_no_es_perilla_se_ignora(base):
    await _escenario(base)
    await _put(base, {"food": 50.0, "closed_months": 99.0, "inventada": 1.0})
    t = (await _get(base))["tarifas"]
    assert t == {"food": pytest.approx(50.0)}


# ── Lo caro: el master del escenario no se toca ─────────────────────────────

@pytest.mark.asyncio
async def test_guardar_perillas_NO_le_borra_el_master_al_escenario(base):
    """⚠️ El camino que habría costado caro.

    `scenario_master` es la MISMA fila que lleva los meses cerrados, el pax por
    noche y las unidades por categoría. Reusar `POST /master/` para esto —que es
    lo barato de hacer— los escribe los tres, y el Revenue Checkbook no conoce
    ninguno: el escenario habría quedado sin unidades y abierto en octubre, con
    todos los totales cuadrando consigo mismos."""
    from decimal import Decimal

    from sqlalchemy import select

    from app.models.scenario_master import ScenarioMaster

    await _escenario(base, master={
        "closed_months": "10", "pax_per_night": Decimal("1.85"),
        "units_json": '{"rt-1": 6}',
    })
    await _put(base, DIEZ)
    base.expire_all()
    sm = (await base.execute(
        select(ScenarioMaster).where(ScenarioMaster.scenario_id == "sc-1")
    )).scalar_one()
    assert sm.closed_months == "10"
    assert sm.pax_per_night == Decimal("1.85")
    assert sm.units_json == '{"rt-1": 6}'
    assert json.loads(sm.driver_rates_json)["no_consume_pct"] == 10.0


@pytest.mark.asyncio
async def test_un_escenario_sin_master_estrena_fila(base):
    """La mayoría de los escenarios no tienen fila en `scenario_master`: guardar
    una perilla la crea en vez de reventar."""
    await _escenario(base)
    await _put(base, {"food": 7.0})
    assert (await _get(base))["tarifas"]["food"] == pytest.approx(7.0)


@pytest.mark.asyncio
async def test_un_escenario_enllavado_no_deja_guardar(base):
    from fastapi import HTTPException

    await _escenario(base, locked=True)
    with pytest.raises(HTTPException) as e:
        await _put(base, DIEZ)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_un_json_roto_no_tumba_la_pantalla(base):
    """Si la columna trae basura, el GET contesta vacío — que es lo mismo que
    «nadie las tocó». Reventar acá dejaría el checkbook en blanco."""
    await _escenario(base, master={"driver_rates_json": "{esto no es json"})
    d = await _get(base)
    assert d["guardadas"] is False and d["tarifas"] == {}


# ── El «% que no consume», en el front ──────────────────────────────────────

CHECKBOOK = "app/revenue/checkbook/page.tsx"


def _fuente() -> str:
    return sin_comentarios((FRONT / CHECKBOOK).read_text(encoding="utf-8"))


def _linea_de(src: str, clave: str) -> str:
    """La línea de `vals` que calcula esa línea de ingreso."""
    for linea in src.splitlines():
        if linea.strip().startswith(f"{clave}:"):
            return linea
    raise AssertionError(f"{CHECKBOOK}: no se encontró la línea {clave} en `vals`")


def test_el_recuadro_existe_y_se_guarda():
    src = _fuente()
    assert "noConsumePct" in src, "falta el recuadro «% que no consume»"
    assert "no_consume_pct" in src, "falta el puente a la columna del backend"
    assert "saveScenarioDriverRates" in src, (
        "el recuadro no guarda: ese es justo el defecto que vino a arreglar")
    assert "getScenarioDriverRates" in src, (
        "la pantalla no lee lo guardado, así que al recargar vuelve al default")


@pytest.mark.parametrize("clave", ["FOOD", "ACTIVITIES", "TRANSPORT"])
def test_las_lineas_de_consumo_llevan_el_factor(clave):
    """Food, Tours y Transporte se venden por consumo: el huésped las lleva
    incluidas y no siempre las usa."""
    src = _fuente()
    if clave == "FOOD":
        # Food sale de una constante que después alimenta a Beverage.
        linea = next(l for l in src.splitlines() if "const food = " in l)
    else:
        linea = _linea_de(src, clave)
    assert "consume" in linea, (
        f"{clave} se calcula sin el «% que no consume»: {linea.strip()}")


def test_beverage_hereda_el_factor_de_food():
    """Un huésped que no se sentó a comer tampoco pidió la bebida de esa comida.
    Beverage sale de Food (`bevRatio %`), así que lo hereda — y NO lo aplica dos
    veces, que sería cobrarle el descuento al descuento."""
    linea = _linea_de(_fuente(), "BEVERAGE")
    assert "food.map" in linea, f"Beverage dejó de salir de Food: {linea.strip()}"
    assert "consume" not in linea, (
        f"Beverage aplica el factor DOS veces (ya viene en Food): {linea.strip()}")


@pytest.mark.parametrize("clave,porque", [
    ("ROOMS", "la noche se cobra ocupada o no: no es un consumo"),
    ("SUSTAINABILITY", "tiene su propio «% que no paga», que es un descuento de cobro"),
])
def test_las_lineas_que_NO_lo_llevan(clave, porque):
    linea = _linea_de(_fuente(), clave)
    assert "consume" not in linea, f"{clave} no debería llevarlo: {porque}"
