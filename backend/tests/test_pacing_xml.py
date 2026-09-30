# -*- coding: utf-8 -*-
"""Lectura de los XML del PACING (`app/importers/pacing_xml.py`)."""
import pytest

from app.importers import pacing_xml as px


def _hf(dias_hist, dias_fore, rev=100.0):
    def g(d, rn, r):
        return (f"<G_CONSIDERED_DATE><CONSIDERED_DATE>{d}</CONSIDERED_DATE><NO_ROOMS>{rn}</NO_ROOMS>"
                f"<REVENUE>{r}</REVENUE><CF_CALC_INV_ROOMS>30</CF_CALC_INV_ROOMS><CF_OOO_ROOMS>0</CF_OOO_ROOMS>"
                f"<COMPLIMENTARY_ROOMS>0</COMPLIMENTARY_ROOMS><GRP_DEDUCT_ROOMS>1</GRP_DEDUCT_ROOMS>"
                f"<ARRIVAL_ROOMS>2</ARRIVAL_ROOMS><NO_PERSONS>4</NO_PERSONS></G_CONSIDERED_DATE>")
    h = "".join(g(d, 5, rev) for d in dias_hist)
    f = "".join(g(d, 3, rev) for d in dias_fore)
    return (f"<HISTORY_FORECAST><LIST_G_REC_TYPE>"
            f"<G_REC_TYPE><REC_TYPE>A_STAT</REC_TYPE><LIST_G_CONSIDERED_DATE>{h}</LIST_G_CONSIDERED_DATE></G_REC_TYPE>"
            f"<G_REC_TYPE><REC_TYPE>B_FORE</REC_TYPE><LIST_G_CONSIDERED_DATE>{f}</LIST_G_CONSIDERED_DATE></G_REC_TYPE>"
            f"</LIST_G_REC_TYPE></HISTORY_FORECAST>").encode()


def _resv(filas):
    def g(f):
        return ("<G_ROOM>" + "".join(f"<{k}>{v}</{k}>" for k, v in f.items()) + "</G_ROOM>")
    return ("<RESENTEREDON><LIST_G_ROOM>" + "".join(g(f) for f in filas)
            + "</LIST_G_ROOM></RESENTEREDON>").encode()


def test_detecta_los_dos_reportes_y_rechaza_lo_demas():
    assert px.tipo_de(_hf(["01-JAN-26"], [])) == px.TIPO_HF
    assert px.tipo_de(_resv([{"RESV_NAME_ID": 1, "INSERT_DATE": "01-01-26"}])) == px.TIPO_RESERVAS
    with pytest.raises(px.XmlNoReconocido):
        px.tipo_de(b"<OTRA_COSA/>")
    with pytest.raises(px.XmlNoReconocido):
        px.tipo_de(b"no es xml")


def test_el_corte_es_el_primer_dia_forecast_y_history_manda():
    # El 02-JAN aparece en los dos bloques: History gana, y un día con historia
    # ya pasó — el corte es el primer día que SÓLO tiene Forecast.
    r = px.leer_history_forecast(_hf(["01-JAN-26", "02-JAN-26"], ["02-JAN-26", "03-JAN-26"]))
    assert r["as_of"] == "2026-01-03"
    assert r["has_forecast"] is True
    assert r["days"]["2026-01-02"][0] == 5 and r["days"]["2026-01-02"][8] == 1
    assert r["days"]["2026-01-03"][0] == 3 and r["days"]["2026-01-03"][8] == 0
    assert r["date_from"] == "2026-01-01" and r["date_to"] == "2026-01-03"


def test_sin_forecast_el_corte_es_el_dia_siguiente_al_ultimo():
    r = px.leer_history_forecast(_hf(["30-DEC-25", "31-DEC-25"], []))
    assert r["as_of"] == "2026-01-01" and r["has_forecast"] is False


def test_las_pseudo_habitaciones_PI_se_descartan_y_el_estado_se_normaliza():
    base = {"INSERT_DATE": "21-11-25", "ARRIVAL": "10-12-26", "NIGHTS": 3, "NO_OF_ROOMS": 1,
            "SHARE_AMOUNT_PER_STAY": 1500, "SHARE_AMOUNT": 500, "RATE_CODE": "BAR"}
    r = px.leer_reservas(_resv([
        {**base, "RESV_NAME_ID": 1, "RESV_STATUS": "RESERVED", "ROOM_CATEGORY_LABEL": "TH"},
        {**base, "RESV_NAME_ID": 2, "RESV_STATUS": "CANCELLED", "ROOM_CATEGORY_LABEL": "TH"},
        {**base, "RESV_NAME_ID": 3, "RESV_STATUS": "RESERVED", "ROOM_CATEGORY_LABEL": "PI"},
    ]))
    assert r["cuenta"] == 2 and r["descartadas_pi"] == 1
    a, x = r["reservas"]
    assert (a["id"], a["st"], a["ins"], a["arr"], a["amt"]) == ("1", "A", "2025-11-21", "2026-12-10", 1500)
    assert x["st"] == "X"


def test_rooms_y_total_se_asignan_por_monto_no_por_nombre():
    arch = [{"nombre": "b.xml", "tipo": px.TIPO_HF, "date_from": "a", "date_to": "b", "as_of": "c",
             "total_revenue": 900},
            {"nombre": "a.xml", "tipo": px.TIPO_HF, "date_from": "a", "date_to": "b", "as_of": "c",
             "total_revenue": 500}]
    px.asignar_tipos(arch)
    assert arch[0]["kind"] == "total" and arch[1]["kind"] == "rooms"
    solo = [{"nombre": "x.xml", "tipo": px.TIPO_HF, "date_from": "a", "date_to": "b", "as_of": "d",
             "total_revenue": 1}]
    px.asignar_tipos(solo)
    assert solo[0]["kind"] == "total" and solo[0]["kind_detectado"] == "confirmar"
