# -*- coding: utf-8 -*-
"""Un mes que el hotel no opera tiene CERO noches disponibles, también en el motor.

Owner, 2026-10-13, después de marcar octubre como cerrado y apretar Recalcular:
*«ya le di y no lo arregla»*. Tenía razón.

## Las dos fuentes decían cosas distintas sobre el mismo escenario

    Planning → Availability        10.020   (calcula en el navegador, respetaba el cierre)
    Revenue Checkbook / P&L / KPIs 10.950   (leen `scenario_stats`, que las escribe el motor)

`calculate_revenue` nunca supo de los meses cerrados: hacía
`units × CALENDAR_DAYS[month-1]` sin excepción. Así que recalcular escribía las
930 noches de octubre de vuelta en las estadísticas, y el botón que debía
arreglarlo era justo el que lo deshacía.

## Y de paso, febrero duraba 28 siempre

`CALENDAR_DAYS` es una lista fija. El motor planifica hasta 2035 y 2028 y 2032
son bisiestos: 30 noches disponibles de menos al año. Las pantallas de Planning
ya usaban el calendario real, así que el motor y la pantalla volvían a diferir
sin que nada fallara.
"""
import calendar
from decimal import Decimal

import pytest

from app.engine.revenue_calculator import (CALENDAR_DAYS, calculate_revenue,
                                           dias_del_mes, room_type_breakdown)


def test_un_mes_cerrado_no_tiene_noches_disponibles():
    """Lo que el owner estaba pidiendo: octubre fuera del inventario."""
    unidades = {"rt1": 30}
    abierto = calculate_revenue(
        month=10, year=2026, rate_cards=[], occ_budgets=[], channels=[],
        pkg_configs=[], other_revenues=[], room_type_units=unidades)
    cerrado = calculate_revenue(
        month=10, year=2026, rate_cards=[], occ_budgets=[], channels=[],
        pkg_configs=[], other_revenues=[], room_type_units=unidades,
        cerrado=True)
    assert abierto.rooms_available == 930      # 30 × 31
    assert cerrado.rooms_available == 0


def test_el_año_cierra_en_10020_con_octubre_cerrado():
    """La cuenta que el owner hacía a mano, y la que dicen sus escenarios 2026
    y su P&L de referencia (CLAUDE.md 17.8: «Rooms Available … 10.020»)."""
    unidades = {"rt1": 30}

    def anual(cerrados):
        return sum(calculate_revenue(
            month=m, year=2026, rate_cards=[], occ_budgets=[], channels=[],
            pkg_configs=[], other_revenues=[], room_type_units=unidades,
            cerrado=m in cerrados).rooms_available for m in range(1, 13))

    assert anual(set()) == 10_950
    assert anual({10}) == 10_020


@pytest.mark.parametrize("anio", [2026, 2027, 2028, 2032])
def test_febrero_dura_lo_que_dura_de_verdad(anio):
    """⚠️ 2028 y 2032 son bisiestos y el motor planifica hasta 2035.

    Las pantallas de Planning usan `new Date(year, m, 0)` —el calendario real—
    así que con la lista fija el motor decía 840 noches de febrero y la pantalla
    870, sobre el mismo escenario y sin que nada avisara.
    """
    assert dias_del_mes(anio, 2) == calendar.monthrange(anio, 2)[1]
    r = calculate_revenue(
        month=2, year=anio, rate_cards=[], occ_budgets=[], channels=[],
        pkg_configs=[], other_revenues=[], room_type_units={"rt1": 30})
    assert r.rooms_available == 30 * calendar.monthrange(anio, 2)[1]
    if calendar.isleap(anio):
        assert r.rooms_available == 870      # y NO 840, que era lo de antes
        assert r.rooms_available != 30 * CALENDAR_DAYS[1]


