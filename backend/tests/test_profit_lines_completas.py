# -*- coding: utf-8 -*-
"""
NINGÚN DEPARTAMENTO PUEDE QUEDAR FUERA DEL RESULTADO.

`OPERATING_PROFIT = SUM(PROFIT_*)`, así que un departamento con línea de ingreso
o de gasto pero SIN su línea de profit desaparece del GOP para abajo — los
totales de arriba lo muestran, el resultado no. Así estuvo Club Madresal: sus
$263,340 de planilla inflaban la utilidad porque el gasto nunca se restaba.

La comprobación es aritmética y no depende de qué departamentos existan:
    OPERATING_PROFIT tiene que ser igual a TOTAL_REVENUES - TOTAL_OPERATING_EXPENSES
Si alguien agrega un departamento y olvida su PROFIT_*, esto falla.
"""
from decimal import Decimal

import pytest

from app.engine.pl_engine import _eval_calc_logic


def _lineas():
    """La estructura del reporte tal como queda con la migración 094.

    Área Recreativa ya no es un departamento operativo: su ingreso se queda
    arriba (`REV_AREC`) y su costo baja al overhead (`OH_AREC`), así que su
    profit es el ingreso a secas — el mismo patrón del Sustainability Fee.
    """
    return [
        # ingresos
        (10, "REV_ROOMS", "MAPPED", ""),
        (11, "REV_FB", "MAPPED", ""),
        (12, "REV_CLUB", "MAPPED", ""),
        (13, "REV_AREC", "MAPPED", ""),
        (14, "REV_SUSTAINABILITY", "MAPPED", ""),
        (15, "REV_MISC_OTHER", "MAPPED", ""),
        (30, "TOTAL_REVENUES", "CALCULATED", "SUM(REV_*)"),
        # gastos departamentales
        (40, "OPEX_ROOMS", "MAPPED", ""),
        (41, "OPEX_FB", "MAPPED", ""),
        (42, "OPEX_CLUB", "MAPPED", ""),
        (44, "OPEX_MISCELLANEOUS", "MAPPED", ""),
        (46, "TOTAL_OPERATING_EXPENSES", "CALCULATED", "SUM(OPEX_*)"),
        # profit por departamento
        (51, "PROFIT_ROOMS", "CALCULATED", "REV_ROOMS - OPEX_ROOMS"),
        (52, "PROFIT_FB", "CALCULATED", "REV_FB - OPEX_FB"),
        (59, "PROFIT_SUSTAINABILITY", "CALCULATED", "REV_SUSTAINABILITY"),
        (60, "PROFIT_MISC_OTHER", "CALCULATED", "REV_MISC_OTHER - OPEX_MISCELLANEOUS"),
        (61, "PROFIT_CLUB", "CALCULATED", "REV_CLUB - OPEX_CLUB"),
        (62, "PROFIT_AREC", "CALCULATED", "REV_AREC"),
        (64, "OPERATING_PROFIT", "CALCULATED", "SUM(PROFIT_*)"),
        # overhead
        (70, "OH_ADMIN", "MAPPED", ""),
        (78, "OH_AREC", "MAPPED", ""),
        (79, "TOTAL_OVERHEAD_EXPENSES", "CALCULATED", "SUM(OH_*)"),
        (81, "TOTAL_GOP", "CALCULATED",
         "OPERATING_PROFIT - TOTAL_OVERHEAD_EXPENSES"),
    ]


def _evaluar(montos: dict, lineas=None) -> dict:
    """Evalúa en orden, igual que calculate_pl_from_mapping."""
    val = {k: Decimal(str(v)) for k, v in montos.items()}
    for _, code, tipo, formula in sorted(lineas or _lineas()):
        # ⚠️ `startswith`, no `== "CALCULATED"`. El motor calcula también las
        # `CALCULATED_REVIEW` (`pl_engine.py`: `lt in ("CALCULATED",
        # "CALCULATED_REVIEW")`), y hay tres —PROFIT_INNOCEANA,
        # PROFIT_CROWTHER_LAB y PROFIT_CLARO_HUERTA—. Tratándolas como dato,
        # esta prueba las leía en CERO y decía que el resultado no cuadraba
        # cuando sí cuadra. Un ayudante de prueba que no imita al motor
        # inventa fallas y, peor, puede tapar las de verdad.
        val[code] = (_eval_calc_logic(formula, val)
                     if str(tipo).startswith("CALCULATED")
                     else val.get(code, Decimal("0")))
    return val


