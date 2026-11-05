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


# ─────────────────────────── rango de fechas de llegada ─────────────────────
def _r(rid, arr, monto, st="CC"):
    return {"resv_name_id": rid, "name": rid, "arrival": arr, "departure": None,
            "room": None, "resv_status": st, "nights": 3, "last_date": None,
            "total_paid_amt": -monto}


LOTE = [_r("A", "2026-12-19", 100), _r("B", "2026-12-20", 200),
        _r("C", "2026-12-25", 300), _r("D", "2026-12-31", 400),
        _r("E", "2027-01-01", 500), _r("F", None, 600)]


def test_el_rango_incluye_los_dos_extremos():
    """«Del 20 al 31 de diciembre» son doce días, con el 20 y el 31 adentro.

    Dejar un extremo afuera es el error que nadie ve: el total baja, se ve
    plausible, y no hay nada que lo delate.
    """
    dentro = motor.en_rango(LOTE, "2026-12-20", "2026-12-31")
    assert [f["resv_name_id"] for f in dentro] == ["B", "C", "D"]
    assert motor._bloque(dentro)["monto"] == pytest.approx(900)


def test_el_rango_deja_afuera_el_dia_anterior_y_el_siguiente():
    dentro = motor.en_rango(LOTE, "2026-12-20", "2026-12-31")
    fuera = {f["resv_name_id"] for f in LOTE} - {f["resv_name_id"] for f in dentro}
    assert fuera == {"A", "E", "F"}      # 19-dic, 1-ene y la que no tiene llegada


def test_un_rango_de_un_solo_dia_trae_ese_dia():
    dentro = motor.en_rango(LOTE, "2026-12-25", "2026-12-25")
    assert [f["resv_name_id"] for f in dentro] == ["C"]


def test_un_extremo_suelto_deja_el_otro_lado_abierto():
    assert [f["resv_name_id"] for f in motor.en_rango(LOTE, "2026-12-25", None)] == ["C", "D", "E"]
    assert [f["resv_name_id"] for f in motor.en_rango(LOTE, None, "2026-12-20")] == ["A", "B"]
    assert len(motor.en_rango(LOTE)) == 5          # todas menos la que no tiene llegada


def test_una_reserva_sin_llegada_nunca_entra_a_un_rango_pero_se_reporta():
    """No puede desaparecer en silencio: si no, la suma de los rangos no cuadra
    contra el total y nadie sabe por qué."""
    r = motor.rango(LOTE, "2026-12-01", "2027-12-31")
    assert "F" not in [f["resv_name_id"] for f in r["filas"]]
    assert r["sin_llegada"]["monto"] == pytest.approx(600)


def test_el_rango_dice_cuanto_pesa_del_corte():
    r = motor.rango(LOTE, "2026-12-20", "2026-12-31")
    assert r["total"]["monto"] == pytest.approx(900)
    assert r["pct_del_corte"] == pytest.approx(900 / 2100 * 100, abs=0.01)
    assert r["dias"] == 12                          # del 20 al 31, los dos adentro


def test_el_rango_trae_los_mismos_analisis_que_el_corte():
    r = motor.rango(LOTE, "2026-12-20", "2026-12-31")
    assert set(r) >= {"total", "pct_del_corte", "dias", "por_dia", "por_estado",
                      "concentracion", "antiguedad", "filas", "sin_llegada"}
    assert sum(x["reservas"] for x in r["por_estado"]) == 3


def test_por_dia_ordena_y_no_inventa_dias_vacios():
    r = motor.rango(LOTE, "2026-12-20", "2026-12-31")
    assert [d["fecha"] for d in r["por_dia"]] == ["2026-12-20", "2026-12-25", "2026-12-31"]
    assert [d["monto"] for d in r["por_dia"]] == [200, 300, 400]


def test_un_rango_vacio_no_revienta():
    r = motor.rango(LOTE, "2027-06-01", "2027-06-30")
    assert r["total"] == {"reservas": 0, "monto": 0.0, "promedio": 0.0, "noches": 0}
    assert r["filas"] == [] and r["por_dia"] == []
    assert r["pct_del_corte"] == 0.0


