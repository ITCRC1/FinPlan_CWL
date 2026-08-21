"""Parser del XML `res_statistics1` de Opera — país de origen por día.

Estructura: RES_STATISTICS1 > … > DAY (con BUSINESS_DATE `01-JAN-26`) >
MARKET (con MASTER_VALUE = código de país) > DETAIL, donde
`NO_DEFINITE_ROOMS` son las noches y `IN_GUEST` los pax.

Se agrega por MES: el archivo del owner (corte 17-ago-2026) trae 212 días,
enero a julio de 2026, 40 países con dato. Las noches por mes que salen de acá
—688, 684, 721, 503, 256, 284, 267— son **idénticas** a las del On the Books
del mismo año, que es un dato que llega por otro camino: dos fuentes
independientes dando el mismo número.

⚠️ **`UK` y `GB` son el MISMO país.** Opera emite los dos: el código legado
`UK` y el ISO `GB`. En el archivo del owner son 439 + 176 = 615 noches, y
dejarlos separados partiría al Reino Unido en dos filas —una de ellas fuera del
top— sin que nada lo avisara.

⚠️ **`{NULL}`** son reservas sin país registrado (35 noches). No es un país:
cae en «Others» junto con los que no están en la lista, para que el total
cierre igual.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

_MON = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

#: Los dos códigos que Opera usa para el Reino Unido → uno solo.
_ALIAS = {"UK": "GB"}

#: Código ISO → nombre. Cubre los 40 países del archivo del owner y algunos
#: más. Un código que no esté acá conserva su código como nombre: se ve raro
#: en pantalla, que es mejor que desaparecer sin ruido.
PAISES = {
    "US": "United States", "GB": "United Kingdom", "CR": "Costa Rica",
    "CH": "Switzerland", "CA": "Canada", "RU": "Russia", "DE": "Germany",
    "FR": "France", "NL": "Netherlands", "ES": "Spain", "SE": "Sweden",
    "IT": "Italy", "DK": "Denmark", "PL": "Poland", "BE": "Belgium",
    "IE": "Ireland", "AU": "Australia", "AT": "Austria", "MX": "Mexico",
    "PE": "Peru", "AR": "Argentina", "CZ": "Czech Republic", "HU": "Hungary",
    "IN": "India", "PT": "Portugal", "BR": "Brazil", "GT": "Guatemala",
    "IO": "British Indian Ocean Terr.", "TF": "French Southern Terr.",
    "CO": "Colombia", "FI": "Finland", "NO": "Norway", "RO": "Romania",
    "CL": "Chile", "CN": "China", "GE": "Georgia", "HR": "Croatia",
    "ZA": "South Africa", "IL": "Israel", "JP": "Japan", "NZ": "New Zealand",
    "PA": "Panama", "NI": "Nicaragua", "HN": "Honduras", "SV": "El Salvador",
    "EC": "Ecuador", "UY": "Uruguay", "VE": "Venezuela", "DO": "Dominican Rep.",
    "GR": "Greece", "TR": "Turkey", "UA": "Ukraine", "KR": "South Korea",
    "SG": "Singapore", "AE": "United Arab Emirates", "LU": "Luxembourg",
    "SK": "Slovakia", "SI": "Slovenia", "EE": "Estonia", "LV": "Latvia",
    "LT": "Lithuania", "BG": "Bulgaria", "IS": "Iceland", "MT": "Malta",
}

#: El cajón de sastre. Tiene que llamarse igual que la fila que ya existe en
#: pantalla, o quedarían dos «otros» distintos.
OTROS = "Others"


def nombre_de(codigo: str) -> str:
    """Código de Opera → nombre de país. `UK` y `GB` dan el mismo nombre."""
    c = (codigo or "").strip().upper()
    c = _ALIAS.get(c, c)
    return PAISES.get(c, c)


def parse_stats_por_codigo(xml_bytes: bytes) -> dict[tuple[int, int, str], dict]:
    """`{(year, month, MASTER_VALUE crudo): {rooms, pax}}`, agregado por mes.

    ⚠️ El MISMO reporte de Opera —`res_statistics1`— se emite abierto por país o
    por market code; lo único que cambia es qué trae `MASTER_VALUE`. Por eso el
    parser devuelve el código CRUDO y no interpreta nada: quien sabe si «TA» es
    un país o un canal es el importador que lo llama, no esto.
    """
    root = ET.fromstring(xml_bytes)
    out: dict[tuple[int, int, str], dict] = {}
    for day in root.iter("DAY"):
        bd = (day.findtext("BUSINESS_DATE") or "").strip()
        partes = bd.split("-")
        if len(partes) < 3:
            continue
        mes = _MON.get(partes[1].strip().upper())
        if not mes:
            continue
        try:
            yy = int(partes[2])
        except ValueError:
            continue
        anio = 2000 + yy if yy < 100 else yy

        for mk in day.iter("MARKET"):
            code = (mk.findtext("MASTER_VALUE") or "").strip()
            if not code:
                continue
            for det in mk.iter("DETAIL"):
                rooms = _f(det, "NO_DEFINITE_ROOMS")
                pax = _f(det, "IN_GUEST")
                if not (rooms or pax):
                    continue
                acc = out.setdefault((anio, mes, code), {"rooms": 0.0, "pax": 0.0})
                acc["rooms"] += rooms
                acc["pax"] += pax
    return out


def parse_country_stats(xml_bytes: bytes) -> dict[tuple[int, int, str], dict]:
    """`{(year, month, nombre_de_pais): {rooms, pax}}`, ya agregado por mes.

    Los alias (`UK`/`GB`) se suman acá, no en el importador: si se dejara para
    después, cualquiera que consumiera el parser vería el país partido en dos.
    `{NULL}` se conserva tal cual — decidir si va a «Others» es del importador,
    que es quien conoce la lista de países importantes.
    """
    out: dict[tuple[int, int, str], dict] = {}
    for (anio, mes, code), v in parse_stats_por_codigo(xml_bytes).items():
        pais = nombre_de(code)
        acc = out.setdefault((anio, mes, pais), {"rooms": 0.0, "pax": 0.0})
        acc["rooms"] += v["rooms"]
        acc["pax"] += v["pax"]
    return out


def _f(nodo, tag: str) -> float:
    v = nodo.findtext(tag)
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def plegar_a_lista(
    datos: dict[tuple[int, int, str], dict],
    importantes: list[str],
) -> tuple[dict[tuple[int, int, str], dict], list[dict]]:
    """Deja los países `importantes` y manda TODO lo demás a «Others».

    Regla del owner (18-ago-2026): «Los países acá listados son los más
    importantes; cualquiera que no se encuentre va a Others.»

    Devuelve `(plegado, al_cajon)`, donde `al_cajon` dice qué países cayeron en
    Others y con cuántas noches. Eso NO es decoración: con el archivo del owner,
    Alemania (64), Francia (53) y España (45) están fuera de la lista y son más
    grandes que Suecia (33) o Dinamarca (20), que sí están. Sin ese detalle, la
    decisión de a quién promover se toma a ciegas.
    """
    permitidos = {p for p in importantes if p != OTROS}
    plegado: dict[tuple[int, int, str], dict] = {}
    fuera: dict[str, dict] = {}
    for (anio, mes, pais), v in datos.items():
        destino = pais if pais in permitidos else OTROS
        if destino == OTROS:
            f = fuera.setdefault(pais, {"rooms": 0.0, "pax": 0.0})
            f["rooms"] += v["rooms"]
            f["pax"] += v["pax"]
        acc = plegado.setdefault((anio, mes, destino), {"rooms": 0.0, "pax": 0.0})
        acc["rooms"] += v["rooms"]
        acc["pax"] += v["pax"]
    al_cajon = sorted(
        ({"pais": p, **v} for p, v in fuera.items()),
        key=lambda x: -x["rooms"],
    )
    return plegado, al_cajon
