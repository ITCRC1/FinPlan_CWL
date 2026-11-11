# -*- coding: utf-8 -*-
"""Checkbook de costo de ventas para el Excel en vivo (owner, 2026-11-11).

«mete tambien el checkbook de costos de ventas». Lo que se cuida: los montos son
los GUARDADOS (los que suma el P&L, con el driver ya aplicado), la línea dice
de dónde sale su cifra, y la puerta es la misma llave de solo lectura.
"""
import pathlib
from decimal import Decimal
from types import SimpleNamespace

from app.api import consolidado_planilla_api as cp

BACK = pathlib.Path(__file__).resolve().parents[1]
FUENTE = (BACK / "app" / "api" / "consolidado_planilla_api.py").read_text(encoding="utf-8")
LIBRO = BACK / "scripts" / "cierre_mensual"


def _linea(**kw):
    base = dict(dept_code="0120", account_code="5101", account_name="FOOD COST",
                calc_mode="DRIVER", driver_type="REVENUE_LINE",
                driver_pct_or_rate=Decimal("0.28"), revenue_line_ref="FOOD", currency="USD")
    base.update(kw)
    meses = kw.pop("meses", [Decimal("100")] * 12)
    return SimpleNamespace(**base, get_month=lambda m: meses[m - 1])


def test_la_fila_trae_el_monto_guardado_y_de_donde_sale():
    f = cp.filas_costos([_linea()], {"0120": "F&B"})[0]
    assert f["meses"] == [100.0] * 12 and f["anual"] == 1200.0
    assert (f["modo"], f["driver"], f["tasa"], f["linea_ingreso"]) == ("DRIVER", "REVENUE_LINE", 0.28, "FOOD")
    assert f["dept_name"] == "F&B" and f["moneda"] == "USD"


def test_una_linea_manual_no_inventa_driver():
    f = cp.filas_costos([_linea(calc_mode="MANUAL", driver_type="", driver_pct_or_rate=None,
                                revenue_line_ref="")], {})[0]
    assert f["modo"] == "MANUAL" and f["driver"] == "" and f["tasa"] == 0.0


def test_va_con_la_llave_y_el_criterio_del_consolidado():
    i = FUENTE.index("async def consolidado_costos(")
    cuerpo = FUENTE[i:]
    assert "Depends(lector_del_consolidado)" in cuerpo
    assert "await _escenario(session, year, tipo, version)" in cuerpo
    assert "CostEntry.scenario_id == escenario.id" in cuerpo


def test_el_libro_tiene_la_pestana():
    ps1 = (LIBRO / "add_pestanas.ps1").read_text(encoding="utf-8-sig")
    assert 'm = "costos.m"' in ps1
    m = (LIBRO / "costos.m").read_text(encoding="utf-8")
    assert 'RelativePath = "api/consolidado/costos/"' in m
