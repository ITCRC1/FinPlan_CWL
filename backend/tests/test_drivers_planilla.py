# -*- coding: utf-8 -*-
"""
LOS 17 CONCEPTOS DE PLANILLA, CALCULADOS POR REGLA.

Antes solo se movían 3 (SW, CCSS, aguinaldo) y los otros 14 eran digitación por
posición × mes — con 110 posiciones son 18,480 celdas, así que en la práctica
quedaban en cero y el costo de planilla salía corto.

Lo que se fija aquí:
  1. Sin parámetros no cambia NADA (los escenarios viejos dan lo mismo).
  2. El ORDEN: overtime, feriados y bono entran a la BASE, así que la CCSS y el
     aguinaldo tienen que calcularse DESPUÉS de ellos.
  3. Las provisiones (vacaciones, cesantía) van sobre la BASE.
  4. Los beneficios en colones se convierten con el TC y NO cotizan.
"""
from decimal import Decimal

import pytest

from app.engine.payroll_calculator import calc_base, recalculate_entry, total_entry
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.payroll_params import PayrollParams
from app.models.payroll_position import PayrollPosition

TC = Decimal("530")
CCSS = Decimal("0.26830")
AGU = Decimal("12")


def _pos(salario="530000"):
    p = PayrollPosition(dept_code="0111", position_name="RECEPCION",
                        employee_name="X", salary_amount=Decimal(salario),
                        salary_currency="CRC")
    for m in ("jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"):
        setattr(p, f"fte_{m}", Decimal("1.0"))
    return p


def _params(**kw):
    pp = PayrollParams(scenario_id="s")
    for c in ("overtime_pct", "bonus_pct", "vacaciones_rate", "severance_annual_rate",
              "cafeteria_daily_crc", "transport_monthly_crc", "housing_monthly_crc",
              "other_monthly_crc"):
        setattr(pp, c, Decimal("0"))
    pp.working_days = "[0,0,0,0,0,0,0,0,0,0,0,0]"
    pp.holidays = "[0,0,0,0,0,0,0,0,0,0,0,0]"
    pp.calendar_days = "[31,28,31,30,31,30,31,31,30,31,30,31]"
    for k, v in kw.items():
        setattr(pp, k, v)
    return pp


def _fila(pos, params=None, month=1):
    e = PayrollConceptEntry(scenario_id="s", position_id="p",
                            dept_code="0111", month=month, year=2027)
    for c in [x for x in dir(e) if x.startswith("c60")]:
        setattr(e, c, Decimal("0"))
    return recalculate_entry(e, pos, month, TC, CCSS, AGU, params=params)


# ── 1. sin parámetros, nada cambia ────────────────────────────────────────────
def test_sin_parametros_solo_se_mueven_los_tres_de_siempre():
    e = _fila(_pos())
    assert e.c6000_sw == Decimal("1000.00")            # 530,000 / 530
    assert e.c6020_ccss == Decimal("268.30")
    assert e.c6021_aguinaldo == Decimal("83.33")
    for c in ("c6001_overtime", "c6003_working_holiday", "c6023_vacation_prov",
              "c6025_cafeteria", "c6026_severance", "c6028_housing",
              "c6029_transport", "c6030_other"):
        assert getattr(e, c) == Decimal("0"), f"{c} se movió sin parámetros"


def test_los_drivers_nacen_en_cero():
    """Un escenario con fila de parámetros pero sin llenar da lo mismo que sin ella."""
    a = _fila(_pos())
    b = _fila(_pos(), _params())
    assert total_entry(a) == total_entry(b)


# ── 2. el orden: lo que entra a la BASE se calcula antes que la CCSS ──────────
def test_el_overtime_entra_a_la_base_y_sube_la_ccss():
    e = _fila(_pos(), _params(overtime_pct=Decimal("0.10")))
    assert e.c6001_overtime == Decimal("100.00")        # 10% de 1,000
    assert calc_base(e) == Decimal("1100.00")
    assert e.c6020_ccss == Decimal("295.13")            # 1,100 × 26.83%
    assert e.c6021_aguinaldo == Decimal("91.67")        # 1,100 / 12


