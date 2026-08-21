# -*- coding: utf-8 -*-
"""El país de origen sale del `res_statistics1` de Opera, por MES y con pax.

**El pedido (owner, 18-ago-2026).** «Yo tengo este XML de Opera donde están los
países de dónde viene la gente. Los países acá listados son los más
importantes; cualquiera que no se encuentre va a Others. Ocupo me los subas por
mes y agregar los pax.»

Antes de construir se midió el archivo real (212 días, enero–julio 2026):

    ene 688 noches / 1.276 pax     may 256 / 469
    feb 684 / 1.272                jun 284 / 454
    mar 721 / 1.401                jul 267 / 582
    abr 503 /   943                       ──────
                                   total 3.403 / 6.397

Las noches por mes son **idénticas** a las del On the Books del mismo año, que
llega por otro camino. Dos fuentes independientes dando el mismo número.
"""
import pytest

from app.importers.opera_country_stats import (
    OTROS, nombre_de, parse_country_stats, plegar_a_lista,
)


def _xml(dias: list[tuple[str, list[tuple[str, float, float]]]]) -> bytes:
    """dias = [(business_date, [(codigo_pais, noches, pax)])]"""
    p = ["<RES_STATISTICS1><LIST_G_5><G_5><LIST_DAY>"]
    for fecha, mercados in dias:
        p.append(f"<DAY><RESORT>COWLCR</RESORT><BUSINESS_DATE>{fecha}</BUSINESS_DATE><LIST_MARKET>")
        for cod, noches, pax in mercados:
            p.append(
                f"<MARKET><MASTER_VALUE>{cod}</MASTER_VALUE><LIST_DETAIL><DETAIL>"
                f"<NO_DEFINITE_ROOMS>{noches}</NO_DEFINITE_ROOMS>"
                f"<IN_GUEST>{pax}</IN_GUEST></DETAIL></LIST_DETAIL></MARKET>")
        p.append("</LIST_MARKET></DAY>")
    p.append("</LIST_DAY></G_5></LIST_G_5></RES_STATISTICS1>")
    return "".join(p).encode("utf-8")


def test_agrega_los_dias_del_mes():
    xml = _xml([("01-JAN-26", [("US", 3, 6)]),
                ("02-JAN-26", [("US", 2, 5)]),
                ("01-FEB-26", [("US", 7, 9)])])
    d = parse_country_stats(xml)
    assert d[(2026, 1, "United States")] == {"rooms": 5.0, "pax": 11.0}
    assert d[(2026, 2, "United States")] == {"rooms": 7.0, "pax": 9.0}


def test_UK_y_GB_son_EL_MISMO_pais():
    """⚠️ Opera emite los dos: el código legado `UK` y el ISO `GB`.

    En el archivo del owner son 439 + 176 = 615 noches. Separados, el Reino
    Unido se parte en dos filas y una de ellas se cae del top — sin que nada
    lo avise.
    """
    assert nombre_de("UK") == nombre_de("GB") == "United Kingdom"
    d = parse_country_stats(_xml([("01-JAN-26", [("UK", 10, 20), ("GB", 5, 9)])]))
    assert list(d) == [(2026, 1, "United Kingdom")]
    assert d[(2026, 1, "United Kingdom")] == {"rooms": 15.0, "pax": 29.0}


def test_el_pax_no_se_pierde():
    """El pax estaba VACÍO en pantalla: cero filas de la métrica `pax`."""
    d = parse_country_stats(_xml([("05-MAR-26", [("CR", 4, 11)])]))
    assert d[(2026, 3, "Costa Rica")]["pax"] == 11.0


def test_lo_que_no_esta_en_la_lista_va_a_Others():
    d = parse_country_stats(_xml([("01-JAN-26", [("US", 10, 20), ("DE", 3, 6), ("FR", 2, 4)])]))
    plegado, cajon = plegar_a_lista(d, ["United States"])
    assert plegado[(2026, 1, "United States")]["rooms"] == 10
    assert plegado[(2026, 1, OTROS)]["rooms"] == 5      # 3 + 2
    assert plegado[(2026, 1, OTROS)]["pax"] == 10       # 6 + 4


def test_plegar_no_pierde_ni_una_noche():
    """La suma después de plegar tiene que ser la misma que antes."""
    d = parse_country_stats(_xml([
        ("01-JAN-26", [("US", 10, 20), ("DE", 3, 6), ("XX", 1, 2)]),
        ("02-JAN-26", [("FR", 2, 4), ("US", 5, 8)]),
    ]))
    antes = sum(v["rooms"] for v in d.values())
    plegado, _ = plegar_a_lista(d, ["United States"])
    assert sum(v["rooms"] for v in plegado.values()) == antes


def test_dice_QUE_cayo_en_Others_y_cuanto():
    """⚠️ No es decoración: es lo que permite decidir a quién promover.

    Con el archivo del owner, Alemania (64 noches), Francia (53) y España (45)
    quedan fuera de la lista y son MÁS GRANDES que Suecia (33) o Dinamarca
    (20), que sí están. Sin este detalle eso no se ve.
    """
    d = parse_country_stats(_xml([("01-JAN-26", [("US", 10, 20), ("DE", 6, 9), ("FR", 3, 5)])]))
    _plegado, cajon = plegar_a_lista(d, ["United States"])
    assert [c["pais"] for c in cajon] == ["Germany", "France"], "ordenado por noches"
    assert cajon[0]["rooms"] == 6


def test_el_NULL_no_es_un_pais_pero_no_se_descarta():
    """35 noches sin país en el archivo del owner. Van a Others: si se
    descartaran, el total dejaría de cuadrar contra el On the Books."""
    d = parse_country_stats(_xml([("01-JAN-26", [("{NULL}", 4, 7), ("US", 1, 2)])]))
    plegado, _ = plegar_a_lista(d, ["United States"])
    assert plegado[(2026, 1, OTROS)]["rooms"] == 4


def test_un_codigo_desconocido_conserva_su_codigo():
    """Se ve raro en pantalla, que es mejor que desaparecer sin ruido."""
    assert nombre_de("ZZ") == "ZZ"


def test_multi_anio_queda_separado():
    d = parse_country_stats(_xml([("01-JAN-26", [("US", 1, 2)]),
                                  ("01-JAN-27", [("US", 9, 9)])]))
    assert d[(2026, 1, "United States")]["rooms"] == 1
    assert d[(2027, 1, "United States")]["rooms"] == 9


def test_el_endpoint_escribe_las_DOS_metricas():
    """El pax era justo lo que faltaba: no puede quedar solo `rooms`."""
    import inspect

    from app.api import revenue_api

    src = inspect.getsource(revenue_api.import_country_xml)
    assert "COUNTRY_METRICS" in src, "tiene que recorrer las dos métricas"
    assert "en_others" in src, "tiene que devolver qué cayó en Others"


def test_el_endpoint_no_pasa_por_el_candado():
    """Un país de origen es un hecho del PMS, no una cifra del presupuesto."""
    import inspect

    from app.api import revenue_api

    src = inspect.getsource(revenue_api.import_country_xml)
    assert "await candado(" not in src
