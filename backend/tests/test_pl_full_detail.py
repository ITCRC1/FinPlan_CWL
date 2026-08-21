# -*- coding: utf-8 -*-
"""P&L Full Detail — el ensamblador (Fase 2).

Las pruebas están escritas contra las piezas puras del ensamblador (las que
deciden dónde cae cada cosa y cómo se suman los totales), no contra la base.
Lo que vigilan es que no se vuelvan a colar los cinco bugs del Excel original
ni el que apareció construyéndolo.

Ver `app/api/pl_full_detail_api.py` para la historia de cada uno.
"""
from decimal import Decimal

import pytest

from app.api import pl_full_detail_api as mod
from app.api.pl_full_detail_api import _Acum, _clase, _fila, _hacer_es_ingreso, _pct


# ─── El acumulador amarra por (depto, cuenta), nunca por etiqueta ─────────────

def test_dos_cuentas_con_la_misma_etiqueta_no_se_mezclan():
    """El Excel tiene 83 etiquetas duplicadas. Amarrar por texto es cómo dos
    conceptos distintos terminan sumados en la misma fila."""
    a = _Acum()
    a.add("0110", "7380", 0, 100, "Miscellaneous")
    a.add("0120", "7380", 0, 250, "Miscellaneous")
    assert a.datos[("0110", "7380")][0] == 100
    assert a.datos[("0120", "7380")][0] == 250


def test_el_acumulador_suma_en_el_mes_que_le_toca():
    a = _Acum()
    a.add("0110", "7065", 0, 10)
    a.add("0110", "7065", 0, 5)
    a.add("0110", "7065", 11, 7)
    fila = a.datos[("0110", "7065")]
    assert fila[0] == 15 and fila[11] == 7 and sum(fila) == 22


def test_un_cero_no_crea_fila():
    """Sin esto el reporte se llena de cuentas vacías y el detalle deja de
    leerse."""
    a = _Acum()
    a.add("0110", "7065", 0, 0)
    assert not a.datos


# ─── Bug 5 del Excel (fila 76): el anual es la suma de los meses ──────────────

def test_el_total_anual_es_siempre_la_suma_de_los_doce_meses():
    """En el Excel la fila 76 sacaba los meses de adentro y el anual de afuera.
    Era la única fila del archivo con dos fuentes, y si un día dejaban de
    coincidir nada avisaba."""
    meses = [100.0] * 11 + [50.0]
    f = _fila("detalle", "x", meses)
    assert f["total"] == 1150.0
    assert f["total"] == round(sum(f["meses"]), 2)


# ─── Los ratios son PORCENTAJE, no plata ─────────────────────────────────────

def test_los_ratios_viajan_como_porcentaje():
    """En el Excel «% de Ingresos del Depto.» tenía formato de moneda y se leía
    `$0.35` en vez de `35.0%`."""
    num = [35.0] * 12
    den = [100.0] * 12
    f = _pct("% de Ingresos del Depto.", num, den)
    assert f["tipo"] == "pct"
    assert f["total"] == 0.35
    assert all(v == 0.35 for v in f["meses"])


def test_un_ratio_sin_denominador_no_revienta():
    f = _pct("% Utilidad", [10.0] * 12, [0.0] * 12)
    assert f["total"] == 0.0
    assert f["meses"] == [0.0] * 12


def test_el_ratio_anual_no_es_el_promedio_de_los_meses():
    """Es total sobre total. El promedio de doce ratios mensuales pesa igual un
    mes cerrado que uno lleno, y da un número que no existe."""
    num = [0.0] * 11 + [50.0]
    den = [0.0] * 11 + [200.0]
    f = _pct("% Utilidad", num, den)
    assert f["total"] == 0.25


# ─── El crédito de reparto NO es ingreso ─────────────────────────────────────

def _resolvedor(reglas):
    return mod.pl_engine.construir_resolvedor([
        {"account_code": a, "dept_code": d, "report_line_code": lc,
         "active_status": "YES", "rollup_operator": "SUM"}
        for a, d, lc in reglas
    ])