def test_el_bono_tambien_entra_a_la_base():
    e = _fila(_pos(), _params(bonus_pct=Decimal("0.05")))
    assert e.c6027_incentive_bonus == Decimal("50.00")
    assert e.c6020_ccss == Decimal("281.72")            # 1,050 × 26.83%


def test_los_feriados_salen_del_calendario():
    """Enero 2027: 31 días, 1 feriado → SW/31 × 1."""
    pp = _params()
    pp.holidays = "[1,0,0,2,1,2,1,2,1,1,0,1]"
    e = _fila(_pos(), pp, month=1)
    assert e.c6003_working_holiday == Decimal("32.26")   # 1,000/31
    # y ese feriado cotiza
    assert calc_base(e) == Decimal("1032.26")
    assert e.c6020_ccss == Decimal("276.96")


def test_sin_feriados_en_el_mes_no_cobra_nada():
    pp = _params()
    pp.holidays = "[1,0,0,2,1,2,1,2,1,1,0,1]"
    e = _fila(_pos(), pp, month=2)                       # febrero: 0 feriados
    assert e.c6003_working_holiday == Decimal("0")


# ── 3. provisiones sobre la BASE ──────────────────────────────────────────────
def test_vacaciones_y_cesantia_van_sobre_la_base_no_sobre_el_salario():
    pp = _params(overtime_pct=Decimal("0.10"),
                 vacaciones_rate=Decimal("0.03846"),
                 severance_annual_rate=Decimal("0.0533"))
    e = _fila(_pos(), pp)
    base = calc_base(e)
    assert base == Decimal("1100.00")                    # con el overtime dentro
    assert e.c6023_vacation_prov == Decimal("42.31")     # 1,100 × 2/52
    assert e.c6026_severance == Decimal("58.63")         # 1,100 × 5.33%, sobre la BASE del mes
    # son provisiones: NO cotizan
    assert e.c6020_ccss == Decimal("295.13")


# ── 4. beneficios en colones ──────────────────────────────────────────────────
def test_la_cafeteria_NO_se_calcula_como_per_diem():
    """La cafetería viene del REPARTO: Allocations toma el costo del depto 0220 y
    lo distribuye por FTE a la cuenta 6025. Si además se calculara aquí como
    per diem, el mismo costo entraría dos veces al P&L."""
    pp = _params(cafeteria_daily_crc=Decimal("3500"))
    pp.working_days = "[22,20,23,21,21,22,22,22,21,22,20,22]"
    e = _fila(_pos(), pp, month=1)
    assert e.c6025_cafeteria == Decimal("0")


def test_transporte_y_vivienda_son_por_persona_al_mes():
    pp = _params(transport_monthly_crc=Decimal("30000"),
                 housing_monthly_crc=Decimal("53000"))
    e = _fila(_pos(), pp)
    assert e.c6029_transport == Decimal("56.60")         # 30,000 / 530
    assert e.c6028_housing == Decimal("100.00")


def test_los_beneficios_no_cotizan():
    pp = _params(cafeteria_daily_crc=Decimal("3500"),
                 transport_monthly_crc=Decimal("30000"))
    pp.working_days = "[22,20,23,21,21,22,22,22,21,22,20,22]"
    e = _fila(_pos(), pp)
    assert e.c6020_ccss == Decimal("268.30")             # igual que sin beneficios


def test_una_posicion_sin_fte_no_cobra_beneficios():
    """Octubre cerrado: FTE 0 → ni salario ni cafetería ni transporte."""
    pos = _pos()
    pos.fte_oct = Decimal("0")
    pp = _params(cafeteria_daily_crc=Decimal("3500"),
                 transport_monthly_crc=Decimal("30000"))
    pp.working_days = "[22,20,23,21,21,22,22,22,21,22,20,22]"
    e = _fila(pos, pp, month=10)
    assert e.c6000_sw == Decimal("0")
    assert e.c6025_cafeteria == Decimal("0")
    assert e.c6029_transport == Decimal("0")
    assert total_entry(e) == Decimal("0")


