# -*- coding: utf-8 -*-
"""Los endpoints tienen que funcionar POR LA RED, no sólo como funciones.

**El defecto que esto atrapa** (owner, 2026-08-19, con la captura: «Failed to
fetch»). Los cinco endpoints del módulo de Costos de Grupos pedían la sesión
así:

    async def leer_tarifario(db=Depends(get_session), ...)

`app/db.py` tiene DOS cosas con nombre parecido: `get_db()`, que es la
dependencia de FastAPI (un generador asíncrono), y `get_session()`, que es un
`@asynccontextmanager` para scripts (`async with get_session() as s:`). Con el
segundo, FastAPI revienta al resolver la dependencia:

    TypeError: '_AsyncGeneratorContextManager' object is not an async iterator

⚠️ **Y en el navegador NO se ve un 500: se ve «Failed to fetch».** La excepción
escapa antes del middleware de CORS, así que la respuesta sale sin cabeceras y
el browser reporta un fallo de red. Parece la API caída, no un bug de una línea.

⚠️ **Por qué no lo atrapó ninguna de las 38 pruebas del módulo.** Todas llamaban
a las funciones directamente —`await leer_tarifario(db=s, _=None)`— así que la
inyección de dependencias de FastAPI nunca corría. Probé la función, no el
endpoint.

⚠️⚠️ **Y cuál de las pruebas de acá lo atrapa: SÓLO la estática.** Se verificó
volviendo a meter el defecto a propósito: las de `TestClient` siguieron en
verde. Los routers se montan con `dependencies=_guard`, y una dependencia de
ROUTER se resuelve ANTES que las del endpoint — así que sin token el 401 sale
antes de tocar la sesión. Es exactamente por eso que en producción el fallo
sólo aparecía con la sesión iniciada, y por eso yo no lo vi.

Las de `TestClient` quedan igual: vigilan que la ruta exista y que exija token,
que también vale. Pero **la que sostiene esta lección es
`test_NINGUN_endpoint_de_la_app_usa_get_session_como_dependencia`**.
"""
import re

import pytest
from fastapi.testclient import TestClient

from app.main import app

# ⚠️ Sin token NO se llega a la sesión: el guard del router 401ea antes. Estas
# rutas vigilan que el endpoint EXISTA y EXIJA token — que un 404 o un 200 acá
# también serían defectos— pero no pueden ver un fallo de dependencia. Eso lo
# ve la prueba estática de más abajo.
GET = ["/api/costos-grupos/tarifario/", "/api/costos-grupos/descuentos/",
       "/api/costos-grupos/resumen/"]
POST = ["/api/costos-grupos/simular/", "/api/costos-grupos/salida-ventas/"]


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize("ruta", GET)
def test_los_GET_del_modulo_resuelven_su_dependencia(cliente, ruta):
    r = cliente.get(ruta)
    assert r.status_code != 500, (
        f"{ruta} revienta al resolver dependencias: {r.text[:300]}")
    assert r.status_code in (401, 403), (
        f"{ruta} devolvió {r.status_code}; sin token tiene que pedir token")


@pytest.mark.parametrize("ruta", POST)
def test_los_POST_del_modulo_resuelven_su_dependencia(cliente, ruta):
    r = cliente.post(ruta, json={"habitaciones": 10, "noches": 3,
                                 "pax": 20, "mes": 7})
    assert r.status_code != 500, (
        f"{ruta} revienta al resolver dependencias: {r.text[:300]}")
    assert r.status_code in (401, 403), (
        f"{ruta} devolvió {r.status_code}; sin token tiene que pedir token")


def test_el_PUT_del_tarifario_resuelve_su_dependencia(cliente):
    r = cliente.put("/api/costos-grupos/tarifario/", json={"filas": []})
    assert r.status_code != 500, r.text[:300]
    assert r.status_code in (401, 403)


def test_NINGUN_endpoint_de_la_app_usa_get_session_como_dependencia():
    """⚠️ La red ancha, y estática: `Depends(get_session)` NO puede existir.

    `get_session` es el context manager de los scripts; la dependencia de
    FastAPI es `get_db`. Los dos nombres viven en `app/db.py` y se confunden a
    simple vista — por eso la regla se vigila, no se recuerda.
    """
    import os

    raiz = os.path.join(os.path.dirname(__file__), "..", "app")
    culpables = []
    for base, _, archivos in os.walk(raiz):
        if "__pycache__" in base:
            continue
        for a in archivos:
            if not a.endswith(".py"):
                continue
            p = os.path.join(base, a)
            with open(p, encoding="utf-8") as f:
                for n, linea in enumerate(f, 1):
                    if re.search(r"Depends\(\s*get_session\s*\)", linea):
                        culpables.append(f"{os.path.relpath(p, raiz)}:{n}")
    assert not culpables, (
        "estos usan `Depends(get_session)`, que revienta con "
        "«'_AsyncGeneratorContextManager' object is not an async iterator» y en "
        f"el navegador se ve como «Failed to fetch»: {culpables}. Va `get_db`")


def test_ninguna_ruta_de_la_app_revienta_antes_de_autenticar(cliente):
    """Para TODA la app: ninguna ruta GET sin parámetros puede dar 500 sin
    token. Cuesta segundos y cubre lo que se agregue mañana.

    ⚠️ No confundir con el defecto de arriba: acá el guard del router contesta
    primero, así que esto atrapa lo que revienta ANTES de autenticar —un import
    roto, un router mal montado— y no lo que revienta después.
    """
    rotas = []
    for ruta in sorted(app.openapi()["paths"]):
        if "{" in ruta:                       # necesita un id de verdad
            continue
        if "get" not in app.openapi()["paths"][ruta]:
            continue
        if ruta.startswith("/api/auth"):      # públicas, tienen su propia prueba
            continue
        r = cliente.get(ruta)
        if r.status_code == 500:
            rotas.append(f"{ruta} -> {r.text[:120]}")
    assert not rotas, f"estas rutas revientan antes de autenticar: {rotas}"
