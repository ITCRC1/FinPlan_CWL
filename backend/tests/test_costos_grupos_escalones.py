# -*- coding: utf-8 -*-
"""Los escalones de costo (§4.4) — pendiente 21.

**La tabla existía, el motor la leía y nadie la podía llenar.** Sin escalones
cargados el modelo subestima los grupos grandes, que son justo los que se
negocian.

Lo que se vigila acá es que la puerta no deje entrar una regla que el motor no
sabe evaluar, y que la lista vacía se DIGA en vez de mostrarse como un cero.
"""
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app, raise_server_exceptions=False)


# ── La puerta ────────────────────────────────────────────────────────────────

def test_las_rutas_existen_y_piden_token(cliente):
    """⚠️ Probar el ENDPOINT, no la función."""
    rutas = cliente.app.openapi()["paths"]
    assert "/api/costos-grupos/escalones/" in rutas
    assert set(rutas["/api/costos-grupos/escalones/"]) == {"get", "post"}
    assert set(rutas["/api/costos-grupos/escalones/{escalon_id}/"]) == {"put", "delete"}

    assert cliente.get("/api/costos-grupos/escalones/").status_code in (401, 403)
    assert cliente.post("/api/costos-grupos/escalones/",
                        json={"driver": "pax", "umbral": "20",
                              "costo_adicional": "150"}).status_code in (401, 403)


# ── Lo que no puede entrar ───────────────────────────────────────────────────

def test_un_driver_que_el_motor_NO_SABE_EVALUAR_no_entra():
    """⚠️ **El defecto que esto evita.** El motor resuelve el driver con un
    diccionario de tres entradas y **saltea** el que no encuentra. Una regla con
    driver `personas` se guardaría feliz y no se aplicaría nunca: el grupo
    saldría barato y nadie vería un error.
    """
    from app.api.costos_grupos_api import DRIVERS, FilaEscalon, _valida_escalon

    ok = FilaEscalon(driver="pax", umbral="20", costo_adicional="150")
    assert _valida_escalon(ok) == (Decimal("20"), Decimal("150"))

    with pytest.raises(HTTPException) as e:
        _valida_escalon(FilaEscalon(driver="personas", umbral="20",
                                    costo_adicional="150"))
    assert e.value.status_code == 400
    assert "personas" in e.value.detail

    # Y la lista de la puerta es exactamente la que evalúa el motor.
    from app.engine.costos_grupos import escalones_aplicables
    import inspect
    fuente = inspect.getsource(escalones_aplicables)
    for d in DRIVERS:
        assert f'"{d}"' in fuente, f"{d} no lo evalúa el motor"


def test_un_umbral_en_CERO_no_entra():
    """Lo cruzarían todos los grupos: dejaría de ser un escalón y sería un
    costo fijo de todo grupo, disfrazado de excepción."""
    from app.api.costos_grupos_api import FilaEscalon, _valida_escalon

    for malo in ("0", "-5"):
        with pytest.raises(HTTPException) as e:
            _valida_escalon(FilaEscalon(driver="pax", umbral=malo,
                                        costo_adicional="150"))
        assert e.value.status_code == 400
        assert "escalón" in e.value.detail


def test_un_numero_ilegible_da_400_con_el_valor():
    from app.api.costos_grupos_api import FilaEscalon, _valida_escalon

    with pytest.raises(HTTPException) as e:
        _valida_escalon(FilaEscalon(driver="pax", umbral="veinte",
                                    costo_adicional="150"))
    assert "veinte" in e.value.detail


def test_los_miles_con_coma_entran():
    """El owner pega de Excel: `1,200` es mil doscientos, no un error."""
    from app.api.costos_grupos_api import FilaEscalon, _valida_escalon

    umbral, costo = _valida_escalon(
        FilaEscalon(driver="hab_grupo", umbral="20", costo_adicional="1,200"))
    assert costo == Decimal("1200") and umbral == Decimal("20")


# ── La lista vacía se DICE ───────────────────────────────────────────────────

def test_la_respuesta_dice_SIN_CARGAR_y_no_lo_deja_deducir():
    """⚠️ Un cero que significa «nadie lo cargó» leído como «no hay costo
    extra» da un piso más barato que la realidad, y encima con cara de medido.
    El motor ya lo advierte en su docstring; la API lo hace visible."""
    import inspect

    from app.api import costos_grupos_api

    fuente = inspect.getsource(costos_grupos_api.leer_escalones)
    assert '"sin_cargar"' in fuente

    from app.engine.costos_grupos import escalones_aplicables
    assert "subestima" in (escalones_aplicables.__doc__ or "")


def test_borrar_un_escalon_ABARATA_y_el_codigo_lo_dice():
    """La alternativa no destructiva existe (`activo`) y tiene que estar a la
    vista de quien lea el endpoint."""
    import inspect

    from app.api import costos_grupos_api

    fuente = inspect.getsource(costos_grupos_api.borrar_escalon)
    assert "abarata" in fuente.lower() and "activo" in fuente


# ── El motor, con reglas cargadas ────────────────────────────────────────────

def test_el_escalon_se_aplica_SOLO_cuando_se_cruza_el_umbral():
    """Se cruza con `>`, no con `>=`: un grupo de exactamente 20 pax no paga el
    guía adicional que existe *a partir de* 20."""
    from types import SimpleNamespace

    from app.engine.costos_grupos import escalones_aplicables

    regla = SimpleNamespace(driver="pax", umbral=Decimal("20"),
                            costo_adicional=Decimal("150"),
                            descripcion="Guía adicional")
    assert escalones_aplicables([regla], Decimal("20"), Decimal("10")) == []
    cruzados = escalones_aplicables([regla], Decimal("21"), Decimal("10"))
    assert len(cruzados) == 1 and cruzados[0].costo == Decimal("150")


def test_sin_reglas_el_motor_devuelve_VACIO_y_por_eso_hace_falta_la_puerta():
    from app.engine.costos_grupos import escalones_aplicables

    assert escalones_aplicables([], Decimal("500"), Decimal("300")) == []
