# -*- coding: utf-8 -*-
"""Los análisis del Deposit Ledger. Python puro: sin base y sin idioma.

Recibe listas de dicts como las que devuelve `importers/deposit_xml.leer` (o
las filas de `DepositEntry` convertidas a dict) y devuelve los cuadros que pinta
la pantalla. Igual que `engine/pacing.py`: así se prueba con listas a mano.

⚠️ **El signo se da vuelta acá y en ningún otro lado.** En el XML y en la base
el depósito es negativo (es un crédito del huésped). Todos los análisis
trabajan con `monto` positivo = plata en custodia. La pestaña «Ledger», que
enseña el archivo tal cual, no pasa por este módulo.
"""
from __future__ import annotations

from datetime import date

MESES = ("ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO",
         "SEP", "OCT", "NOV", "DIC")

#: Tramos de antigüedad del depósito, en días desde el último movimiento.
TRAMOS = ((0, 30, "0–30"), (31, 60, "31–60"), (61, 90, "61–90"),
          (91, 180, "91–180"), (181, 365, "181–365"), (366, 10 ** 6, "365+"))


def monto(f: dict) -> float:
    """El depósito como plata en custodia: positivo."""
    return abs(float(f.get("total_paid_amt") or 0))


def _mes(iso: str | None) -> str | None:
    return iso[:7] if iso and len(iso) >= 7 else None


def _etiqueta_mes(ym: str) -> str:
    a, m = ym.split("-")
    return f"{MESES[int(m) - 1]} {a}"


def _dias(desde: str | None, hasta: date) -> int | None:
    if not desde:
        return None
    try:
        return (hasta - date.fromisoformat(desde)).days
    except ValueError:
        return None


def _bloque(filas: list[dict]) -> dict:
    tot = sum(monto(f) for f in filas)
    n = len(filas)
    return {"reservas": n, "monto": round(tot, 2),
            "promedio": round(tot / n, 2) if n else 0.0,
            "noches": sum(int(f.get("nights") or 0) for f in filas)}


def por_mes_de_llegada(filas: list[dict]) -> dict:
    """Cuánto depósito hay guardado contra cada mes de llegada.

    Es la pregunta de caja: de la plata en custodia, cuánta se convierte en
    ingreso en noviembre, cuánta en diciembre, cuánta en 2028.
    """
    grupos: dict[str, list[dict]] = {}
    sin_fecha: list[dict] = []
    for f in filas:
        ym = _mes(f.get("arrival"))
        (grupos.setdefault(ym, []) if ym else sin_fecha).append(f)

    meses = []
    acum = 0.0
    total = sum(monto(f) for f in filas)
    for ym in sorted(grupos):
        b = _bloque(grupos[ym])
        acum += b["monto"]
        estados = {}
        for f in grupos[ym]:
            e = f.get("resv_status") or "—"
            estados[e] = round(estados.get(e, 0.0) + monto(f), 2)
        meses.append({
            "mes": ym, "etiqueta": _etiqueta_mes(ym), **b,
            "pct": round(b["monto"] / total * 100, 2) if total else 0.0,
            "acumulado": round(acum, 2),
            "pct_acumulado": round(acum / total * 100, 2) if total else 0.0,
            "por_estado": dict(sorted(estados.items(), key=lambda x: -x[1])),
        })
    return {"meses": meses,
            "sin_llegada": _bloque(sin_fecha) if sin_fecha else None,
            "total": _bloque(filas)}


def por_campo(filas: list[dict], campo: str) -> list[dict]:
    """Agrupa por un campo cualquiera (estado, garantía, habitación)."""
    g: dict[str, list[dict]] = {}
    for f in filas:
        g.setdefault(f.get(campo) or "—", []).append(f)
    total = sum(monto(f) for f in filas)
    out = [{"clave": k, **_bloque(v),
            "pct": round(sum(monto(x) for x in v) / total * 100, 2) if total else 0.0}
           for k, v in g.items()]
    return sorted(out, key=lambda x: -x["monto"])


def antiguedad(filas: list[dict], corte: str | None = None) -> dict:
    """Hace cuánto está cada depósito, desde su último movimiento.

    Un depósito muy viejo contra una llegada lejana es normal; uno viejo contra
    una llegada que ya pasó es una reserva que quedó colgada y hay que mirar.
    """
    hoy = date.fromisoformat(corte) if corte else date.today()
    tramos = {etq: [] for _a, _b, etq in TRAMOS}
    sin = []
    for f in filas:
        d = _dias(f.get("last_date"), hoy)
        if d is None:
            sin.append(f)
            continue
        d = max(d, 0)
        for a, b, etq in TRAMOS:
            if a <= d <= b:
                tramos[etq].append(f)
                break
    total = sum(monto(f) for f in filas)
    return {
        "corte": hoy.isoformat(),
        "tramos": [{"tramo": etq, **_bloque(tramos[etq]),
                    "pct": round(sum(monto(x) for x in tramos[etq]) / total * 100, 2)
                           if total else 0.0}
                   for _a, _b, etq in TRAMOS],
        "sin_fecha": _bloque(sin) if sin else None,
    }


def llegadas_vencidas(filas: list[dict], corte: str | None = None) -> list[dict]:
    """Depósitos cuya llegada ya pasó y que siguen en el ledger.

    Si el corte es del 4 de noviembre y hay un depósito contra una llegada de
    setiembre, ese huésped ya vino —o no vino— y la plata debió salir del
    ledger. Es el hallazgo que paga el módulo.
    """
    hoy = date.fromisoformat(corte) if corte else date.today()
    out = []
    for f in filas:
        d = _dias(f.get("arrival"), hoy)
        if d is not None and d > 0:
            out.append({**f, "monto": monto(f), "dias_vencido": d})
    return sorted(out, key=lambda x: -x["dias_vencido"])


