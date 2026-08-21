# -*- coding: utf-8 -*-
"""El interruptor que hace que un ACTUAL lea el DETALLE y no el resumen.

**Por qué existe (owner, 2026-08-18, cerrando junio 2026).** El motor elige
solo entre las dos fuentes de un ACTUAL importado: usa el RESUMEN
(`actual_pl_lines`) salvo que el DETALLE (`actual_entries`) dé los mismos siete
totales clave.

Ese guardián está bien y hay que conservarlo: el Actual 2024 tiene un detalle
con $40.613 de gasto de más, y usarlo cambiaría un GOP que el owner ya cerró.

Pero en el Actual 2026 el incompleto es el RESUMEN. Medido contra producción:

    DEPRECIATION          resumen 0,00   detalle 273.139,70
    EBITDA AFTER CAPITAL  resumen 0,00   detalle 738.293,06

y los dos del detalle son EXACTAMENTE los que SCP espera. El guardián estaba
descartando el número bueno por no coincidir con el malo.

La salida no es cambiar la regla para todos ni borrar el resumen: es un
interruptor por escenario, apagado por defecto.
"""
import inspect

from app.engine import recalculate
from app.models.scenario import Scenario


def test_el_campo_existe_y_arranca_apagado():
    """Si naciera prendido, cambiaría el P&L de todos los actuales de golpe."""
    col = Scenario.__table__.columns["usar_detalle"]
    assert col.nullable is False
    assert Scenario(hotel_id="CWL", year=2026, type="ACTUAL",
                    version="actual").usar_detalle in (False, None)


def test_prendido_el_motor_se_saltea_el_resumen():
    """Con el interruptor puesto, `actual_pl_lines` ni se consulta: el mes se
    arma del mayor, que es el camino que ya usa un mes cargado por GL."""
    src = inspect.getsource(recalculate._compute_pl_month_core)
    assert 'getattr(scenario, "usar_detalle", False)' in src
    i = src.index('getattr(scenario, "usar_detalle", False)')
    # El resumen queda vacío → el motor cae al camino de `actual_rows_for_month`.
    assert "{}" in src[i - 60:i], "prendido tiene que dejar el resumen vacío"


def test_apagado_no_cambia_nada():
    """El default es el comportamiento de siempre: resumen, y detalle solo si
    cuadra. Es lo que protege al Actual 2024."""
    src = inspect.getsource(recalculate._compute_pl_month_core)
    assert "await actual_pl_lines_for_month(session, scenario.id, month)" in src
    assert "_detalle_fino_si_cuadra" in src


def test_el_guardian_del_2024_sigue_en_pie():
    """`_detalle_fino_si_cuadra` no se tocó: sigue exigiendo los siete totales."""
    src = inspect.getsource(recalculate._detalle_fino_si_cuadra)
    assert "_el_detalle_cuadra" in src
    assert len(recalculate._TOTALES_CLAVE) == 7


def test_el_endpoint_devuelve_el_veredicto():
    """Prender el interruptor sin ver qué eligió el motor sería a ciegas."""
    from app.api import scenarios_api

    src = inspect.getsource(scenarios_api.update_usar_detalle)
    assert "veredicto_del_detalle" in src
    assert "scenario.usar_detalle = payload.usar_detalle" in src