def test_el_detalle_por_tipo_usa_el_mismo_criterio():
    """Si el total dice cero y el detalle por categoría dice 930, el cuadro se
    ve bien y no dice la verdad — que es el defecto más caro de este proyecto."""
    unidades = {"rt1": 30}
    filas = room_type_breakdown(month=10, rate_cards=[], occ_budgets=[],
                                room_type_units=unidades, year=2026,
                                cerrado=True)
    assert filas and all(f["nights_available"] == 0 for f in filas)
    abiertas = room_type_breakdown(month=10, rate_cards=[], occ_budgets=[],
                                   room_type_units=unidades, year=2026)
    assert abiertas[0]["nights_available"] == 930


def test_sin_año_el_detalle_se_comporta_como_antes():
    """`year` es opcional a propósito: las llamadas viejas no lo mandaban y no
    se las puede romper. Sin año se cae a la lista fija, que es lo que hacían."""
    filas = room_type_breakdown(month=2, rate_cards=[], occ_budgets=[],
                                room_type_units={"rt1": 30})
    assert filas[0]["nights_available"] == 30 * CALENDAR_DAYS[1]


def test_el_recalculo_le_pasa_los_meses_cerrados_al_motor():
    """⚠️ El motor puede saber del cierre y el recálculo no decírselo.

    Es lo que pasaba: `calculate_revenue` se llamaba sin más, y `scenario_stats`
    —que es de donde leen el P&L, el Revenue Checkbook y los KPIs— quedaba con
    las noches del calendario.
    """
    import inspect

    from app.engine import recalculate
    fuente = inspect.getsource(recalculate.load_revenue_results)
    # El modelo recibe el mes cerrado...
    assert "cerrado=month in" in fuente
    # ...y la resolucion sale de UNA sola funcion, compartida con el API que
    # alimenta las pantallas. Si cada lado resolviera por su cuenta, volverian
    # a decir cosas distintas del mismo escenario, que es como empezo todo.
    assert "meses_cerrados_resueltos" in fuente


# ── El override vacío HEREDA, no pisa ───────────────────────────────────────

def test_un_override_vacio_hereda_de_la_propiedad():
    """⚠️ La causa que quedaba, y la que hizo que esto tomara cuatro vueltas.

    Owner, 2026-10-13: *«ya corrige esta mierda de una vez»*. Los seis
    escenarios 2027 tenían `closed_months = ''` guardado y con la regla vieja
    —`is not None`— eso PISABA el `'10'` de la propiedad: marcar octubre cerrado
    en el hotel no hacía nada en ellos.

    Y el `''` nació de rebote: `put_scenario_master` escribe el campo en CADA
    guardado, así que al guardar las UNIDADES del 2027 se llevó puesto el
    cierre. No había forma de decir «heredá» — cualquier guardado detachaba el
    escenario de la propiedad, en silencio.
    """
    from app.api.revenue_api import meses_cerrados_resueltos

    class H:
        closed_months_list = [10]

    class SM:
        def __init__(self, v):
            self.closed_months = v

    # Sin fila de master: la propiedad manda.
    assert meses_cerrados_resueltos(H(), None) == [10]
    # Fila con el campo vacío o nulo: hereda. Antes pisaba con «ninguno».
    assert meses_cerrados_resueltos(H(), SM("")) == [10]
    assert meses_cerrados_resueltos(H(), SM(None)) == [10]
    # Declarado: el escenario manda, que es para lo que existe el override.
    assert meses_cerrados_resueltos(H(), SM("10,11")) == [10, 11]
    assert meses_cerrados_resueltos(H(), SM("9")) == [9]


def test_la_pantalla_de_ocupacion_descuenta_el_mes_cerrado():
    """Antes NO lo descontaba, a propósito: «la capacidad física existe igual».

    Ese razonamiento se cayó cuando el motor dejó de contarlas: mantenerlo
    convertía a esta pantalla en la única que no coincide. Y el daño va para el
    lado que no se revisa — la ocupación anual salía 46,8 % en vez de ~51 %, y
    un número desfavorable se acepta sin mirarlo.
    """
    import pathlib

    pagina = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app"
              / "revenue" / "occupancy" / "page.tsx")
    txt = pagina.read_text(encoding="utf-8", errors="replace")
    assert "closed.has(mi + 1) ? 0" in txt
    assert "Los meses cerrados NO" not in txt, "volvió el criterio viejo"
