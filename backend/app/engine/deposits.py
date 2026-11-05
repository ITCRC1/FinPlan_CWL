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

from datetime import date, timedelta

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


def en_rango(filas: list[dict], desde: str | None = None,
             hasta: str | None = None) -> list[dict]:
    """Las reservas cuya LLEGADA cae en el rango, **con los dos extremos adentro**.

    Owner, 2026-11-05: *«si yo quiero saber cuanto deposits hay del 20 de
    diciembre al 31 de diciembre»*. El 20 y el 31 cuentan: quien pide «del 20 al
    31» está pidiendo doce días, no diez.

    ⚠️ Las fechas son ISO (`2026-12-20`), y en ISO comparar como texto da el
    mismo orden que comparar como fecha. Por eso no hace falta convertirlas —
    pero sólo mientras sean ISO: con `20-12-26` esto mentiría en silencio.

    ⚠️ Una reserva sin fecha de llegada **no entra en ningún rango**, y por eso
    el que llama tiene que contarlas aparte (`rango()` lo hace). Si se dejaran
    caer sin decir nada, la suma de todos los rangos no daría el total y nadie
    sabría por qué.
    """
    return [f for f in filas
            if f.get("arrival")
            and (not desde or f["arrival"] >= desde)
            and (not hasta or f["arrival"] <= hasta)]


def rango(filas: list[dict], desde: str | None = None, hasta: str | None = None,
          corte: str | None = None) -> dict:
    """Todo lo que se sabe de los depósitos de un rango de llegadas.

    Es el mismo juego de análisis que el del corte completo, pero sobre la
    ventana pedida: lo que importa de «del 20 al 31 de diciembre» no es sólo
    cuánto suma, sino de qué estados viene y en cuántas reservas se concentra.
    """
    dentro = en_rango(filas, desde, hasta)
    sin_llegada = [f for f in filas if not f.get("arrival")]
    total = sum(monto(f) for f in filas)
    b = _bloque(dentro)
    return {
        "desde": desde, "hasta": hasta,
        "total": b,
        "pct_del_corte": round(b["monto"] / total * 100, 2) if total else 0.0,
        "dias": _dias_entre(desde, hasta),
        "por_dia": por_dia(dentro),
        "por_estado": por_campo(dentro, "resv_status"),
        "concentracion": concentracion(dentro),
        "antiguedad": antiguedad(dentro, corte),
        "filas": sorted(dentro, key=lambda f: (f.get("arrival") or "", -monto(f))),
        "sin_llegada": _bloque(sin_llegada) if sin_llegada else None,
    }


def _dias_entre(desde: str | None, hasta: str | None) -> int | None:
    if not desde or not hasta:
        return None
    try:
        return (date.fromisoformat(hasta) - date.fromisoformat(desde)).days + 1
    except ValueError:
        return None


def por_dia(filas: list[dict]) -> list[dict]:
    """Un renglón por día de llegada con depósito. Para rangos cortos."""
    g: dict[str, list[dict]] = {}
    for f in filas:
        if f.get("arrival"):
            g.setdefault(f["arrival"], []).append(f)
    return [{"fecha": d, **_bloque(g[d])} for d in sorted(g)]


#: La misma tasa que usan los motores de cash flow (`cashflow_directo`,
#: `cashflow_budget`, `cashflow_criterios`). Se deja como parámetro de la ruta
#: para que se pueda mover sin tocar código, pero el default es uno solo.
IVA_RATE = 0.13


