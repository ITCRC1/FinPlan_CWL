# -*- coding: utf-8 -*-
"""Libro del Cierre Contable Mensual (owner, 2026-11-11).

«Que tenga la versión Precierre, que es donde preliminarmente subo los
resultados para revisar». Se blinda que el Pre-Cierre se pueda pedir por su
nombre SIN que cambie lo que recibe quien no pide versión, y que el libro
apunte a las seis versiones fijas.
"""
import pathlib
from types import SimpleNamespace

from app.api.consolidado_api import _escoger_escenario
from app.api.precierre_api import VERSION_ESPEJO

LIBRO = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "cierre_mensual"


def _e(version, pre=False, cur=False):
    return SimpleNamespace(version=version, es_precierre=pre, is_current_forecast=cur)


# Como los devuelve la consulta: el más reciente primero, y el espejo es lo último creado.
ACTUALES = [_e(VERSION_ESPEJO, pre=True), _e("actual")]


def test_sin_version_el_actual_nunca_es_el_espejo():
    assert _escoger_escenario(ACTUALES, "ACTUAL", None).version == "actual"


def test_el_precierre_se_pide_por_su_nombre():
    e = _escoger_escenario(ACTUALES, "ACTUAL", VERSION_ESPEJO)
    assert e.es_precierre and e.version == "Pre-Cierre"


def test_si_se_llamaran_igual_gana_el_actual_real():
    dos = [_e("Pre-Cierre", pre=True), _e("Pre-Cierre")]
    assert _escoger_escenario(dos, "ACTUAL", "Pre-Cierre").es_precierre is False


def test_una_version_que_no_existe_no_cae_en_otra():
    assert _escoger_escenario(ACTUALES, "ACTUAL", "Final") is None


def test_el_forecast_sin_version_es_el_current():
    fc = [_e("Working"), _e("October", cur=True), _e("Aug")]
    assert _escoger_escenario(fc, "FORECAST", None).version == "October"


def test_el_libro_baja_las_seis_versiones_fijas():
    src = (LIBRO / "build_cierre.py").read_text(encoding="utf-8")
    for etiqueta in ("Actual 2024", "Actual 2025", "Actual 2026", "Pre-Cierre 2026",
                     "Budget 2026", "Forecast 2026"):
        assert f'"{etiqueta}"' in src, etiqueta
    assert f'"{VERSION_ESPEJO}"' in src


def test_el_libro_no_guarda_la_llave():
    src = (LIBRO / "build_cierre.py").read_text(encoding="utf-8")
    assert 'cfg["C5"] = ""' in src


def test_cada_pestana_pega_al_backend_y_no_al_frontend():
    """Power Query no sigue redirecciones: el frontend responde 308 y muere."""
    src = (LIBRO / "build_cierre.py").read_text(encoding="utf-8")
    assert 'cfg["C4"] = "https://finplancwl-backend.up.railway.app"' in src
