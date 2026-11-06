# -*- coding: utf-8 -*-
"""Las cuentas del mayor por mes, y que Σ sea la utilidad cambiada de signo.

Owner, 2026-11-05: *«que lo pongas en el tab Reports al final para poder
conciliar los resultados… y que exista un proceso de validación interno para
que pegue con los reportes»*.

## Lo que estas pruebas defienden

La propiedad que hace útil al reporte: **Σ de todas las filas = −utilidad**.
Si eso vale, cada peso del mayor llegó a un renglón del P&L. Si no vale, el
reporte dice cuál se quedó afuera.

## El error que casi se comete, y que estas pruebas impiden repetir

La primera versión decidía el signo por el **primer dígito de la cuenta**:
4xxx = ingreso = crédito. Daba una diferencia de **180.817,68** contra ACTUAL
2026, que era **exactamente el doble** de 90.408,84 — y un factor dos aparece
cuando una partida se resta de un lado y se suma del otro. Eran estas:

    0161  4900  Distribución   −18.852,40  → OH_LAUNDRY    [OVERHEAD EXPENSES]
    0220  4901  Distribución   −71.556,43  → OH_CAFETERIA  [OVERHEAD EXPENSES]

Clase 4, pero **no son ingreso**: son el crédito con que el reparto deja a
lavandería y cafetería en cero. Manda la **sección del P&L**, no el dígito.
"""
from decimal import Decimal

import pytest

from app.engine import gl_por_mes as gl

ZERO = Decimal("0")


def _fila(cuenta, dept="0110", nombre="", **meses):
    base = {"dept_code": dept, "account_code": cuenta, "account_name": nombre}
    base.update({m: ZERO for m in gl.MESES})
    base.update(meses)
    return base


def _resolver(mapa):
    """`(dept, cuenta) -> (regla, cómo)` a partir de {cuenta: line_code}."""
    def r(dept, cuenta):
        lc = mapa.get(cuenta)
        if lc is None:
            return None, "DROP"
        return {"report_line_code": lc, "report_line_name": lc}, "exact"
    return r


SECCIONES = {
    "REV_ROOMS": "REVENUES",
    "REV_FB": "REVENUES",
    "COS_FB": "COST OF SALES",
    "DEPT_PAYROLL": "OPERATING EXPENSES",
    "OH_ADMIN": "OVERHEAD EXPENSES",
    "OH_LAUNDRY": "OVERHEAD EXPENSES",
    "DEPRECIATION": "DEPRECIATION",
}


# ── El signo ────────────────────────────────────────────────────────────────

def test_el_ingreso_se_muestra_negativo():
    [fila] = gl.armar_grilla(
        [_fila("4000", jan=Decimal("1000"))],
        resolver=_resolver({"4000": "REV_ROOMS"}),
        seccion_de_linea=SECCIONES.get)
    assert fila["meses"][0] == Decimal("-1000")
    assert fila["categoria"] == "REVENUE"


def test_el_gasto_se_muestra_positivo():
    [fila] = gl.armar_grilla(
        [_fila("7065", jan=Decimal("400"))],
        resolver=_resolver({"7065": "OH_ADMIN"}),
        seccion_de_linea=SECCIONES.get)
    assert fila["meses"][0] == Decimal("400")
    assert fila["categoria"] == "OPERATING_EXPENSES"


def test_una_4xxx_que_el_PL_manda_a_overhead_NO_se_invierte():
    """⚠️ El defecto exacto que costó 180.817,68 de diferencia.

    `4900 Distribución` es clase 4 y es el crédito del reparto de lavandería.
    El P&L la manda a OVERHEAD EXPENSES. Si se la invierte por empezar con 4,
    la plata se mueve de lado y la diferencia sale al DOBLE del monto.
    """
    [fila] = gl.armar_grilla(
        [_fila("4900", dept="0161", jan=Decimal("-18852.40"))],
        resolver=_resolver({"4900": "OH_LAUNDRY"}),
        seccion_de_linea=SECCIONES.get)
    assert fila["meses"][0] == Decimal("-18852.40"), "no se invierte"
    assert fila["categoria"] == "OPERATING_EXPENSES"
    assert fila["clase_discrepa"] is True, "y queda marcada para el validador"


def test_sin_mapeo_el_signo_cae_al_primer_digito():
    """Es lo único que queda — y la fila sale marcada DROP."""
    [fila] = gl.armar_grilla(
        [_fila("4000", jan=Decimal("500"))],
        resolver=_resolver({}), seccion_de_linea=SECCIONES.get)
    assert fila["meses"][0] == Decimal("-500")
    assert fila["mapeo"] == "DROP"


# ── La igualdad ─────────────────────────────────────────────────────────────

def test_la_suma_es_la_utilidad_cambiada_de_signo():
    grilla = gl.armar_grilla([
        _fila("4000", jan=Decimal("1000")),                    # ingreso
        _fila("5101", dept="0120", jan=Decimal("300")),        # costo
        _fila("6000", jan=Decimal("200")),                     # planilla
    ], resolver=_resolver({"4000": "REV_ROOMS", "5101": "COS_FB",
                           "6000": "DEPT_PAYROLL"}),
       seccion_de_linea=SECCIONES.get)
    # utilidad = 1000 − 300 − 200 = 500  →  Σ debe dar −500
    assert gl.total_del_reporte(grilla) == Decimal("-500")
    res = gl.conciliar(grilla, utilidad_pl=Decimal("500"))
    assert res["cuadra"] is True
    assert res["diferencia"] == ZERO


