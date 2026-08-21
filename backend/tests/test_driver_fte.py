# -*- coding: utf-8 -*-
"""
COSTO POR FTE: monto por persona × la gente de cada mes.

La cafetería no es un % del ingreso ni un monto parejo: se come según cuánta
gente haya. Con este driver el owner pone el costo por persona y el mes se calcula
solo — y octubre, con el lodge cerrado y FTE 0, cae a cero sin que nadie tenga que
acordarse de ponerlo.
"""
from decimal import Decimal

import pytest

from app.engine.cost_calculator import calculate_cost_amount, recalculate_cost_entries
from app.models.cost_entry import CostEntry, DRIVER_TYPES


def _entry(rate="90"):
    e = CostEntry(scenario_id="s", hotel_id="CWL", dept_code="0220",
                  account_code="5700", account_name="Cafetería",
                  calc_mode="DRIVER", driver_type="FTE",
                  driver_pct_or_rate=Decimal(rate))
    for m in ("jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"):
        setattr(e, m, Decimal("0"))
    return e


def test_el_driver_existe():
    assert "FTE" in DRIVER_TYPES


def test_el_costo_del_mes_es_monto_por_persona_por_fte():
    e = _entry("90")
    assert calculate_cost_amount(e, 1, None, fte=Decimal("129")) == Decimal("11610.00")


def test_octubre_cerrado_no_cuesta():
    """FTE 0 → el mes no cuesta nada. Es el punto del driver."""
    e = _entry("90")
    assert calculate_cost_amount(e, 10, None, fte=Decimal("0")) == Decimal("0")


def test_sube_y_baja_con_la_gente():
    e = _entry("90")
    enero = calculate_cost_amount(e, 1, None, fte=Decimal("129"))
    junio = calculate_cost_amount(e, 6, None, fte=Decimal("100"))
    assert enero > junio
    assert junio == Decimal("9000.00")


def test_sin_fte_no_inventa_un_costo():
    e = _entry("90")
    assert calculate_cost_amount(e, 1, None, fte=None) == Decimal("0")


def test_el_recalculo_escribe_el_mes():
    e = _entry("90")
    recalculate_cost_entries([e], 1, None, fte=Decimal("129"))
    assert e.get_month(1) == Decimal("11610.00")


def test_no_toca_las_lineas_manuales():
    e = _entry("90")
    e.calc_mode = "MANUAL"
    e.set_month(1, Decimal("50000"))
    recalculate_cost_entries([e], 1, None, fte=Decimal("129"))
    assert e.get_month(1) == Decimal("50000")


@pytest.mark.parametrize("rate,fte,esperado", [
    ("0", "129", "0.00"),        # sin tarifa no cobra
    ("90", "0.5", "45.00"),      # media plaza, medio costo
    ("125.50", "12", "1506.00"),
])
def test_casos(rate, fte, esperado):
    assert calculate_cost_amount(_entry(rate), 3, None,
                                 fte=Decimal(fte)) == Decimal(esperado)


def test_la_base_de_la_cafeteria_es_quien_come():
    """Para el 0220 la base son los deptos marcados en Allocation, no toda la
    propiedad: no se le da almuerzo a quien está excluido."""
    import inspect
    from app.api import costs_api
    src = inspect.getsource(costs_api._fte_por_mes)
    assert "CafeteriaAllocationConfig" in src
    assert "participates" in src
    assert '"0220"' in src
