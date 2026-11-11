# -*- coding: utf-8 -*-
"""Un forecast rodante arma su mayor con los meses cerrados del ACTUAL.

Amarena, 2026-11-11: el GL de los Forecast 2026 no pegaba con la utilidad del
P&L (−$62,311.92 y −$22,845.96) porque la grilla leía enero–julio de los
checkbooks del forecast mientras el P&L los tomaba del ACTUAL.
"""
from decimal import Decimal

from app.engine.gl_por_mes import MESES, mezclar_por_corte


def _fila(dept, cuenta, montos, nombre=""):
    return {"dept_code": dept, "account_code": cuenta, "account_name": nombre,
            "outlet": "", **{m: Decimal(str(v)) for m, v in zip(MESES, montos)}}


def test_meses_cerrados_del_actual_y_abiertos_propios():
    propias = [_fila("0110", "7065", [100] * 12)]
    reales = [_fila("0110", "7065", [7] * 12, "CLEANING")]
    [f] = mezclar_por_corte(propias, reales, 3)
    assert [f[m] for m in MESES] == [7, 7, 7] + [100] * 9
    assert f["account_name"] == "CLEANING"


def test_cuenta_solo_real_y_cuenta_solo_propia():
    propias = [_fila("0120", "5101", [50] * 12)]
    reales = [_fila("0182", "7020", [9] * 12)]
    filas = {f["account_code"]: f for f in mezclar_por_corte(propias, reales, 2)}
    assert [filas["7020"][m] for m in MESES] == [9, 9] + [0] * 10
    assert [filas["5101"][m] for m in MESES] == [0, 0] + [50] * 10


def test_fila_que_solo_tiene_movimiento_del_lado_que_no_manda_se_descarta():
    propias = [_fila("0110", "7100", [10, 10] + [0] * 10)]   # solo meses cerrados
    reales = [_fila("0110", "7105", [0] * 11 + [5])]         # solo mes abierto
    assert mezclar_por_corte(propias, reales, 2) == []


def test_la_suma_es_la_del_actual_hasta_el_corte_mas_la_propia_despues():
    propias = [_fila("0110", "4000", [-1000] * 12), _fila("0113", "6000", [300] * 12)]
    reales = [_fila("0110", "4000", [-800] * 12), _fila("0113", "6000", [250] * 12)]
    total = sum(f[m] for f in mezclar_por_corte(propias, reales, 7) for m in MESES)
    assert total == 7 * (-800 + 250) + 5 * (-1000 + 300)