def _fin_de_mes(anio: int, mes: int) -> str:
    return (date(anio + mes // 12, mes % 12 + 1, 1) - timedelta(days=1)).isoformat()


def por_cobrar(otb: dict, filas: list[dict], iva: float = IVA_RATE,
               corte: str | None = None) -> dict:
    """Cuánto falta por cobrar de lo que ya está vendido, mes a mes.

    Owner, 2026-11-05: *«on the books no tiene impuestos. entonces on the books
    total revenue más el 13% menos los depósitos recibidos es el saldo por
    cobrar del mes»*. Esa es la fórmula, literal:

        saldo = OTB total revenue × (1 + IVA) − depósitos recibidos

    `otb` viene como `{(año, mes): {"total", "rooms", "noches"}}`.

    ⚠️ **Las dos cifras no se cuentan igual, y hay que decirlo.** El OTB mide
    el INGRESO por noche: una estadía del 28-dic al 2-ene reparte su plata
    entre diciembre y enero. El depósito está contra la LLEGADA: esa misma
    estadía tiene **todo** su depósito en diciembre. En el ledger de noviembre
    2026 eso son 13 reservas de diciembre por $113,047 que se van en enero —
    no es un detalle, así que cada mes reporta `cruzan` y la pantalla lo
    muestra. Prorratear el depósito por noches sería inventar: lo que el
    huésped abonó no tiene por qué repartirse igual que las noches.

    ⚠️ **Los meses que ya pasaron no tienen saldo por cobrar.** El OTB trae el
    año entero —enero incluido— pero el Deposit Ledger solo lista llegadas
    FUTURAS: de un mes cerrado el huésped ya se hospedó y pagó al salir, así
    que el depósito es cero y la resta daría «nos deben el mes completo». En
    el corte del 4-nov-2026 eso son $4,0 millones de saldo inventado sobre un
    total de $7,3. Cada mes lleva `pasado` y los totales van partidos: el que
    sirve para cobrar es `total_abierto`.
    """
    hoy = date.fromisoformat(corte) if corte else date.today()
    dep: dict[tuple[int, int], list[dict]] = {}
    for f in filas:
        a = f.get("arrival")
        if a:
            dep.setdefault((int(a[:4]), int(a[5:7])), []).append(f)

    meses = []
    for k in sorted(set(otb) | set(dep)):
        o = otb.get(k) or {}
        ot = float(o.get("total") or 0.0)
        con_iva = ot * (1 + iva)
        delmes = dep.get(k, [])
        d = sum(monto(f) for f in delmes)
        # Las que llegan este mes y se van en otro: su depósito está entero
        # acá y su ingreso no.
        cruzan = [f for f in delmes
                  if f.get("departure") and f["departure"][:7] != f"{k[0]}-{k[1]:02d}"]
        meses.append({
            "year": k[0], "month": k[1],
            "etiqueta": f"{MESES[k[1] - 1]} {k[0]}",
            "otb_total": round(ot, 2),
            "otb_rooms": round(float(o.get("rooms") or 0.0), 2),
            "otb_noches": round(float(o.get("noches") or 0.0), 2),
            "iva": round(con_iva - ot, 2),
            "con_iva": round(con_iva, 2),
            "deposito": round(d, 2),
            "reservas": len(delmes),
            "saldo": round(con_iva - d, 2),
            "pct_cobrado": round(d / con_iva * 100, 2) if con_iva else None,
            "cruzan": {"reservas": len(cruzan),
                       "monto": round(sum(monto(f) for f in cruzan), 2)},
            # Un mes con depósito y sin OTB es una llegada más allá del
            # horizonte del forecast: no es un error, pero no se puede
            # calcular saldo y la pantalla tiene que decirlo.
            "sin_otb": ot == 0 and d > 0,
            # El mes ya cerró antes del corte del ledger: lo que se vendió ahí
            # ya se cobró al salir, y acá no queda saldo que perseguir.
            "pasado": _fin_de_mes(k[0], k[1]) < hoy.isoformat(),
        })

    def junta(ms: list[dict]) -> dict:
        ot = sum(m["otb_total"] for m in ms)
        iv = sum(m["iva"] for m in ms)
        dp = sum(m["deposito"] for m in ms)
        return {"otb_total": round(ot, 2), "iva": round(iv, 2),
                "con_iva": round(ot + iv, 2), "deposito": round(dp, 2),
                "saldo": round(ot + iv - dp, 2), "meses": len(ms),
                "reservas": sum(m["reservas"] for m in ms),
                "pct_cobrado": round(dp / (ot + iv) * 100, 2) if ot + iv else None}

    sin_llegada = [f for f in filas if not f.get("arrival")]
    return {
        "iva_pct": iva,
        "corte": hoy.isoformat(),
        "meses": meses,
        #: El que sirve para cobrar: solo los meses que todavía no cerraron.
        "total_abierto": junta([m for m in meses if not m["pasado"]]),
        "total_pasado": junta([m for m in meses if m["pasado"]]),
        "total": junta(meses),
        "sin_llegada": _bloque(sin_llegada) if sin_llegada else None,
    }


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
