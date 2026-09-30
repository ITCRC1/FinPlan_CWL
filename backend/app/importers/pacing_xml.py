# -*- coding: utf-8 -*-
"""Lectura de los XML de Opera que alimentan el módulo PACING.

Dos reportes, los dos de Oracle Reports:

* **History & Forecast** (`<HISTORY_FORECAST>`): un día por `G_CONSIDERED_DATE`,
  agrupados en bloques `G_REC_TYPE` History (A_STAT) y Forecast (B_FORE). El
  mismo reporte sale en dos versiones —Rooms Only y Total Revenue— con las
  mismas noches y distinto ingreso.
* **Reservations Entered On** (`<RESENTEREDON>`): una fila por reserva con su
  fecha de creación (`INSERT_DATE`), llegada, noches, tarifa y estado.

A diferencia de `opera_history_forecast.py` —que sirve al On the Books semanal
y sólo necesita noches, ingreso y pax— acá se lee todo lo que el pacing usa:
inventario, fuera de servicio, cortesías y grupos. Ese parser no se toca: su
contrato lo prueban `test_otb_xml_dia_repetido` y compañía.

⚠️ **La fecha de corte sale del archivo.** Es el primer día Forecast: History
llega hasta ayer. Un archivo sin Forecast (sólo historia, por ejemplo un año ya
cerrado) toma como corte el día siguiente al último.

⚠️ **Las pseudo-habitaciones se descartan.** En CWL `ROOM_CATEGORY_LABEL = PI`
son cuentas maestras («Lost Interface Posting» y similares): 2.133 de 4.815
líneas del primer archivo. Contarlas inventa noches que no existen.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, timedelta

_MON = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8,
        "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12, "ENE": 1, "ABR": 4, "AGO": 8, "DIC": 12}
_HISTORY = ("A_STAT", "HISTORY", "STAT")
_FORECAST = ("B_FORE", "FORECAST", "FORE")

TIPO_HF = "history_forecast"
TIPO_RESERVAS = "reservations"


class XmlNoReconocido(ValueError):
    """El XML no es ninguno de los dos reportes que entiende el pacing."""


def tipo_de(xml_bytes: bytes) -> str:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise XmlNoReconocido(f"XML inválido: {e}") from e
    tag = root.tag.upper()
    if tag == "HISTORY_FORECAST" or root.find(".//G_CONSIDERED_DATE") is not None:
        return TIPO_HF
    if tag == "RESENTEREDON" or root.find(".//G_ROOM/INSERT_DATE") is not None:
        return TIPO_RESERVAS
    raise XmlNoReconocido(f"no es History & Forecast ni Reservations Entered On ({root.tag})")


def _num(node, tag) -> float:
    v = node.findtext(tag)
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _fecha_mon(txt: str | None) -> str | None:
    """`01-JAN-26` → `2026-01-01`."""
    if not txt:
        return None
    p = txt.strip().split("-")
    if len(p) != 3:
        return None
    mes = _MON.get(p[1].strip().upper())
    try:
        d, y = int(p[0]), int(p[2])
    except ValueError:
        return None
    if not mes:
        return None
    y = 2000 + y if y < 100 else y
    try:
        return date(y, mes, d).isoformat()
    except ValueError:
        return None


def _fecha_num(txt: str | None) -> str | None:
    """`21-11-25` → `2025-11-21` (formato del Entered On)."""
    if not txt:
        return None
    p = txt.strip().split("-")
    if len(p) != 3:
        return _fecha_mon(txt)
    try:
        d, m, y = int(p[0]), int(p[1]), int(p[2])
    except ValueError:
        return _fecha_mon(txt)
    y = 2000 + y if y < 100 else y
    try:
        return date(y, m, d).isoformat()
    except ValueError:
        return None


def _es_history(bloque) -> bool | None:
    crudo = ""
    for tag in ("REC_TYPE", "REC_TYPE_DESC", "CF_REC_TYPE"):
        crudo = (bloque.findtext(tag) or "").strip()
        if crudo:
            break
    u = crudo.upper()
    if any(u.startswith(p) for p in _HISTORY):
        return True
    if any(u.startswith(p) for p in _FORECAST):
        return False
    return None


def leer_history_forecast(xml_bytes: bytes) -> dict:
    """`{as_of, has_forecast, date_from, date_to, total_revenue, days}`.

    `days[fecha] = [rn, rev, inv, ooo, comp, grp, arr, pax, hist]`. Dentro de un
    bloque las partes del mismo día se suman; entre bloques gana History.
    """
    root = ET.fromstring(xml_bytes)
    por_bloque: dict[tuple[str, int], list[float]] = {}
    for bloque in root.iter("G_REC_TYPE"):
        h = _es_history(bloque)
        prio = 0 if h else (1 if h is False else 2)
        for g in bloque.iter("G_CONSIDERED_DATE"):
            d = _fecha_mon(g.findtext("CONSIDERED_DATE"))
            if not d:
                continue
            fila = [_num(g, "NO_ROOMS"), _num(g, "REVENUE"), _num(g, "CF_CALC_INV_ROOMS"),
                    _num(g, "CF_OOO_ROOMS"), _num(g, "COMPLIMENTARY_ROOMS"),
                    _num(g, "GRP_DEDUCT_ROOMS") + _num(g, "GRP_NON_DEDUCT_ROOMS"),
                    _num(g, "ARRIVAL_ROOMS"), _num(g, "NO_PERSONS")]
            acc = por_bloque.setdefault((d, prio), [0.0] * 8)
            for k in range(8):
                acc[k] += fila[k]
    elegido: dict[str, tuple[int, list[float]]] = {}
    for (d, prio), v in por_bloque.items():
        if d not in elegido or prio < elegido[d][0]:
            elegido[d] = (prio, v)
    if not elegido:
        return {"days": {}}
    days = {}
    for d, (prio, v) in sorted(elegido.items()):
        v = [round(x, 2) for x in v]
        days[d] = [*v, 1 if prio == 0 else 0]
    fechas = sorted(days)
    forecast = [d for d in fechas if not days[d][8]]
    as_of = forecast[0] if forecast else (date.fromisoformat(fechas[-1]) + timedelta(days=1)).isoformat()
    return {"as_of": as_of, "has_forecast": bool(forecast), "date_from": fechas[0], "date_to": fechas[-1],
            "total_revenue": round(sum(v[1] for v in days.values()), 2), "days": days}


def _estado(txt: str) -> str:
    u = (txt or "").upper()
    if "CANCEL" in u:
        return "X"
    if "NO SHOW" in u:
        return "N"
    if "PROSPECT" in u or "WAIT" in u:
        return "P"
    return "A"


def leer_reservas(xml_bytes: bytes) -> dict:
    """`{reservas: [...], cuenta, descartadas_pi, min_ins, max_ins}`."""
    root = ET.fromstring(xml_bytes)
    out, pi = [], 0
    for g in root.iter("G_ROOM"):
        t = lambda tag: (g.findtext(tag) or "").strip()
        if t("ROOM_CATEGORY_LABEL").upper() == "PI":
            pi += 1
            continue
        rid, ins, arr = t("RESV_NAME_ID"), _fecha_num(t("INSERT_DATE")), _fecha_num(t("ARRIVAL"))
        if not rid or not ins or not arr:
            continue
        try:
            nts = int(float(t("NIGHTS") or 0))
        except ValueError:
            nts = 0
        try:
            rms = int(float(t("NO_OF_ROOMS") or 1)) or 1
        except ValueError:
            rms = 1
        out.append({"id": rid, "ins": ins, "arr": arr, "nts": nts, "rms": rms,
                    "amt": round(_num(g, "SHARE_AMOUNT_PER_STAY"), 2), "st": _estado(t("RESV_STATUS")),
                    "fl": t("COMP_HOUSE_YN")[:2],
                    "ch": (t("C_T_S_NAME") or t("COMPANY_NAME") or t("TRAVEL_AGENT_NAME"))[:80],
                    "rate": t("RATE_CODE")[:20], "blk": 1 if t("GROUP_NAME") else 0,
                    "room_type": t("ROOM_CATEGORY_LABEL")[:20], "guest": t("FULL_NAME")[:80],
                    "grupo": t("GROUP_NAME")[:80], "garantia": t("GUARANTEE_CODE")[:20],
                    "pax": int(_num(g, "PERSONS")), "tarifa_noche": round(_num(g, "SHARE_AMOUNT"), 2)})
    fechas = [r["ins"] for r in out]
    return {"reservas": out, "cuenta": len(out), "descartadas_pi": pi,
            "min_ins": min(fechas) if fechas else None, "max_ins": max(fechas) if fechas else None}


def asignar_tipos(archivos: list[dict]) -> None:
    """Rooms Only vs Total Revenue, sin depender del nombre del archivo.

    Dos History & Forecast del mismo rango: el de MAYOR ingreso es Total. Uno
    suelto queda como Total salvo que se diga otra cosa — y se marca para que la
    pantalla pida confirmarlo.
    """
    hf = [a for a in archivos if a.get("tipo") == TIPO_HF and not a.get("error")]
    grupos: dict[tuple, list[dict]] = {}
    for a in hf:
        grupos.setdefault((a["date_from"], a["date_to"], a["as_of"]), []).append(a)
    for g in grupos.values():
        if len(g) == 2:
            g.sort(key=lambda a: a["total_revenue"])
            g[0]["kind"], g[1]["kind"] = "rooms", "total"
            for a in g:
                a["kind_detectado"] = "par"
        else:
            for a in g:
                a.setdefault("kind", "total")
                a["kind_detectado"] = "confirmar"
