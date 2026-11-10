# -*- coding: utf-8 -*-
"""LOS COSTOS «% DEL INGRESO» SE CALCULAN SOBRE EL INGRESO QUE MUESTRA EL P&L.

**Lo que pasaba (auditoría del 2026-11-10, hallazgo C2).** El Budget Working
2027 lee su ingreso del checkbook (`revenue_source='checkbook'`), pero el
checkbook de costos tenía su propio cargador que armaba el ingreso con tarifas ×
ocupación SIEMPRE. Ese modelo no conoce el «5 % que no consume» ni el Retail al
1 %, así que daba $134.810 más de ingreso, y los costos con driver salían
$17.990 más altos: Food al 31,58 % del Food Revenue del P&L en vez del 30 % que
dice la línea. Recalcular no lo arreglaba —volvía a usar el mismo ingreso—, y la
fila de referencia de la pantalla mostraba ese ingreso, así que el error se
confirmaba solo.

**El arreglo:** `_load_revenue_results` delega en
`recalculate.load_revenue_results`, el mismo que usa el P&L. Probado contra la
base real con rollback: Food 314.540,20 → 298.814,21, Beverage 89.119,76 →
84.664,03, Gift Shop 18.751,66 → 20.943,38; Net Profit 335.707,39 → 348.300,39.
"""
import inspect
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.api import costs_api


def test_el_cargador_de_costos_delega_en_el_del_pl():
    src = inspect.getsource(costs_api._load_revenue_results)
    assert "load_revenue_results(db, scenario)" in src, (
        "el checkbook de costos tiene que leer el MISMO ingreso que el P&L; un "
        "cargador propio vuelve a ignorar `revenue_source`")
    assert "calculate_annual_revenue" not in src


@pytest.mark.asyncio
async def test_respeta_revenue_source(monkeypatch):
    """Lo que devuelve es lo que devuelve el cargador del P&L, en orden de mes."""
    from app.engine import recalculate

    llamado = {}

    async def falso(session, scenario):
        llamado["scenario"] = scenario
        return {2: SimpleNamespace(month=2), 1: SimpleNamespace(month=1)}

    monkeypatch.setattr(recalculate, "load_revenue_results", falso)
    esc = SimpleNamespace(id="x", revenue_source="checkbook")
    out = await costs_api._load_revenue_results("x", esc, None)
    assert llamado["scenario"] is esc
    assert [r.month for r in out] == [1, 2]


@pytest.mark.parametrize("depto,esperado", [
    ("0120", Decimal("160")),   # food + beverage + fnb_misc
    ("0165", Decimal("7")),     # Gift Shop: solo retail, no el total del hotel
    ("0151", Decimal("7")),
    ("0140", Decimal("11")),    # Spa solo, sin retail
    ("0150", Decimal("13")),    # Tours sin Innoceana
    ("0155", Decimal("17")),
    ("0152", Decimal("19")),
    ("0999", Decimal("1000")),  # sin mapa: total del hotel, como antes
])
def test_el_margen_usa_el_ingreso_de_su_depto(depto, esperado):
    rev = SimpleNamespace(food=Decimal("100"), beverage=Decimal("50"),
                          fnb_misc=Decimal("10"), retail=Decimal("7"),
                          spa=Decimal("11"), activities=Decimal("13"),
                          innoceana=Decimal("17"), transport=Decimal("19"),
                          laundry=Decimal("23"), total_revenue=Decimal("1000"))
    assert costs_api._ingreso_del_depto(rev, depto) == esperado


def test_sin_ingreso_el_margen_es_cero():
    assert costs_api._ingreso_del_depto(None, "0120") == Decimal("0")


# ── Las 14 líneas del checkbook de ingresos ────────────────────────────────

def test_un_costo_puede_apoyarse_en_cualquier_linea_del_checkbook():
    """Antes FNB_MISC, LAUNDRY y el Club daban $0 sin aviso."""
    from app.engine.cost_calculator import _get_revenue_line
    from app.models.revenue_entry import REVENUE_LINES as LINEAS_INGRESO
    from app.models.cost_entry import REVENUE_LINES as LINEAS_COSTO
    assert set(LINEAS_COSTO) == set(LINEAS_INGRESO)
    valores = {ln.lower(): Decimal(i + 1) for i, ln in enumerate(LINEAS_INGRESO)}
    rev = SimpleNamespace(**valores)
    for ln in LINEAS_INGRESO:
        esperado = (valores["club"] + valores["club_actividad"] + valores["club_visitantes"]
                    if ln == "CLUB" else valores[ln.lower()])
        assert _get_revenue_line(rev, ln) == esperado, ln


@pytest.mark.parametrize("fn", ["get_monthly_revenue", "get_monthly_revenue_single"])
def test_los_endpoints_de_ingreso_usan_el_cargador_del_pl(fn):
    """Key Indicators y el mes suelto leen el MISMO ingreso que el P&L."""
    from app.api import revenue_api
    src = inspect.getsource(getattr(revenue_api, fn))
    assert "load_revenue_results(db, scenario)" in src
    assert "calculate_annual_revenue" not in src and "calculate_revenue(" not in src
