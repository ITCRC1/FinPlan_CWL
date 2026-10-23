# -*- coding: utf-8 -*-
"""Rooms para Hotel Consolidation: solo lectura y con la misma puerta que el consolidado."""
import pathlib

from fastapi.testclient import TestClient

from app.main import app

FUENTE = (pathlib.Path(__file__).resolve().parents[1] / "app" / "api" / "consolidado_rooms_api.py").read_text(encoding="utf-8")


def test_sin_llave_ni_sesion_no_entra():
    c = TestClient(app, raise_server_exceptions=False)
    for ruta in ("/api/consolidado/rooms/escenarios/",
                 "/api/consolidado/rooms/escenario/x/",
                 "/api/consolidado/rooms/pacing/?year=2027",
                 "/api/consolidado/rooms/pickup/?year=2027",
                 "/api/consolidado/rooms/rack-rooms/x/",
                 "/api/consolidado/country-mix/?year=2026",
                 "/api/consolidado/channel-mix/?year=2026"):
        assert c.get(ruta).status_code == 401, ruta


def test_la_llave_equivocada_no_entra(monkeypatch):
    monkeypatch.setenv("CONSOLIDADO_API_KEY", "llave-correcta-de-prueba")
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/consolidado/rooms/escenarios/", headers={"X-Api-Key": "llave-incorrecta"})
    assert r.status_code == 401


def test_ninguna_ruta_escribe():
    assert "@router.get(" in FUENTE
    for verbo in ("@router.post(", "@router.put(", "@router.patch(", "@router.delete("):
        assert verbo not in FUENTE


def test_usa_get_db_y_no_get_session():
    assert "Depends(get_session)" not in FUENTE


def test_pickup_solo_entrega_totales():
    """Pickup y canales salen agregados: nada de reservas ni huéspedes."""
    bloque = FUENTE.split('"/consolidado/rooms/pickup/"')[1]
    assert '"pickup"' in bloque and '"canales"' in bloque
    for prohibido in ('"reservas"', '"fotos"', '"posicion"'):
        assert prohibido not in bloque


def test_rack_rooms_solo_entrega_totales():
    """Rack Rooms sale agregado por mes y segmento: sin reservas ni huéspedes."""
    bloque = FUENTE.split('"/consolidado/rooms/rack-rooms/{scenario_id}/"')[1]
    assert "_escenario_propio" in bloque and "rack_rooms_api._ver" in bloque
    assert '"entradas"' not in bloque.split("return {")[1]


def test_country_mix_solo_entrega_conteos_por_pais():
    """Country mix para el Owner Dashboard: conteo por país y mes; sin reservas ni huéspedes."""
    bloque = FUENTE.split('"/consolidado/country-mix/"')[1]
    assert "lector_del_consolidado" in bloque and "Scenario.hotel_id == HOTEL_ID" in bloque
    for prohibido in ('"reservas"', '"huespedes"', '"guests"'):
        assert prohibido not in bloque


def test_channel_mix_solo_entrega_conteos_por_canal():
    """Channel mix para el Owner Dashboard (2.5): conteo por canal y mes; sin reservas ni huéspedes."""
    bloque = FUENTE.split('"/consolidado/channel-mix/"')[1]
    assert "lector_del_consolidado" in bloque and "Scenario.hotel_id == HOTEL_ID" in bloque
    assert "ChannelMixEntry" in bloque
    for prohibido in ('"reservas"', '"huespedes"', '"guests"', "ChannelMixDetail"):
        assert prohibido not in bloque


def test_el_checkbook_de_ingresos_pide_llave():
    c = TestClient(app, raise_server_exceptions=False)
    assert c.get("/api/consolidado/revenue-checkbook/x/").status_code == 401
