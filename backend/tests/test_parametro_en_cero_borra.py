"""Un parámetro de planilla que pasa a 0 borra lo que había calculado.

Owner, 2026-11-27: puso la provisión de vacaciones en 0% y los US$ 61,010 de 6023
siguieron en el Budget 2027 Working: «debería ser lógico que si se pone en 0,
automáticamente hay que recalcular». Antes el 0 quería decir «ahora es manual» y el
monto viejo quedaba. Un driver que YA estaba en 0 sigue sin tocarse (montos a mano).
"""
import inspect

from app.api import payroll_api as api


def test_pasar_a_cero_borra_el_concepto():
    anual, por_mes = api.drivers_apagados({"vacaciones_rate": 0.04}, {"vacaciones_rate": 0})
    assert anual == ["c6023_vacation_prov"] and por_mes == {}


def test_un_driver_que_ya_estaba_en_cero_no_se_toca():
    anual, por_mes = api.drivers_apagados({"vacaciones_rate": 0}, {"vacaciones_rate": 0})
    assert anual == [] and por_mes == {}


def test_bajar_sin_llegar_a_cero_no_borra():
    anual, _ = api.drivers_apagados({"overtime_pct": 0.05}, {"overtime_pct": 0.02})
    assert anual == []


def test_un_mes_de_feriados_en_cero_borra_ese_mes():
    antes = {"holidays": [1, 0, 2, 1, 1, 0, 1, 3, 1, 0, 0, 2]}
    despues = {"holidays": [1, 0, 0, 1, 1, 0, 1, 3, 1, 0, 0, 2]}
    _, por_mes = api.drivers_apagados(antes, despues)
    assert por_mes == {"c6003_working_holiday": [3]}


def test_todos_los_drivers_numericos_tienen_su_concepto():
    assert set(api.CONCEPTO_DEL_DRIVER) == set(api.DRIVERS_NUM)


def test_guardar_respeta_los_meses_cerrados():
    src = inspect.getsource(api.put_payroll_params)
    assert "meses_cerrados" in src and "abiertos" in src