# Caso real de Budget Working 2027 el día que se cargó la planilla del Club.
CWL = {"REV_ROOMS": 3560261, "REV_FB": 1066739, "REV_SUSTAINABILITY": 251082,
       "REV_CLUB": 0, "REV_AREC": 0, "REV_MISC_OTHER": 0,
       "OPEX_ROOMS": 489005, "OPEX_FB": 580604, "OPEX_CLUB": 263340,
       "OPEX_MISCELLANEOUS": 0,
       "OH_ADMIN": 812340, "OH_AREC": 41}


def test_el_resultado_cuadra_con_ingresos_menos_gastos():
    v = _evaluar(CWL)
    assert v["OPERATING_PROFIT"] == v["TOTAL_REVENUES"] - v["TOTAL_OPERATING_EXPENSES"]


def test_el_gop_cuadra_con_ingresos_menos_todos_los_gastos():
    """La identidad que ningún cambio de bloque puede romper:
    GOP = Ingresos − Gastos operativos − Overhead.
    Es la que vigila que mover un departamento de bloque no invente ni pierda
    plata (pasó con Área Recreativa, migración 094)."""
    v = _evaluar(CWL)
    assert v["TOTAL_GOP"] == (v["TOTAL_REVENUES"]
                              - v["TOTAL_OPERATING_EXPENSES"]
                              - v["TOTAL_OVERHEAD_EXPENSES"])


def test_area_recreativa_es_centro_de_costo():
    """Su costo pesa en el overhead, no en los gastos operativos, y su ingreso
    sigue contando en INGRESOS TOTALES (no se replica el Excel, que lo bota)."""
    sin = _evaluar({**CWL, "OH_AREC": 0})
    con = _evaluar(CWL)
    assert sin["TOTAL_OPERATING_EXPENSES"] == con["TOTAL_OPERATING_EXPENSES"]
    assert con["TOTAL_OVERHEAD_EXPENSES"] - sin["TOTAL_OVERHEAD_EXPENSES"] == Decimal("41")
    assert sin["TOTAL_GOP"] - con["TOTAL_GOP"] == Decimal("41")

    con_ingreso = _evaluar({**CWL, "REV_AREC": 9000})
    assert con_ingreso["TOTAL_REVENUES"] - con["TOTAL_REVENUES"] == Decimal("9000")
    assert con_ingreso["TOTAL_GOP"] - con["TOTAL_GOP"] == Decimal("9000")


def test_el_costo_del_club_si_baja_el_resultado():
    """Meter costo en el Club tiene que bajar el resultado en ese mismo monto."""
    sin = _evaluar({**CWL, "OPEX_CLUB": 0})["OPERATING_PROFIT"]
    con = _evaluar(CWL)["OPERATING_PROFIT"]
    assert sin - con == Decimal("263340")


def test_el_sustainability_fee_si_entra_al_resultado():
    sin = _evaluar({**CWL, "REV_SUSTAINABILITY": 0})["OPERATING_PROFIT"]
    con = _evaluar(CWL)["OPERATING_PROFIT"]
    assert con - sin == Decimal("251082")


def test_sustainability_y_misc_no_se_pisan():
    """Antes las dos líneas tenían la MISMA fórmula: el mismo ingreso contaba doble."""
    v = _evaluar({**CWL, "REV_MISC_OTHER": 100000, "OPEX_MISCELLANEOUS": 30000})
    assert v["PROFIT_SUSTAINABILITY"] == Decimal("251082")
    assert v["PROFIT_MISC_OTHER"] == Decimal("70000")


