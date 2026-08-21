# -*- coding: utf-8 -*-
"""El costo repartido tiene que verse en el checkbook del que lo recibe.

El P&L suma DOS corrientes para un mismo par (departamento, cuenta): las
lineas del checkbook y lo que le cae por allocation. La pantalla solo mostraba
la primera, asi que el 0110 enseñaba $25,295.87 en la 7310 y se callaba los
$15,585.81 que recibe por reparto, y el 0162 no enseñaba nada aunque carga
$1,558.58 de costo de venta de lavanderia.

Estas filas van aparte y no se editan. Convertirlas en lineas de verdad del
checkbook las contaria dos veces.
"""
from decimal import Decimal
from types import SimpleNamespace

from app.api._allocated import agrupar_repartos


def _fila(dept, cuenta, mes, monto, origen="0161", base="KILOS"):
    return SimpleNamespace(
        target_dept=dept, account=cuenta, month=mes,
        amount_usd=Decimal(str(monto)), source_dept=origen, basis_type=base,
    )


def test_agrupa_los_12_meses_en_una_linea():
    filas = [_fila("0162", "5301", m, "130.00") for m in range(1, 13)]
    out = agrupar_repartos(filas)
    assert len(out) == 1
    linea = out[0]
    assert linea["account_code"] == "5301"
    assert linea["source_dept"] == "0161"
    assert linea["jan"] == "130.00"
    assert Decimal(linea["total"]) == Decimal("1560.00")


def test_nunca_es_editable():
    """Si la pantalla la dejara editar, el usuario escribiria un numero que el
    proximo recalculo le borra sin avisar."""
    out = agrupar_repartos([_fila("0162", "5301", 1, "130")])
    assert out[0]["editable"] is False


def test_una_cuenta_con_dos_origenes_no_se_mezcla():
    """La 7310 podria recibir de lavanderia y de otro reparto. Sumarlas en una
    sola linea esconde de donde viene cada parte."""
    filas = [
        _fila("0110", "7310", 1, "1000", origen="0161"),
        _fila("0110", "7310", 1, "250", origen="0220", base="FTE"),
    ]
    out = agrupar_repartos(filas)
    assert len(out) == 2
    por_origen = {l["source_dept"]: l for l in out}
    assert Decimal(por_origen["0161"]["total"]) == Decimal("1000")
    assert Decimal(por_origen["0220"]["total"]) == Decimal("250")
    assert por_origen["0220"]["basis_type"] == "FTE"


def test_cuenta_en_cero_no_ensucia_la_pantalla():
    out = agrupar_repartos([_fila("0162", "5301", m, "0") for m in range(1, 13)])
    assert out == []


def test_toma_el_nombre_del_mapeo():
    out = agrupar_repartos(
        [_fila("0162", "5301", 1, "130")],
        {"5301": "Costo Servicio Lavanderia (huespedes)"},
    )
    assert out[0]["account_name"] == "Costo Servicio Lavanderia (huespedes)"


def test_sin_repartos_no_devuelve_nada():
    assert agrupar_repartos([]) == []


def test_cada_pantalla_ve_su_clase_de_cuenta():
    """Un reparto de PLANILLA no puede aparecer dentro del checkbook de OPEX.

    Cada reparto usa su clase: lavanderia manda linen y uniformes a la 7310 y
    7685 (clase 7, gasto operativo) y el lavado de huespedes a la 5301 (clase
    5, costo de venta); cafeteria y salarios usan 6025 y 6000, que son PLANILLA
    y no tienen checkbook donde vivir. Sin filtro, el bloque de repartidos
    metia la 6000 en el checkbook de OPEX y el cuadro dejaba de cuadrar contra
    su propio total.
    """
    filas = [
        _fila("0183", "6000", 1, "1450", origen="0152", base="FTE"),   # salarios
        _fila("0183", "6025", 1, "300", origen="0220", base="FTE"),    # cafeteria
        _fila("0183", "7685", 1, "150", origen="0161", base="FTE"),    # uniformes
        _fila("0183", "5301", 1, "90", origen="0161"),                 # costo de venta
    ]
    def clases(cs):
        return sorted(l["account_code"] for l in agrupar_repartos(
            [f for f in filas if f.account[:1] in cs]))

    assert clases("7") == ["7685"]              # checkbook de OPEX
    assert clases("5") == ["5301"]              # checkbook de Costos
    assert clases("6") == ["6000", "6025"]      # planilla
    assert clases("") == []                     # sin clase no pasa ninguna
    # y sin filtrar, estan las cuatro
    assert len(agrupar_repartos(filas)) == 4
