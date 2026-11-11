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


# ── El plan al lado de Integrity ─────────────────────────────────────────────
# Owner, 2026-11-10: *«quiero mapear budget 2027 y forecast 2026 working separado
# por rooms y Villas»* · *«available rooms per room type»* · *«occupied room per
# room type»* · *«las estadísticas de spa, laundry»*.

_TIPOS = [
    {"codigo": "BL01", "nombre": "Corcovado Deluxe", "depto": "0110", "n7": "01", "unidades": 6},
    {"codigo": "RO04", "nombre": "Sirena", "depto": "0110", "n7": "04", "unidades": 8},
    {"codigo": "SH07", "nombre": "Villas Deluxe", "depto": "0115", "n7": "07", "unidades": 3},
]


def _agr(*movs):
    """movs: (mes, cuenta con día, débito)."""
    return si.agregar([(m, c, Decimal(str(d)), Decimal("0")) for m, c, d in movs])


def _con_dato():
    return {(t["codigo"], 1): {"disponibles": 1, "ocupadas": 0, "pax": 0} for t in _TIPOS}


def _dep(v, codigo):
    return next((h for h in v["habitaciones"] if h["depto"] == codigo), None)


def test_rooms_y_villas_salen_separados_por_su_depto():
    v = si.armar_plan(_TIPOS, _con_dato(), {}, [None] * 12, {}, {})
    deptos = {h["depto"]: [t["codigo"] for t in h["tipos"]] for h in v["habitaciones"]}
    assert deptos == {"0110": ["BL01", "RO04"], "0115": ["SH07"]}
    # Residencias no tiene tipos en esta lista: no aparece vacía.
    assert "0116" not in deptos


def test_cada_tipo_lleva_su_cuenta_con_el_nivel_7_del_inventario():
    v = si.armar_plan(_TIPOS, _con_dato(), {}, [None] * 12, {}, {})
    villas = _dep(v, "0115")["tipos"][0]
    assert villas["cuenta"] == "9000-0115-SEG-N4-001-DD-07"


def test_disponibles_ocupadas_y_ocupacion_por_tipo():
    por_tipo = {("BL01", 1): {"disponibles": 186, "ocupadas": 148.8, "pax": 297.6},
                ("RO04", 1): {"disponibles": 248, "ocupadas": 124, "pax": 248}}
    v = si.armar_plan(_TIPOS, por_tipo, {}, [None] * 12, {}, {})
    rooms = v["habitaciones"][0]
    bl = rooms["tipos"][0]
    assert bl["disponibles"][0] == 186 and bl["ocupadas"][0] == 148.8
    assert bl["ocupacion"][0] == pytest.approx(0.8)
    assert rooms["total"]["disponibles"][0] == 434
    assert rooms["total"]["ocupadas"][0] == pytest.approx(272.8)
    assert rooms["total"]["ocupacion"][0] == pytest.approx(272.8 / 434)
    # Un mes sin plan queda vacío, no en cero.
    assert bl["disponibles"][1] is None and rooms["total"]["ocupacion"][1] is None


def test_un_tipo_sin_noches_disponibles_no_divide_por_cero():
    por_tipo = {("SH07", 1): {"disponibles": 0, "ocupadas": 0, "pax": 0}}
    v = si.armar_plan(_TIPOS, por_tipo, {}, [None] * 12, {}, {})
    assert _dep(v, "0115")["tipos"][0]["ocupacion"][0] is None


def test_integrity_suma_todos_los_segmentos_del_tipo():
    """9000-DEPTO-SEGMENTO-FIT/GRUPO-001-DD-HAB: BAR (001) y TAGP (005) del
    mismo tipo y mes son las ocupadas de ese tipo."""
    agr = _agr((2, "9000-0110-001-001-001-03-01", 10),
               (2, "9000-0110-005-002-001-14-01", 4),
               (2, "9000-0110-001-001-001-03-04", 7))
    v = si.armar_plan(_TIPOS, {}, {}, [None] * 12, {}, agr)
    rooms = v["habitaciones"][0]
    assert rooms["tipos"][0]["real_ocupadas"][1] == 14
    assert rooms["tipos"][1]["real_ocupadas"][1] == 7
    assert rooms["total"]["real_ocupadas"][1] == 21