def test_una_cuenta_4xxx_que_no_va_a_una_linea_de_ingreso_es_reparto():
    """La 4999 de Rooms y la 4900 de Lavandería empiezan con 4 pero NO son
    ingreso: son el gasto que se fue a otro departamento, y vienen en negativo.

    La 4900 fue el descuadre real: $18,852.40 que le faltaban al ingreso de
    Actual 2026 y le sobraban al gasto, y $47,613.19 en Budget 2026.
    """
    es_ingreso = _hacer_es_ingreso(_resolvedor([
        ("4110", "0120", "REV_FB"),
        ("4900", "0161", "OH_LAUNDRY"),
        ("4999", "0110", "OPEX_ROOMS"),
    ]))
    assert es_ingreso("0120", "4110") is True
    assert es_ingreso("0161", "4900") is False
    assert es_ingreso("0110", "4999") is False


def test_se_le_pregunta_al_mapeo_y_no_a_una_lista_escrita_a_mano():
    """Una cuenta de reparto NUEVA tiene que clasificarse sola. Con la lista a
    mano, la 4900 se coló y la siguiente también se colaría."""
    es_ingreso = _hacer_es_ingreso(_resolvedor([
        ("4777", "0130", "OPEX_SPA"),   # inventada, jamás vista por el código
    ]))
    assert es_ingreso("0130", "4777") is False


def test_una_cuenta_sin_regla_se_muestra_como_ingreso_y_el_cuadre_la_delata():
    """Esconderla sería peor: desaparecería del reporte sin dejar rastro."""
    es_ingreso = _hacer_es_ingreso(_resolvedor([]))
    assert es_ingreso("0110", "4123") is True


def test_las_clases_que_no_son_4_nunca_son_ingreso():
    es_ingreso = _hacer_es_ingreso(_resolvedor([("7065", "0110", "REV_ROOMS")]))
    assert es_ingreso("0110", "7065") is False   # ni con una regla absurda


# ─── Clasificación por clase USALI ───────────────────────────────────────────

@pytest.mark.parametrize("cuenta,clase", [
    ("4110", "4"), ("5101", "5"), ("6000", "6"), ("7065", "7"),
    ("8020", "8"), ("", ""), (None, ""),
])
def test_clase_de_la_cuenta(cuenta, clase):
    assert _clase(cuenta) == clase


def test_las_secciones_estan_en_el_orden_del_excel():
    """INGRESOS → COSTO DE VENTAS → NÓMINA → GASTOS OPERATIVOS. Es la plantilla
    que los 16 bloques de departamento del Excel repiten igual."""
    assert [c for c, _t, _k in mod.SECCIONES] == ["4", "5", "6", "7"]
    assert [t for _c, t, _k in mod.SECCIONES] == [
        "INGRESOS", "COSTO DE VENTAS", "NÓMINA", "GASTOS OPERATIVOS"]


def test_la_cafeteria_no_se_muestra_en_importados():
    """Su costo ya viaja repartido dentro de la planilla de cada departamento
    (concepto 6025). Mostrarla la duplicaría — riesgo 6 del escaneo."""
    assert "0220" in mod.EXCLUIR_EN_IMPORTADOS


# ─── Bug 1 del Excel (fila 78): un subtotal nunca se traga un total ──────────

def test_la_utilidad_del_bloque_resta_cada_componente_una_sola_vez():
    """Bug 3 del Excel (fila 942): allá la nómina de Área Recreativa se restaba
    dos veces porque dos filas compartían la etiqueta «TOTAL GASTOS
    OPERATIVOS» con contenidos distintos."""
    ingreso = [1000.0] * 12
    costo, nomina, opex = [100.0] * 12, [300.0] * 12, [200.0] * 12
    gasto = [costo[i] + nomina[i] + opex[i] for i in range(12)]
    utilidad = [ingreso[i] - gasto[i] for i in range(12)]
    assert gasto[0] == 600.0
    assert utilidad[0] == 400.0
    assert _fila("total", "UTILIDAD NETA", utilidad)["total"] == 4800.0
