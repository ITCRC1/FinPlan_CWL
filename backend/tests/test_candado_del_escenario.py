# -*- coding: utf-8 -*-
"""El candado del escenario — owner, 2026-08-20.

*«Me gustaría proteger el Planning tab, no quisiera que nadie toque… o si está
enllavado nadie puede editar los checkbook.»*

**Lo que estaba pasando, medido:** 194 endpoints escriben y el candado se
verificaba en catorce. `revenue_api` tenía 36 endpoints de escritura y CERO
chequeos; `payroll_api` 17 y cero; `opex_api` 8 y cero. Enllavar frenaba los
imports y el recálculo pero **no impedía editar planilla, opex, revenue ni
costos** — el candado parecía protección y no lo era.
"""
import inspect
import re

import pytest
from fastapi.testclient import TestClient

from app import candado
from app.main import app


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app, raise_server_exceptions=False)


class _Escenario:
    def __init__(self, locked: bool):
        self.status = "locked" if locked else "draft"
        self.type, self.version, self.year = "BUDGET", "Final", 2027

    @property
    def is_locked(self) -> bool:
        return self.status == "locked"


class _DB:
    def __init__(self, sc):
        self.sc = sc

    async def get(self, modelo, sid):
        return self.sc


class _Pedido:
    def __init__(self, metodo="PUT", params=None, plantilla="/api/opex/{scenario_id}/bulk/"):
        self.method = metodo
        self.path_params = params if params is not None else {"scenario_id": "x"}
        self.scope = {"route": type("R", (), {"path": plantilla})()}
        self.url = type("U", (), {"path": plantilla})()


async def _correr(pedido, sc):
    return await candado.candado_del_escenario(pedido, _DB(sc))


# ── Lo que frena ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("metodo", ["POST", "PUT", "PATCH", "DELETE"])
async def test_no_se_puede_ESCRIBIR_sobre_un_escenario_enllavado(metodo):
    from app.errores import ErrorApi

    with pytest.raises(ErrorApi) as e:
        await _correr(_Pedido(metodo), _Escenario(True))
    assert e.value.status_code == 409
    assert e.value.clave == "escenario.enllavado"


@pytest.mark.asyncio
async def test_el_mensaje_dice_CUAL_escenario():
    """«Está enllavado» sin decir cuál obliga a adivinar en una pantalla que
    puede tener varios abiertos."""
    from app.errores import ErrorApi

    with pytest.raises(ErrorApi) as e:
        await _correr(_Pedido(), _Escenario(True))
    assert "BUDGET" in str(e.value.params.get("escenario", ""))


@pytest.mark.asyncio
async def test_tambien_frena_COPIAR_ENCIMA_de_uno_enllavado():
    """⚠️ `target_id` es el DESTINO de una copia: escribir encima de un
    escenario cerrado es justo el caso peligroso."""
    from app.errores import ErrorApi

    p = _Pedido("POST", {"target_id": "x"},
                "/api/scenarios/{target_id}/copy-from/{source_id}/")
    with pytest.raises(ErrorApi):
        await _correr(p, _Escenario(True))


# ── Lo que NO frena ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("metodo", ["GET", "HEAD"])
async def test_LEER_un_escenario_enllavado_se_puede(metodo):
    """Es lo que más se hace con un escenario cerrado: consultarlo."""
    assert await _correr(_Pedido(metodo), _Escenario(True)) is None


@pytest.mark.asyncio
async def test_DESENLLAVAR_sigue_siendo_posible():
    """⚠️ **La excepción que evita un candado irreversible.** Si el candado
    bloqueara también el interruptor que lo abre, enllavar dejaría un escenario
    que nadie puede desbloquear ni corregir desde la app."""
    p = _Pedido("PATCH", {"scenario_id": "x"}, "/api/scenarios/{scenario_id}/status/")
    assert await _correr(p, _Escenario(True)) is None


@pytest.mark.asyncio
async def test_un_escenario_ABIERTO_no_se_frena():
    assert await _correr(_Pedido(), _Escenario(False)) is None


@pytest.mark.asyncio
async def test_una_ruta_SIN_escenario_no_se_frena():
    """La mayoría de las escrituras del sistema no tienen escenario: usuarios,
    catálogos, provisionamiento. El candado tiene que ser invisible ahí."""
    assert await _correr(_Pedido("POST", {}, "/api/auth/users/"), _Escenario(True)) is None


@pytest.mark.asyncio
async def test_un_escenario_QUE_NO_EXISTE_deja_pasar():
    """⚠️ El endpoint tiene que poder devolver su propio 404. Contestar 409
    diría «está enllavado» de algo que ni siquiera está."""
    assert await candado.candado_del_escenario(_Pedido(), _DB(None)) is None


# ── El mecanismo ─────────────────────────────────────────────────────────────

def test_es_UNA_dependencia_en_el_router_y_no_108_ediciones():
    """⚠️ Es el mismo mecanismo que cubrió las 23 puertas de subida en la Fase 0
    de Guillermo. Insertar el `if` en 108 endpoints son 108 ediciones que hay que
    repetir cada vez que se agrega una — y la que se olvide **no falla: deja
    escribir**."""
    import pathlib

    main = pathlib.Path(candado.__file__).parent / "main.py"
    texto = main.read_text(encoding="utf-8")
    assert "Depends(candado_del_escenario)" in texto
    assert "_guard = [Depends(get_current_user), Depends(candado_del_escenario)]" in texto


def test_cubre_TODAS_las_rutas_de_escritura_con_escenario():
    """La medición que originó esto: 108 rutas de escritura llevan
    `scenario_id`. Si aparece otro nombre para lo mismo, esta prueba lo cuenta
    antes de que quede una puerta sin candado."""
    paths = app.openapi()["paths"]
    con_escenario = 0
    for p, ops in paths.items():
        if not any(m in ops for m in ("post", "put", "patch", "delete")):
            continue
        if any(f"{{{k}}}" in p for k in candado.LLAVES):
            con_escenario += 1
    assert con_escenario >= 100, f"sólo {con_escenario} rutas de escritura con escenario"


def test_la_excepcion_esta_en_UN_lugar():
    """Una excepción repartida es una que nadie puede auditar."""
    fuente = inspect.getsource(candado)
    assert "PERMITIDAS = " in fuente
    assert len(candado.PERMITIDAS) == 1, "creció la lista de excepciones"


def test_esto_es_un_CANDADO_y_no_un_permiso():
    """⚠️ Dice «este escenario no se toca», no «vos no podés». Quién puede
    desenllavar sigue siendo `PATCH /scenarios/{id}/status/`, que hoy **no
    exige admin** (pendiente 14) — y con el candado puesto eso importa más:
    quien pueda desenllavar puede volver a escribir."""
    fuente = inspect.getsource(candado)
    assert "no un permiso" in fuente
    assert "pendiente 14" in fuente


def test_el_docstring_deja_la_MEDICION_escrita():
    """Un número medido que no se anota se convierte en una opinión."""
    fuente = inspect.getsource(candado)
    assert "194 endpoints" in fuente
    for archivo in ("revenue_api", "payroll_api", "opex_api"):
        assert archivo in fuente
