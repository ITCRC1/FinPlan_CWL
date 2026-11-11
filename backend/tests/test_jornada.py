# -*- coding: utf-8 -*-
"""La jornada y la identidad de las horas.

**Regla vigente (owner, 2026-11-10):** las horas del mes son los **días naturales
del mes × 8**, y esa es la base del FTE: «configurar cada mes con un total de
horas según el número de días que tenga el mes, por 8 horas diarias» ·
«podemos poner esto como base para el cálculo del FTE». 2027: ene 248, feb 224,
abr 240 … total 2,920.

Reemplaza a la base fija de 240 (30 × 8) del 2026-08-14. De esa regla sigue en
pie todo lo demás: el mes se trabaja completo (el día libre semanal ya está
adentro), vacaciones e incapacidad sustituyen horas, las extras van por encima.
"""
from decimal import Decimal

import pytest

from app.engine import jornada as j


@pytest.mark.parametrize("anio,mes,horas", [
    (2027, 1, 248), (2027, 2, 224), (2027, 3, 248), (2027, 4, 240),
    (2027, 5, 248), (2027, 6, 240), (2027, 7, 248), (2027, 8, 248),
    (2027, 9, 240), (2027, 10, 248), (2027, 11, 240), (2027, 12, 248),
])
def test_cada_mes_son_sus_dias_por_8(anio, mes, horas):
    """La tabla del owner, mes por mes."""
    assert j.horas_del_mes(anio, mes) == Decimal(horas)


def test_el_anio_2027_suma_2920():
    """365 días × 8. El total de la tabla del owner."""
    assert sum(j.horas_del_mes(2027, m) for m in range(1, 13)) == Decimal("2920")


def test_febrero_bisiesto_da_232():
    assert j.horas_del_mes(2028, 2) == Decimal("232")


def test_ya_no_hay_un_240_fijo():
    """Que nadie vuelva a dividir por una constante: el mes sale del calendario."""
    assert not hasattr(j, "HORAS_MES")
    assert j.HORAS_POR_DIA == Decimal("8")


def test_media_jornada_cierra_en_la_mitad():
    assert j.horas_del_mes(2027, 1, Decimal("0.5")) == Decimal("124")
    assert j.horas_del_mes(2027, 4, Decimal("0.5")) == Decimal("120")


def test_una_posicion_completa_cierra():
    """El caso normal: un mes de 31 días son 248 regulares."""
    cierra, dif = j.cierra_la_jornada({"9980": 248}, 2027, 1)
    assert cierra and dif == 0


def test_240_en_un_mes_de_31_dias_no_cierra():
    """Con la regla vieja cerraba; ahora faltan 8 horas, un día entero."""
    cierra, dif = j.cierra_la_jornada({"9980": 240}, 2027, 1)
    assert not cierra and dif == Decimal("-8")


def test_febrero_cierra_en_224():
    assert j.cierra_la_jornada({"9980": 224}, 2027, 2)[0]


def test_las_vacaciones_y_la_incapacidad_reemplazan_horas_regulares():
    """No se suman ENCIMA del mes: sustituyen horas que no se trabajaron."""
    cierra, dif = j.cierra_la_jornada({"9980": 180, "9985": 40, "9986": 20}, 2027, 4)
    assert cierra and dif == 0


def test_las_extras_van_POR_ENCIMA_del_mes():
    """⚠️ «Las extras y los días libres laborados es otra cosa» (owner)."""
    cierra, dif = j.cierra_la_jornada({"9980": 248, "9981": 20}, 2027, 1)
    assert cierra and dif == 0
    for extra in j.CUENTAS_SOBRE_LA_JORNADA:
        assert extra not in j.CUENTAS_DE_LA_JORNADA


def test_las_tres_de_encima_son_extras_dia_libre_y_feriado():
    assert set(j.CUENTAS_SOBRE_LA_JORNADA) == {"9981", "9982", "9983"}


def test_una_posicion_que_no_cierra_se_avisa():
    """Faltan 40 horas: o el FTE está mal, o alguien no cargó las vacaciones."""
    cierra, dif = j.cierra_la_jornada({"9980": 200}, 2027, 4)
    assert not cierra
    assert dif == Decimal("-40")


def test_el_dia_libre_laborado_va_por_encima():
    cierra, _ = j.cierra_la_jornada({"9980": 240, "9982": 8}, 2027, 4)
    assert cierra, "informar un día libre laborado no puede romper el cierre"


def test_el_fte_sale_de_las_horas_del_calendario():
    """FTE = horas regulares ÷ (días del mes × 8). 248 en enero y 224 en febrero
    son los dos un FTE completo."""
    assert j.fte_desde_horas(248, 2027, 1) == Decimal("1")
    assert j.fte_desde_horas(224, 2027, 2) == Decimal("1")
    assert j.fte_desde_horas(120, 2027, 4) == Decimal("0.5")


def test_el_redondeo_no_dispara_el_aviso():
    """Media jornada de tolerancia (4 horas)."""
    assert j.cierra_la_jornada({"9980": Decimal("244")}, 2027, 1)[0]
    assert j.cierra_la_jornada({"9980": Decimal("252")}, 2027, 1)[0]
    assert not j.cierra_la_jornada({"9980": Decimal("238")}, 2027, 1)[0]


@pytest.mark.parametrize("fte,horas", [(1, 248), ("0.5", 124), ("0.25", 62)])
def test_el_cierre_respeta_el_fte(fte, horas):
    assert j.cierra_la_jornada({"9980": horas}, 2027, 1, fte)[0]


# ─── La 9979: la base guardada en una cuenta (owner, 2026-11-10) ─────────────

def test_la_base_vive_en_la_9979():
    assert j.CUENTA_BASE == "9979"
    from app.seed_stats import leer_catalogo
    c = {x["code"]: x for x in leer_catalogo()}["9979"]
    assert c["dims"] == [] and c["unidad"] == "hours" and c["agrega"] == "SUM"


def test_sin_valor_cargado_la_base_es_el_calendario():
    b = j.bases_del_anio(2027)
    assert b[0] == Decimal("248") and b[1] == Decimal("224") and sum(b) == Decimal("2920")


def test_lo_cargado_en_la_9979_manda():
    b = j.bases_del_anio(2027, {1: 240, 7: Decimal("200")})
    assert b[0] == Decimal("240") and b[6] == Decimal("200")
    assert b[1] == Decimal("224")        # febrero sin dato: calendario


def test_un_cero_en_la_9979_no_vale():
    """Una jornada de 0 horas haría infinito el FTE: el mes cerrado se dice con FTE 0."""
    assert j.bases_del_anio(2027, {10: 0})[9] == Decimal("248")


def test_el_cierre_y_el_fte_usan_la_base_cargada():
    assert j.cierra_la_jornada({"9980": 240}, 2027, 1, base=240)[0]
    assert not j.cierra_la_jornada({"9980": 240}, 2027, 1)[0]
    assert j.fte_desde_horas(120, 2027, 1, base=240) == Decimal("0.5")
