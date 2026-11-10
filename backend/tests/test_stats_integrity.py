# -*- coding: utf-8 -*-
"""Las estadísticas de Integrity al mes (Master Data → Estadísticas → Stats).

Owner, 2026-11-10: *«la contabilidad manda»* · *«solo full month»*. El dato sale
del Balance de Comprobación guardado; en Integrity el nivel 6 es el día y acá se
suma al mes. Ver `app/engine/stats_integrity.py`.
"""
import inspect
from decimal import Decimal

import pytest

from app.api import stats_integrity_api as api
from app.engine import stats_integrity as si


# ── La llave del mes ─────────────────────────────────────────────────────────

def test_la_llave_del_mes_es_el_codigo_sin_el_dia():
    assert si.clave_mensual("9000-0110-008-002-001-14-07") == "9000-0110-008-002-001-07"
    assert si.dia("9000-0110-008-002-001-14-07") == "14"


def test_dos_dias_de_la_misma_cuenta_dan_la_misma_llave():
    a = si.clave_mensual("9110-0123-120-999-001-01-00")
    b = si.clave_mensual("9110-0123-120-999-001-31-00")
    assert a == b


def test_las_horas_no_tienen_dia_y_tambien_entran():
    assert si.clave_mensual("9980-0113-508-013-015-00-00") == "9980-0113-508-013-015-00"


@pytest.mark.parametrize("malo", ["9000", "9000-0110-001", "", None, "Total 9000-0110-001-001-001-01-01"])
def test_lo_que_no_es_una_cuenta_de_siete_niveles_no_da_llave(malo):
    assert si.clave_mensual(malo) is None


# ── La suma del mes ──────────────────────────────────────────────────────────

def test_el_mes_es_la_suma_de_sus_dias_y_un_reverso_descuenta():
    ag = si.agregar([
        (1, "9000-0110-008-002-001-03-04", 6, 0),
        (1, "9000-0110-008-002-001-04-04", 6, 0),
        (1, "9000-0110-008-002-001-05-04", 0, 2),      # reverso
    ])
    v = ag[(1, "9000-0110-008-002-001-04")]
    assert v["valor"] == Decimal("10")
    assert v["dias"] == {"03", "04", "05"}
    assert v["movimientos"] == 3


def test_meses_distintos_no_se_mezclan():
    ag = si.agregar([(1, "9700-0160-999-999-001-02-00", 100, 0),
                     (2, "9700-0160-999-999-001-02-00", 80, 0)])
    assert ag[(1, "9700-0160-999-999-001-00")]["valor"] == 100
    assert ag[(2, "9700-0160-999-999-001-00")]["valor"] == 80


def test_solo_entra_la_clase_9():
    ag = si.agregar([(1, "4000-0110-001-001-001-01-01", 999, 0),
                     (1, "7310-0110-800-000-000-00-00", 5, 0)])
    assert ag == {}


# ── El catálogo homologado ───────────────────────────────────────────────────

def test_el_catalogo_de_cwl_carga_y_no_tiene_claves_repetidas():
    cat = si.leer_catalogo("CWL")
    claves = [c["clave"] for c in cat["cuentas"]]
    assert len(claves) == len(set(claves)) > 1900
    assert len(cat["grupos"]) == 44


def test_las_noches_usan_los_segmentos_de_opera_y_su_cuenta_de_ingreso_gemela():
    cat = si.leer_catalogo("CWL")
    noches = [c for c in cat["cuentas"] if c["grupo"] == "9000"]
    assert len(noches) == 113
    bar_king = next(c for c in noches if c["clave"] == "9000-0110-001-001-001-01")
    assert "Best Available Rate" in bar_king["descripcion"]
    assert bar_king["cuenta_ingreso"] == "4000-0110-001-001-001-DD-01"
    # Villas y Residencias en su propio departamento.
    assert {c["depto"] for c in noches} == {"0110", "0115", "0116"}


def test_un_hotel_sin_catalogo_devuelve_vacio():
    cat = si.leer_catalogo("XXX")
    assert cat["cuentas"] == []


# ── La vista ─────────────────────────────────────────────────────────────────

def test_lo_que_integrity_registra_fuera_del_catalogo_se_muestra_no_se_tira():
    cat = si.leer_catalogo("CWL")
    vista = si.armar_vista(cat, si.agregar([(3, "9999-0110-001-001-001-01-01", 5, 0)]), [3])
    assert vista["fuera_de_catalogo"][0]["clave"] == "9999-0110-001-001-001-01"
    assert vista["fuera_de_catalogo"][0]["meses"][2] == 5.0


def test_una_cuenta_del_catalogo_trae_sus_doce_meses_y_su_grupo_suma():
    cat = si.leer_catalogo("CWL")
    vista = si.armar_vista(cat, si.agregar([
        (1, "9980-0113-508-013-015-00-00", 1848, 0),
        (2, "9980-0113-508-013-015-00-00", 1700, 0)]), [1, 2])
    c = next(x for x in vista["cuentas"] if x["clave"] == "9980-0113-508-013-015-00")
    assert c["meses"][:3] == [1848.0, 1700.0, None]
    assert c["total"] == 3548.0
    g = next(x for x in vista["grupos"] if x["grupo"] == "9980")
    assert g["meses"][0] == 1848.0 and g["con_dato"] == 1
    assert vista["meses_cargados"] == [1, 2]


# ── No es una segunda puerta ni una segunda verdad ──────────────────────────

def test_lee_el_mayor_guardado_y_no_escribe_nada():
    src = inspect.getsource(api)
    assert "MayorMovimiento" in src
    for prohibido in ("db.add(", ".commit(", "delete(", "insert(", "UploadFile"):
        assert prohibido not in src, f"la pantalla de Stats no carga ni escribe: {prohibido}"


def test_el_motor_no_toca_la_base_ni_el_pl():
    src = inspect.getsource(si)
    for prohibido in ("sqlalchemy", "app.db", "pl_engine", "StatisticalEntry"):
        assert prohibido not in src