def concentracion(filas: list[dict], top: int = 10) -> dict:
    """Cuánto del total pesan los depósitos más grandes."""
    orden = sorted(filas, key=monto, reverse=True)
    total = sum(monto(f) for f in filas)
    mayores = [{"resv_name_id": f.get("resv_name_id"), "name": f.get("name"),
                "arrival": f.get("arrival"), "resv_status": f.get("resv_status"),
                "nights": f.get("nights"), "monto": round(monto(f), 2),
                "pct": round(monto(f) / total * 100, 2) if total else 0.0}
               for f in orden[:top]]
    return {"top": mayores,
            "pct_top": round(sum(m["monto"] for m in mayores) / total * 100, 2)
                       if total else 0.0,
            "total": round(total, 2), "reservas": len(filas)}


# ───────────────────────────── comparación entre cortes ─────────────────────
def comparar(antes: list[dict], despues: list[dict]) -> dict:
    """Qué cambió entre dos cortes del ledger.

    Cuatro grupos, y la suma de sus efectos explica el movimiento del total:

    * **entraron** — reservas que no estaban en el corte viejo. Depósito nuevo.
    * **salieron** — estaban y ya no están: el huésped se hospedó (el depósito
      se aplicó al folio), canceló, o le devolvieron la plata. El ledger no
      dice cuál de las tres: dice que la plata salió de custodia.
    * **subieron / bajaron** — siguen, con otro monto. Un abono más, o una
      devolución parcial.
    * **iguales** — ni se movieron.

    ⚠️ La llave es `resv_name_id`, no el nombre ni la confirmación: es la única
    que Opera garantiza estable entre corridas.
    """
    a = {f["resv_name_id"]: f for f in antes if f.get("resv_name_id")}
    b = {f["resv_name_id"]: f for f in despues if f.get("resv_name_id")}

    def fila(f, otro=None):
        d = {"resv_name_id": f.get("resv_name_id"), "name": f.get("name"),
             "arrival": f.get("arrival"), "departure": f.get("departure"),
             "room": f.get("room"), "resv_status": f.get("resv_status"),
             "nights": f.get("nights"), "last_date": f.get("last_date"),
             "monto": round(monto(f), 2)}
        if otro is not None:
            d["monto_antes"] = round(monto(otro), 2)
            d["delta"] = round(monto(f) - monto(otro), 2)
            if (otro.get("resv_status") or "") != (f.get("resv_status") or ""):
                d["estado_antes"] = otro.get("resv_status")
        return d

    entraron = [fila(b[k]) for k in b.keys() - a.keys()]
    salieron = [fila(a[k]) for k in a.keys() - b.keys()]
    subieron, bajaron, iguales = [], [], []
    for k in a.keys() & b.keys():
        delta = round(monto(b[k]) - monto(a[k]), 2)
        (subieron if delta > 0.004 else bajaron if delta < -0.004 else iguales) \
            .append(fila(b[k], a[k]))

    def tot(xs, campo="monto"):
        return round(sum(x[campo] for x in xs), 2)

    ta, tb = round(sum(monto(f) for f in antes), 2), round(sum(monto(f) for f in despues), 2)
    return {
        "antes": {"reservas": len(antes), "monto": ta},
        "despues": {"reservas": len(despues), "monto": tb},
        "variacion": {"reservas": len(despues) - len(antes), "monto": round(tb - ta, 2)},
        "entraron": {"reservas": len(entraron), "monto": tot(entraron),
                     "filas": sorted(entraron, key=lambda x: -x["monto"])},
        "salieron": {"reservas": len(salieron), "monto": tot(salieron),
                     "filas": sorted(salieron, key=lambda x: -x["monto"])},
        "subieron": {"reservas": len(subieron), "monto": tot(subieron, "delta"),
                     "filas": sorted(subieron, key=lambda x: -x["delta"])},
        "bajaron": {"reservas": len(bajaron), "monto": tot(bajaron, "delta"),
                    "filas": sorted(bajaron, key=lambda x: x["delta"])},
        "iguales": {"reservas": len(iguales), "monto": tot(iguales)},
    }


def cuadre(cmp: dict) -> float:
    """Lo que debe dar cero: entraron − salieron + subieron + bajaron = variación.

    Si no da cero, la comparación perdió una reserva por el camino. La prueba
    `test_deposits.py` lo exige y la pantalla lo muestra.
    """
    movido = (cmp["entraron"]["monto"] - cmp["salieron"]["monto"]
              + cmp["subieron"]["monto"] + cmp["bajaron"]["monto"])
    return round(movido - cmp["variacion"]["monto"], 2)


def resumen_completo(filas: list[dict], corte: str | None = None) -> dict:
    """Todo lo que pinta la pestaña de análisis, de una sola pasada."""
    return {
        "total": _bloque(filas),
        "por_mes": por_mes_de_llegada(filas),
        "por_estado": por_campo(filas, "resv_status"),
        "por_garantia": por_campo(filas, "guarantee_code"),
        "antiguedad": antiguedad(filas, corte),
        "vencidos": llegadas_vencidas(filas, corte),
        "concentracion": concentracion(filas),
    }