# ── 5. el conjunto ────────────────────────────────────────────────────────────
def test_carga_total_con_todos_los_drivers_puestos():
    """Un caso completo: la carga sobre el salario tiene que quedar en rango CR."""
    pp = _params(overtime_pct=Decimal("0.05"), bonus_pct=Decimal("0"),
                 vacaciones_rate=Decimal("0.03846"),
                 severance_annual_rate=Decimal("0.0533"),
                 cafeteria_daily_crc=Decimal("3500"),
                 transport_monthly_crc=Decimal("30000"))
    pp.working_days = "[22,20,23,21,21,22,22,22,21,22,20,22]"
    pp.holidays = "[1,0,0,2,1,2,1,2,1,1,0,1]"
    e = _fila(_pos(), pp, month=1)
    carga = (total_entry(e) - e.c6000_sw) / e.c6000_sw
    assert Decimal("0.55") <= carga <= Decimal("0.80"), f"carga fuera de rango: {carga:.1%}"


@pytest.mark.parametrize("concepto", [
    "c6002_day_off", "c6004_disabilities", "c6010_commissions", "c6024_vacations_taken",
    "c6022_occ_hazard",
])
def test_los_conceptos_por_persona_siguen_siendo_manuales(concepto):
    """Estos no salen de una regla: el motor no los debe tocar.
    6022 Occ. Hazard además ya está dentro del 26.83% de la CCSS."""
    e = PayrollConceptEntry(scenario_id="s", position_id="p", dept_code="0111",
                            month=1, year=2027)
    for c in [x for x in dir(e) if x.startswith("c60")]:
        setattr(e, c, Decimal("0"))
    setattr(e, concepto, Decimal("77.77"))
    recalculate_entry(e, _pos(), 1, TC, CCSS, AGU, params=_params(
        overtime_pct=Decimal("0.10"), cafeteria_daily_crc=Decimal("3500")))
    assert getattr(e, concepto) == Decimal("77.77"), f"{concepto} fue pisado por el motor"


# ── 6. INS de riesgos del trabajo: un monto que se reparte por FTE ────────────
# El INS NO es parte del 26.83% de la CCSS: es una póliza aparte que el INS
# factura al patrono, y la empresa la reparte entre todos los empleados.
from app.engine.payroll_calculator import repartir_ins  # noqa: E402

TC_MES = {m: TC for m in range(1, 13)}


def _plantel(n=3, meses=12):
    """n posiciones × meses, todas con FTE 1."""
    filas = []
    for i in range(n):
        p = _pos()
        for m in range(1, meses + 1):
            e = PayrollConceptEntry(scenario_id="s", position_id=f"p{i}",
                                    dept_code="0111", month=m, year=2027)
            e.c6022_occ_hazard = Decimal("0")
            filas.append((e, p))
    return filas


def test_el_ins_se_reparte_completo():
    """El reparto es EXACTO en colones. Al pasarlo a dólares cada fila se redondea
    a centavo, así que sobre 36 filas la diferencia puede llegar a unos centavos —
    inmaterial, pero no es cero y la prueba no debe fingir que lo es."""
    filas = _plantel(3)
    repartido = repartir_ins(filas, Decimal("6360000"), TC_MES)
    suma = sum(e.c6022_occ_hazard for e, _ in filas)
    assert repartido == suma
    esperado_usd = Decimal("6360000") / TC
    tolerancia = Decimal("0.01") * len(filas)          # medio centavo por fila
    assert abs(suma - esperado_usd) <= tolerancia


