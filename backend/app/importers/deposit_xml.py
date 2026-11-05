# -*- coding: utf-8 -*-
"""Lectura del Deposit Ledger de Opera (`<DEPOSIT_LEDGER>`).

Un XML de Oracle Reports con una fila `G_1` por reserva que tiene depósito
cobrado. Trece campos, todos string, sin anidar.

    <G_1>
      <RESV_NAME_ID>78239860</RESV_NAME_ID>
      <ARRIVAL>05-11-26</ARRIVAL>          dd-mm-yy
      <NAME>Haralovich,Bryan</NAME>
      <ROOM>22</ROOM>
      <TOTAL_PAID_AMT>-5019.76</TOTAL_PAID_AMT>
      <DEPARTURE>09-11-26</DEPARTURE>
      <LAST_DATE>07-09-26</LAST_DATE>      último movimiento del depósito
      <RESV_STATUS>CC</RESV_STATUS>
      <TRUNC_ARRIVAL>05-NOV-26</TRUNC_ARRIVAL>
      …
    </G_1>

⚠️ **`ARRIVAL` es dd-mm-yy, no mm-dd-yy.** `05-11-26` es el 5 de noviembre y no
el 11 de mayo. Lo confirma `TRUNC_ARRIVAL`, que trae el mes con letras
(`05-NOV-26`): por eso, cuando las dos vienen, **manda TRUNC_ARRIVAL**. Leer al
revés movería de mes la mitad del ledger sin que nada falle.

⚠️ **El signo no se toca.** Ver `app/models/deposit.py`.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date

_MON = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7,
        "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
        "ENE": 1, "ABR": 4, "AGO": 8, "DIC": 12}

CAMPOS = ("resv_name_id", "confirmation_no", "name", "sname", "room", "arrival",
          "departure", "last_date", "resv_status", "guarantee_code",
          "external_reference", "total_paid_amt", "nights")


class XmlNoEsDepositLedger(ValueError):
    """El archivo no es un Deposit Ledger."""


def es_deposit_ledger(xml_bytes: bytes) -> bool:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return False
    return root.tag.upper() == "DEPOSIT_LEDGER" or root.find(".//TOTAL_PAID_AMT") is not None


def _texto(nodo, tag: str) -> str | None:
    v = nodo.findtext(tag)
    v = (v or "").strip()
    return v or None


def _num(nodo, tag: str) -> float:
    v = nodo.findtext(tag)
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _fecha_mon(txt: str | None) -> str | None:
    """`05-NOV-26` → `2026-11-05`. El mes con letras no admite ambigüedad."""
    if not txt:
        return None
    p = txt.strip().split("-")
    if len(p) != 3:
        return None
    mes = _MON.get(p[1].strip().upper())
    if not mes:
        return None
    try:
        d, y = int(p[0]), int(p[2])
        return date(2000 + y if y < 100 else y, mes, d).isoformat()
    except ValueError:
        return None


def _fecha_num(txt: str | None) -> str | None:
    """`05-11-26` → `2026-11-05` (día-mes-año, como todo Opera en esta propiedad)."""
    if not txt:
        return None
    p = txt.strip().split("-")
    if len(p) != 3:
        return None
    if not p[1].isdigit():
        return _fecha_mon(txt)
    try:
        d, m, y = int(p[0]), int(p[1]), int(p[2])
        return date(2000 + y if y < 100 else y, m, d).isoformat()
    except ValueError:
        return None


def _noches(llegada: str | None, salida: str | None) -> int:
    if not llegada or not salida:
        return 0
    try:
        n = (date.fromisoformat(salida) - date.fromisoformat(llegada)).days
    except ValueError:
        return 0
    return n if n > 0 else 0


def leer(xml_bytes: bytes) -> list[dict]:
    """Devuelve una fila por reserva, con las fechas ya en ISO."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise XmlNoEsDepositLedger(f"XML inválido: {e}") from e
    nodos = root.findall(".//G_1")
    if not nodos:
        raise XmlNoEsDepositLedger(
            f"no trae reservas G_1 (raíz <{root.tag}>): ¿es un Deposit Ledger?")

    filas = []
    for n in nodos:
        rid = _texto(n, "RESV_NAME_ID")
        if not rid:
            continue                       # sin id no se puede comparar entre cortes
        # TRUNC_ARRIVAL manda: trae el mes con letras y no se puede leer al revés.
        llegada = _fecha_mon(_texto(n, "TRUNC_ARRIVAL")) or _fecha_num(_texto(n, "ARRIVAL"))
        salida = _fecha_num(_texto(n, "DEPARTURE"))
        filas.append({
            "resv_name_id": rid,
            "confirmation_no": _texto(n, "CONFIRMATION_NO"),
            "name": _texto(n, "NAME"),
            "sname": _texto(n, "SNAME"),
            "room": _texto(n, "ROOM"),
            "arrival": llegada,
            "departure": salida,
            "last_date": _fecha_num(_texto(n, "LAST_DATE")),
            "resv_status": _texto(n, "RESV_STATUS"),
            "guarantee_code": _texto(n, "GUARANTEE_CODE"),
            "external_reference": _texto(n, "EXTERNAL_REFERENCE"),
            "total_paid_amt": _num(n, "TOTAL_PAID_AMT"),
            "nights": _noches(llegada, salida),
        })
    return filas


def corte_de(filas: list[dict]) -> str | None:
    """La fecha del corte: el movimiento más reciente del archivo.

    El Deposit Ledger no dice en qué fecha se corrió. Lo más cerca es el
    `LAST_DATE` mayor: ningún depósito puede haberse movido después de que se
    imprimió el reporte. Si el archivo no trae ninguna, quien sube pone la fecha.
    """
    fechas = [f["last_date"] for f in filas if f.get("last_date")]
    return max(fechas) if fechas else None


def resumen(filas: list[dict]) -> dict:
    llegadas = sorted(f["arrival"] for f in filas if f.get("arrival"))
    return {
        "cuenta": len(filas),
        "total_amt": round(sum(f["total_paid_amt"] for f in filas), 2),
        "min_arrival": llegadas[0] if llegadas else None,
        "max_arrival": llegadas[-1] if llegadas else None,
        "as_of": corte_de(filas),
        "sin_llegada": sum(1 for f in filas if not f.get("arrival")),
    }
