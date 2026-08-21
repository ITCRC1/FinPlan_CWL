# -*- coding: utf-8 -*-
"""Capital Reserve: el % es un driver, no la verdad — mismo patrón que
Management Fees (`test_honorarios_administracion.py`).

Pendiente en `docs/PENDIENTES.md` (B7 residual): *"Lo que se escriba en
`CAPITAL_RESERVE` duplica el driver de Management Fees."* **Medido: no hay
duplicación en ningún lado.** `calculate_budget_pl_from_mapping` mezcla
`extra_seeds` (el checkbook manual, incluido lo que suba el Excel de
`nonop_excel.py`) DENTRO de `seeds` primero, y el % de Capital Reserve —si
está configurado— **reemplaza** esa llave con `seeds["CAPITAL_RESERVE"] =
total_rev × pct`, una asignación, no una suma. Verificado leyendo
`pl_engine.py` línea por línea.

Lo que SÍ es real, y no estaba avisado en ningún lado: con el % configurado,
**lo que se tipee en la hoja Capital Reserve del Excel se descarta en
silencio** — no se pierde en el sentido de B7 (la plantilla no lo tira al
importar), se pierde DESPUÉS, en el cálculo. Se agregó el aviso en la propia
hoja (`nonop_excel.py`); esta prueba fija que el mecanismo sigue siendo
reemplazo y no suma, para que nadie lo "corrija" hacia una suma creyendo la
nota vieja.
"""
from decimal import Decimal

from app.engine.pl_engine import ManualInputs, calculate_budget_pl_from_mapping

REPORT_LINES = [
    {"display_order": 10, "line_code": "REV_ROOMS", "line_name": "Rooms",
     "section": "REVENUES", "line_type": "MAPPED", "active": True},
    {"display_order": 30, "line_code": "TOTAL_REVENUES", "line_name": "Total",
     "section": "REVENUES", "line_type": "CALCULATED",
     "calculation_logic": "SUM(REV_*)", "active": True},
    {"display_order": 90, "line_code": "CAPITAL_RESERVE", "line_name": "Capital Reserve",
     "section": "CAPITAL", "line_type": "MAPPED", "active": True},
    {"display_order": 91, "line_code": "LARGE_CAPEX", "line_name": "Large Capex",
     "section": "CAPITAL", "line_type": "MAPPED", "active": True},
]
REVENUE = {"rooms": Decimal("1000000")}


def _pl(manual: ManualInputs, extra=None) -> dict:
    lines = calculate_budget_pl_from_mapping(
        [], [], REPORT_LINES, revenue_by_line=REVENUE, manual=manual,
        extra_seeds=extra,
    )
    return {l.line_code: l.amount_usd for l in lines}


def test_con_porcentaje_el_porcentaje_gana_y_no_se_suma_lo_digitado():
    """El caso del pendiente: alguien tipeó $12.345 en la hoja Excel Y el %
    de Capital Reserve está configurado en 4%. El resultado tiene que ser
    SOLO el 4% del ingreso — nunca $12.345 + 4%."""
    v = _pl(ManualInputs(capital_reserve_pct=Decimal("0.04")),
            extra={"CAPITAL_RESERVE": Decimal("12345")})
    assert v["CAPITAL_RESERVE"] == Decimal("40000")


def test_sin_porcentaje_respeta_lo_digitado():
    """Sin % configurado, la hoja Excel SÍ es la fuente — nada la reemplaza."""
    v = _pl(ManualInputs(), extra={"CAPITAL_RESERVE": Decimal("12345")})
    assert v["CAPITAL_RESERVE"] == Decimal("12345")


def test_large_capex_no_tiene_driver_y_nunca_se_pisa():
    """A diferencia de Capital Reserve, Large Capex no tiene formula de %:
    la hoja Excel es SIEMPRE la fuente, con o sin nada configurado."""
    v = _pl(ManualInputs(capital_reserve_pct=Decimal("0.04")),
            extra={"LARGE_CAPEX": Decimal("99999")})
    assert v["LARGE_CAPEX"] == Decimal("99999")
