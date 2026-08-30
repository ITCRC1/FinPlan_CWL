# -*- coding: utf-8 -*-
"""
UN CERO PUBLICADO NO ES UNA UTILIDAD DE CERO.

`OPERATING_PROFIT = SUM(PROFIT_*)`, y la plantilla del motor viejo —la que usa
`actual_pl_from_lines` para todo escenario con resumen importado— no emite ni
una linea `OPPROFIT_*`. Si el resumen tampoco trae su propio total, la utilidad
operativa salia en CERO, sin error y sin aviso.

Medido contra produccion el 2026-08-30, escenario `2026 FORECAST April`
(corte=4, `source_mode=imported`):

    month/7   OPERATING_PROFIT 0,00        con REV 235.416,28 y OPEX 141.353,77
    ytd/5     2.085.124,53   ≠ 2.169.290,10   congelado
    ytd/6     2.085.124,53   ≠ 2.206.538,07   congelado
    ytd/7     2.085.124,53   ≠ 2.300.600,60   congelado

El congelamiento es el mismo bug visto de lejos: los meses <= corte vienen del
ACTUAL enlazado —que si trae el total— y los de despues aportan cero, asi que el
acumulado se queda con lo ultimo bueno.

Lo lee la junta directiva en el Monthly Executive Summary, donde la cascada
entera (GOP, EBITDA, variaciones contra Reforecast) cuelga de esa linea.
"""
from decimal import Decimal

from app.engine.pl_engine import (actual_pl_from_lines, add_pl_aliases, get_line)


def D(x) -> Decimal:
    return Decimal(str(x))


# Julio 2026 del `2026 FORECAST April`, tal como lo publicaba produccion.
JULIO_FORECAST_APRIL = {
    "TOTAL_REVENUES": D("235416.28"),
    "TOTAL_OPEXP": D("141353.77"),
    "TOTAL_OVERHEAD": D("120000.00"),
    "GOP": D("-25937.25"),
}
UTILIDAD_ESPERADA = D("235416.28") - D("141353.77")


def test_el_resumen_sin_total_de_utilidad_ya_no_publica_cero():
    """El caso medido: el snapshot no trae la utilidad operativa."""
    pl = actual_pl_from_lines(JULIO_FORECAST_APRIL)
    assert get_line(pl, "TOTAL_OP_PROFIT") == UTILIDAD_ESPERADA
    assert get_line(pl, "TOTAL_OP_PROFIT") != D("0")


def test_la_cifra_es_la_del_reporte_del_bug():
    """94.062,52 segun el reporte, al centavo de redondeo."""
    pl = actual_pl_from_lines(JULIO_FORECAST_APRIL)
    assert abs(get_line(pl, "TOTAL_OP_PROFIT") - D("94062.52")) < D("0.02")


def test_un_cero_almacenado_tambien_se_corrige():
    """Si el resumen guardo la linea PERO en cero, es el mismo dato ausente."""
    pl = actual_pl_from_lines({**JULIO_FORECAST_APRIL, "TOTAL_OP_PROFIT": D("0")})
    assert get_line(pl, "TOTAL_OP_PROFIT") == UTILIDAD_ESPERADA


def test_la_linea_derivada_se_declara_calculada():
    """No se publica como si viniera del resumen: `is_calculated` lo dice."""
    pl = actual_pl_from_lines(JULIO_FORECAST_APRIL)
    ln = next(x for x in pl if x.line_code == "TOTAL_OP_PROFIT")
    assert ln.is_calculated is True


def test_no_pisa_la_utilidad_QUE_SI_VINO_en_el_resumen():
    """La regla que evita inventar: si el resumen trajo su total, manda el.

    Mayo 2026 del Actual real trae 87.066,00, que NO es ingresos menos gastos
    (244.654,00 - 157.588,00 = 87.066,00 — coincide, asi que se usa un valor
    distinto a proposito para probar que no se recalcula)."""
    a = {"TOTAL_REVENUES": D("244654.00"), "TOTAL_OPEXP": D("157588.00"),
         "TOTAL_OP_PROFIT": D("87000.00")}
    pl = actual_pl_from_lines(a)
    assert get_line(pl, "TOTAL_OP_PROFIT") == D("87000.00")
    ln = next(x for x in pl if x.line_code == "TOTAL_OP_PROFIT")
    assert ln.is_calculated is False


def test_sin_los_totales_de_arriba_usa_gop_mas_overhead():
    """El otro camino a la misma cifra, cuando el resumen es aun mas pobre."""
    pl = actual_pl_from_lines({"GOP": D("-25937.25"), "TOTAL_OVERHEAD": D("120000.00")})
    assert get_line(pl, "TOTAL_OP_PROFIT") == D("94062.75")


def test_un_mes_vacio_sigue_en_cero():
    """Sin plata no hay nada que derivar: cero de verdad se queda en cero."""
    pl = actual_pl_from_lines({"TOTAL_REVENUES": D("0"), "TOTAL_OPEXP": D("0")})
    assert get_line(pl, "TOTAL_OP_PROFIT") == D("0")


def test_la_utilidad_derivada_llega_al_codigo_CANONICO():
    """Lo que leen los consumidores es `OPERATING_PROFIT`, no `TOTAL_OP_PROFIT`.

    El puente es `add_pl_aliases`, que copia el valor no-cero entre los dos
    vocabularios — y que ANTES no tenia nada que copiar, porque los dos estaban
    en cero (`if val == ZERO: continue`)."""
    pl = add_pl_aliases(actual_pl_from_lines(JULIO_FORECAST_APRIL))
    assert get_line(pl, "OPERATING_PROFIT") == UTILIDAD_ESPERADA


def test_la_identidad_central_se_cumple_en_el_camino_importado():
    """La misma que vigila `test_profit_lines_completas` para el camino nuevo:
    OPERATING_PROFIT = TOTAL_REVENUES - TOTAL_OPERATING_EXPENSES."""
    pl = add_pl_aliases(actual_pl_from_lines(JULIO_FORECAST_APRIL))
    assert (get_line(pl, "OPERATING_PROFIT")
            == get_line(pl, "TOTAL_REVENUES") - get_line(pl, "TOTAL_OPEXP"))
