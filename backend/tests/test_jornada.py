# -*- coding: utf-8 -*-
"""La jornada y la identidad de las horas.

**La regla del owner (2026-08-14):** «Se trabajan 8 horas por día, y un día libre
a la semana, en una base de 30 días naturales» — y después, corrigiendo la
lectura obvia: «al final, las horas regulares, más horas tomadas en vacaciones,
horas incapacidad, más las horas extras, debe dar **240 horas**».

De «un día libre a la semana» uno deduciría 25.71 días trabajados y 205.71 horas.
El owner cierra en 240, que son los 30 días completos: la base es el mes natural
entero y el día libre ya está adentro. Estas pruebas fijan esa lectura para que
nadie la vuelva a deducir mal.
"""
from decimal import Decimal

import pytest

from app.engine import jornada as j


def test_el_mes_son_240_horas():
    """30 días × 8 horas. El número que dio el owner, no uno derivado de restar
    los días libres — esa fue justamente la deducción equivocada."""
    assert j.HORAS_MES == Decimal("240")


def test_media_jornada_cierra_en_la_mitad():
    assert j.horas_del_mes(Decimal("0.5")) == Decimal("120")
    assert j.horas_del_mes(1) == Decimal("240")


def test_una_posicion_completa_cierra():
    """El caso normal: 240 regulares, nada más."""
    cierra, dif = j.cierra_la_jornada({"9980": 240})
    assert cierra and dif == 0


def test_las_vacaciones_y_la_incapacidad_reemplazan_horas_regulares():
    """No se suman ENCIMA del mes: sustituyen horas que no se trabajaron. Si se
    sumaran encima, cualquiera con vacaciones daría más de 240 y el aviso
    saltaría para todo el mundo."""
    cierra, dif = j.cierra_la_jornada({"9980": 180, "9985": 40, "9986": 20})
    assert cierra and dif == 0


def test_las_extras_van_POR_ENCIMA_del_mes():
    """⚠️ «Las extras y los días libres laborados es otra cosa» (owner).

    Son tiempo trabajado ADEMÁS del mes, pagado recargado. Si entraran en la
    identidad, quien trabaja extras «no cerraría» — cuando es justo al revés:
    trabajó más. Un mes completo con 20 horas extras cierra igual.
    """
    cierra, dif = j.cierra_la_jornada({"9980": 240, "9981": 20})
    assert cierra and dif == 0
    for extra in j.CUENTAS_SOBRE_LA_JORNADA:
        assert extra not in j.CUENTAS_DE_LA_JORNADA


def test_las_tres_de_encima_son_extras_dia_libre_y_feriado():
    assert set(j.CUENTAS_SOBRE_LA_JORNADA) == {"9981", "9982", "9983"}


def test_una_posicion_que_no_cierra_se_avisa():
    """Faltan 40 horas: o el FTE está mal, o alguien no cargó las vacaciones."""
    cierra, dif = j.cierra_la_jornada({"9980": 200})
    assert not cierra
    assert dif == Decimal("-40")


def test_el_dia_libre_laborado_va_por_encima():
    """El día libre semanal ya vive dentro de los 30 días de la base. Lo que se
    cuenta en la 9982 es el día libre que SE TRABAJÓ, y eso es tiempo de más."""
    cierra, _ = j.cierra_la_jornada({"9980": 240, "9982": 8})
    assert cierra, "informar un día libre laborado no puede romper el cierre"


def test_el_fte_sale_de_las_horas_regulares():
    """La fórmula de CLAUDE.md §18.4, que hasta hoy no tenía divisor."""
    assert j.fte_desde_horas(240) == Decimal("1")
    assert j.fte_desde_horas(120) == Decimal("0.5")


def test_el_redondeo_no_dispara_el_aviso():
    """Media jornada de tolerancia: un mes que cierra en 236 o en 244 no es un
    error de dato."""
    assert j.cierra_la_jornada({"9980": Decimal("236")})[0]
    assert j.cierra_la_jornada({"9980": Decimal("244")})[0]
    assert not j.cierra_la_jornada({"9980": Decimal("230")})[0]


@pytest.mark.parametrize("fte,horas", [(1, 240), ("0.5", 120), ("0.25", 60)])
def test_el_cierre_respeta_el_fte(fte, horas):
    assert j.cierra_la_jornada({"9980": horas}, fte)[0]
