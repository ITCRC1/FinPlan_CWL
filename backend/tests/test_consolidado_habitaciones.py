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


# ── Repartos: Cafetería y Lavandería como centros de costo (owner, 2026-11-12) ─

def test_los_repartos_suman_cero_con_la_4999():
    """«queda en 0 con la cuenta 4999»: el crédito del centro y los cargos a los
    deptos salen en filas separadas y suman 0 por tipo."""
    from types import SimpleNamespace as N
    ent = [N(allocation_type="CAFETERIA", source_dept="0220", target_dept="0220", account="4999", month=1, amount_usd=-300),
           N(allocation_type="CAFETERIA", source_dept="0220", target_dept="0113", account="6025", month=1, amount_usd=200),
           N(allocation_type="CAFETERIA", source_dept="0220", target_dept="0150", account="6025", month=1, amount_usd=100)]
    pl_engine.set_dept_catalog([
        {"dept_code": "0110", "default_pl_group": "ROOMS", "parent_dept_code": ""},
        {"dept_code": "0113", "default_pl_group": "ROOMS", "parent_dept_code": "0110"}])
    try:
        filas = cp.filas_repartos(ent, {"0220": "Cafeteria"})
    finally:
        pl_engine.reset_dept_catalog()
    assert sum(f["anual"] for f in filas) == 0
    cred = [f for f in filas if f["rol"] == "crédito"]
    assert len(cred) == 1 and cred[0]["cuenta"] == "4999" and cred[0]["anual"] == -300
    hk = next(f for f in filas if f["destino"] == "0113")
    assert hk["destino_gl"] == "0110" and hk["rol"] == "cargo" and hk["meses"][0] == 200


def test_la_ruta_de_repartos_solo_lee_con_la_llave():
    i = FUENTE.index('@router.get("/consolidado/repartos/")')
    cuerpo = FUENTE[i:]
    assert "lector_del_consolidado" in cuerpo
    assert "session.add" not in cuerpo and "commit" not in cuerpo


# ── Reparto de salarios regla por regla (owner, 2026-11-12) ──────────────────

def _regla(origen="0113", destinos=None, sale=-100.0):
    destinos = destinos if destinos is not None else {"0220": [100.0] + [0.0] * 11}
    return {"origen": origen, "posicion": "0113-04", "puesto": "ROOM ATTENDANT", "empleados": "X",
            "cuenta": "6000", "portion_pct": 1.0, "cafeteria_pct": 0.2, "override": [False] * 12,
            "planilla": [90.0] + [0.0] * 11, "sw": [70.0] + [0.0] * 11, "ccss": [0.0] * 12,
            "aguinaldo": [0.0] * 12, "cafeteria": [0.0] * 12, "dummy": [0.0] * 12,
            "cargado": [100.0] + [0.0] * 11, "sale": [sale] + [0.0] * 11, "entra": destinos}


def test_cada_salida_va_con_su_entrada_y_netean():
    """«se hace la salida de housekeeping y entra en cafetería»: la regla trae su
    SALE y su ENTRA juntos, y la suma da 0."""
    filas = cp.filas_reparto_salarios([_regla()], {("0113", 1): -100.0, ("0220", 1): 100.0},
                                      {"0113": "Housekeeping", "0220": "Employee Dining"})
    sale = next(f for f in filas if f["concepto"] == "2 · SALE del origen")
    entra = next(f for f in filas if f["concepto"] == "2 · ENTRA al destino")
    assert (sale["destino"], sale["anual"]) == ("0113", -100.0)
    assert (entra["destino"], entra["destino_nombre"], entra["anual"]) == ("0220", "Employee Dining", 100.0)
    assert next(f for f in filas if f["concepto"].startswith("3 · Sale + entra"))["anual"] == 0
    assert all(f["anual"] == 0 for f in filas if f["concepto"].startswith("4 · Control"))


