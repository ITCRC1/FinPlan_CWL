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
                 "/api/consolidado/rooms/pacing/?year=2027"):
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
