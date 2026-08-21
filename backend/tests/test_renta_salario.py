"""Impuesto al salario por tramos — Costa Rica.

El impuesto es progresivo: cada tramo cobra su tasa SOBRE EL EXCESO del piso.
Estas pruebas fijan ese comportamiento, porque el error clásico es aplicar la
tasa del tramo al salario completo.
"""
import pytest

from app.engine.renta_salario import (TRAMOS_CR_2026, impuesto_mensual,
                                       normalizar_tramos, retencion_persona,
                                       tramo_de)


def test_exento_hasta_el_primer_techo():
    assert impuesto_mensual(918_000) == 0
    assert impuesto_mensual(500_000) == 0
    assert impuesto_mensual(0) == 0


def test_cobra_sobre_el_exceso_no_sobre_el_total():
    """₡1,000,000 paga 10% de ₡82,000 = ₡8,200. NO 10% de ₡1,000,000."""
    assert impuesto_mensual(1_000_000) == pytest.approx(8_200)


def test_acumula_tramo_por_tramo():
    # ₡2,000,000: 10% de (1,347,000−918,000) + 15% de (2,000,000−1,347,000)
    esperado = 0.10 * 429_000 + 0.15 * 653_000
    assert impuesto_mensual(2_000_000) == pytest.approx(esperado)


def test_tramo_mas_alto_sin_techo():
    # ₡6,000,000 recorre los cuatro tramos gravados
    esperado = (0.10 * (1_347_000 - 918_000)
                + 0.15 * (2_364_000 - 1_347_000)
                + 0.20 * (4_727_000 - 2_364_000)
                + 0.25 * (6_000_000 - 4_727_000))
    assert impuesto_mensual(6_000_000) == pytest.approx(esperado)


def test_en_el_borde_de_un_tramo_no_salta():
    """Justo en el techo de un tramo no puede haber un salto de impuesto."""
    for techo in (918_000, 1_347_000, 2_364_000, 4_727_000):
        antes = impuesto_mensual(techo)
        despues = impuesto_mensual(techo + 1)
        assert despues - antes < 1.0


def test_el_tramo_reportado():
    assert tramo_de(500_000) == 1
    assert tramo_de(1_000_000) == 2
    assert tramo_de(2_000_000) == 3
    assert tramo_de(3_000_000) == 4
    assert tramo_de(9_000_000) == 5


def test_convierte_con_el_tipo_de_cambio():
    """Los tramos están en colones y la planilla en dólares."""
    r = retencion_persona(base_usd=4_000, tc=500, deducir_ccss=False)
    assert r["base_crc"] == pytest.approx(2_000_000)
    assert r["impuesto_crc"] == pytest.approx(impuesto_mensual(2_000_000))
    assert r["impuesto_usd"] == pytest.approx(r["impuesto_crc"] / 500)


def test_deduce_la_ccss_obrera_de_la_base():
    con = retencion_persona(4_000, 500, ccss_obrera_rate=0.1067, deducir_ccss=True)
    sin = retencion_persona(4_000, 500, ccss_obrera_rate=0.1067, deducir_ccss=False)
    assert con["gravable_crc"] < sin["gravable_crc"]
    assert con["impuesto_crc"] < sin["impuesto_crc"]
    assert con["gravable_crc"] == pytest.approx(2_000_000 * (1 - 0.1067))


def test_salario_bajo_no_paga():
    r = retencion_persona(1_000, 500)      # ₡500,000
    assert r["impuesto_usd"] == 0
    assert r["tramo"] == 1


def test_sin_tipo_de_cambio_no_inventa():
    assert retencion_persona(4_000, 0)["impuesto_usd"] == 0


def test_tramos_invalidos_caen_a_la_tabla_oficial():
    assert normalizar_tramos(None) == TRAMOS_CR_2026
    assert normalizar_tramos([]) == TRAMOS_CR_2026
    assert normalizar_tramos("cualquier cosa") == TRAMOS_CR_2026


def test_tramos_propios_se_respetan_y_se_ordenan():
    propios = [{"desde": 1_000_000, "hasta": None, "tasa": 0.30},
               {"desde": 0, "hasta": 1_000_000, "tasa": 0.0}]
    t = normalizar_tramos(propios)
    assert t[0]["desde"] == 0
    assert impuesto_mensual(1_500_000, t) == pytest.approx(0.30 * 500_000)