def test_el_control_muestra_si_lo_guardado_no_es_lo_que_dice_la_regla():
    filas = cp.filas_reparto_salarios([_regla()], {("0113", 1): -100.0, ("0220", 1): 80.0}, {})
    ctl = {f["destino"]: f["anual"] for f in filas if f["concepto"].startswith("4 · Control")}
    assert ctl == {"0113": 0.0, "0220": 20.0}


def test_una_regla_sin_fte_en_el_destino_lo_dice():
    filas = cp.filas_reparto_salarios([_regla(destinos={}, sale=0.0)], {}, {})
    assert any("No se movió nada" in f["concepto"] for f in filas)


def test_en_repartos_el_salario_sale_y_entra_no_es_cargo():
    from types import SimpleNamespace as N
    ent = [N(allocation_type="SALARY", source_dept="0113", target_dept="0113", account="6000", month=1, amount_usd=-50),
           N(allocation_type="SALARY", source_dept="0113", target_dept="0220", account="6000", month=1, amount_usd=50)]
    roles = {f["destino"]: f["rol"] for f in cp.filas_repartos(ent, {})}
    assert roles == {"0113": "sale", "0220": "entra"}


def test_la_ruta_de_salarios_solo_lee_y_usa_las_piezas_del_recalculo():
    i = FUENTE.index("async def _reparto_salarios_recreado")
    cuerpo = FUENTE[i:FUENTE.index('@router.get("/consolidado/repartos/")')]
    assert "lector_del_consolidado" in cuerpo
    assert "session.add" not in cuerpo and "commit" not in cuerpo and "delete(" not in cuerpo
    for pieza in ("calc_sw", "loaded_salary_breakdown", "calculate_salary_distribution"):
        assert pieza in cuerpo


# ── Centros de costo armados en el servidor (owner, 2026-11-12) ──────────────
# En Power Query la consulta volvía a bajar el GL entero y con «Actualizar todo»
# quedaba en «Download did not complete».

def _gl(dept, cat, v):
    return {"dept_code": dept, "categoria": cat, "meses": [v] + [0.0] * 11}


def test_el_centro_acumula_reparte_y_queda_en_cero():
    grilla = [_gl("0220", "COST_OF_SALES", 60.0), _gl("0220", "PAYROLL", 30.0),
              _gl("0220", "OPERATING_EXPENSES", 10.0), _gl("0220", "ALLOCATIONS", -100.0),
              _gl("0110", "PAYROLL", 999.0)]
    rep = [{"tipo": "CAFETERIA", "rol": "cargo", "destino_gl": "0110", "meses": [70.0] + [0.0] * 11},
           {"tipo": "CAFETERIA", "rol": "cargo", "destino_gl": "0150", "meses": [30.0] + [0.0] * 11},
           {"tipo": "CAFETERIA", "rol": "crédito", "destino_gl": "0220", "meses": [-100.0] + [0.0] * 11}]
    f = {(r["centro"][:4], r["concepto"], r["depto"]): r["anual"] for r in cp.filas_centros_costo(grilla, rep)}
    assert f[("Cafe", "Total acumulado", "0220")] == 100.0
    assert f[("Cafe", "NETO DEL CENTRO (debe dar 0)", "0220")] == 0
    assert f[("Cafe", "Cargo a departamento", "0110")] == 70.0
    assert f[("Cafe", "Cargos + credito (debe dar 0)", "")] == 0


def test_sin_reparto_guardado_lo_dice_en_vez_de_mostrar_un_descuadre():
    filas = cp.filas_centros_costo([_gl("0161", "PAYROLL", 5.0), _gl("0161", "ALLOCATIONS", -5.0)], [])
    lav = [r for r in filas if r["centro"].startswith("Lav")]
    assert any("viene hecho en el mayor" in r["concepto"] for r in lav)
    assert not any(r["concepto"].startswith("Cargos +") for r in lav)


def test_la_consulta_del_libro_no_rebaja_el_gl():
    m = (pathlib.Path(__file__).resolve().parents[1] / "scripts" / "gl_en_vivo"
         / "centros_costo.m").read_text(encoding="utf-8")
    assert "api/consolidado/centros-costo/" in m
    assert "Table.SelectRows(GL" not in m and "Repartos," not in m
