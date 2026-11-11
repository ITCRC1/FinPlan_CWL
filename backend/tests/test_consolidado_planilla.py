# -*- coding: utf-8 -*-
"""Posiciones y checkbooks para el Excel en vivo (owner, 2026-11-11).

Lo que se blinda: que las cifras salgan del MISMO reporte que la pantalla, que
vayan con la llave de solo lectura, y que cada fila cuadre contra sí misma.
"""
import pathlib
from decimal import Decimal
from types import SimpleNamespace

from app.api import consolidado_planilla_api as cp

FUENTE = (pathlib.Path(__file__).resolve().parents[1] / "app" / "api"
          / "consolidado_planilla_api.py").read_text(encoding="utf-8")
MAIN = (pathlib.Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8")

CONCEPTOS = [
    {"key": "c6000_sw", "code": "6000", "label": "Salario bruto", "grupo": "DEVENGADO"},
    {"key": "c6020_ccss", "code": "6020", "label": "CCSS patronal", "grupo": "CARGAS"},
    {"key": "c6028_housing", "code": "6028", "label": "Vivienda", "grupo": "BENEFICIOS"},
]


def _rep():
    sw = [1000.0] * 9 + [0.0] + [1000.0] * 2
    ccss = [round(v * 0.2683, 2) for v in sw]
    return {
        "conceptos": CONCEPTOS,
        "rows": [{
            "position_id": "p1", "position_code": "0111-01", "position_name": "RECEPCIONISTA",
            "employee_name": "ANA", "employee_type": "1-Permanente",
            "dept_code": "0111", "dept_name": "Front Desk",
            "salary_amount": 530000.0, "salary_currency": "CRC",
            "fte": [1.0] * 9 + [0.0] + [1.0] * 2, "fte_prom": 0.9167,
            "meses": {"c6000_sw": sw, "c6020_ccss": ccss, "c6028_housing": [0.0] * 12},
            "devengado": 11000.0, "cargas": round(sum(ccss), 2), "beneficios": 0.0,
        }],
    }


def test_el_costo_del_mes_es_la_suma_de_sus_conceptos():
    [f] = cp.filas_posiciones(_rep())
    assert f["costo"][0] == 1268.30
    assert f["costo"][9] == 0.0
    assert f["costo_anual"] == round(sum(f["costo"]), 2)
    assert f["costo_anual"] == round(f["devengado"] + f["cargas"] + f["beneficios"], 2)


def test_la_fila_de_posicion_trae_nombre_y_salario():
    """El owner eligió «con nombre y salario» (2026-11-11)."""
    [f] = cp.filas_posiciones(_rep())
    assert f["empleado"] == "ANA" and f["salario"] == 530000.0 and f["moneda"] == "CRC"
    assert len(f["fte"]) == 12 and f["tipo_plaza"] == "1-Permanente"


def test_el_checkbook_de_planilla_omite_conceptos_en_cero():
    filas = cp.filas_planilla(_rep())
    assert [f["cuenta"] for f in filas] == ["6000", "6020"]
    for f in filas:
        assert f["anual"] == round(sum(f["meses"]), 2)


def test_planilla_y_posiciones_suman_lo_mismo():
    rep = _rep()
    assert round(sum(f["anual"] for f in cp.filas_planilla(rep)), 2) == \
        round(sum(f["costo_anual"] for f in cp.filas_posiciones(rep)), 2)


def test_el_opex_trae_doce_meses_en_usd_y_su_moneda():
    def e(dept, cta, det, mes):
        return SimpleNamespace(dept_code=dept, account_code=cta, account_name="CLEANING",
                               detail_code=det, detail_desc="Detergente", currency="CRC",
                               get_month=lambda m: Decimal("10.005") if m == mes else Decimal("0"))
    filas = cp.filas_opex([e("0200", "7065", "801", 3), e("0110", "7065", "800", 1)],
                          {"0110": "Rooms"})
    assert [f["dept"] for f in filas] == ["0110", "0200"]
    assert filas[0]["dept_name"] == "Rooms" and filas[1]["dept_name"] == ""
    assert filas[0]["meses"][0] == 10.01 and filas[0]["anual"] == 10.01
    assert filas[0]["moneda"] == "CRC"


def test_reusa_el_reporte_de_la_pantalla():
    assert "planilla_por_posicion(" in FUENTE, (
        "si arma la planilla por su cuenta, el Excel y la pantalla van a divergir")


def test_las_tres_puertas_van_con_la_llave_de_solo_lectura():
    for ruta in ("/consolidado/posiciones/", "/consolidado/planilla/", "/consolidado/opex/"):
        i = FUENTE.index(f'@router.get("{ruta}")')
        j = FUENTE.find("@router", i + 1)
        assert "lector_del_consolidado" in FUENTE[i: j if j > 0 else len(FUENTE)], ruta


def test_resuelve_con_el_mismo_criterio_del_consolidado():
    assert "_escoger_escenario(" in FUENTE


def test_el_router_esta_montado():
    assert "consolidado_planilla_router" in MAIN
