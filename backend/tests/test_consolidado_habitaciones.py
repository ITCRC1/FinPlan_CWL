# -*- coding: utf-8 -*-
"""Estadísticas por tipo y por set, y el depto del GL en la planilla (owner, 2026-11-12).

«las estadísticas que traigan también máximo detalle para habitaciones
estándares y para villas» · «los checkbooks de planilla con el gl para poder
auditar los datos calculados».
"""
import pathlib

from app.api import consolidado_planilla_api as cp
from app.engine import pl_engine

FUENTE = (pathlib.Path(__file__).resolve().parents[1] / "app" / "api"
          / "consolidado_planilla_api.py").read_text(encoding="utf-8")

TIPOS = [
    {"codigo": "BL01", "nombre": "Corcovado Deluxe", "depto": "0110", "unidades": 6},
    {"codigo": "RO04", "nombre": "Sirena Suites", "depto": "0110", "unidades": 8},
    {"codigo": "SH07", "nombre": "Villas Deluxe", "depto": "0115", "unidades": 3},
]


def _v(d, o, p, ing):
    return {"disponibles": d, "ocupadas": o, "pax": p, "ingreso": ing}


def test_cada_tipo_lleva_su_set_y_sus_indicadores():
    por_tipo = {("BL01", 1): _v(186, 93, 186, 46500.0), ("SH07", 2): _v(84, 15, 30, 25500.0)}
    filas = cp.filas_habitaciones(TIPOS, por_tipo, {})
    t = [f for f in filas if f["nivel"] == "Tipo"]
    bl = next(f for f in t if f["codigo"] == "BL01")
    assert bl["set"] == "Habitaciones estándar" and bl["mes"] == 1
    assert bl["ocupacion"] == 0.5 and bl["adr"] == 500.0 and bl["revpar"] == 250.0
    sh = next(f for f in t if f["codigo"] == "SH07")
    assert sh["set"] == "Villas" and sh["depto"] == "0115" and sh["adr"] == 1700.0


def test_el_set_suma_sus_tipos_y_los_indicadores_salen_de_las_sumas():
    """Ocupación del set = Σ ocupadas / Σ disponibles, no el promedio de dos %."""
    por_tipo = {("BL01", 1): _v(186, 186, 300, 90000.0), ("RO04", 1): _v(248, 62, 100, 20000.0)}
    filas = cp.filas_habitaciones(TIPOS, por_tipo, {})
    s = next(f for f in filas if f["nivel"] == "Set" and f["depto"] == "0110" and f["mes"] == 1)
    assert s["disponibles"] == 434 and s["ocupadas"] == 248 and s["unidades"] == 14
    assert abs(s["ocupacion"] - 248 / 434) < 1e-12          # no (1.0 + 0.25) / 2
    assert s["adr"] == 110000.0 / 248
    h = next(f for f in filas if f["nivel"] == "Hotel" and f["mes"] == 1)
    assert h["ocupadas"] == 248 and h["set"] == "Total hotel"


def test_villas_y_estandar_quedan_en_sets_separados():
    por_tipo = {("BL01", 3): _v(186, 100, 180, 50000.0), ("SH07", 3): _v(93, 30, 60, 51000.0)}
    filas = cp.filas_habitaciones(TIPOS, por_tipo, {})
    sets = {f["depto"]: f for f in filas if f["nivel"] == "Set" and f["mes"] == 3}
    assert set(sets) == {"0110", "0115"}
    assert sets["0115"]["ingreso"] == 51000.0 and sets["0110"]["ingreso"] == 50000.0
    hotel = next(f for f in filas if f["nivel"] == "Hotel" and f["mes"] == 3)
    assert hotel["ingreso"] == 101000.0


def test_un_mes_sin_tipo_no_se_reparte():
    """2024, 2025 y los meses propios del forecast solo traen el total: va como
    «Sin tipo» y suma al hotel, sin inventar el reparto por tipo."""
    filas = cp.filas_habitaciones(TIPOS, {}, {10: _v(930, 400, 720, 240000.0)})
    st = [f for f in filas if f["nivel"] == "Sin tipo"]
    assert len(st) == 1 and st[0]["codigo"] == "" and st[0]["adr"] == 600.0
    assert not [f for f in filas if f["nivel"] == "Tipo"]
    assert next(f for f in filas if f["nivel"] == "Hotel")["ocupadas"] == 400


def test_sin_ocupadas_no_divide_por_cero():
    filas = cp.filas_habitaciones(TIPOS, {("BL01", 10): _v(0, 0, 0, 0.0)}, {})
    f = next(f for f in filas if f["nivel"] == "Tipo")
    assert f["ocupacion"] is None and f["adr"] is None and f["revpar"] is None


def test_la_ruta_va_con_la_llave_y_respeta_la_vigencia_del_tipo():
    i = FUENTE.index('@router.get("/consolidado/habitaciones/")')
    cuerpo = FUENTE[i:]
    assert "lector_del_consolidado" in cuerpo
    assert "vigente_desde_anio" in cuerpo                       # las Villas no existían en 2026
    assert "_room_stats_from_actuals" in cuerpo and "get_revenue_by_room_type" in cuerpo


def test_la_planilla_trae_el_depto_con_que_la_muestra_el_gl():
    """El checkbook guarda el sub-depto; el GL lo sube al padre, salvo Villas."""
    conceptos = [{"key": "c6000_sw", "code": "6000", "label": "Salario", "grupo": "DEVENGADO"}]
    fila = lambda d: {"position_code": "x", "position_name": "P", "employee_name": "E",
                      "dept_code": d, "dept_name": "", "meses": {"c6000_sw": [100.0] * 12}}
    pl_engine.set_dept_catalog([
        {"dept_code": "0110", "default_pl_group": "ROOMS", "parent_dept_code": ""},
        {"dept_code": "0111", "default_pl_group": "ROOMS", "parent_dept_code": "0110"},
        {"dept_code": "0115", "default_pl_group": "ROOMS", "parent_dept_code": "0110"}])
    try:
        out = cp.filas_planilla({"conceptos": conceptos, "rows": [fila("0111"), fila("0115")]})
    finally:
        pl_engine.reset_dept_catalog()
    assert [f["dept_gl"] for f in out] == ["0110", "0115"]