def test_una_cuenta_sin_mapeo_es_la_diferencia():
    """El caso real del Pre-Cierre 2026: una sola cuenta, 529,21."""
    grilla = gl.armar_grilla([
        _fila("4000", jan=Decimal("1000")),
        _fila("8050", dept="0250", nombre="OTHER OWNERS' EXPENSES",
              jan=Decimal("529.21")),
    ], resolver=_resolver({"4000": "REV_ROOMS"}),
       seccion_de_linea=SECCIONES.get)
    # El P&L no ve la 8050, así que su utilidad es 1000.
    res = gl.conciliar(grilla, utilidad_pl=Decimal("1000"))
    assert res["cuadra"] is False
    assert res["diferencia"] == Decimal("529.21")
    assert len(res["sin_mapeo"]) == 1
    assert res["sin_mapeo_total"] == Decimal("529.21")
    assert res["sin_mapeo"][0]["account_code"] == "8050"


def test_las_estadisticas_no_suman():
    """Las 9xxx son noches y kilos. Sumarlas rompería la igualdad sin avisar."""
    grilla = gl.armar_grilla([
        _fila("4000", jan=Decimal("1000")),
        _fila("9000", jan=Decimal("930")),      # noches disponibles
    ], resolver=_resolver({"4000": "REV_ROOMS"}),
       seccion_de_linea=SECCIONES.get)
    assert gl.total_del_reporte(grilla) == Decimal("-1000")
    resumen = {f["categoria"]: f for f in gl.resumen_por_categoria(grilla)}
    assert resumen["STATISTICS"]["suma"] is False
    assert resumen["NET"]["total"] == Decimal("-1000")


def test_las_estadisticas_sin_mapeo_no_se_denuncian():
    """Una 9xxx no tiene por qué llegar al P&L: no es plata."""
    grilla = gl.armar_grilla([_fila("9000", jan=Decimal("930"))],
                             resolver=_resolver({}))
    res = gl.conciliar(grilla, utilidad_pl=ZERO)
    assert res["sin_mapeo"] == []


# ── La comparación renglón por renglón ──────────────────────────────────────

def test_el_ingreso_se_compara_en_la_misma_vara():
    """La grilla lo tiene negativo y el P&L positivo.

    ⚠️ Mirar el SIGNO del número para decidir da el doble del monto cada vez
    que un gasto resulta negativo — es lo que pasó con `INCOME_TAXES`. Se mira
    la SECCIÓN.
    """
    grilla = gl.armar_grilla([_fila("4000", jan=Decimal("1000"))],
                             resolver=_resolver({"4000": "REV_ROOMS"}),
                             seccion_de_linea=SECCIONES.get)
    res = gl.conciliar(grilla, utilidad_pl=Decimal("1000"),
                       por_linea_pl={"REV_ROOMS": Decimal("1000")},
                       comparables={"REV_ROOMS"}, secciones=SECCIONES)
    [linea] = res["por_linea"]
    assert linea["gl"] == Decimal("1000"), "puesto en la vara del P&L"
    assert linea["diferencia"] == ZERO


def test_un_gasto_negativo_no_se_duplica():
    """El caso de `INCOME_TAXES`: −17.530,33 en los dos lados, diferencia 0."""
    grilla = gl.armar_grilla(
        [_fila("8060", dept="0250", jan=Decimal("-17530.33"))],
        resolver=_resolver({"8060": "DEPRECIATION"}),
        seccion_de_linea=SECCIONES.get)
    res = gl.conciliar(grilla, utilidad_pl=Decimal("17530.33"),
                       por_linea_pl={"DEPRECIATION": Decimal("-17530.33")},
                       comparables={"DEPRECIATION"}, secciones=SECCIONES)
    [linea] = res["por_linea"]
    assert linea["diferencia"] == ZERO


def test_solo_se_comparan_los_renglones_comparables():
    """⚠️ El motor emite `GOP`, `EBITDA_BEFORE` y `EBITDA_AFTER`, que **no
    están en la configuración**. Comparados salen con el mayor en cero y una
    diferencia igual a todo el renglón: ruido que tapa lo que sí importa.
    """
    grilla = gl.armar_grilla([_fila("4000", jan=Decimal("1000"))],
                             resolver=_resolver({"4000": "REV_ROOMS"}),
                             seccion_de_linea=SECCIONES.get)
    res = gl.conciliar(grilla, utilidad_pl=Decimal("1000"),
                       por_linea_pl={"REV_ROOMS": Decimal("1000"),
                                     "GOP": Decimal("-581947.24")},
                       comparables={"REV_ROOMS"}, secciones=SECCIONES)
    assert [l["pl_line_code"] for l in res["por_linea"]] == ["REV_ROOMS"]


def test_el_resumen_abre_planilla_de_opex():
    """El P&L mete las dos en OPERATING EXPENSES; el reporte las separa."""
    grilla = gl.armar_grilla([
        _fila("6000", jan=Decimal("200")),
        _fila("7065", jan=Decimal("400")),
    ], resolver=_resolver({"6000": "DEPT_PAYROLL", "7065": "OH_ADMIN"}),
       seccion_de_linea=SECCIONES.get)
    cats = {r["account_code"]: r["categoria"] for r in grilla}
    assert cats["6000"] == "PAYROLL"
    assert cats["7065"] == "OPERATING_EXPENSES"


@pytest.mark.parametrize("cuenta,esperado", [
    ("4000", "REVENUE"), ("5101", "COST_OF_SALES"), ("6000", "PAYROLL"),
    ("7065", "OPERATING_EXPENSES"), ("8040", "BELOW_GOP"), ("9000", "STATISTICS"),
])
def test_sin_seccion_la_categoria_sale_del_primer_digito(cuenta, esperado):
    assert gl.categoria_de(cuenta) == esperado
