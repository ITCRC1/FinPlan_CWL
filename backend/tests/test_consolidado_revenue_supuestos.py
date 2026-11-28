# -*- coding: utf-8 -*-
"""Los supuestos del ingreso para el Master File (owner, 2026-11-28).

«como puedo mantener este excel para correr cuando yo quiera pero que la
informacion se calcule en forma automatica» · «metelo en el master file».

El libro reconstruye cada línea con fórmulas a partir de esta tabla larga, así
que lo que importa es que cada clave exista con el nombre que el libro busca.
"""
import pathlib

from app.api import consolidado_rooms_api as cr

FUENTE = (pathlib.Path(__file__).resolve().parents[1] / "app" / "api"
          / "consolidado_rooms_api.py").read_text(encoding="utf-8")

TIPOS = [
    {"codigo": "BL01", "nombre": "Corcovado Deluxe", "depto": "", "unidades": 6},
    {"codigo": "SH07", "nombre": "Villas Deluxe", "depto": "0115", "unidades": 3},
]


def _filas(**kw):
    base = dict(
        info={"escenario": "BUDGET Working 2027", "fuente": "checkbook"},
        tipos=TIPOS,
        por_tipo_mes={("BL01", 1): {"occ": 0.8, "rack": 825, "pax": 2, "neta": 657.52, "manual": False},
                      ("SH07", 2): {"occ": 0.15, "rack": 0, "pax": 2, "neta": 1700, "manual": True}},
        dias=[31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31],
        abiertos=[1] * 9 + [0] + [1, 1],
        canales=[{"channel": "TA", "mix": [0.55] * 12, "comm": [0.3] * 12}],
        factor_neto=[0.797] * 12,
        perillas={"food": 126.0, "no_consume_pct": 5.0},
        checkbook={"ROOMS": [100.0] * 12},
        otros={"RETAIL": [7.0] * 12},
    )
    base.update(kw)
    filas = cr.filas_supuestos(**base)
    return {f["clave"]: f for f in filas}


def test_las_categorias_salen_en_orden_con_su_set():
    d = _filas()
    assert d["ORDEN|1|0"]["texto"] == "BL01" and d["ORDEN|2|0"]["texto"] == "SH07"
    assert d["SET|BL01|0"]["texto"] == "Standard"
    assert d["SET|SH07|0"]["texto"] == "Villas"
    assert d["UNID|SH07|0"]["valor"] == 3


def test_sin_dept_code_cae_en_standard_como_en_el_checkbook():
    assert cr.nombre_del_set("") == "Standard"
    assert cr.nombre_del_set(None) == "Standard"
    assert cr.nombre_del_set("0116") == "Residences"


def test_la_neta_a_mano_solo_sale_donde_esta_fijada():
    """Sin NETMAN el libro usa rack x factor neto; con NETMAN, el monto."""
    d = _filas()
    assert d["NETMAN|SH07|2"]["valor"] == 1700
    assert "NETMAN|BL01|1" not in d


def test_un_mes_sin_tarjeta_vale_cero_no_falta():
    """El libro busca las 12 claves de cada categoría: que falte una daría #N/A."""
    d = _filas()
    for c in ("BL01", "SH07"):
        for m in range(1, 13):
            for k in ("OCC", "RACK", "PAX"):
                assert f"{k}|{c}|{m}" in d
    assert d["OCC|BL01|5"]["valor"] == 0


def test_mes_cerrado_perillas_checkbook_y_otros():
    d = _filas()
    assert d["ABRE|-|10"]["valor"] == 0 and d["ABRE|-|1"]["valor"] == 1
    assert d["NF|-|3"]["valor"] == 0.797
    assert d["PERILLA|no_consume_pct|0"]["valor"] == 5.0
    assert d["CB|ROOMS|12"]["valor"] == 100.0
    assert d["OTRO|RETAIL|1"]["valor"] == 7.0
    assert d["MIX|TA|1"]["valor"] == 0.55 and d["CANAL|1|0"]["texto"] == "TA"


def test_las_perillas_siguen_el_orden_de_la_pantalla():
    """Semilla, luego paquete, luego guardadas: el mismo orden del checkbook."""
    i_sem = FUENTE.index('semilla("driver_rates")', FUENTE.index("def revenue_supuestos"))
    i_paq = FUENTE.index("tarifas_del_paquete(await", i_sem)
    i_gua = FUENTE.index("_perillas_guardadas(sm)", i_paq)
    assert i_sem < i_paq < i_gua


def test_la_ruta_es_de_solo_lectura_y_usa_la_llave():
    cuerpo = FUENTE[FUENTE.index("async def revenue_supuestos"):]
    assert "lector_del_consolidado" in cuerpo
    for escribe in ("db.add(", ".commit(", ".delete(", "flush("):
        assert escribe not in cuerpo
