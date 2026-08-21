# -*- coding: utf-8 -*-
"""
Dos controles que la app no tenía cubiertos:

1. EL CANDADO — una versión enllavada (Budget Final, un Draft cerrado) no se puede
   sobreescribir. Antes las cargas masivas borraban y reescribían sin mirar el
   estado, así que un presupuesto aprobado se podía perder con un archivo.

2. LA RENTA ES ANUAL — el P&L sumaba MAX(0, EBT_mes × 30%) mes a mes, así que la
   pérdida de un mes no se compensaba y el impuesto salía de más. En Corcovado
   esto pega todos los años porque el lodge cierra en octubre.
"""
import pytest

from app.api.pl_api import _apply_tax_correction
from app.models.scenario import Scenario, ScenarioLockedError


# ─── 1. El candado ────────────────────────────────────────────────────────────
def _escenario(status: str) -> Scenario:
    return Scenario(id="x", hotel_id="CWL", year=2027, type="BUDGET",
                    version="Final", status=status)


def test_enllavado_no_se_puede_editar():
    with pytest.raises(ScenarioLockedError):
        _escenario("locked").assert_editable()


def test_borrador_si_se_puede_editar():
    _escenario("draft").assert_editable()   # no lanza


@pytest.mark.parametrize("archivo,funcion", [
    ("opex_api", "bulk_replace_opex"),
    ("costs_api", "bulk_replace_costs"),
    ("payroll_api", "bulk_replace_payroll"),
    ("payroll_api", "update_salaries"),
    ("nonop_api", "bulk_replace_nonop"),
    ("pl_api", "upsert_scenario_stats"),
    ("actuals_api", "clear_actuals"),
    ("scenarios_api", "clear_months_from"),
])
def test_las_cargas_masivas_miran_el_candado(archivo, funcion):
    """Si alguien quita el assert_editable de una carga masiva, esto falla."""
    import importlib
    import inspect
    mod = importlib.import_module(f"app.api.{archivo}")
    src = inspect.getsource(getattr(mod, funcion))
    assert "assert_editable" in src, (
        f"{archivo}.{funcion} escribe datos sin comprobar si la versión está enllavada")


@pytest.mark.parametrize("archivo,funcion", [
    ("scenarios_api", "import_gl_detail"),
    ("scenarios_api", "import_pl_snapshot"),
])
def test_los_importadores_saltan_lo_enllavado(archivo, funcion):
    import importlib
    import inspect
    mod = importlib.import_module(f"app.api.{archivo}")
    src = inspect.getsource(getattr(mod, funcion))
    assert "is_locked" in src, (
        f"{archivo}.{funcion} carga sobre una versión enllavada sin avisar")


# ─── 2. La renta es anual ─────────────────────────────────────────────────────
# Caso real de Corcovado: octubre cerrado, así que da pérdida.
MESES_CWL_2027 = [705496.0, 718097.0, 748986.0, 645941.0, 240842.0, 238189.0,
                  246659.0, 254730.0, 27149.0, -103488.0, 421472.0, 697251.0]


def _anual(meses):
    """Lo que armaba el P&L antes: sumar el impuesto de cada mes con piso en cero."""
    return {"EBT": sum(meses),
            "INCOME_TAXES": round(sum(max(0.0, m) for m in meses) * 0.30, 2),
            "NET_PROFIT": 0.0}


def test_la_perdida_de_un_mes_se_compensa_en_el_ano():
    a = _anual(MESES_CWL_2027)
    de_mas = a["INCOME_TAXES"] - sum(MESES_CWL_2027) * 0.30
    assert de_mas == pytest.approx(103488.0 * 0.30, abs=1)   # el error que había
    _apply_tax_correction(a, MESES_CWL_2027)
    assert a["INCOME_TAXES"] == pytest.approx(sum(MESES_CWL_2027) * 0.30, abs=1)
    assert a["NET_PROFIT"] == pytest.approx(a["EBT"] - a["INCOME_TAXES"], abs=1)


def test_sin_meses_en_perdida_no_cambia_nada():
    meses = [m for m in MESES_CWL_2027 if m > 0]
    a = _anual(meses)
    antes = a["INCOME_TAXES"]
    _apply_tax_correction(a, meses)
    assert a["INCOME_TAXES"] == pytest.approx(antes, abs=1)


def test_un_solo_mes_no_se_toca():
    a = {"EBT": 705496.0, "INCOME_TAXES": 211648.8, "NET_PROFIT": 0.0}
    _apply_tax_correction(a, [705496.0])
    assert a["INCOME_TAXES"] == pytest.approx(211648.8, abs=1)


def test_no_se_cobra_renta_sobre_una_perdida():
    a = {"EBT": -103488.0, "INCOME_TAXES": 39000.0, "NET_PROFIT": 0.0}
    _apply_tax_correction(a, [-103488.0])
    assert a["INCOME_TAXES"] == 0.0
    assert a["NET_PROFIT"] == pytest.approx(-103488.0, abs=1)


