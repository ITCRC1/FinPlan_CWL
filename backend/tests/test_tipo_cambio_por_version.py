# -*- coding: utf-8 -*-
"""
EL TIPO DE CAMBIO VIVE POR VERSIÓN Y VIAJA CON ELLA.

El TC mueve todo lo que está en colones: salarios, CCSS, aguinaldo, vacaciones,
el reparto del INS y los beneficios. Si una copia no se lleva el TC del original,
calcula la misma planilla con OTRO dólar y da cifras distintas sin que se vea por qué.
"""
from decimal import Decimal

import pytest

from app.api.scenarios_api import COPY_DATASETS, DEFAULT_COPY_DATASETS
from app.engine.payroll_calculator import calc_sw
from app.models.exchange_rate import ExchangeRate, get_tc_for_month
from app.models.payroll_position import PayrollPosition


def test_el_tc_viaja_al_copiar_una_version():
    """Si `rates` sale de la lista por defecto, la copia hereda otro dólar."""
    assert "rates" in DEFAULT_COPY_DATASETS, (
        "el TC no viaja al copiar: la copia calcularía la planilla en colones con "
        "un dólar distinto al del original")
    assert ExchangeRate in COPY_DATASETS["rates"]


def _pos(salario="530000"):
    p = PayrollPosition(dept_code="0111", position_name="X", employee_name="Y",
                        salary_amount=Decimal(salario), salary_currency="CRC")
    for m in ("jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"):
        setattr(p, f"fte_{m}", Decimal("1.0"))
    return p


def test_el_tc_cambia_el_salario_en_dolares():
    """La razón por la que el TC tiene que estar ligado a la versión."""
    assert calc_sw(_pos(), 1, Decimal("530")) == Decimal("1000.00")
    assert calc_sw(_pos(), 1, Decimal("500")) == Decimal("1060.00")


def test_cada_mes_puede_tener_su_tc():
    rates = [ExchangeRate(scenario_id="s", hotel_id="CWL", month=m, year=2027,
                          tc_crc_usd=Decimal("530") + m) for m in range(1, 13)]
    assert get_tc_for_month(rates, 1) == Decimal("531")
    assert get_tc_for_month(rates, 12) == Decimal("542")


def test_un_mes_sin_tc_usa_el_anterior():
    """Fallback documentado: sin fila exacta se toma el mes anterior más cercano."""
    rates = [ExchangeRate(scenario_id="s", hotel_id="CWL", month=1, year=2027,
                          tc_crc_usd=Decimal("530"))]
    assert get_tc_for_month(rates, 7) == Decimal("530")


def test_sin_ningun_tc_es_un_error_explicito():
    with pytest.raises(ValueError):
        get_tc_for_month([], 1)


# ── El TC que varía mes a mes ────────────────────────────────────────────────
# El owner adelantó que al inicio del año se usa un TC parejo pero después cambia
# mes a mes. Eso rompe cualquier cálculo que tome un solo TC para todo el año.
from app.engine.payroll_calculator import repartir_beneficio        # noqa: E402
from app.models.payroll_concept_entry import PayrollConceptEntry    # noqa: E402


def _filas(meses=12):
    p = _pos()
    out = []
    for m in range(1, meses + 1):
        e = PayrollConceptEntry(scenario_id="s", position_id="p",
                                dept_code="0111", month=m, year=2027)
        e.c6022_occ_hazard = Decimal("0")
        out.append((e, p))
    return out


TC_VARIABLE = {m: Decimal("520") + m * 5 for m in range(1, 13)}   # 525 … 580


def test_cada_mes_se_convierte_con_su_propio_tc():
    """Un monto en colones repartido parejo da MENOS dólares en los meses caros."""
    filas = _filas()
    repartir_beneficio(filas, "c6022_occ_hazard", Decimal("1200000"), TC_VARIABLE)
    ene = filas[0][0].c6022_occ_hazard      # 100,000 / 525
    dic = filas[11][0].c6022_occ_hazard     # 100,000 / 580
    assert ene == Decimal("190.48")
    assert dic == Decimal("172.41")
    assert ene > dic, "el mes con el colón más débil debe costar menos dólares"


def test_el_reparto_en_colones_cuadra_aunque_el_tc_varie():
    filas = _filas()
    repartir_beneficio(filas, "c6022_occ_hazard", Decimal("1200000"), TC_VARIABLE)
    en_colones = sum(e.c6022_occ_hazard * TC_VARIABLE[e.month] for e, _ in filas)
    assert abs(en_colones - Decimal("1200000")) <= Decimal("12")   # centavo por fila


def test_un_monto_ya_en_dolares_no_se_convierte():
    """El costo de un departamento ya está en USD: pasarlo a colones con el TC de
    enero y devolverlo mes a mes daba cifras equivocadas."""
    filas = _filas()
    total = repartir_beneficio(filas, "c6025_cafeteria", Decimal("1200"),
                               TC_VARIABLE, en_usd=True)
    assert total == Decimal("1200.00")
    assert all(e.c6025_cafeteria == Decimal("100.00") for e, _ in filas)


def test_el_error_del_tc_unico_es_medible():
    """Con TC parejo los dos caminos coinciden; con TC variable, no."""
    tc_parejo = {m: Decimal("530") for m in range(1, 13)}
    a = _filas()
    repartir_beneficio(a, "c6022_occ_hazard", Decimal("6360"), tc_parejo, en_usd=True)
    b = _filas()
    repartir_beneficio(b, "c6022_occ_hazard", Decimal("6360"), TC_VARIABLE, en_usd=True)
    assert sum(e.c6022_occ_hazard for e, _ in a) == sum(e.c6022_occ_hazard for e, _ in b)


def test_el_reparto_de_beneficios_viaja_al_copiar():
    """Sin BenefitAllocationConfig en la copia, el INS (y cualquier reparto) queda
    en cero en la version nueva y nadie se entera."""
    from app.models.benefit_allocation_config import BenefitAllocationConfig
    assert BenefitAllocationConfig in COPY_DATASETS["allocations"]
    assert "allocations" in DEFAULT_COPY_DATASETS
