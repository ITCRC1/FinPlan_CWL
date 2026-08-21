# -*- coding: utf-8 -*-
"""El factor neto de los canales — el defecto del 9,5640.

**Qué pasaba.** `compute_net_factor` sumaba `mezcla × (1 − comisión)` **sin
dividir**, y los canales se guardan POR MES (`UNIQUE (escenario, canal, mes)`).
Con las 36 filas de un escenario devolvía **9,5640**: doce veces el 0,7970
real. Un factor mayor que 1 no es un factor — multiplicaría el ingreso de
comida, tours y traslado por nueve.

**Qué tan cerca estaba de morder.** Medido en producción el 2026-08-20: ocho
escenarios —los presupuestos 2028 a 2035— tienen 36 canales y **cero tarifas**,
así que `_effective_net_factor` devuelve `None` y caen a este cálculo. Hoy
multiplican cero porque están vacíos; el camino se abre en cuanto alguien
cargue tarifas netas dejando el rack en cero, porque ahí la ocupación **sí**
acumula.
"""
from decimal import Decimal

import pytest

from app.models.sales_channel_config import compute_net_factor


class _Canal:
    def __init__(self, canal, mezcla, comision, mes=1):
        self.channel, self.month = canal, mes
        self.mix_pct, self.commission_pct = Decimal(mezcla), Decimal(comision)


def _mes(mes):
    """Los tres canales de CWL para un mes: 60/5/35 con 28%/20%/0%."""
    return [_Canal("TA", "0.60", "0.28", mes),
            _Canal("OTA", "0.05", "0.20", mes),
            _Canal("DIRECT", "0.35", "0", mes)]


# ── El defecto ──────────────────────────────────────────────────────────────

def test_UN_FACTOR_NETO_NUNCA_PUEDE_PASAR_DE_UNO():
    """⚠️ **La prueba que sostiene el arreglo.** Es aritmética, no gusto: el
    factor es «cuánto de cada dólar le queda al hotel». Mayor que 1 significaría
    que cobra más de lo que factura."""
    doce_meses = [c for m in range(1, 13) for c in _mes(m)]
    assert len(doce_meses) == 36
    nf = compute_net_factor(doce_meses)
    assert nf <= Decimal("1"), f"devolvió {nf}: el defecto volvió"
    assert Decimal("0.82") < nf < Decimal("0.83")


def test_los_doce_meses_dan_LO_MISMO_que_uno():
    """Si la mezcla no cambia mes a mes, pasar doce meses o uno tiene que dar
    el mismo número. Antes daba doce veces más."""
    uno = compute_net_factor(_mes(1))
    doce = compute_net_factor([c for m in range(1, 13) for c in _mes(m)])
    assert uno == doce


def test_el_valor_es_el_de_produccion():
    """0,60×0,72 + 0,05×0,80 + 0,35×1,00 = **0,8220**, el del Budget 2026 Final.

    ⚠️ No confundir con el 0,7970 del tarifario: ése sale de `neto/rack` de las
    tarifas, no de los canales. Son dos números distintos con el mismo nombre, y
    ahí es fácil dar por bueno el equivocado.
    """
    nf = compute_net_factor(_mes(1))
    assert nf.quantize(Decimal("0.0001")) == Decimal("0.8220")


# ── La trampa del arreglo obvio ─────────────────────────────────────────────

def test_UN_ESCENARIO_CON_CANALES_EN_UN_SOLO_MES_NO_SE_CAE_EN_LOS_DEMAS():
    """⚠️ **Por esto no alcanzaba con filtrar por mes.**

    El Budget 2026 Final tiene sus tres canales **sólo en el mes 1**. Filtrar a
    secas le habría dado factor **0** de febrero a diciembre — o sea ingreso de
    paquetes en cero, un defecto peor que el que se venía a arreglar.
    """
    solo_enero = _mes(1)
    for mes in range(1, 13):
        nf = compute_net_factor(solo_enero, mes)
        assert nf > 0, f"el mes {mes} quedó en cero"
        assert nf == compute_net_factor(solo_enero, 1)


def test_cuando_SI_hay_filas_del_mes_se_usan_esas():
    """Una mezcla estacional tiene que respetarse: en el mes que tiene filas
    propias manda ese mes, no el promedio del año."""
    canales = _mes(1) + [_Canal("DIRECT", "1.00", "0", 7)]   # julio: todo directo
    assert compute_net_factor(canales, 7) == Decimal("1")
    assert compute_net_factor(canales, 1).quantize(Decimal("0.0001")) == Decimal("0.8220")


# ── Los bordes ──────────────────────────────────────────────────────────────

def test_sin_canales_devuelve_cero_y_no_revienta():
    assert compute_net_factor([]) == Decimal("0")
    assert compute_net_factor([], 7) == Decimal("0")


def test_una_mezcla_en_cero_no_divide_por_cero():
    """Tres canales al 0% de mezcla: el peso es cero. Reventar acá tumbaría el
    recálculo del escenario entero."""
    vacios = [_Canal("TA", "0", "0.28"), _Canal("OTA", "0", "0.20")]
    assert compute_net_factor(vacios) == Decimal("0")


def test_una_mezcla_que_no_suma_uno_igual_da_un_promedio_valido():
    """⚠️ Con la división, una mezcla mal cargada —que suma 0,8 o 1,3— sigue
    dando un promedio ponderado entre 0 y 1. Antes, sumar sin dividir
    propagaba el error de carga directo al ingreso."""
    mal = [_Canal("TA", "0.90", "0.28"), _Canal("DIRECT", "0.40", "0")]
    nf = compute_net_factor(mal)
    assert Decimal("0") < nf <= Decimal("1")


@pytest.mark.parametrize("comision", ["0", "0.28", "1"])
def test_el_factor_queda_entre_cero_y_uno_para_cualquier_comision(comision):
    nf = compute_net_factor([_Canal("TA", "1", comision)])
    assert Decimal("0") <= nf <= Decimal("1")


# ── El caller pasa el mes ───────────────────────────────────────────────────

def test_el_motor_de_revenue_le_pasa_el_MES():
    """Sin el mes, un escenario con mezcla estacional usaría el promedio del
    año en los doce meses."""
    import inspect

    from app.engine import revenue_calculator

    fuente = inspect.getsource(revenue_calculator.calculate_revenue)
    assert "compute_net_factor(channels, month)" in fuente