def test_se_reparte_parejo_cuando_todos_tienen_el_mismo_fte():
    filas = _plantel(3)                       # 3 posiciones × 12 meses = 36 filas
    repartir_ins(filas, Decimal("6360000"), TC_MES)
    esperado = Decimal("6360000") / 36 / TC   # ₡176,666.67 → $333.33
    for e, _ in filas:
        assert abs(e.c6022_occ_hazard - esperado) < Decimal("0.02")


def test_quien_tiene_mas_fte_paga_mas():
    filas = _plantel(2, meses=1)
    filas[1][1].fte_jan = Decimal("0.5")      # media plaza
    repartir_ins(filas, Decimal("530000"), TC_MES)
    completo, medio = filas[0][0], filas[1][0]
    assert abs(completo.c6022_occ_hazard - medio.c6022_occ_hazard * 2) <= Decimal("0.02")
    assert completo.c6022_occ_hazard > medio.c6022_occ_hazard


def test_octubre_cerrado_no_paga_ins():
    """FTE 0 → no recibe reparto, y el monto se distribuye entre los demás."""
    filas = _plantel(1)
    filas[9][1].fte_oct = Decimal("0")        # esa posición no trabaja en octubre
    repartir_ins(filas, Decimal("5300000"), TC_MES)
    assert filas[9][0].c6022_occ_hazard == Decimal("0")
    suma = sum(e.c6022_occ_hazard for e, _ in filas)
    assert abs(suma - Decimal("5300000") / TC) <= Decimal("0.01") * len(filas)
    # y lo que no pagó octubre lo absorbieron los otros 11 meses
    assert all(e.c6022_occ_hazard > 0 for e, _ in filas if e.month != 10)


def test_sin_monto_las_6022_quedan_en_cero():
    filas = _plantel(2)
    for e, _ in filas:
        e.c6022_occ_hazard = Decimal("99")    # basura de una corrida anterior
    assert repartir_ins(filas, Decimal("0"), TC_MES) == Decimal("0")
    assert all(e.c6022_occ_hazard == Decimal("0") for e, _ in filas)


def test_el_ins_no_cotiza_ccss():
    """Es un seguro, no salario: no entra a la BASE."""
    e = _fila(_pos())
    base_antes = calc_base(e)
    e.c6022_occ_hazard = Decimal("500")
    assert calc_base(e) == base_antes


# ── 7. reparto genérico: cualquier cuenta de beneficio, por FTE o por cabeza ──
from app.engine.payroll_calculator import repartir_beneficio        # noqa: E402
from app.models.benefit_allocation_config import (                  # noqa: E402
    BenefitAllocationConfig, CUENTAS_BENEFICIO)


@pytest.mark.parametrize("cuenta,columna", [
    ("6022", "c6022_occ_hazard"), ("6025", "c6025_cafeteria"),
    ("6028", "c6028_housing"), ("6029", "c6029_transport"),
    ("6030", "c6030_other"), ("6004", "c6004_disabilities"),
])
def test_el_reparto_sirve_para_cualquier_cuenta_de_beneficio(cuenta, columna):
    filas = _plantel(2, meses=1)
    cfg = BenefitAllocationConfig(scenario_id="s", account=cuenta)
    assert cfg.columna == columna
    repartir_beneficio(filas, columna, Decimal("1060000"), TC_MES)
    assert sum(getattr(e, columna) for e, _ in filas) == Decimal("2000.00")


def test_reparto_por_cabeza_ignora_el_peso_de_la_plaza():
    """HEADCOUNT: media plaza paga lo mismo que una completa."""
    filas = _plantel(2, meses=1)
    filas[1][1].fte_jan = Decimal("0.5")
    repartir_beneficio(filas, "c6029_transport", Decimal("1060000"),
                       TC_MES, base="HEADCOUNT")
    a, b = filas[0][0].c6029_transport, filas[1][0].c6029_transport
    assert a == b == Decimal("1000.00")