def test_un_mes_sin_balanza_no_se_ve_como_cero_noches():
    agr = _agr((2, "9000-0110-001-001-001-03-01", 10))
    v = si.armar_plan(_TIPOS, {}, {}, [None] * 12, {}, agr)
    assert v["habitaciones"][0]["tipos"][0]["real_ocupadas"][0] is None


def test_las_villas_de_integrity_no_se_mezclan_con_rooms():
    agr = _agr((3, "9000-0115-002-001-001-05-07", 9))
    v = si.armar_plan(_TIPOS, {}, {}, [None] * 12, {}, agr)
    assert _dep(v, "0110") is None            # Rooms no tiene ni plan ni real
    assert _dep(v, "0115")["tipos"][0]["real_ocupadas"][2] == 9


def test_el_forecast_lleva_el_total_de_los_meses_sin_tipo():
    v = si.armar_plan(_TIPOS, {}, {11: {"disponibles": 900, "ocupadas": 410.1}},
                      [None] * 12, {}, {})
    assert v["sin_tipo"]["disponibles"][10] == 900
    assert v["sin_tipo"]["ocupadas"][10] == 410.1
    assert v["sin_tipo"]["disponibles"][0] is None
    assert si.armar_plan(_TIPOS, {}, {}, [None] * 12, {}, {})["sin_tipo"] is None


def test_spa_compara_tratamientos_con_9201_a_9209():
    spa = [94.2] + [None] * 11
    agr = _agr((1, "9201-0140-001-999-001-02-00", 30),
               (1, "9205-0140-001-999-001-09-00", 12),
               (1, "9250-0140-001-999-001-09-00", 99))   # retail de spa: no es tratamiento
    v = si.armar_plan(_TIPOS, {}, {}, spa, {}, agr)
    assert v["spa"]["plan"][0] == 94.2
    assert v["spa"]["real"][0] == 42
    assert v["spa"]["real"][1] is None


def test_lavanderia_lleva_los_kilos_del_plan_y_los_de_integrity_por_cuenta():
    kilos = {"rooms": [2000.0] * 12, "fb": [800.0] * 12}
    agr = _agr((1, "9700-0160-999-999-001-05-00", 1900),
               (1, "9701-0160-999-999-001-05-00", 750))
    v = si.armar_plan(_TIPOS, {}, {}, [None] * 12, kilos, agr)
    areas = {f["area"]: f for f in v["lavanderia"]["plan"]}
    assert areas["rooms"]["cuenta"] == "9700" and areas["rooms"]["plan"][0] == 2000
    assert areas["fb"]["cuenta"] == "9701"
    assert "spa" not in areas            # sin plan, no se inventa una fila
    assert v["lavanderia"]["real"]["9700"][0] == 1900
    assert v["lavanderia"]["real"]["9702"][0] is None


def test_el_plan_no_escribe_y_no_recalcula_las_noches():
    """Las noches salen de «Ingresos por tipo» (`get_revenue_by_room_type`) o
    del ACTUAL enlazado; un segundo cálculo es como se llegó a tener seis."""
    src = inspect.getsource(api.plan)
    assert "get_revenue_by_room_type" in src
    assert "_room_stats_from_actuals" in src
    assert "days_in_month" not in src and "monthrange" not in src
    for verbo in ("db.add(", "db.commit(", "db.delete(", ".flush("):
        assert verbo not in src


def test_el_plan_numera_todos_los_tipos_antes_de_filtrar_por_vigencia():
    """SH07 tiene que ser 07 también en un año en que no existe, o el nivel 7
    de Integrity se cruzaría con el tipo equivocado."""
    src = inspect.getsource(api.plan)
    assert "for i, rt in enumerate(rts, 1)" in src
    assert "vigente_desde_anio <= esc.year" in src


def test_un_depto_sin_ningun_dato_no_se_muestra_pero_uno_en_cero_si():
    """2024 y 2025 no tienen apertura por tipo: la sección entera saldría en «—».
    Residencias, con 0 unidades, sale en cero: el cero es un dato."""
    assert si.armar_plan(_TIPOS, {}, {}, [None] * 12, {}, {})["habitaciones"] == []
    v = si.armar_plan(_TIPOS, {("SH07", 1): {"disponibles": 0, "ocupadas": 0, "pax": 0}},
                      {}, [None] * 12, {}, {})
    assert [h["depto"] for h in v["habitaciones"]] == ["0115"]


def test_el_actual_sin_apertura_por_tipo_cae_al_total_del_hotel():
    src = inspect.getsource(api.plan)
    assert 'fuente = "actual_sin_tipo"' in src


