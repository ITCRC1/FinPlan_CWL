# -*- coding: utf-8 -*-
"""LA PLANILLA POR CUENTA TIENE QUE PEGAR CON LA PLANILLA POR DEPARTAMENTO.

Owner, 2026-09-10: *«mete un nuevo tab […] donde me pongas todas las cuentas de
Payroll por totales. Todas ellas sumadas al final esa debe pegar con los
reportes de cada departamento. Esto es para ver total salarios, total
comisiones, total horas extras, y todo»*.

El sistema ya abria la planilla por DEPARTAMENTO y por MES. Este es el tercer
corte —por CUENTA— y contesta «cuanto pagamos de horas extra este mes» sin
sumar a mano veintitantos departamentos.

## Por que hay un guard y no solo el endpoint

Dos cuadros que dicen cuanto cuesta la planilla y no coinciden es peor que
tener uno solo: no hay forma de saber cual mirar, y ninguno de los dos avisa.
La unica manera de que peguen siempre es que lean LO MISMO y filtren IGUAL.
Eso es lo que se fija aca.
"""
import io
import os

API = os.path.join(os.path.dirname(__file__), "..", "app", "api", "payroll_api.py")


def _src():
    return io.open(API, encoding="utf-8").read()


def test_las_17_cuentas_son_exactamente_las_que_suma_el_total():
    """Si `CONCEPTOS` y `total_entry` dejaran de cubrir lo mismo, el corte por
    cuenta y el corte por departamento darian numeros distintos — y como cada
    uno cuadra CONSIGO MISMO, nadie lo notaria."""
    from decimal import Decimal
    from app.api.consulta_api import CONCEPTOS
    from app.engine.payroll_calculator import total_entry
    from app.models.payroll_concept_entry import PayrollConceptEntry

    assert len(CONCEPTOS) == 17

    # Una entrada con un valor distinto en cada concepto: si `total_entry` se
    # saltara uno, la suma no daria.
    e = PayrollConceptEntry()
    esperado = Decimal("0")
    for i, (campo, _codigo, _rotulo) in enumerate(CONCEPTOS, start=1):
        valor = Decimal(str(i * 11))
        setattr(e, campo, valor)
        esperado += valor

    assert total_entry(e) == esperado, (
        "la suma de los 17 conceptos no da el total: el corte por cuenta y el "
        "corte por departamento van a diferir")


def test_lee_la_misma_tabla_que_el_reporte_por_departamento():
    src = _src()
    i = src.index("async def payroll_por_cuenta")
    cuerpo = src[i:]
    assert "select(PayrollConceptEntry)" in cuerpo


def test_filtra_igual_que_el_reporte_por_departamento():
    """Misma exclusion de deptos de allocation, con la misma excepcion del
    Pre-Cierre. Si uno excluyera el 0220 y el otro no, los dos cuadros
    diferirian en el gasto de cafeteria sin decir por que."""
    src = _src()
    i = src.index("async def payroll_por_cuenta")
    cuerpo = src[i:]
    assert "allocation_en_overhead(esc)" in cuerpo
    assert "ALLOC_EXCL_PAYROLL" in cuerpo
    # Y el reporte por departamento sigue usando la misma pareja.
    antes = src[:i]
    assert "excluir = set() if allocation_en_overhead(" in antes
    assert "ALLOC_EXCL_PAYROLL" in antes


def test_la_ruta_no_choca_con_la_del_escenario():
    """`/payroll/por-cuenta/` no puede caer en `/payroll/{scenario_id}/...`."""
    src = _src()
    assert '"/payroll/por-cuenta/"' in src
    assert '@router.get("/payroll/{scenario_id}/")' not in src
