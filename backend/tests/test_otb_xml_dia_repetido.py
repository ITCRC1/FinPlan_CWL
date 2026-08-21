# -*- coding: utf-8 -*-
"""On the Books · XML de Opera con el mismo día repetido dos veces.

Bug real de producción (2026-08-17, semana 28): `parse_history_forecast` usa
`root.iter("G_CONSIDERED_DATE")`, que recorre TODO el árbol — si Opera anida
el mismo día bajo más de un grupo (History y Forecast solapados en el día de
corte), (month, day) sale dos veces en la lista plana. El import insertaba
una fila de `otb_daily_occ` por cada entrada de la lista, sin agregar, y la
segunda chocaba contra la llave única (scenario, week, month, day) — 500,
"Failed to fetch" en el navegador, y el escenario quedaba sin la semana
cargada. `_otb_agrega_por_dia` es el fix: agrega antes de insertar.

⚠️ **CORREGIDO EL 2026-08-18.** El primer arreglo AGREGABA SUMANDO, y eso
estaba mal: los dos bloques del XML del owner se solapan en TODO el año, no
solo en el día de corte, así que el On the Books salía al doble —enero con
132% de ocupación y $6.315.043 contra $4.872.775 de presupuesto—. Sumar
resolvía el choque de llave única y creaba un error peor, que además no
reventaba: daba un número grande y plausible.

Ahora entre bloques se ELIGE uno (gana History, que es lo ocurrido) y solo se
suma DENTRO de un mismo bloque, donde las filas sí son partes de un día. Lo
cubre `test_otb_no_cuenta_dos_veces`; acá se conserva lo que este archivo
protegía de verdad: que un día repetido no tumbe la carga.
"""
from app.api.revenue_api import _otb_agrega_por_dia
from app.importers.opera_history_forecast import parse_history_forecast

XML_DIA_REPETIDO = """<?xml version="1.0"?>
<HISTORY_FORECAST>
  <G_REC_TYPE>
    <REC_TYPE>A_STAT</REC_TYPE>
    <G_CONSIDERED_DATE>
      <CONSIDERED_DATE>01-JAN-26</CONSIDERED_DATE>
      <NO_ROOMS>25</NO_ROOMS>
      <REVENUE>12000</REVENUE>
      <NO_PERSONS>40</NO_PERSONS>
    </G_CONSIDERED_DATE>
  </G_REC_TYPE>
  <G_REC_TYPE>
    <REC_TYPE>B_FORE</REC_TYPE>
    <G_CONSIDERED_DATE>
      <CONSIDERED_DATE>01-JAN-26</CONSIDERED_DATE>
      <NO_ROOMS>25</NO_ROOMS>
      <REVENUE>12000</REVENUE>
      <NO_PERSONS>40</NO_PERSONS>
    </G_CONSIDERED_DATE>
    <G_CONSIDERED_DATE>
      <CONSIDERED_DATE>02-JAN-26</CONSIDERED_DATE>
      <NO_ROOMS>10</NO_ROOMS>
      <REVENUE>5000</REVENUE>
      <NO_PERSONS>15</NO_PERSONS>
    </G_CONSIDERED_DATE>
  </G_REC_TYPE>
</HISTORY_FORECAST>
"""


def test_el_parser_refleja_el_xml_tal_cual_duplicado_incluido():
    """El parser NO deduplica — es un espejo fiel del XML. La responsabilidad
    de agregar es del import, no del parser (así el parser sigue sirviendo
    para inspeccionar el archivo crudo si hace falta)."""
    filas = parse_history_forecast(XML_DIA_REPETIDO.encode())
    ene1 = [r for r in filas if r["month"] == 1 and r["day"] == 1]
    assert len(ene1) == 2, "el 1-ene tiene que aparecer 2 veces: así lo trae el XML"


def test_un_dia_repetido_no_tumba_la_carga_ni_se_duplica():
    """Lo que este archivo protege: el día repetido sale UNA vez, así que no
    choca contra la llave única. Y —desde el 2026-08-18— tampoco se suma:
    25 + 25 daría 50 noches de un día que tuvo 25."""
    filas = parse_history_forecast(XML_DIA_REPETIDO.encode())
    por_dia = _otb_agrega_por_dia(filas)
    assert len(por_dia) == 2  # 1-ene y 2-ene, no 3 filas
    assert por_dia[(2026, 1, 1)]["rooms_sold"] == 25.0    # el de History, no 50
    assert por_dia[(2026, 1, 1)]["revenue"] == 12000.0
    assert por_dia[(2026, 1, 2)]["rooms_sold"] == 10.0    # el día sin duplicar, intacto


def test_el_parser_saca_el_ano_real_de_la_fecha():
    """"01-JAN-26" -> year=2026. El horizonte multi-año del owner (forecast
    hasta 5 años adelante en el mismo XML) depende de esto: sin año propio,
    todo caía en el mismo balde de 12 meses sin importar a qué año pertenecía."""
    filas = parse_history_forecast(XML_DIA_REPETIDO.encode())
    assert all(r["year"] == 2026 for r in filas)


def test_dia_sin_duplicar_no_se_altera():
    filas = [{"year": 2027, "month": 3, "day": 15, "rooms_sold": 8.0, "revenue": 3200.0, "pax": 12.0}]
    por_dia = _otb_agrega_por_dia(filas)
    assert por_dia == {(2027, 3, 15): {"rooms_sold": 8.0, "revenue": 3200.0, "pax": 12.0}}


def test_anos_distintos_no_se_mezclan():
    """El mismo (month, day) en dos años distintos son dos días DISTINTOS —
    no se pueden sumar entre sí como si fueran el mismo (era el bug antes de
    que `year` existiera como columna)."""
    filas = [
        {"year": 2026, "month": 6, "day": 1, "rooms_sold": 20.0, "revenue": 9000.0, "pax": 30.0},
        {"year": 2027, "month": 6, "day": 1, "rooms_sold": 5.0, "revenue": 2000.0, "pax": 8.0},
    ]
    por_dia = _otb_agrega_por_dia(filas)
    assert len(por_dia) == 2
    assert por_dia[(2026, 6, 1)]["rooms_sold"] == 20.0
    assert por_dia[(2027, 6, 1)]["rooms_sold"] == 5.0
