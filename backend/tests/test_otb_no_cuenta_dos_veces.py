# -*- coding: utf-8 -*-
"""El On the Books no puede contar el mismo día dos veces.

**El defecto (owner, 2026-08-18).** «Hay algo incorrecto acá, no sé de dónde
sale total revenue 6315043, ninguno de los escenarios tiene ese saldo.»

No salía de ningún escenario: era el snapshot W34 del OTB, y estaba al doble.
La prueba estaba en la propia pantalla — enero con **132,3% de ocupación**:
1.353 noches vendidas en un hotel de 30 habitaciones, cuando el actual de ese
mes fueron 683. Casi exactamente el doble.

**La causa.** El XML de Opera trae dos bloques `G_REC_TYPE` —A_STAT (History)
y B_FORE (Forecast)— y el parser recorría el árbol entero con `root.iter()`,
juntando los días de los dos. El importador después SUMABA las filas repetidas.
El diseño daba por hecho que History cubría el pasado y Forecast el futuro sin
pisarse; en el archivo del owner se solapan.

El comentario de la función que sumaba ya lo advertía: «el revenue mensual
habría sumado ese día DOBLE en silencio». Estaba escrito y pasó igual, porque
nada lo verificaba.
"""
import pytest

from app.importers.opera_history_forecast import (
    dias_duplicados, elegir_por_dia, parse_history_forecast,
)


def _xml(bloques: list[tuple[str, list[tuple[str, float, float, float]]]]) -> bytes:
    """bloques = [(rec_type, [(fecha, rooms, revenue, pax)])]"""
    partes = ["<HISTORY_FORECAST>"]
    for tipo, dias in bloques:
        partes.append(f"<G_REC_TYPE><REC_TYPE>{tipo}</REC_TYPE>")
        for fecha, rooms, rev, pax in dias:
            partes.append(
                f"<G_CONSIDERED_DATE><CONSIDERED_DATE>{fecha}</CONSIDERED_DATE>"
                f"<NO_ROOMS>{rooms}</NO_ROOMS><REVENUE>{rev}</REVENUE>"
                f"<NO_PERSONS>{pax}</NO_PERSONS></G_CONSIDERED_DATE>")
        partes.append("</G_REC_TYPE>")
    partes.append("</HISTORY_FORECAST>")
    return "".join(partes).encode("utf-8")


#: El caso del owner: el MISMO día en los dos bloques, con el mismo dato.
SOLAPADO = _xml([
    ("A_STAT", [("01-JAN-26", 20, 10_000, 35), ("02-JAN-26", 22, 11_000, 40)]),
    ("B_FORE", [("01-JAN-26", 20, 10_000, 35), ("15-JUL-26", 18, 9_000, 30)]),
])


def test_el_parser_dice_de_que_bloque_viene_cada_dia():
    filas = parse_history_forecast(SOLAPADO)
    assert len(filas) == 4
    assert {f["rec_type"] for f in filas} == {"history", "forecast"}


def test_un_dia_en_los_dos_bloques_se_cuenta_UNA_vez():
    """Es el bug: antes sumaba y el 1-ene daba 40 noches y $20.000."""
    dias = elegir_por_dia(parse_history_forecast(SOLAPADO))
    assert dias[(2026, 1, 1)]["rooms_sold"] == 20
    assert dias[(2026, 1, 1)]["revenue"] == 10_000
    # Y el total del archivo no se infla.
    assert sum(v["rooms_sold"] for v in dias.values()) == 20 + 22 + 18
    assert sum(v["revenue"] for v in dias.values()) == 30_000


def test_cuando_se_pisan_gana_HISTORY():
    """Lo ocurrido le gana a la proyección de un día que ya pasó."""
    xml = _xml([
        ("A_STAT", [("01-JAN-26", 20, 10_000, 35)]),
        ("B_FORE", [("01-JAN-26", 99, 99_000, 99)]),
    ])
    dias = elegir_por_dia(parse_history_forecast(xml))
    assert dias[(2026, 1, 1)]["rooms_sold"] == 20, "tenía que ganar History"


def test_dentro_de_un_mismo_bloque_SI_se_suma():
    """Opera abre el día por market o tipo de habitación: ahí son partes."""
    xml = _xml([("A_STAT", [("01-JAN-26", 12, 6_000, 20),
                            ("01-JAN-26", 8, 4_000, 15)])])
    dias = elegir_por_dia(parse_history_forecast(xml))
    assert dias[(2026, 1, 1)]["rooms_sold"] == 20
    assert dias[(2026, 1, 1)]["revenue"] == 10_000


def test_se_puede_saber_cuantos_dias_venian_repetidos():
    """Para poder decirlo en la respuesta del import, no adivinarlo."""
    assert dias_duplicados(parse_history_forecast(SOLAPADO)) == [(2026, 1, 1)]


def test_un_xml_sin_bloques_sigue_leyendose():
    """Hay plantillas que no emiten G_REC_TYPE. Sin esto devolvería vacío."""
    xml = ("<HISTORY_FORECAST><G_CONSIDERED_DATE>"
           "<CONSIDERED_DATE>03-MAR-26</CONSIDERED_DATE><NO_ROOMS>9</NO_ROOMS>"
           "<REVENUE>4500</REVENUE><NO_PERSONS>12</NO_PERSONS>"
           "</G_CONSIDERED_DATE></HISTORY_FORECAST>").encode()
    dias = elegir_por_dia(parse_history_forecast(xml))
    assert dias[(2026, 3, 3)]["rooms_sold"] == 9


def test_el_multianio_sigue_funcionando():
    """El horizonte del owner llega a 5 años en el mismo archivo."""
    xml = _xml([("B_FORE", [("01-JAN-26", 5, 100, 8), ("01-JAN-30", 7, 200, 9)])])
    dias = elegir_por_dia(parse_history_forecast(xml))
    assert {k[0] for k in dias} == {2026, 2030}


def test_el_importador_usa_la_regla_nueva():
    import inspect

    from app.api import revenue_api

    src = inspect.getsource(revenue_api._otb_agrega_por_dia)
    assert "elegir_por_dia" in src, "el importador tiene que dejar de sumar todo"


def test_el_importador_rechaza_una_ocupacion_imposible():
    """El candado: un mes no puede vender más noches de las que tiene."""
    import inspect

    from app.api import revenue_api

    src = inspect.getsource(revenue_api.import_otb_xml)
    # ⚠️ Antes esto buscaba el texto «ocupación imposible» en el fuente. Al
    # pasar los mensajes al catálogo bilingüe (2026-08-19) ese texto se fue de
    # acá, y la línea quedó coincidiendo con un COMENTARIO: si alguien borraba
    # la guarda y dejaba el comentario, seguía pasando. Ahora mira la clave,
    # que es código.
    assert "otb.ocupacion_imposible" in src
    assert "ErrorApi(422" in src
    assert "calendar.monthrange" in src