def test_reparto_por_fte_si_pesa_la_plaza():
    filas = _plantel(2, meses=1)
    filas[1][1].fte_jan = Decimal("0.5")
    repartir_beneficio(filas, "c6029_transport", Decimal("1060000"), TC_MES, base="FTE")
    a, b = filas[0][0].c6029_transport, filas[1][0].c6029_transport
    assert abs(a - b * 2) <= Decimal("0.02")
    assert abs(a + b - Decimal("2000.00")) <= Decimal("0.02")


def test_quien_no_trabaja_no_recibe_ni_por_cabeza():
    filas = _plantel(2, meses=1)
    filas[1][1].fte_jan = Decimal("0")
    repartir_beneficio(filas, "c6030_other", Decimal("530000"), TC_MES, base="HEADCOUNT")
    assert filas[1][0].c6030_other == Decimal("0")
    assert filas[0][0].c6030_other == Decimal("1000.00")


def test_las_cuentas_que_cotizan_no_son_repartibles():
    """6001/6010/6027 entran a la BASE de la CCSS: son salario, no un pote a repartir."""
    for c in ("6000", "6001", "6002", "6003", "6010", "6020", "6021", "6024", "6027"):
        assert c not in CUENTAS_BENEFICIO, f"{c} no debería ser repartible"


def test_una_cuenta_desconocida_no_hace_nada():
    filas = _plantel(2, meses=1)
    cfg = BenefitAllocationConfig(scenario_id="s", account="9999")
    assert cfg.columna == ""
    assert repartir_beneficio(filas, cfg.columna, Decimal("100000"), TC_MES) == Decimal("0")


# ── 8. lo manual sobrevive al recálculo ──────────────────────────────────────
# Un driver en CERO significa "este concepto no es automático". Sin esta regla,
# recalcular borraría lo que el owner subió por Excel.
@pytest.mark.parametrize("columna,driver", [
    ("c6001_overtime", "overtime_pct"),
    ("c6027_incentive_bonus", "bonus_pct"),
    ("c6026_severance", "severance_annual_rate"),
    ("c6029_transport", "transport_monthly_crc"),
    ("c6028_housing", "housing_monthly_crc"),
    ("c6030_other", "other_monthly_crc"),
    ("c6023_vacation_prov", "vacaciones_rate"),
])
def test_con_el_driver_en_cero_se_respeta_el_monto_manual(columna, driver):
    e = _fila(_pos(), _params())
    setattr(e, columna, Decimal("123.45"))
    recalculate_entry(e, _pos(), 1, TC, CCSS, AGU, params=_params())
    assert getattr(e, columna) == Decimal("123.45"), (
        f"recalcular borró el monto manual de {columna}")


@pytest.mark.parametrize("columna,driver,valor", [
    ("c6001_overtime", "overtime_pct", Decimal("0.10")),
    ("c6029_transport", "transport_monthly_crc", Decimal("30000")),
])
def test_con_el_driver_puesto_manda_la_formula(columna, driver, valor):
    e = _fila(_pos(), _params())
    setattr(e, columna, Decimal("999.99"))
    recalculate_entry(e, _pos(), 1, TC, CCSS, AGU, params=_params(**{driver: valor}))
    assert getattr(e, columna) != Decimal("999.99")


def test_las_horas_extra_manuales_si_mueven_la_ccss():
    """Entran a la BASE: subir horas extra a mano tiene que subir CCSS y aguinaldo."""
    e = _fila(_pos(), _params())
    assert e.c6020_ccss == Decimal("268.30")
    e.c6001_overtime = Decimal("100.00")
    recalculate_entry(e, _pos(), 1, TC, CCSS, AGU, params=_params())
    assert e.c6001_overtime == Decimal("100.00")     # no se borró
    assert e.c6020_ccss == Decimal("295.13")         # y sí cotizó
    assert e.c6021_aguinaldo == Decimal("91.67")


