# -*- coding: utf-8 -*-
"""El signo del mes del Pre-Cierre, verificado contra el mayor (owner, 2026-11-13).

Integrity entrega «Mes Actual» sin signo y `monto_mes` le pone el del acumulado.
Una reversa —el mes al revés que el año— entraba con el signo cambiado: en
octubre 2026, 11 cuentas y el GOP unos $7.600 peor. El mayor del mismo mes trae
débito y crédito: si da el mismo monto con el signo contrario, manda el mayor.
"""
import pathlib
from decimal import Decimal as D

from app.importers import integrity_final as I

API = pathlib.Path(__file__).resolve().parents[1] / "app" / "api"


def _f(cuenta, mes_crc, depto=""):
    return {"cuenta": cuenta, "mes_crc": D(str(mes_crc)), "mes_usd": D(str(mes_crc)) / D("456.04"),
            "depto": depto, "descripcion": ""}


def test_una_reversa_toma_el_signo_del_mayor():
    """6023-0111: el acumulado del año es gasto (+) pero en octubre se revirtió."""
    filas = [_f("6023-0111", 117967.28)]
    mayor = {"6023-0111-500-011-015-00-00": D("-100000.00"), "6023-0111-501-013-015-00-00": D("-17967.28")}
    c = I.corregir_signos(filas, mayor, D("456.04"))
    assert len(c) == 1 and filas[0]["mes_crc"] == D("-117967.28")
    assert filas[0]["mes_usd"] == D("-117967.28") / D("456.04")


def test_el_ingreso_usa_la_misma_convencion_que_monto_mes():
    """Ingreso: el mayor da crédito (−) y el cargador lo guarda con signo_de; una
    devolución (débito) es el caso que se invierte."""
    cuenta = "4000-0110"
    normal = I.monto_mes(cuenta, 50000, -964928001)          # cómo lo carga hoy
    filas = [_f(cuenta, normal)]
    mayor = {"4000-0110-001-001-001-01-01": D("50000")}      # débito: devolución
    I.corregir_signos(filas, mayor, D("456.04"))
    assert filas[0]["mes_crc"] == I.signo_de(cuenta) * D("50000")


def test_si_el_signo_ya_coincide_no_toca_nada():
    filas = [_f("6000-0111", 3060051.58)]
    assert I.corregir_signos(filas, {"6000-0111-500-011-015-00-00": D("3060051.58")}, D("456.04")) == []
    assert filas[0]["mes_crc"] == D("3060051.58")


def test_si_el_monto_no_coincide_no_se_adivina():
    """Otro corte (falta media quincena en el mayor): no hay con qué decidir."""
    filas = [_f("6023-0200", 314547.68)]
    assert I.corregir_signos(filas, {"6023-0200-591-013-015-00-00": D("-150000")}, D("456.04")) == []
    assert filas[0]["mes_crc"] == D("314547.68")


def test_sin_mayor_de_la_cuenta_o_mes_en_cero_no_toca():
    filas = [_f("7400-0161", 0), _f("7100-0110", 500)]
    assert I.corregir_signos(filas, {}, D("456.04")) == []


def test_correrla_dos_veces_no_vuelve_a_invertir():
    filas = [_f("5201-0151", 184064)]
    mayor = {"5201-0151-800-000-000-00-00": D("-184064")}
    assert len(I.corregir_signos(filas, mayor, D("456.04"))) == 1
    assert I.corregir_signos(filas, mayor, D("456.04")) == []
    assert filas[0]["mes_crc"] == D("-184064")


def test_la_cuenta_padre_suma_sus_hijas_del_mayor():
    filas = [_f("6023-0122", 499013), _f("6023-0122-530", 300000)]
    mayor = {"6023-0122-530-013-015-00-00": D("-300000"), "6023-0122-531-013-015-00-00": D("-199013")}
    c = I.corregir_signos(filas, mayor, D("456.04"))
    assert {x["cuenta"] for x in c} == {"6023-0122", "6023-0122-530"}


def test_corre_en_las_dos_puertas_y_antes_del_espejo():
    """Subir el Pre-Cierre y subir el mayor: en cualquier orden queda corregido."""
    pc = (API / "precierre_api.py").read_text(encoding="utf-8")
    i = pc.index("signos = await corregir_signos_del_borrador(db, pc)")
    assert i < pc.index("espejo = await _reflejar(db, pc, idioma)", i)
    ag = (API / "auditoria_gl_api.py").read_text(encoding="utf-8")
    assert "_corregir_el_precierre_del_mes(db, anio, mes)" in ag
    assert "corregir_signos_del_borrador" in ag and "_reflejar" in ag
