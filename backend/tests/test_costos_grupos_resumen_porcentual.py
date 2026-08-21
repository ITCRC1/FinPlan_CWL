# -*- coding: utf-8 -*-
"""RESUMEN FULLY LOADED — el cuadro aprobado por la Junta.

Owner, 2026-08-20: *«quiero tener un tab así, resumido»* y después *«podés
ampliar ese summary que quede más claro»*, con su reporte **PROPUESTA DE
DESCUENTOS — COSTO FULLY LOADED TEMPORADA ALTA** (base Actual YTD abril 2026) a
la vista.

**La prueba de aceptación es su propio cuadro, al centavo.** Las fórmulas se
derivaron de esos números; reproducirlos es lo único que demuestra que el motor
hace lo mismo que él hace a mano. Si un día esto deja de dar, el motor dejó de
decir lo que la Junta aprobó.
"""
from decimal import Decimal

import inspect
import pytest

from app.engine import costos_grupos as cg

FEE_PCT = Decimal("0.03")

# Su cuadro, columna por columna:
#   concepto → (revenue, costo dept $, overhead $, fee $, utilidad $)
SU_CUADRO = {
    "ROOMS":          ("1586673.99", "275406.79", "388847.33", "47600.22", "874819.65"),
    "FB":             ("541209.61",  "346878.80", "132634.63", "16236.29",  "45459.90"),
    "SPA":            ("33229.72",    "18619.54",   "8143.63",   "996.89",   "5469.66"),
    # ⚠️ La Tienda PIERDE. Es la fila que hace falta para que el cuadro sea
    # honesto: margen −2,1% y descuento −2,2%.
    "RETAIL":         ("20807.43",    "15526.44",   "5099.29",   "624.22",   "-442.52"),
    "TOURS":          ("464224.15",  "227395.42", "113767.74", "13926.72", "109134.26"),
    "TRANSPORTATION": ("161123.82",   "79669.99",  "39486.73",  "4833.71",  "37133.39"),
}

# La banda de totales de arriba de su cuadro.
TOTAL_REVENUE = Decimal("2807268.72")
TOTAL_COSTO = Decimal("963496.98")
TOTAL_OVERHEAD = Decimal("687979.35")
TOTAL_FEE = Decimal("84218.06")
TOTAL_UTILIDAD = Decimal("1071574.33")
MARGEN_PONDERADO = Decimal("0.382")


def _armar():
    """Un mes sintético con SUS revenues y SUS costos departamentales.

    El overhead se pone como el TOTAL de su cuadro: el motor lo reparte por
    revenue, así que si el reparto está bien tiene que devolver sus seis cifras.
    """
    revenue, costo = {}, {}
    for c, (rev, cost, *_rest) in SU_CUADRO.items():
        revenue[f"REV_{c}"] = Decimal(rev)
        costo[f"OPEX_{c}"] = Decimal(cost)
    mes = cg.MesDeCostos(
        mes=1, temporada="ALTA", dias_abiertos=31,
        revenue_por_dept=revenue, costo_por_dept=costo,
        overhead_por_componente={"OH_ADMIN": TOTAL_OVERHEAD},
    )
    comp = {}
    for c in SU_CUADRO:
        comp[(c, "ingreso")] = [f"REV_{c}"]
        comp[(c, "propio")] = [f"OPEX_{c}"]
    return [mes], comp


def _correr():
    meses, comp = _armar()
    return cg.resumen_fully_loaded(meses, comp,
                                   {"management_fee_pct": str(FEE_PCT)},
                                   list(SU_CUADRO))


def _centavo(v: Decimal) -> Decimal:
    return round(v, 2)


# ── La prueba de aceptación ──────────────────────────────────────────────────

@pytest.mark.parametrize("concepto", list(SU_CUADRO))
def test_reproduce_EL_CUADRO_DEL_OWNER_al_centavo(concepto):
    r = _correr()
    f = {x.concepto: x for x in r.filas}[concepto]
    rev, costo, overhead, fee, utilidad = SU_CUADRO[concepto]

    assert _centavo(f.revenue) == Decimal(rev)
    assert _centavo(f.costo_departamento) == Decimal(costo)
    # Al centavo salvo un redondeo: el overhead se reparte por proporción.
    assert abs(f.overhead - Decimal(overhead)) < Decimal("0.05"), "overhead"
    assert _centavo(f.fee) == Decimal(fee)
    assert abs(f.utilidad - Decimal(utilidad)) < Decimal("0.05"), "utilidad"


def test_reproduce_LA_BANDA_DE_TOTALES():
    r = _correr()
    assert _centavo(r.revenue) == TOTAL_REVENUE
    assert _centavo(r.costo_departamental) == TOTAL_COSTO
    assert abs(r.overhead - TOTAL_OVERHEAD) < Decimal("0.05")
    assert _centavo(r.fee) == TOTAL_FEE
    assert abs(r.utilidad - TOTAL_UTILIDAD) < Decimal("0.05")
    assert round(r.margen_ponderado, 3) == MARGEN_PONDERADO


