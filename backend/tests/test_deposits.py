# -*- coding: utf-8 -*-
"""Lo que el Deposit Ledger no puede equivocarse.

Cuatro cosas, y las cuatro ya se podían romper en silencio:

1. **La fecha dd-mm-yy.** `05-11-26` es el 5 de noviembre. Leerla al revés
   movería de mes la mitad del ledger sin que nada falle.
2. **El signo.** El XML trae el depósito negativo y así se guarda; el análisis
   lo da vuelta. Si alguien normaliza al importar, la pestaña «Ledger» deja de
   ser fiel al archivo y nadie lo nota.
3. **La comparación cuadra.** entraron − salieron + subieron + bajaron tiene
   que dar exactamente la variación del total. Si no, se perdió una reserva por
   el camino y el reporte miente con cara de autoridad.
4. **Salieron ≠ cancelaron.** Una reserva que desaparece del ledger pudo
   hospedarse, cancelar o que le devolvieran la plata. El motor reporta que
   salió de custodia y nada más.
"""
from datetime import date

import pytest

from app.engine import deposits as motor
from app.importers import deposit_xml as dx

XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<DEPOSIT_LEDGER>
  <LIST_G_1>
    <G_1>
      <RESV_NAME_ID>111</RESV_NAME_ID>
      <ARRIVAL>05-11-26</ARRIVAL>
      <SNAME>UNOA</SNAME><NAME>Uno,A</NAME><ROOM>22</ROOM>
      <TOTAL_PAID_AMT>-5019.76</TOTAL_PAID_AMT>
      <DEPARTURE>09-11-26</DEPARTURE>
      <CONFIRMATION_NO>599823308</CONFIRMATION_NO>
      <EXTERNAL_REFERENCE></EXTERNAL_REFERENCE>
      <LAST_DATE>07-09-26</LAST_DATE>
      <RESV_STATUS>CC</RESV_STATUS><GUARANTEE_CODE>CC</GUARANTEE_CODE>
      <TRUNC_ARRIVAL>05-NOV-26</TRUNC_ARRIVAL>
    </G_1>
    <G_1>
      <RESV_NAME_ID>222</RESV_NAME_ID>
      <ARRIVAL>03-12-26</ARRIVAL>
      <SNAME>DOSB</SNAME><NAME>Dos,B</NAME><ROOM>14</ROOM>
      <TOTAL_PAID_AMT>-1000</TOTAL_PAID_AMT>
      <DEPARTURE>06-12-26</DEPARTURE>
      <CONFIRMATION_NO>591649167</CONFIRMATION_NO>
      <EXTERNAL_REFERENCE></EXTERNAL_REFERENCE>
      <LAST_DATE>25-10-26</LAST_DATE>
      <RESV_STATUS>DP</RESV_STATUS><GUARANTEE_CODE>DP</GUARANTEE_CODE>
      <TRUNC_ARRIVAL>03-DEC-26</TRUNC_ARRIVAL>
    </G_1>
  </LIST_G_1>
