"""Parser del XML 'History Forecast' de Opera (Oracle Reports).

Estructura: HISTORY_FORECAST > ... > G_REC_TYPE (A_STAT=History / B_FORE=Forecast)
> G_CONSIDERED_DATE (uno por DÍA) con CONSIDERED_DATE (01-JAN-26), NO_ROOMS
(rooms sold), REVENUE, NO_PERSONS (pax), INVENTORY_ROOMS.

Combinando History (días pasados) + Forecast (días futuros) = el On the Books del
año completo, día a día. El horizonte del owner llega hasta 5 años adelante en el
MISMO archivo (history_forecast con forecast a 2030 mientras el corte es 2026), así
que el AÑO de cada fila sale del propio XML — no se asume el año del escenario.

⚠️ **LOS DOS BLOQUES SE SOLAPAN, y por eso cada fila dice de cuál viene.**

El diseño original daba por hecho que History cubría el pasado y Forecast el
futuro, sin pisarse, y sumaba todo lo que encontrara. No es así: en el archivo
del owner (corte W34-2026) enero aparece en LOS DOS bloques con el mismo dato,
y sumarlos daba 1.353 noches vendidas en un hotel de 30 habitaciones —132% de
ocupación— y un On the Books de $6.315.043 contra un presupuesto de $4.872.775.

Devuelve [{year, month, day, rec_type, rooms_sold, revenue, pax}], donde
`rec_type` es 'history' | 'forecast' | ''. Quién se queda con el día cuando
está en los dos lo decide `elegir_por_dia`, no este parser: acá solo se lee.
"""
from __future__ import annotations
import xml.etree.ElementTree as ET

_MON = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

#: Cómo rotula Opera cada bloque. Se compara por prefijo y sin distinguir
#: mayúsculas: el mismo reporte sale como `A_STAT`/`B_FORE` o como
#: `History`/`Forecast` según la plantilla.
_HISTORY = ("A_STAT", "HISTORY", "STAT")
_FORECAST = ("B_FORE", "FORECAST", "FORE")


def _f(node, tag) -> float:
    v = node.findtext(tag)
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _tipo_de(nodo) -> str:
    """'history' | 'forecast' | '' — leyendo el rótulo del bloque G_REC_TYPE."""
    crudo = ""
    for tag in ("REC_TYPE", "REC_TYPE_DESC", "CF_REC_TYPE"):
        crudo = (nodo.findtext(tag) or "").strip()
        if crudo:
            break
    if not crudo:
        crudo = (nodo.get("REC_TYPE") or "").strip()
    u = crudo.upper()
    if any(u.startswith(p) for p in _HISTORY):
        return "history"
    if any(u.startswith(p) for p in _FORECAST):
        return "forecast"
    return ""


def _dia(gd, rec_type: str) -> dict | None:
    cd = gd.findtext("CONSIDERED_DATE")  # 01-JAN-26
    if not cd:
        return None
    parts = cd.split("-")
    if len(parts) < 3:
        return None
    try:
        day = int(parts[0])
    except ValueError:
        return None
    month = _MON.get(parts[1].strip().upper())
    if not month:
        return None
    try:
        yy = int(parts[2])
    except ValueError:
        return None
    year = 2000 + yy if yy < 100 else yy  # "26" -> 2026; ya-4-dígitos queda igual
    return {
        "year": year, "month": month, "day": day, "rec_type": rec_type,
        "rooms_sold": _f(gd, "NO_ROOMS"),
        "revenue": _f(gd, "REVENUE"),
        "pax": _f(gd, "NO_PERSONS"),
    }


def parse_history_forecast(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    out: list[dict] = []
    vistos: set[int] = set()

    # Primero por bloque, para saber de cuál viene cada día.
    for bloque in root.iter("G_REC_TYPE"):
        tipo = _tipo_de(bloque)
        for gd in bloque.iter("G_CONSIDERED_DATE"):
            vistos.add(id(gd))
            fila = _dia(gd, tipo)
            if fila:
                out.append(fila)

    # Y los días que cuelguen fuera de un G_REC_TYPE — hay plantillas que no lo
    # emiten. Sin esto, un XML sin bloques devolvería vacío.
    for gd in root.iter("G_CONSIDERED_DATE"):
        if id(gd) in vistos:
            continue
        fila = _dia(gd, "")
        if fila:
            out.append(fila)
    return out


def elegir_por_dia(filas: list[dict]) -> dict[tuple[int, int, int], dict]:
    """`{(year, month, day): {rooms_sold, revenue, pax}}` SIN contar dos veces.

    Dentro de un mismo bloque se SUMA —Opera puede abrir el día por market o
    por tipo de habitación, y ahí las partes son partes—. Entre bloques se
    ELIGE UNO: si el día está en History y en Forecast, gana History, que es
    lo ocurrido; el forecast de un día que ya pasó es una proyección vieja.

    Esto reemplaza al `_otb_agrega_por_dia` que sumaba todo. Su propio
    comentario ya advertía el riesgo —«el revenue mensual habría sumado ese día
    DOBLE en silencio»— y eso fue exactamente lo que pasó.
    """
    por_bloque: dict[tuple[int, int, int, str], dict] = {}
    for r in filas:
        k = (r["year"], r["month"], r["day"], r.get("rec_type") or "")
        v = por_bloque.setdefault(k, {"rooms_sold": 0.0, "revenue": 0.0, "pax": 0.0})
        v["rooms_sold"] += r["rooms_sold"]
        v["revenue"] += r["revenue"]
        v["pax"] += r["pax"]

    # history > forecast > sin rótulo. Un solo bloque por día.
    prioridad = {"history": 0, "forecast": 1, "": 2}
    elegido: dict[tuple[int, int, int], tuple[int, dict]] = {}
    for (y, m, d, tipo), v in por_bloque.items():
        p = prioridad.get(tipo, 3)
        actual = elegido.get((y, m, d))
        if actual is None or p < actual[0]:
            elegido[(y, m, d)] = (p, v)
    return {k: v for k, (_p, v) in elegido.items()}


def dias_duplicados(filas: list[dict]) -> list[tuple[int, int, int]]:
    """Los días que vienen en MÁS DE UN bloque. Para poder decirlo, no adivinarlo."""
    bloques: dict[tuple[int, int, int], set[str]] = {}
    for r in filas:
        bloques.setdefault((r["year"], r["month"], r["day"]), set()).add(
            r.get("rec_type") or "")
    return sorted(k for k, v in bloques.items() if len(v) > 1)