def test_reproduce_LOS_PORCENTAJES_del_primer_cuadro():
    """El otro reporte del owner, el porcentual: costo dept %, margen y
    descuento máximo. Al décimo, que es como está impreso."""
    esperado = {          # concepto → (costo %, margen %, descuento máx %)
        "ROOMS":          (Decimal("0.174"), Decimal("0.551"), Decimal("0.568")),
        "FB":             (Decimal("0.641"), Decimal("0.084"), Decimal("0.087")),
        "SPA":            (Decimal("0.560"), Decimal("0.165"), Decimal("0.170")),
        "RETAIL":         (Decimal("0.746"), Decimal("-0.021"), Decimal("-0.022")),
        "TOURS":          (Decimal("0.490"), Decimal("0.235"), Decimal("0.242")),
        "TRANSPORTATION": (Decimal("0.494"), Decimal("0.230"), Decimal("0.238")),
    }
    filas = {f.concepto: f for f in _correr().filas}
    for concepto, (c_pct, margen, descuento) in esperado.items():
        f = filas[concepto]
        assert round(f.costo_departamento_pct, 3) == c_pct, f"costo {concepto}"
        assert round(f.margen_actual, 3) == margen, f"margen {concepto}"
        assert round(f.descuento_maximo, 3) == descuento, f"descuento {concepto}"


def test_el_COSTO_FULLY_LOADED_es_los_tres_juntos():
    """Habitaciones 44,9% · F&B 91,6% · Spa 83,5% · Tienda 102,1% · Tours 76,5%
    · Transporte 77,0% — de su cuadro."""
    esperado = {"ROOMS": "0.449", "FB": "0.916", "SPA": "0.835",
                "RETAIL": "1.021", "TOURS": "0.765", "TRANSPORTATION": "0.770"}
    for f in _correr().filas:
        assert round(f.costo_fully_loaded_pct, 3) == Decimal(esperado[f.concepto]), \
            f.concepto


# ── Lo que no se puede romper ────────────────────────────────────────────────

def test_la_TIENDA_sale_en_NEGATIVO_y_no_recortada_a_cero():
    """⚠️ Mostrar 0% diría «no podés descontar» cuando la verdad es «ya estás
    debajo del costo» — que es otra conversación, y la que hay que tener."""
    f = {x.concepto: x for x in _correr().filas}["RETAIL"]
    assert f.utilidad < 0
    assert f.margen_actual < 0
    assert f.descuento_maximo < 0
    assert f.cubre is False
    assert f.estado == cg.ESTADO_PIERDE


def test_el_ESTADO_dice_lo_mismo_que_el_cuadro():
    r = _correr()
    assert r.pierden == ["RETAIL"]
    for f in r.filas:
        if f.concepto != "RETAIL":
            assert f.estado == cg.ESTADO_OK, f.concepto


def test_la_banda_suma_LAS_FILAS_MOSTRADAS_y_no_el_PL_entero():
    """⚠️ Su «Revenue analizado» son los seis departamentos del cuadro. Poner el
    revenue total del hotel haría que el margen ponderado no cerrara contra las
    filas de abajo — y nadie sabría cuál de los dos mirar."""
    r = _correr()
    assert _centavo(r.revenue) == _centavo(
        sum((f.revenue for f in r.filas), Decimal("0")))
    assert "las filas mostradas" in inspect.getsource(cg.resumen_fully_loaded)


def test_el_OVERHEAD_va_asignado_POR_REVENUE_a_todos():
    """⚠️ **La divergencia con el motor de pisos, y es a propósito.**
    `comision_maxima` carga el overhead SÓLO a Habitaciones, porque
    cargárselo además a F&B o Tours lo contaría dos veces dentro del mismo
    paquete (§4.2). Este cuadro es para leer el P&L y fijar techos de comisión,
    no para fijar pisos — y ahí va plano, como en el reporte del owner.
    """
    r = _correr()
    assert len({f.overhead_pct for f in r.filas}) == 1
    assert round(r.overhead_pct, 4) == Decimal("0.2451")
    # Y el otro camino sigue cargándolo sólo a Habitaciones.
    assert 'if concepto == "ROOMS"' in inspect.getsource(cg.comision_maxima)


def test_el_DESCUENTO_MAXIMO_devuelve_el_fee():
    """⚠️ Si la tarifa baja, el fee —que es un % de la venta— baja con ella. Sin
    ese gross-up el techo sale más bajo que el real y se rechaza negocio que sí
    convenía."""
    for f in _correr().filas:
        assert round(f.descuento_maximo * (Decimal("1") - FEE_PCT), 8) == \
            round(f.margen_actual, 8), f.concepto


def test_un_departamento_SIN_INGRESO_no_sale_en_CERO():
    """⚠️ El porcentaje sería una división por cero disfrazada, y una fila en
    cero se lee como «no cuesta nada»."""
    meses, comp = _armar()
    comp[("CLUB", "ingreso")] = ["REV_CLUB"]        # sin monto
    comp[("CLUB", "propio")] = ["OPEX_CLUB"]
    r = cg.resumen_fully_loaded(meses, comp, {"management_fee_pct": str(FEE_PCT)})
    assert "CLUB" not in [f.concepto for f in r.filas]


def test_cada_fila_CIERRA_contra_su_revenue():
    """Costo propio + overhead + fee + utilidad = revenue. Si no cierra, alguna
    columna está midiendo contra otro denominador."""
    for f in _correr().filas:
        suma = f.costo_departamento + f.overhead + f.fee + f.utilidad
        assert abs(suma - f.revenue) < Decimal("0.01"), f.concepto