def test_los_rangos_que_parten_el_corte_suman_el_total():
    """Dos ventanas pegadas, sin huecos ni solapes, tienen que dar el total de
    las que SÍ tienen llegada."""
    a = motor.en_rango(LOTE, None, "2026-12-25")
    b = motor.en_rango(LOTE, "2026-12-26", None)
    con_llegada = [f for f in LOTE if f["arrival"]]
    assert (motor._bloque(a)["monto"] + motor._bloque(b)["monto"]
            == pytest.approx(motor._bloque(con_llegada)["monto"]))
    assert len(a) + len(b) == len(con_llegada)


def test_el_rango_sobre_el_archivo_real():
    """Diciembre completo del ledger de prueba: el mes que más depósito tiene."""
    filas = dx.leer(XML)
    r = motor.rango(filas, "2026-12-01", "2026-12-31")
    assert [f["resv_name_id"] for f in r["filas"]] == ["222"]
    assert r["total"]["monto"] == pytest.approx(1000)


# ──────────────────────── saldo por cobrar (OTB + IVA − depósito) ───────────
OTB = {(2026, 12): {"total": 417440.90, "rooms": 290194.70, "noches": 464.0},
       (2027, 1): {"total": 632913.00, "rooms": 409442.00, "noches": 500.0}}


def _d(rid, arr, dep, monto):
    return {"resv_name_id": rid, "name": rid, "arrival": arr, "departure": dep,
            "room": None, "resv_status": "CC", "nights": 4, "last_date": None,
            "total_paid_amt": -monto}


def test_la_formula_del_saldo_es_la_del_owner():
    """saldo = OTB total revenue × (1 + IVA) − depósitos. Nada más."""
    r = motor.por_cobrar(OTB, [_d("A", "2026-12-10", "2026-12-14", 380783.77)])
    dic = next(m for m in r["meses"] if (m["year"], m["month"]) == (2026, 12))
    assert dic["otb_total"] == pytest.approx(417440.90)
    assert dic["iva"] == pytest.approx(417440.90 * 0.13, abs=0.01)
    assert dic["con_iva"] == pytest.approx(417440.90 * 1.13, abs=0.01)
    assert dic["deposito"] == pytest.approx(380783.77)
    assert dic["saldo"] == pytest.approx(417440.90 * 1.13 - 380783.77, abs=0.01)


def test_el_iva_se_le_suma_al_otb_y_no_al_deposito():
    """El OTB viene SIN impuestos; el depósito es lo que el huésped ya pagó, con
    impuesto adentro. Aplicarle el 13% al depósito inflaría lo cobrado."""
    r = motor.por_cobrar({(2026, 12): {"total": 1000.0}},
                         [_d("A", "2026-12-10", "2026-12-14", 500)])
    dic = r["meses"][0]
    assert dic["con_iva"] == pytest.approx(1130.0)
    assert dic["deposito"] == pytest.approx(500.0)      # intacto
    assert dic["saldo"] == pytest.approx(630.0)


def test_sin_el_iva_el_saldo_seria_otro():
    """La prueba de que el 13% hace algo: sin él, el saldo baja $130."""
    con = motor.por_cobrar({(2026, 12): {"total": 1000.0}},
                           [_d("A", "2026-12-10", "2026-12-14", 500)])["meses"][0]
    sin = motor.por_cobrar({(2026, 12): {"total": 1000.0}},
                           [_d("A", "2026-12-10", "2026-12-14", 500)], iva=0.0)["meses"][0]
    assert con["saldo"] - sin["saldo"] == pytest.approx(130.0)


def test_el_pct_cobrado_se_mide_contra_el_total_con_iva():
    r = motor.por_cobrar({(2026, 12): {"total": 1000.0}},
                         [_d("A", "2026-12-10", "2026-12-14", 565)])
    assert r["meses"][0]["pct_cobrado"] == pytest.approx(50.0)


