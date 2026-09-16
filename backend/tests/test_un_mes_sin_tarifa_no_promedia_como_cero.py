# -*- coding: utf-8 -*-
"""Un mes sin ADR cargado no arrastra el promedio hacia abajo.

Owner, 2026-09-16, mirando el ACTUAL 2026: «revisa por que no hay rate en junio
y julio». Esos dos meses tienen noches vendidas y la tarifa en blanco.

`adr = 0` con noches vendidas NO significa «se vendio a cero» — significa que
no se sabe a cuanto. Puesto en el denominador del promedio ponderado, esas 395
noches (11.3% del YTD) bajaban el ADR del periodo de $587.89 a $521.39: un
numero que no es de nadie, sin error y sin aviso.

Mismo criterio que el owner ya habia pedido para los socios del Club: se
promedian los meses que TIENEN el dato.
"""
from app.api.pl_api import _aggregate_selected


class _L:
    """Lo minimo que `_aggregate_selected` le pide a una linea."""
    def __init__(self, code, amt):
        self.line_code, self.amount_usd = code, amt
        self.line_name, self.section, self.dept_code = code, "REVENUES", ""
        self.is_calculated = False


def _mes(month, occ, adr, rooms_rev=0.0):
    return {"month": month,
            "kpis": {"rooms_available": 930, "rooms_occupied": occ,
                     "guests": 0.0, "adr": adr},
            "lines": [_L("REV_ROOMS", rooms_rev), _L("TOTAL_REVENUES", rooms_rev)]}


def test_el_mes_sin_tarifa_queda_fuera_del_promedio():
    sel = [_mes(1, 100, 600.0), _mes(2, 100, 400.0), _mes(3, 100, 0.0)]
    adr = _aggregate_selected(sel, lo_subido_manda=True)["kpis"]["adr"]
    # Promedio de los DOS meses con tarifa. Con el cero adentro daria 333.33.
    assert round(adr, 2) == 500.00, adr


def test_las_noches_del_mes_sin_tarifa_igual_se_cuentan():
    """Solo el ADR ignora ese mes. La ocupacion no: las noches se vendieron."""
    sel = [_mes(1, 100, 600.0), _mes(2, 100, 0.0)]
    k = _aggregate_selected(sel, lo_subido_manda=True)["kpis"]
    assert k["rooms_occupied"] == 200
    assert round(k["adr"], 2) == 600.00


def test_sin_ninguna_tarifa_se_deriva_de_la_linea():
    """Si NINGUN mes trae tarifa no hay promedio que sacar: se deriva del
    ingreso, que es el comportamiento que ya existia."""
    sel = [_mes(1, 100, 0.0, rooms_rev=50_000.0)]
    adr = _aggregate_selected(sel, lo_subido_manda=True)["kpis"]["adr"]
    assert round(adr, 2) == 500.00, adr