# ── 9. 6002 Día libre: automático, con la misma forma que los feriados ───────
def test_los_dias_libres_se_prorratean_sobre_el_salario():
    """6002 = S&W ÷ días del mes × días libres del mes. Enero: 31 días, 4 libres."""
    pp = _params()
    pp.days_off = "[4,4,5,4,4,4,4,5,4,0,4,4]"
    e = _fila(_pos(), pp, month=1)
    assert e.c6002_day_off == Decimal("129.03")          # 1,000 / 31 × 4


def test_los_dias_libres_cotizan_ccss_y_aguinaldo():
    """Entran a la BASE, así que tienen que calcularse ANTES que la CCSS."""
    pp = _params()
    pp.days_off = "[4,0,0,0,0,0,0,0,0,0,0,0]"
    e = _fila(_pos(), pp, month=1)
    assert calc_base(e) == Decimal("1129.03")
    assert e.c6020_ccss == Decimal("302.92")             # 1,129.03 × 26.83%
    assert e.c6021_aguinaldo == Decimal("94.09")


def test_dias_libres_y_feriados_conviven_en_el_mismo_mes():
    pp = _params()
    pp.days_off = "[4,0,0,0,0,0,0,0,0,0,0,0]"
    pp.holidays = "[1,0,0,0,0,0,0,0,0,0,0,0]"
    e = _fila(_pos(), pp, month=1)
    assert e.c6002_day_off == Decimal("129.03")
    assert e.c6003_working_holiday == Decimal("32.26")
    assert calc_base(e) == Decimal("1161.29")


def test_un_mes_sin_dias_libres_no_cobra_nada():
    pp = _params()
    pp.days_off = "[4,4,5,4,4,4,4,5,4,0,4,4]"
    e = _fila(_pos(), pp, month=10)                       # octubre cerrado: 0
    assert e.c6002_day_off == Decimal("0")


def test_con_el_calendario_vacio_el_dia_libre_sigue_siendo_manual():
    e = _fila(_pos(), _params())
    e.c6002_day_off = Decimal("88.88")
    recalculate_entry(e, _pos(), 1, TC, CCSS, AGU, params=_params())
    assert e.c6002_day_off == Decimal("88.88")


# ── 10. el reparto tiene que cubrir TODAS las filas ──────────────────────────
def test_una_fila_fuera_del_reparto_deja_monto_viejo():
    """Si una fila no entra al reparto, se queda con lo del reparto anterior y el
    total se pasa del monto de la póliza. Paso en produccion: 24 filas protegidas
    quedaron fuera y el INS repartio $2,677.55 en vez de $2,641.51."""
    todas = _plantel(2, meses=1)
    repartir_beneficio(todas, "c6022_occ_hazard", Decimal("1060000"), TC_MES)
    assert sum(e.c6022_occ_hazard for e, _ in todas) == Decimal("2000.00")

    # segunda corrida dejando una fila fuera
    parcial = todas[:1]
    repartir_beneficio(parcial, "c6022_occ_hazard", Decimal("530000"), TC_MES)
    total = sum(e.c6022_occ_hazard for e, _ in todas)
    assert total == Decimal("2000.00"), (
        "la fila excluida conservo su monto viejo: el reparto se paso del monto")


def test_el_reparto_reinicia_todas_las_filas_que_recibe():
    filas = _plantel(2, meses=1)
    for e, _ in filas:
        e.c6022_occ_hazard = Decimal("999")
    repartir_beneficio(filas, "c6022_occ_hazard", Decimal("530000"), TC_MES)
    assert sum(e.c6022_occ_hazard for e, _ in filas) == Decimal("1000.00")


def test_las_filas_protegidas_entran_al_reparto():
    """Proteger una fila es no PISAR su planilla importada, no dejarla fuera del
    reparto. Se comprueba sobre el codigo del orquestador."""
    import inspect
    from app.engine import recalculate
    src = inspect.getsource(recalculate._recalc_payroll)
    i_prot = src.index("protegidas += 1")
    i_cont = src.index("continue", i_prot)
    assert "para_ins.append" in src[i_prot:i_cont], (
        "la fila protegida sale del bucle sin entrar al reparto de beneficios")