def test_recalcular_no_borra_planilla_importada_sin_salario():
    """El Budget Final 2026 trae $1.26M de planilla del GL con los salarios en
    blanco. Recalcular ponía todo en cero. Ahora esas filas se respetan."""
    import inspect
    from app.engine import recalculate
    src = inspect.getsource(recalculate._recalc_payroll)
    assert "sin_salario" in src and "total_entry(entry)" in src, (
        "_recalc_payroll volvió a pisar filas con datos cuando la posición no "
        "tiene salario cargado")
    assert "protegidas" in src, "no avisa cuántas filas se dejaron sin tocar"


def test_una_cifra_contabilizada_de_verdad_se_respeta():
    """Un Actual con la cuenta 8060 cargada no se pisa con la tasa estatutaria."""
    a = {"EBT": sum(MESES_CWL_2027), "INCOME_TAXES": 999999.0, "NET_PROFIT": 0.0}
    _apply_tax_correction(a, MESES_CWL_2027)
    assert a["INCOME_TAXES"] == 999999.0


# ─── 3. Mensual con signo, consolidado al año ─────────────────────────────────
# La corrección de arriba (`_apply_tax_correction`) arregla la COLUMNA anual del
# P&L. Pero el motor escribe el impuesto mes a mes, así que todo lo que suma los
# doce meses por su cuenta —cash flow, dashboards, exports, comparativos— leía la
# cifra inflada. Estos controles son sobre el motor.
#
# La regla, en palabras del owner: «El impuesto de renta se calcula mes a mes no
# importa si es negativo o positivo. Y se consolida anualmente» — «algunos meses
# puede ser negativo, otros positivos, pero en forma anual debe ser positivo».
from decimal import Decimal                                        # noqa: E402

from app.engine.pl_engine import renta_por_mes            # noqa: E402

_MESES = [Decimal(str(m)) for m in MESES_CWL_2027]
_TASA = Decimal("0.30")


def test_cada_mes_lleva_el_30_de_SU_ebt():
    """Mes a mes, sin piso y sin prorratear el anual hacia atrás."""
    r = renta_por_mes(_MESES, _TASA)
    assert r == [m * _TASA for m in _MESES]


def test_el_mes_en_perdida_da_credito_no_cero():
    """Octubre cierra el lodge y da pérdida: tiene que mostrar impuesto NEGATIVO.
    Antes mostraba cero, o sea un mes en pérdida sin efecto fiscal — y eso
    ensucia el flujo de caja mensual y la lectura de un mes suelto."""
    r = renta_por_mes(_MESES, _TASA)
    assert _MESES[9] < 0                              # octubre, el mes negativo
    assert r[9] == _MESES[9] * _TASA
    assert r[9] < 0, "un mes en pérdida genera un crédito, no un cero"


def test_la_suma_de_los_doce_es_el_impuesto_del_ano():
    """La condición que no se puede romper: el mensual y el anual no pueden
    contar dos verdades sobre la misma cuenta."""
    r = renta_por_mes(_MESES, _TASA)
    assert sum(r) == sum(_MESES) * _TASA


def test_el_ano_en_perdida_no_paga_ni_acredita():
    """El piso de cero existe, pero es ANUAL. Si el ejercicio completo cierra en
    pérdida el impuesto del año es cero —no un reembolso— y entonces los doce
    meses tienen que dar cero también, o la suma no cerraría contra el anual."""
    meses = [Decimal("100"), Decimal("-500")]
    r = renta_por_mes(meses, _TASA)
    assert r == [Decimal("0"), Decimal("0")]
    assert sum(r) == max(sum(meses) * _TASA, Decimal("0"))


def test_el_piso_mensual_cobraba_de_mas():
    """El error concreto que se corrigió, con los meses reales de Corcovado."""
    viejo = sum(max(m, Decimal("0")) for m in _MESES) * _TASA
    nuevo = sum(renta_por_mes(_MESES, _TASA))
    assert float(viejo - nuevo) == pytest.approx(float(-_MESES[9] * _TASA), abs=1)


def test_el_motor_toma_la_renta_que_le_dan():
    """`calculate_budget_pl_from_mapping` debe usar el impuesto ya resuelto con
    el año a la vista, en vez de recalcular MAX(0, EBT_mes × 30%) por su cuenta."""
    import inspect
    from app.engine import pl_engine
    src = inspect.getsource(pl_engine.calculate_budget_pl_from_mapping)
    assert "income_tax" in src and "if income_tax is not None" in src, (
        "el motor volvió a decidir el impuesto mirando un mes solo")


def test_el_orquestador_mira_los_doce_meses():
    """Si alguien saca `_pl_del_ano` del camino del P&L, el piso vuelve a ser
    mensual y la sobre-provisión regresa sin que nada avise."""
    import inspect
    from app.engine import recalculate
    src = inspect.getsource(recalculate._compute_pl_month_core)
    assert "_pl_del_ano" in src, (
        "el P&L de un presupuesto volvió a calcular la renta mes a mes")