# ── Horas regulares ──────────────────────────────────────────────────────────
# Owner, 2026-11-10: *«y revisa los labour hours»* · *«regular hours»*.

def test_horas_de_integrity_suman_las_posiciones_del_depto():
    agr = _agr((1, "9980-0113-508-013-015-00-00", 240),
               (1, "9980-0113-509-013-015-00-00", 200),
               (1, "9981-0113-508-013-015-00-00", 30),     # extras: no son regulares
               (1, "9980-0122-600-013-015-00-00", 480))
    r = si.real_horas_por_depto(agr)
    assert r["0113"][0] == 440 and r["0122"][0] == 480
    assert r["0113"][1] is None


def test_las_horas_del_plan_van_al_lado_de_la_9980():
    v = si.armar_horas({"0113": [3600.0] * 12, "0150": [240.0] * 12}, {"0113": "Housekeeping"},
                       _agr((1, "9980-0113-508-013-015-00-00", 3400),
                            (1, "9980-0186-700-013-015-00-00", 480)), [240.0] * 12)
    d = {f["depto"]: f for f in v["deptos"]}
    assert d["0113"]["plan"][0] == 3600 and d["0113"]["real"][0] == 3400
    assert d["0113"]["nombre"] == "Housekeeping"
    # Un depto que está en un solo lado igual aparece: es lo que hay que mirar.
    assert d["0150"]["real"][0] is None
    assert d["0186"]["plan"][0] is None and d["0186"]["real"][0] == 480
    assert v["total"]["plan"][0] == 3840 and v["total"]["real"][0] == 3880


def test_las_horas_del_plan_son_dias_del_mes_por_8():
    """Owner, 2026-11-10: cada mes con sus días × 8 horas, no 240 fijo."""
    src = inspect.getsource(api.plan)
    assert "jornada.bases_del_anio(anio" in src
    assert "jornada.CUENTA_BASE" in src
    import re
    assert not re.search(r"240\s*\*|\*\s*240|Decimal\(\"240\"\)", src)


def test_el_fte_de_las_dos_columnas_sale_de_las_horas_del_mes():
    """FTE = horas ÷ (días del mes × 8): 248 en enero y 224 en febrero son 1 FTE."""
    h = [248.0, 224.0] + [240.0] * 10
    agr = _agr((1, "9980-0113-508-013-015-00-00", 248), (2, "9980-0113-508-013-015-00-00", 112))
    v = si.armar_horas({"0113": [496.0, 448.0] + [0.0] * 10}, {}, agr, h)
    d = v["deptos"][0]
    assert d["fte_plan"][:2] == [2.0, 2.0]
    assert d["fte_real"][:2] == [1.0, 0.5] and d["fte_real"][2] is None
    assert v["total"]["fte_real"][:2] == [1.0, 0.5]
    assert v["horas_por_fte"] == h


def test_el_fte_real_usa_la_9979_de_integrity_donde_la_haya():
    """Enero: Integrity registró su base (8 × 31 = 248 en la 9979) → el FTE real
    se divide por esa. Febrero: Integrity no la tiene → se usa la del plan."""
    h = [240.0] * 12
    agr = _agr((1, "9979-0180-000-000-000-00-00", 248),
               (1, "9980-0113-508-013-015-00-00", 248),
               (2, "9980-0113-508-013-015-00-00", 240))
    v = si.armar_horas({"0113": [240.0] * 12}, {}, agr, h)
    d = v["deptos"][0]
    assert d["fte_real"][0] == 1.0          # 248 ÷ 248 (la 9979 de Integrity)
    assert d["fte_real"][1] == 1.0          # 240 ÷ 240 (la base del plan)
    assert d["fte_plan"][0] == 1.0          # el plan, con SU base
    assert v["horas_por_fte_real"][0] == 248 and v["horas_por_fte_real"][1] is None
    # La 9979 no es horas de ningún depto: no aparece como fila.
    assert {f["depto"] for f in v["deptos"]} == {"0113"}


def test_cafeteria_y_lavanderia_cuentan_horas_aunque_sean_allocation():
    """Para el P&L son allocation; su gente trabaja horas e Integrity las registra."""
    src = inspect.getsource(api._fte_por_depto)
    assert "ALLOC_EXCL" not in src and "allocation_en_overhead" not in src
    assert 'p.position_code == "GL"' in src
    assert "_dept_fte_override" in src