def test_las_reservas_que_cruzan_el_mes_se_reportan():
    """Su depósito está entero en el mes de llegada y su ingreso no: el que lee
    tiene que poder ver de cuánta plata se trata."""
    filas = [_d("A", "2026-12-28", "2027-01-03", 13795.44),   # cruza
             _d("B", "2026-12-10", "2026-12-14", 5000.00)]    # no cruza
    dic = motor.por_cobrar(OTB, filas)["meses"][0]
    assert dic["cruzan"]["reservas"] == 1
    assert dic["cruzan"]["monto"] == pytest.approx(13795.44)
    assert dic["deposito"] == pytest.approx(18795.44)   # las dos cuentan completas


def test_un_mes_con_deposito_y_sin_otb_se_marca():
    """Una llegada más allá del horizonte del forecast: no hay saldo que calcular."""
    r = motor.por_cobrar(OTB, [_d("A", "2028-10-23", "2028-10-27", 80052.75)])
    oct28 = next(m for m in r["meses"] if (m["year"], m["month"]) == (2028, 10))
    assert oct28["sin_otb"] is True
    assert oct28["otb_total"] == 0 and oct28["pct_cobrado"] is None


def test_un_mes_con_otb_y_sin_deposito_debe_todo():
    r = motor.por_cobrar({(2027, 3): {"total": 453837.0}}, [])
    mar = r["meses"][0]
    assert mar["deposito"] == 0
    assert mar["saldo"] == pytest.approx(453837.0 * 1.13, abs=0.01)
    assert mar["pct_cobrado"] == 0.0


def test_los_meses_ya_cerrados_se_marcan_y_no_entran_al_saldo_abierto():
    """El OTB trae el año entero; el ledger, solo llegadas futuras. Un mes
    cerrado daría «nos deben el mes completo» y eso no es un saldo."""
    otb = {(2026, 1): {"total": 862234.0}, (2026, 12): {"total": 417440.90}}
    r = motor.por_cobrar(otb, [_d("A", "2026-12-10", "2026-12-14", 380783.77)],
                         corte="2026-11-04")
    ene = next(m for m in r["meses"] if m["month"] == 1)
    dic = next(m for m in r["meses"] if m["month"] == 12)
    assert ene["pasado"] is True and dic["pasado"] is False
    assert r["total_abierto"]["saldo"] == pytest.approx(dic["saldo"], abs=0.01)
    assert r["total_pasado"]["saldo"] == pytest.approx(ene["saldo"], abs=0.01)
    assert r["total"]["saldo"] == pytest.approx(
        r["total_abierto"]["saldo"] + r["total_pasado"]["saldo"], abs=0.01)


def test_el_mes_del_corte_sigue_abierto():
    """El corte es el 4 de noviembre: noviembre todavía no cerró."""
    r = motor.por_cobrar({(2026, 11): {"total": 239564.0}}, [], corte="2026-11-04")
    assert r["meses"][0]["pasado"] is False


def test_el_mes_anterior_al_corte_ya_cerro():
    r = motor.por_cobrar({(2026, 10): {"total": 1072.0}}, [], corte="2026-11-04")
    assert r["meses"][0]["pasado"] is True


def test_los_totales_son_la_suma_de_los_meses():
    filas = [_d("A", "2026-12-10", "2026-12-14", 1000),
             _d("B", "2027-01-05", "2027-01-09", 2000)]
    r = motor.por_cobrar(OTB, filas, corte="2026-11-04")
    assert r["total"]["otb_total"] == pytest.approx(sum(m["otb_total"] for m in r["meses"]))
    assert r["total"]["deposito"] == pytest.approx(3000)
    assert r["total"]["saldo"] == pytest.approx(
        r["total"]["con_iva"] - r["total"]["deposito"], abs=0.01)


def test_una_reserva_sin_llegada_no_entra_a_ningun_mes_pero_se_reporta():
    filas = [_d("A", "2026-12-10", "2026-12-14", 1000),
             {"resv_name_id": "X", "arrival": None, "departure": None,
              "total_paid_amt": -700, "nights": 0, "resv_status": "CC"}]
    r = motor.por_cobrar(OTB, filas)
    assert r["total"]["deposito"] == pytest.approx(1000)
    assert r["sin_llegada"]["monto"] == pytest.approx(700)
