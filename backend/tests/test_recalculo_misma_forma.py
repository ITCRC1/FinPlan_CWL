# -*- coding: utf-8 -*-
"""
EL RECÁLCULO DEVUELVE LA MISMA FORMA PARA ACTUAL Y PARA BUDGET.

Dos cosas que la rama ACTUAL no hacía:

1. **No devolvía `avisos`.** El botón compartido lo lee con `?? []` y zafa, pero
   cualquier pantalla que haga `r.avisos.length` revienta según el escenario que
   tenga elegido — un bug que solo aparece con actuales.

2. **No sellaba `last_recalc_at`.** Ese sello se compara contra el `updated_at`
   de planilla / tipos de cambio / configs de reparto para avisar «el reporte
   quedó atrás de lo que ya editaste». Sin sellarlo, un ACTUAL recién
   recalculado mostraba ese aviso para siempre — y un aviso que está siempre
   encendido no avisa nada.
"""
import inspect

from app.engine import recalculate


def _rama_actual() -> str:
    """El cuerpo de la rama que NO calcula, hasta su `return`.

    La condición dejó de ser `type == "ACTUAL"` y pasó a preguntar por el
    ORIGEN del dato (`lo_subido_manda`): un BUDGET o un FORECAST importado
    también entra acá. El anclaje sigue el cambio; lo que prueban los tests —que
    esa rama devuelva la misma forma que la de cálculo— no se movió.
    """
    src = inspect.getsource(recalculate.recalculate_scenario)
    i = src.index('if scenario.type == "ACTUAL" or await lo_subido_manda(')
    j = src.index("}", src.index("return", i))
    return src[i:j]


def test_la_rama_actual_devuelve_avisos():
    assert '"avisos"' in _rama_actual(), (
        "la rama ACTUAL no devuelve `avisos`: quien haga r.avisos.length se "
        "rompe solo con escenarios actuales")


def test_la_rama_actual_sella_el_recalculo():
    assert "last_recalc_at" in _rama_actual(), (
        "sin sellar last_recalc_at, un ACTUAL recalculado sigue mostrando "
        "«el reporte quedó atrás» para siempre")


def test_las_dos_ramas_devuelven_las_mismas_llaves():
    src = inspect.getsource(recalculate.recalculate_scenario)
    for llave in ('"scenario_id"', '"payroll_entries_updated"',
                  '"allocation_entries"', '"pl_lines"', '"avisos"', '"status"'):
        assert src.count(llave) >= 2, f"{llave} no está en las dos ramas"
