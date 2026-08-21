# -*- coding: utf-8 -*-
"""
LAS SEMILLAS SE PIDEN POR UNA RUTA, Y LA RUTA SE EJECUTA.

## Por qué existe (2026-08-16)

Cuatro listas seguían escritas a mano: el catálogo de OPEX y los canales del mix
adentro del backend, las tarifas del checkbook y las reasignaciones de salario
adentro de dos pantallas de Next.js. Ninguna prueba las miraba, y las dos del
frontend viajaban en el bundle: una propiedad nueva abría la pantalla con el
producto de Corcovado y a un clic de guardarlo.

Ahora viven en `seed_data/<HOTEL_ID>/`. Pero mudar el archivo no sirve de nada si
la ruta que lo sirve no existe o revienta: **leerla no es ejecutarla**. Esto la
ejecuta.

## Lo que cuida

* Las dos rutas nuevas responden 200 y traen los datos.
* Una propiedad SIN semilla recibe `seeded: false` y una lista vacía — no la de
  Corcovado. Es el modo en que esto fallaba antes de existir.
* Sembrar cuentas de OPEX en una propiedad sin catálogo da 400 con explicación,
  en vez de estampar las 27 cuentas de otro hotel.
* Los canales del mix son la semilla MÁS lo que el escenario ya tenga guardado.
  Antes el GET sumaba todas las filas al total pero solo mostraba las de la
  constante: un canal fuera de la lista entraba en el total, no aparecía en el
  detalle y los porcentajes no cerraban en 100%. Es la misma forma de fallar que
  le hizo mostrar 22 departamentos con 38 en la base.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def cliente():
    from app.api.semillas_api import router
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_las_tarifas_del_checkbook_se_sirven(cliente):
    r = cliente.get("/api/semillas/driver-rates/")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["seeded"] is True
    assert d["tarifas"]["food"] and d["tarifas"]["nights_per_stay"]


def test_las_reasignaciones_se_sirven(cliente):
    r = cliente.get("/api/semillas/reasignaciones-salario/")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["seeded"] is True
    filas = d["reasignaciones"]
    assert filas and all({"name", "legacy", "source", "target", "fte"} <= set(f) for f in filas)


@pytest.mark.parametrize("nombre", ["driver_rates", "reasignaciones_salario",
                                    "opex_accounts", "canales_mix"])
def test_una_propiedad_sin_carpeta_no_recibe_la_de_corcovado(nombre):
    """`None`, no la lista de otro hotel. Es TODO el punto del cambio."""
    from app.seed_data import semilla_cruda
    assert semilla_cruda(nombre, hotel_id="HOTEL_QUE_NO_EXISTE") is None


def test_los_codigos_no_pierden_el_cero_de_adelante():
    """`semilla()` convierte a Decimal toda cadena que parezca número: `"0113"`
    se volvería `Decimal('113')` y el departamento dejaría de existir, en
    silencio. Por eso estos archivos se leen con `semilla_cruda`."""
    from app.seed_data import semilla, semilla_cruda
    crudo = semilla_cruda("reasignaciones_salario")["reasignaciones"]
    assert all(isinstance(f["source"], str) and f["source"].startswith("0") for f in crudo)
    # Y la trampa que se está esquivando, medida — no afirmada de memoria.
    convertido = semilla("reasignaciones_salario")["reasignaciones"]
    assert str(convertido[0]["source"]) != crudo[0]["source"]


def test_ningun_puesto_reasigna_mas_de_un_fte():
    """No se puede mover más gente de la que el puesto tiene.

    ROOM ATTENDANT decía `fte: 2.00`, heredado de la planilla 2026: ahí UNA
    posición (`508 CAMARERO`) cargaba varios FTE y «2» quería decir «dos
    camareras». En el head count 2027 cada camarera es su propia posición
    —`0113-03` a `0113-15`, 1,0000 FTE cada una—, así que ese 2,00 reasignaba el
    DOBLE del salario de la posición elegida y nada lo decía. Corregido a 1,00
    el 2026-08-16, que es lo que la regla guardada ya movía.

    Se mide por (departamento, puesto) porque un puesto se parte entre varios
    destinos —el guía va mitad a Compras y mitad a Transporte— y lo que no puede
    pasarse de uno es la SUMA.

    Si alguna vez una propiedad carga posiciones que traen varios FTE adentro,
    éste es el lugar donde se revisa el supuesto, no el archivo.
    """
    from collections import defaultdict
    from app.seed_data import semilla_cruda

    por_puesto = defaultdict(float)
    for f in semilla_cruda("reasignaciones_salario")["reasignaciones"]:
        assert f["fte"] > 0, f"{f['name']}: un renglón que mueve 0 no hace nada"
        por_puesto[(f["source"], f["name"])] += f["fte"]

    de_mas = {k: v for k, v in por_puesto.items() if v > 1.0001}
    assert not de_mas, f"reasignan más de un FTE: {de_mas}"


def test_sembrar_opex_sin_catalogo_avisa_en_vez_de_usar_el_de_otro():
    from app.api.opex_api import _catalogo_de_arranque
    assert _catalogo_de_arranque(), "CWL sí tiene catálogo: la prueba no mide nada"
    import app.seed_data as sd
    original = sd.HOTEL_ID
    try:
        sd.HOTEL_ID = "HOTEL_QUE_NO_EXISTE"
        assert _catalogo_de_arranque() is None
    finally:
        sd.HOTEL_ID = original


@pytest.mark.asyncio
async def test_el_mix_muestra_los_canales_guardados_que_la_semilla_no_nombra():
    """Lo guardado nunca desaparece de la pantalla."""
    from app.api.revenue_api import _canales_del_mix
    from app.seed_data import semilla_cruda

    class _Res:
        def __init__(self, filas): self._f = filas
        def scalars(self): return self
        def all(self): return self._f

    class _DB:
        def __init__(self, filas): self._f = filas
        async def execute(self, *a, **k): return _Res(self._f)

    base = semilla_cruda("canales_mix")["canales"]
    # Nada guardado: la semilla tal cual, en su orden (el PUT escribe por posición).
    assert await _canales_del_mix(_DB([]), "x", "rooms") == base
    # Un canal que la semilla no nombra: se agrega al final, no se pierde.
    con_extra = await _canales_del_mix(_DB([base[0], "Wholesaler"]), "x", "rooms")
    assert con_extra == base + ["Wholesaler"]