</DEPOSIT_LEDGER>"""


# ───────────────────────────────── el lector ────────────────────────────────
def test_la_fecha_es_dia_mes_anio():
    """`05-11-26` es el 5 de noviembre, no el 11 de mayo."""
    filas = {f["resv_name_id"]: f for f in dx.leer(XML)}
    assert filas["111"]["arrival"] == "2026-11-05"
    assert filas["111"]["departure"] == "2026-11-09"
    assert filas["111"]["last_date"] == "2026-09-07"
    assert filas["222"]["arrival"] == "2026-12-03"


def test_trunc_arrival_manda_sobre_arrival():
    """Con el mes en letras no hay ambigüedad posible: esa gana."""
    xml = XML.replace(b"<ARRIVAL>05-11-26</ARRIVAL>", b"<ARRIVAL>11-05-26</ARRIVAL>")
    filas = {f["resv_name_id"]: f for f in dx.leer(xml)}
    assert filas["111"]["arrival"] == "2026-11-05"   # el TRUNC dice 05-NOV-26


def test_el_signo_del_xml_se_respeta():
    """En el archivo el depósito es un crédito: negativo. Así se guarda."""
    filas = dx.leer(XML)
    assert all(f["total_paid_amt"] < 0 for f in filas)
    assert dx.resumen(filas)["total_amt"] == pytest.approx(-6019.76)


def test_el_analisis_lo_da_vuelta():
    """Plata en custodia: positiva. La vuelta se da en el motor, no al importar."""
    filas = dx.leer(XML)
    assert motor._bloque(filas)["monto"] == pytest.approx(6019.76)


def test_las_noches_salen_de_las_fechas():
    filas = {f["resv_name_id"]: f for f in dx.leer(XML)}
    assert filas["111"]["nights"] == 4
    assert filas["222"]["nights"] == 3


def test_el_corte_es_el_ultimo_movimiento():
    """El reporte no dice cuándo se corrió; el LAST_DATE mayor es la cota."""
    assert dx.corte_de(dx.leer(XML)) == "2026-10-25"


def test_un_xml_que_no_es_ledger_se_rechaza():
    with pytest.raises(dx.XmlNoEsDepositLedger):
        dx.leer(b"<HISTORY_FORECAST><G_CONSIDERED_DATE/></HISTORY_FORECAST>")


def test_una_reserva_sin_id_se_descarta():
    """Sin `RESV_NAME_ID` no se puede aparear entre cortes: no entra."""
    xml = XML.replace(b"<RESV_NAME_ID>222</RESV_NAME_ID>", b"<RESV_NAME_ID></RESV_NAME_ID>")
    assert [f["resv_name_id"] for f in dx.leer(xml)] == ["111"]


# ─────────────────────────────── por mes de llegada ─────────────────────────
def test_por_mes_de_llegada_separa_y_acumula():
    r = motor.por_mes_de_llegada(dx.leer(XML))
    assert [m["mes"] for m in r["meses"]] == ["2026-11", "2026-12"]
    assert r["meses"][0]["etiqueta"] == "NOV 2026"
    assert r["meses"][0]["monto"] == pytest.approx(5019.76)
    assert r["meses"][-1]["acumulado"] == pytest.approx(6019.76)
    assert r["meses"][-1]["pct_acumulado"] == pytest.approx(100.0)
    assert r["total"]["reservas"] == 2


def test_una_reserva_sin_llegada_no_se_pierde():
    """Va a su propio renglón, no al primer mes ni al limbo."""
    filas = dx.leer(XML)
    filas.append({"resv_name_id": "333", "arrival": None, "total_paid_amt": -500,
                  "nights": 0, "resv_status": "CC"})
    r = motor.por_mes_de_llegada(filas)
    assert r["sin_llegada"]["monto"] == pytest.approx(500)
    assert r["total"]["monto"] == pytest.approx(6519.76)
    assert sum(m["monto"] for m in r["meses"]) == pytest.approx(6019.76)


# ───────────────────────────────── antigüedad ───────────────────────────────
def test_antiguedad_por_tramos():
    r = motor.antiguedad(dx.leer(XML), corte="2026-11-04")
    tramos = {t["tramo"]: t for t in r["tramos"]}
    assert tramos["0–30"]["reservas"] == 1      # 25-oct → 10 días
    assert tramos["31–60"]["reservas"] == 1     # 07-set → 58 días
    assert sum(t["reservas"] for t in r["tramos"]) == 2


def test_llegadas_vencidas():
    """Un depósito contra una llegada que ya pasó es el hallazgo que importa."""
    filas = dx.leer(XML)
    assert motor.llegadas_vencidas(filas, corte="2026-11-04") == []
    v = motor.llegadas_vencidas(filas, corte="2026-11-20")
    assert [x["resv_name_id"] for x in v] == ["111"]
    assert v[0]["dias_vencido"] == 15


# ──────────────────────────────── comparación ───────────────────────────────
def _f(rid, monto, arr="2026-11-05", st="CC"):
    return {"resv_name_id": rid, "name": rid, "arrival": arr, "departure": None,
            "room": None, "resv_status": st, "nights": 3, "last_date": None,
            "total_paid_amt": -monto}


def test_comparar_separa_los_cuatro_grupos():
    antes = [_f("A", 100), _f("B", 200), _f("C", 300)]
    despues = [_f("B", 250), _f("C", 300), _f("D", 400)]   # A salió, D entró, B subió
    c = motor.comparar(antes, despues)
    assert [x["resv_name_id"] for x in c["entraron"]["filas"]] == ["D"]
    assert [x["resv_name_id"] for x in c["salieron"]["filas"]] == ["A"]
    assert [x["resv_name_id"] for x in c["subieron"]["filas"]] == ["B"]
    assert c["subieron"]["monto"] == pytest.approx(50)
    assert c["iguales"]["reservas"] == 1
    assert c["variacion"]["monto"] == pytest.approx(350)
    assert c["variacion"]["reservas"] == 0


def test_la_comparacion_cuadra_siempre():
    """entraron − salieron + subieron + bajaron == variación. Sin excepción."""
    casos = [
        ([_f("A", 100)], []),                                   # todo salió
        ([], [_f("A", 100)]),                                   # todo entró
        ([_f("A", 100), _f("B", 50)], [_f("A", 40)]),           # baja y salida
        ([_f("A", 100)], [_f("A", 100)]),                       # nada se movió
        ([_f("A", 1), _f("B", 2), _f("C", 3)],
         [_f("B", 9), _f("C", 3), _f("D", 4), _f("E", 5)]),
    ]
    for antes, despues in casos:
        assert motor.cuadre(motor.comparar(antes, despues)) == 0.0


def test_un_cambio_de_estado_se_anota():
    """Si la reserva sigue pero cambió de estado, la comparación lo dice."""
    c = motor.comparar([_f("A", 100, st="DP")], [_f("A", 150, st="CC")])
    assert c["subieron"]["filas"][0]["estado_antes"] == "DP"


def test_el_delta_de_una_devolucion_parcial_es_negativo():
    c = motor.comparar([_f("A", 500)], [_f("A", 200)])
    assert c["bajaron"]["filas"][0]["delta"] == pytest.approx(-300)
    assert c["salieron"]["reservas"] == 0          # no salió: sigue, con menos


def test_comparar_usa_el_id_y_no_el_nombre():
    """Opera solo garantiza estable el RESV_NAME_ID."""
    antes = [_f("A", 100)]
    despues = [{**_f("A", 100), "name": "Otro nombre completamente"}]
    c = motor.comparar(antes, despues)
    assert c["iguales"]["reservas"] == 1
    assert c["entraron"]["reservas"] == c["salieron"]["reservas"] == 0


# ──────────────────────────────── concentración ─────────────────────────────
def test_concentracion():
    r = motor.concentracion(dx.leer(XML), top=1)
    assert r["top"][0]["resv_name_id"] == "111"
    assert r["pct_top"] == pytest.approx(83.39, abs=0.01)
    assert r["reservas"] == 2


def test_resumen_completo_trae_todo():
    r = motor.resumen_completo(dx.leer(XML), corte="2026-11-04")
    assert set(r) == {"total", "por_mes", "por_estado", "por_garantia",
                      "antiguedad", "vencidos", "concentracion"}
    assert r["total"]["monto"] == pytest.approx(6019.76)