@pytest.mark.parametrize("dept", ["CLUB", "AREC"])
def test_cada_departamento_tiene_su_linea_de_profit(dept):
    codes = {c for _, c, _, _ in _lineas()}
    assert f"PROFIT_{dept}" in codes, (
        f"El departamento {dept} tiene REV_/OPEX_ pero no PROFIT_: "
        f"su plata no llegaría al GOP")


def test_el_motor_pone_a_area_recreativa_en_el_overhead():
    """El otro lado del mismo cambio: el motor viejo (constantes de pl_engine)
    tiene que decir lo mismo que el reporte de la base."""
    from app.engine import pl_engine as e
    assert "AREC" in e.OVERHEAD_DEPT_GROUPS
    assert "AREC" not in e.OPERATING_DEPT_GROUPS
    assert "AREC" in e.OVERHEAD_GROUP_ORDER
    assert "AREC" in e.REVENUE_ONLY_GROUPS      # el ingreso sí se queda arriba
    assert "AREC" in e.OPERATING_GROUP_ORDER    # …con su línea de ingreso
    e.reset_dept_catalog()
    assert e.group_for_dept("270") == "AREC"


def test_un_departamento_nuevo_sin_profit_rompe_la_prueba():
    """Prueba de la prueba: si se olvida el PROFIT_, el cuadre falla."""
    lineas = [x for x in _lineas() if x[1] != "PROFIT_CLUB"]
    v = _evaluar(CWL, lineas)
    assert v["OPERATING_PROFIT"] != v["TOTAL_REVENUES"] - v["TOTAL_OPERATING_EXPENSES"]


# ═════════════════════════════════════════════════════════════════════════════
# LAS MISMAS IDENTIDADES, CONTRA EL REPORTE DE VERDAD
#
# ⚠️ Todo lo de arriba corre sobre `_lineas()`, una estructura ESCRITA A MANO.
# Es útil —permite montos controlados— pero **nunca abre `mapping_pl.json`**, así
# que se quedó congelada: todavía dice `SUM(OPEX_*)` sin `+ SUM(COS_*)` y
# `PROFIT_FB = REV_FB - OPEX_FB` sin sus tres líneas de costo.
#
# O sea que el archivo cuyo docstring promete «si alguien agrega un departamento
# y olvida su PROFIT_*, esto falla» seguiría en verde aunque alguien borrara
# `+ SUM(COS_*)` del seed — que es exactamente el desastre de $664,928 que la
# separación del costo de ventas quiso blindar (2026-08-14).
#
# Lo de abajo corre las MISMAS identidades sobre el reporte real.
# ═════════════════════════════════════════════════════════════════════════════
import json
import pathlib

SEED = pathlib.Path(__file__).resolve().parents[1] / "app" / "seed_data" / "mapping_pl.json"


def _reporte_real():
    """Las líneas del reporte vigente, en el formato de `_lineas()`."""
    cfg = json.loads(SEED.read_text(encoding="utf-8"))["report_line_config"]
    return [(r["display_order"], r["line_code"], r.get("line_type", "MAPPED"),
             r.get("calculation_logic") or "")
            for r in cfg if r.get("active", True) and r.get("line_type") != "KPI"]


def _montos_sinteticos() -> dict:
    """$1,000 en CADA línea que recibe cuentas. Así ninguna puede quedar en cero
    por casualidad y taparse a sí misma."""
    d = json.loads(SEED.read_text(encoding="utf-8"))
    con_cuentas = {r["report_line_code"] for r in d["account_mapping"]
                   if r.get("active_status") == "YES"}
    tipos = {r["line_code"]: r.get("line_type", "MAPPED")
             for r in d["report_line_config"]}
    return {c: 1000 for c in con_cuentas
            if str(tipos.get(c, "MAPPED")).startswith("MAPPED")}


def test_real_el_resultado_cuadra_con_ingresos_menos_gastos():
    """La identidad central, contra el reporte de verdad y con TODAS las líneas
    con dato. Si una `COS_*` se cae de `TOTAL_OPERATING_EXPENSES` o de su
    `PROFIT_*`, esto revienta."""
    v = _evaluar(_montos_sinteticos(), _reporte_real())
    assert v["OPERATING_PROFIT"] == v["TOTAL_REVENUES"] - v["TOTAL_OPERATING_EXPENSES"], (
        f"OPERATING_PROFIT={v['OPERATING_PROFIT']} pero ingresos menos gastos dan "
        f"{v['TOTAL_REVENUES'] - v['TOTAL_OPERATING_EXPENSES']}. Hay una línea que "
        "entra en un lado y no en el otro."
    )


def test_real_el_gop_cuadra():
    v = _evaluar(_montos_sinteticos(), _reporte_real())
    assert v["TOTAL_GOP"] == (v["TOTAL_REVENUES"] - v["TOTAL_OPERATING_EXPENSES"]
                              - v["TOTAL_OVERHEAD_EXPENSES"])


def test_real_toda_linea_con_cuentas_llega_a_algun_total():
    """⚠️ La propiedad que faltaba en TODO el proyecto.

    Una línea con cuentas detrás que ningún total suma es plata que desaparece
    del P&L sin que nada avise. Se comprueba MOVIÉNDOLA: se le suman $1,000 y
    los totales tienen que reaccionar.

    Esto es lo que hace irrelevante que alguien invente un prefijo nuevo: no
    depende de que la prueba conozca el prefijo.
    """
    lineas = _reporte_real()
    base = _montos_sinteticos()
    v0 = _evaluar(base, lineas)
    huerfanas = []
    for code in sorted(base):
        v1 = _evaluar({**base, code: base[code] + 1000}, lineas)
        # La cascada COMPLETA, hasta el neto: las líneas de abajo del GOP
        # —renta, intereses, depreciación, impuesto— no mueven los totales
        # operativos y no por eso son huérfanas.
        movio = any(v1[t] != v0[t] for t in
                    ("TOTAL_REVENUES", "TOTAL_OPERATING_EXPENSES",
                     "TOTAL_OVERHEAD_EXPENSES", "TOTAL_GOP", "OPERATING_PROFIT",
                     "EBITDA_BEFORE_CAPITAL", "EBITDA_AFTER_CAPITAL", "EBT",
                     "NET_PROFIT"))
        if not movio:
            huerfanas.append(code)
    assert not huerfanas, (
        f"estas líneas tienen cuentas y NINGÚN total las suma: {huerfanas}. "
        "Su plata no aparece en el P&L."
    )


def test_real_cada_departamento_operativo_tiene_su_profit():
    """La versión NO circular. La de arriba saca los códigos del mismo fixture
    que valida, así que no puede fallar nunca."""
    codes = {c for _, c, _, _ in _reporte_real()}
    faltan = []
    for c in codes:
        if not c.startswith("REV_"):
            continue
        suf = c[len("REV_"):]
        # Las líneas hijas (`REV_FB_BEV`) cuelgan del profit de su padre.
        if any(f"PROFIT_{suf}" == p or suf.startswith(p[len("PROFIT_"):] + "_")
               for p in codes if p.startswith("PROFIT_")):
            continue
        faltan.append(c)
    assert not faltan, (
        f"líneas de ingreso sin línea de utilidad: {faltan}. Su ingreso sale en "
        "el total de arriba y nunca llega al GOP."
    )


def test_real_las_formulas_de_los_totales_no_perdieron_su_prefijo():
    """El caso concreto que el fixture sintético dejó de ver."""
    por = {c: f for _, c, _, f in _reporte_real()}
    assert "SUM(COS_*)" in por["TOTAL_OPERATING_EXPENSES"]
    assert "SUM(COH_*)" in por["TOTAL_OVERHEAD_EXPENSES"]
