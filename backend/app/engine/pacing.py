# -*- coding: utf-8 -*-
"""Motor del módulo PACING: posición, STLY, alcance y meta.

**Qué contesta.** Dónde estoy parado para cada mes de un año (lo que está en
libros hoy), cuánto tenía el año anterior a la misma fecha (STLY), cuánto se
vendió después de esa fecha hasta el cierre (pickup), y hasta dónde puedo
llegar si repito ese comportamiento (alcance). Todo contra la meta de la
compañía cuando está cargada.

**De dónde salen los datos.** Dos reportes de Opera:

* *History & Forecast* (Rooms Only y Total Revenue): el día a día con la marca
  History (real) o Forecast (en libros). Cada carga es una FOTO con su fecha de
  corte —el primer día Forecast—. Las fotos se guardan todas: con el tiempo son
  la curva de pacing y el STLY exacto del año siguiente.
* *Reservations Entered On*: cada reserva con su fecha de creación. Permite
  reconstruir qué había en libros en cualquier fecha pasada.

**El motor es puro.** Recibe diccionarios y devuelve diccionarios: nada de
sesión ni de base. Así se prueba sin Postgres y el API sólo junta los datos.

Formatos de entrada
-------------------
Foto (snapshot)::

    {"kind": "total"|"rooms", "as_of": "2026-09-30", "has_forecast": True,
     "days": {"2026-01-01": [rn, rev, inv, ooo, comp, grp, arr, pax, hist]}}

Reserva::

    {"id": "…", "ins": "2026-03-02", "arr": "2026-12-20", "nts": 3, "rms": 1,
     "amt": 1830.0, "st": "A"|"X"|"N"|"P", "fl": "C"|"H"|"", "ch": "…",
     "rate": "…", "blk": 0|1}

``st``: A = activa (reservada, in-house o check-out), X = cancelada,
N = no show, P = prospecto/lista de espera.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Iterable

# Índices de la fila diaria de una foto.
RN, REV, INV, OOO, COMP, GRP, ARR, PAX, HIST = range(9)

ESCENARIOS = ("avail", "add", "mult", "otb")
FUENTES_STLY = ("auto", "snap", "resv", "rm")


# ───────────────────────────── fechas ─────────────────────────────
def _d(iso: str) -> date:
    return date.fromisoformat(iso)


def mas_dias(iso: str, n: int) -> str:
    return (_d(iso) + timedelta(days=n)).isoformat()


def dias_entre(a: str, b: str) -> int:
    """a − b en días."""
    return (_d(a) - _d(b)).days


def un_anio_antes(iso: str) -> str:
    y, rest = int(iso[:4]), iso[4:]
    return f"{y - 1}{'-02-28' if rest == '-02-29' else rest}"


def un_anio_despues(iso: str) -> str:
    y, rest = int(iso[:4]), iso[4:]
    return f"{y + 1}{'-02-28' if rest == '-02-29' else rest}"


def dias_del_mes(y: int, m0: int) -> int:
    return calendar.monthrange(y, m0 + 1)[1]


# ───────────────────────────── fotos H&F ─────────────────────────────
def fotos_de(snaps: Iterable[dict], kind: str) -> list[dict]:
    return sorted((s for s in snaps if s.get("kind") == kind), key=lambda s: s["as_of"])


def combinar(snaps: Iterable[dict], kind: str) -> dict[str, list]:
    """Un día, un dato. History manda sobre Forecast; entre dos del mismo tipo,
    la foto más reciente."""
    out: dict[str, list] = {}
    for s in fotos_de(snaps, kind):
        for d, r in s["days"].items():
            c = out.get(d)
            if c is None or r[HIST] or not c[HIST]:
                out[d] = r
    return out


def ultimo_corte(snaps: Iterable[dict], kind: str) -> str | None:
    l = [s for s in fotos_de(snaps, kind) if s.get("has_forecast", True)]
    return l[-1]["as_of"] if l else None


def _mes_vacio() -> dict:
    return {"rn": 0.0, "rev": 0.0, "inv": 0.0, "ooo": 0.0, "comp": 0.0, "grp": 0.0,
            "pax": 0.0, "n": 0, "h": 0, "neg": 0, "neg_rev": 0.0}


def mensual(days: dict[str, list], year: int) -> list[dict]:
    m = [_mes_vacio() for _ in range(12)]
    for d, r in days.items():
        if int(d[:4]) != year:
            continue
        o = m[int(d[5:7]) - 1]
        o["rn"] += r[RN]; o["rev"] += r[REV]; o["inv"] += r[INV]; o["ooo"] += r[OOO]
        o["comp"] += r[COMP]; o["grp"] += r[GRP]; o["pax"] += r[PAX]
        o["n"] += 1; o["h"] += 1 if r[HIST] else 0
        if r[REV] < 0:
            o["neg"] += 1; o["neg_rev"] += r[REV]
    return m


def anios_en(days: dict[str, list]) -> list[int]:
    return sorted({int(d[:4]) for d in days})


def habitaciones(days: dict[str, list]) -> int:
    mx = 0
    for r in days.values():
        mx = max(mx, int(r[INV] + r[OOO]))
    return mx or 30


def relacion_historica(snaps: list[dict]) -> float:
    """Total ÷ Rooms del último año de días History en las dos fotos."""
    t, r = combinar(snaps, "total"), combinar(snaps, "rooms")
    corte = ultimo_corte(snaps, "total") or ultimo_corte(snaps, "rooms")
    desde = mas_dias(corte, -365) if corte else "0000-00-00"
    a = b = 0.0
    for d, v in t.items():
        w = r.get(d)
        if d < desde or not v[HIST] or not w or not w[HIST]:
            continue
        a += v[REV]; b += w[REV]
    return a / b if b > 0 else 1.0


# ───────────────────────────── reservas ─────────────────────────────
@dataclass
class Noches:
    lista: list[dict] = field(default_factory=list)
    min_ins: str | None = None
    max_ins: str | None = None
    cuenta: int = 0


def expandir(reservas: Iterable[dict]) -> Noches:
    """Cada reserva se abre en sus noches: una fila por noche con su tarifa."""
    out = Noches()
    for r in reservas:
        ins, arr, nts, rms = r["ins"], r["arr"], int(r.get("nts") or 0), int(r.get("rms") or 1)
        out.cuenta += 1
        out.min_ins = ins if out.min_ins is None or ins < out.min_ins else out.min_ins
        out.max_ins = ins if out.max_ins is None or ins > out.max_ins else out.max_ins
        if nts <= 0:
            continue
        por_noche = float(r.get("amt") or 0) / nts * rms
        base = _d(arr)
        lead = (base - _d(ins)).days
        ch = (r.get("ch") or "").strip() or "Sin agencia / directo"
        for k in range(nts):
            dia = base + timedelta(days=k)
            out.lista.append({"y": dia.year, "m": dia.month - 1, "d": dia.isoformat(),
                              "rms": rms, "amt": por_noche, "ins": ins, "st": r.get("st") or "A",
                              "fl": r.get("fl") or "", "ch": ch, "blk": int(r.get("blk") or 0),
                              "lead": lead, "id": r.get("id")})
    return out


def reservas_mensual(N: Noches, year: int, pred) -> list[dict]:
    m = [{"rn": 0.0, "amt": 0.0} for _ in range(12)]
    for x in N.lista:
        if x["y"] != year or not pred(x):
            continue
        m[x["m"]]["rn"] += x["rms"]; m[x["m"]]["amt"] += x["amt"]
    return m


def reservas_cubren(N: Noches, D: str, corte: str) -> bool:
    return bool(N.cuenta) and N.min_ins is not None and N.min_ins <= D and N.max_ins >= mas_dias(corte, -3)


# ───────────────────────────── STLY ─────────────────────────────
def stly_foto(snaps, kind, year, corte):
    objetivo = un_anio_antes(corte)
    mejor = None
    for s in fotos_de(snaps, kind):
        if not s.get("has_forecast", True):
            continue
        cov = sum(1 for d in s["days"] if int(d[:4]) == year)
        if cov < 300:
            continue
        g = abs(dias_entre(s["as_of"], objetivo))
        if g <= 21 and (mejor is None or g < mejor[0]):
            mejor = (g, s)
    if not mejor:
        return None
    s = mejor[1]
    return {"src": "snap", "as_of": s["as_of"], "gap": dias_entre(objetivo, s["as_of"]),
            "m": [{"rn": o["rn"], "rev": o["rev"]} for o in mensual(s["days"], year)]}


def stly_reservas(N: Noches, kind, year, corte, ly):
    D = un_anio_antes(corte)
    if ly is None or not reservas_cubren(N, D, corte):
        return None
    bk = reservas_mensual(N, year, lambda x: x["st"] == "A" and x["ins"] <= D)
    todo = reservas_mensual(N, year, lambda x: x["st"] == "A" and x["ins"] <= corte)
    canc = reservas_mensual(N, year, lambda x: x["st"] == "X" and x["ins"] <= D)
    m = []
    for i, o in enumerate(ly):
        if kind == "rooms":
            rev = bk[i]["amt"]
        else:
            rev = o["rev"] * min(1.0, bk[i]["amt"] / todo[i]["amt"]) if todo[i]["amt"] > 0 else 0.0
        m.append({"rn": bk[i]["rn"], "rev": rev, "canc_max": canc[i]["rn"]})
    return {"src": "resv", "as_of": D, "gap": 0, "m": m, "migracion": N.min_ins}


def stly_rm(config, kind, year, corte):
    b = ((config or {}).get("stly") or {}).get("years", {}).get(str(year))
    if not b or not isinstance(b.get("rn"), list):
        return None
    rv = b.get(kind) or []
    return {"src": "rm", "as_of": b.get("asOf"), "source": b.get("source"),
            "gap": dias_entre(un_anio_antes(corte), b["asOf"]) if b.get("asOf") else None,
            "m": [{"rn": float(v or 0), "rev": float((rv[i] if i < len(rv) else 0) or 0)}
                  for i, v in enumerate(b["rn"][:12])]}


def stly_para(ctx: "Contexto", kind, year, corte, ly):
    if not corte:
        return None
    f = {"snap": lambda: stly_foto(ctx.snaps, kind, year, corte),
         "resv": lambda: stly_reservas(ctx.noches, kind, year, corte, ly),
         "rm": lambda: stly_rm(ctx.config, kind, year, corte)}
    if ctx.fuente != "auto":
        r = f[ctx.fuente]()
        if r:
            return r
    return f["snap"]() or f["resv"]() or f["rm"]()


# ───────────────────────────── contexto ─────────────────────────────
@dataclass
class Contexto:
    snaps: list[dict]
    noches: Noches
    config: dict
    escenario: str = "avail"
    fuente: str = "auto"
    _cache: dict = field(default_factory=dict)

    def dias(self, kind):
        k = ("dias", kind)
        if k not in self._cache:
            self._cache[k] = combinar(self.snaps, kind)
        return self._cache[k]

    def corte(self, kind):
        return ultimo_corte(self.snaps, kind)

    def en_sitio(self) -> dict:
        c = self.config or {}
        modo = c.get("onsite_mode") or "pct"
        pct = c.get("onsite_pct")
        return {"modo": modo, "pct": (12.0 if pct is None else float(pct)) / 100.0}


# ───────────────────────────── posición y alcance ─────────────────────────────
def construir(ctx: Contexto, kind: str, T: int, escenario: str | None = None) -> dict:
    esc = escenario or ctx.escenario
    days = ctx.dias(kind)
    corte = ctx.corte(kind)
    cur, ly = mensual(days, T), mensual(days, T - 1)
    rc = habitaciones(days)

    # Meses del año anterior sin History & Forecast: el cierre sale de las reservas.
    if ctx.noches.cuenta:
        R = relacion_historica(ctx.snaps) if kind == "total" else 1.0
        rv = reservas_mensual(ctx.noches, T - 1, lambda x: x["st"] == "A")
        for i, o in enumerate(ly):
            if o["n"] == 0 and rv[i]["rn"] > 0:
                o["rn"] = rv[i]["rn"]; o["rev"] = rv[i]["amt"] * R; o["de_reservas"] = True

    # Si el año anterior es el año en curso, sus meses abiertos cuentan a su alcance.
    y0 = int(corte[:4]) if corte else None
    if y0 == T - 1:
        PL = con_en_sitio(ctx, construir(ctx, kind, T - 1, esc), kind)
        for i, x in enumerate(PL["rows"]):
            if not x["cerrado"] and (x["proj"] or x["otb_rn"]):
                ly[i]["rn"] = x["proj"]; ly[i]["rev"] = x["proj_rev"]
                ly[i]["alcance"] = True; ly[i]["reservado"] = x["proj_rev"] - (x.get("en_sitio") or 0)

    st = stly_para(ctx, kind, T - 1, corte, ly)
    otb_r = (reservas_mensual(ctx.noches, T, lambda x: x["st"] == "A" and x["ins"] <= corte)
             if st and st["src"] == "resv" else None)
    ly_rn = sum(o["rn"] for o in ly); ly_rev = sum(o["rev"] for o in ly)
    ly_adr = ly_rev / ly_rn if ly_rn else 0.0

    rows = []
    for i, c in enumerate(cur):
        l = ly[i]; s = st["m"][i] if st else None; D = dias_del_mes(T, i)
        cap = c["inv"] + (D - c["n"]) * rc if c["n"] else D * rc
        st_rn = s["rn"] if s else None
        pick = l["rn"] - st_rn if st_rn is not None else None
        base_pace = otb_r[i]["rn"] if otb_r else c["rn"]
        cap_ly = l["inv"] + (dias_del_mes(T - 1, i) - l["n"]) * rc if l["n"] else dias_del_mes(T - 1, i) * rc
        tasa = (max(0.0, min(1.0, (pick or 0) / (cap_ly - st_rn)))
                if st_rn is not None and cap_ly - st_rn > 0 else None)
        proj = c["rn"]
        if esc == "avail":
            proj = c["rn"] + tasa * max(0.0, cap - c["rn"]) if tasa is not None else c["rn"]
        elif esc == "add":
            proj = c["rn"] + max(0.0, pick or 0)
        elif esc == "mult":
            proj = c["rn"] * (l["rn"] / st_rn) if st_rn else c["rn"] + max(0.0, pick or 0)
        proj = max(c["rn"], min(proj, cap))
        adr_ref = l["rev"] / l["rn"] if l["rn"] > 0 else (c["rev"] / c["rn"] if c["rn"] else ly_adr)
        proj_rev = c["rev"] + (proj - c["rn"]) * adr_ref
        cerrado = c["n"] == D and c["h"] == D
        if cerrado:
            proj, proj_rev = c["rn"], c["rev"]
        rows.append({
            "i": i, "cap": cap, "otb_rn": c["rn"], "otb_rev": c["rev"],
            "adr": c["rev"] / c["rn"] if c["rn"] else None, "occ": c["rn"] / cap if cap else None,
            "grp": c["grp"], "st_rn": st_rn, "st_rev": s["rev"] if s else None,
            "pace": base_pace / st_rn if st_rn else None, "base_pace": base_pace,
            "bloqueos": c["rn"] - otb_r[i]["rn"] if otb_r else None, "tasa": tasa,
            "ly_rn": l["rn"], "ly_rev": l["rev"], "ly_adr": l["rev"] / l["rn"] if l["rn"] else None,
            "ly_h": l["h"], "ly_n": l["n"], "pick": pick, "proj": proj, "proj_rev": proj_rev,
            "proj_occ": proj / cap if cap else None, "cap_ly": cap_ly, "cerrado": cerrado,
            "ly_de_reservas": bool(l.get("de_reservas")), "ly_alcance": bool(l.get("alcance")),
            "falta": max(0.0, l["rn"] - c["rn"]), "asegurado": c["rn"] / l["rn"] if l["rn"] else None,
            "ly_cerrado_hotel": l["n"] > 0 and l["inv"] == 0,
            "canc_max": s.get("canc_max") if s else None,
        })
    tot = _totales(rows, st, ly_rn, ly_rev, ly_adr, otb_r is not None)
    return {"T": T, "kind": kind, "corte": corte, "st": st, "rows": rows, "tot": tot,
            "ly": ly, "cur": cur, "rc": rc, "escenario": esc}


def _totales(rows, st, ly_rn, ly_rev, ly_adr, con_bloqueos):
    s = lambda k: sum((r[k] or 0) for r in rows)
    t = {"cap": s("cap"), "otb_rn": s("otb_rn"), "otb_rev": s("otb_rev"),
         "st_rn": s("st_rn") if st else None, "st_rev": s("st_rev") if st else None,
         "ly_rn": ly_rn, "ly_rev": ly_rev, "pick": s("pick") if st else None,
         "proj": s("proj"), "proj_rev": s("proj_rev"), "grp": s("grp"),
         "base_pace": s("base_pace"), "bloqueos": s("bloqueos") if con_bloqueos else None}
    t["falta"] = max(0.0, ly_rn - t["otb_rn"])
    t["adr"] = t["otb_rev"] / t["otb_rn"] if t["otb_rn"] else None
    t["pace"] = t["base_pace"] / t["st_rn"] if t["st_rn"] else None
    t["occ"] = t["otb_rn"] / t["cap"] if t["cap"] else None
    t["proj_occ"] = t["proj"] / t["cap"] if t["cap"] else None
    t["asegurado"] = t["otb_rn"] / ly_rn if ly_rn else None
    t["ly_adr"] = ly_adr
    return t


def con_en_sitio(ctx: Contexto, P: dict, kind: str) -> dict:
    """Total Revenue en libros trae lo reservado (paquetes). El consumo en sitio
    entra al cerrar: para meses abiertos se estima como % del Room Revenue
    proyectado (supuesto de Finanzas) o con la relación histórica Total/Rooms."""
    for x in P["rows"]:
        x["en_sitio"] = 0.0
        x["proj_rev_reservado"] = x["proj_rev"]
    ajustes = ctx.en_sitio()
    if kind == "total" and fotos_de(ctx.snaps, "rooms"):
        PR = construir(ctx, "rooms", P["T"], P["escenario"])
        if ajustes["modo"] == "pct":
            anio_adr = P["tot"]["otb_rev"] / P["tot"]["otb_rn"] if P["tot"]["otb_rn"] else None
            rl = mensual(ctx.dias("rooms"), P["T"] - 1)
            for i, x in enumerate(P["rows"]):
                if x["cerrado"]:
                    continue
                l = P["ly"][i]
                if l.get("alcance") and l.get("reservado") is not None and l["rn"]:
                    b_adr = l["reservado"] / l["rn"]
                elif not l.get("de_reservas") and not l.get("alcance") and l["rn"] and rl[i]["n"]:
                    b_adr = max(0.0, (l["rev"] - ajustes["pct"] * rl[i]["rev"]) / l["rn"])
                elif x["otb_rn"]:
                    b_adr = x["otb_rev"] / x["otb_rn"]
                else:
                    b_adr = anio_adr or 0.0
                reservado = x["otb_rev"] + (x["proj"] - x["otb_rn"]) * b_adr
                x["en_sitio"] = ajustes["pct"] * PR["rows"][i]["proj_rev"]
                x["proj_rev"] = reservado + x["en_sitio"]
                x["proj_rev_reservado"] = reservado
        else:
            tl, rl = mensual(ctx.dias("total"), P["T"] - 1), mensual(ctx.dias("rooms"), P["T"] - 1)
            G = relacion_historica(ctx.snaps)
            for i, x in enumerate(P["rows"]):
                if x["cerrado"]:
                    continue
                R = tl[i]["rev"] / rl[i]["rev"] if tl[i]["h"] and rl[i]["h"] == rl[i]["n"] and rl[i]["rev"] > 0 else G
                ajustado = max(x["proj_rev"], PR["rows"][i]["proj_rev"] * R)
                x["en_sitio"] = ajustado - x["proj_rev"]
                x["proj_rev"] = ajustado
    P["tot"]["proj_rev_reservado"] = P["tot"]["proj_rev"]
    P["tot"]["proj_rev"] = sum(x["proj_rev"] for x in P["rows"])
    P["tot"]["en_sitio"] = sum(x["en_sitio"] for x in P["rows"])
    return P


def estado(r: dict) -> str:
    if not r["ly_rn"] and r["otb_rn"]:
        return "nuevo"
    if not r["ly_rn"] and not r["otb_rn"]:
        return "sin_actividad"
    x = r["proj"] / r["ly_rn"]
    xr = r["proj_rev"] / r["ly_rev"] if r["ly_rev"] > 0 else 1.0
    if x >= 1 and xr < 0.97:
        return "rn_arriba_ingreso_abajo"
    if x >= 1:
        return "supera"
    if x >= 0.9:
        return "cerca"
    return "debajo"


# ───────────────────────────── meta ─────────────────────────────
def meta_de(config: dict, kind: str, year: int) -> dict | None:
    b = ((config or {}).get("meta") or {}).get("years", {}).get(str(year))
    if not b or not isinstance(b.get("rn"), list):
        return None
    def arr(k):
        v = b.get(k) or []
        return [float(v[i] or 0) if i < len(v) else 0.0 for i in range(12)]
    return {"rn": arr("rn"), "avail": arr("avail"), "rev": arr(kind), "total": arr("total"),
            "rooms": arr("rooms"), "source": b.get("source"), "actual_months": int(b.get("actualMonths") or 0),
            "scenario_id": b.get("scenario_id")}


def cierre_contra_meta(ctx: Contexto, kind: str) -> dict | None:
    corte = ctx.corte(kind)
    if not corte:
        return None
    y0 = int(corte[:4])
    B = meta_de(ctx.config, kind, y0)
    P0 = con_en_sitio(ctx, construir(ctx, kind, y0), kind)
    filas = []
    for x in P0["rows"]:
        i = x["i"]
        m_rn = B["rn"][i] if B else None
        m_rev = B["rev"][i] if B else None
        filas.append({"i": i, "base": "real" if x["cerrado"] else ("cerrado" if not x["otb_rn"] and not x["proj"] else "abierto"),
                      "meta_rn": m_rn, "meta_rev": m_rev, "otb_rn": x["otb_rn"], "otb_rev": x["otb_rev"],
                      "pick": x["pick"], "proj": x["proj"], "proj_rev": x["proj_rev"], "en_sitio": x["en_sitio"],
                      "cerrado": x["cerrado"]})
    ytd = {k: sum(f[k2] or 0 for f in filas if f["cerrado"]) for k, k2 in
           (("meta_rn", "meta_rn"), ("meta_rev", "meta_rev"), ("rn", "proj"), ("rev", "proj_rev"))}
    abiertos = [f for f in filas if not f["cerrado"]]
    return {"year": y0, "meta": B, "stly": P0["st"], "filas": filas, "ytd": ytd,
            "total": {"meta_rn": sum(f["meta_rn"] or 0 for f in filas), "meta_rev": sum(f["meta_rev"] or 0 for f in filas),
                      "rn": sum(f["proj"] for f in filas), "rev": sum(f["proj_rev"] for f in filas),
                      "otb_rn": sum(f["otb_rn"] for f in abiertos), "otb_rev": sum(f["otb_rev"] for f in abiertos),
                      "en_sitio": sum(f["en_sitio"] for f in filas)}}


# ───────────────────────────── curva, pickup, canales, cancelaciones ─────────────────────────────
def curva(ctx: Contexto, T: int, corte: str) -> dict | None:
    N = ctx.noches
    if not N.cuenta or not corte:
        return None
    ini = N.min_ins if N.min_ins > mas_dias(corte, -365) else mas_dias(corte, -365)
    fin = un_anio_despues(N.max_ins)
    fin = min(fin, f"{T}-12-31")
    xs, d = [], ini
    while d <= fin:
        xs.append(d); d = mas_dias(d, 7)
    if xs[-1] != fin:
        xs.append(fin)

    def acumulado(y):
        l = sorted(((x["ins"], x["rms"]) for x in N.lista if x["y"] == y and x["st"] == "A"))
        fechas, sumas, c = [], [], 0
        for f, r in l:
            c += r
            if fechas and fechas[-1] == f:
                sumas[-1] = c
            else:
                fechas.append(f); sumas.append(c)
        import bisect

        def en(fecha):
            k = bisect.bisect_right(fechas, fecha) - 1
            return sumas[k] if k >= 0 else 0
        return en

    cT, cL = acumulado(T), acumulado(T - 1)
    vT = [cT(x) if x <= N.max_ins else None for x in xs]
    vL = []
    for x in xs:
        b = un_anio_antes(x)
        vL.append(cL(b) if N.min_ins <= b <= N.max_ins else None)
    hoy_T, hoy_L = cT(corte), cL(un_anio_antes(corte))
    hitos = []
    y, m = int(corte[:4]), int(corte[5:7])
    for k in range(1, 13):
        mm = m + k
        yy = y + (mm - 1) // 12
        mm = (mm - 1) % 12 + 1
        fin_mes = date(yy, mm, calendar.monthrange(yy, mm)[1]).isoformat()
        b = un_anio_antes(fin_mes)
        if b > N.max_ins or fin_mes > f"{T}-12-31":
            break
        hitos.append({"fecha": fin_mes, "deberia": hoy_T + (cL(b) - hoy_L)})
        if len(hitos) >= 6:
            break
    return {"xs": xs, "anio": vT, "anterior": vL, "hoy_anio": hoy_T, "hoy_anterior": hoy_L,
            "hitos": hitos, "migracion": N.min_ins if N.min_ins >= un_anio_antes(corte) else None}


def pickup_reciente(ctx: Contexto, T: int, corte: str) -> dict | None:
    N = ctx.noches
    if not N.cuenta or not corte:
        return None
    D = un_anio_antes(corte)

    def ventana(y, fin, w):
        ini = mas_dias(fin, -w)
        a = am = x = 0.0
        for r in N.lista:
            if r["y"] != y or r["ins"] <= ini or r["ins"] > fin:
                continue
            if r["st"] == "A":
                a += r["rms"]; am += r["amt"]
            elif r["st"] == "X":
                x += r["rms"]
        return {"rn": a, "tarifa": am, "canceladas": x, "migracion": N.min_ins > ini and N.min_ins <= fin}

    filas = [{"dias": w, "anio": ventana(T, corte, w), "anterior": ventana(T - 1, D, w)} for w in (7, 14, 30, 60, 90)]
    ini30 = mas_dias(corte, -30)
    por_mes = [0.0] * 12
    for r in N.lista:
        if r["y"] == T and r["st"] == "A" and ini30 < r["ins"] <= corte:
            por_mes[r["m"]] += r["rms"]
    return {"ventanas": filas, "ultimos_30_por_mes": por_mes}


def canales(ctx: Contexto, T: int) -> list[dict]:
    g: dict[str, dict] = {}
    for r in ctx.noches.lista:
        if r["st"] != "A" or r["y"] not in (T, T - 1):
            continue
        o = g.setdefault(r["ch"], {"canal": r["ch"], "rn": 0.0, "tarifa": 0.0, "rn_anterior": 0.0})
        if r["y"] == T:
            o["rn"] += r["rms"]; o["tarifa"] += r["amt"]
        else:
            o["rn_anterior"] += r["rms"]
    return sorted((o for o in g.values() if o["rn"] > 0), key=lambda o: -o["rn"])


def cancelaciones(ctx: Contexto, T: int) -> dict:
    N = ctx.noches

    def vacio():
        return [{"a": 0.0, "x": 0.0, "b": [0.0, 0.0, 0.0, 0.0], "mig": 0.0} for _ in range(12)]
    c = {T - 1: vacio(), T: vacio()}
    for r in N.lista:
        if r["y"] not in c:
            continue
        o = c[r["y"]][r["m"]]
        if r["st"] == "A":
            o["a"] += r["rms"]
            if r["ins"] == N.min_ins:
                o["mig"] += r["rms"]
            else:
                l = r["lead"]
                o["b"][0 if l <= 30 else 1 if l <= 90 else 2 if l <= 180 else 3] += r["rms"]
        elif r["st"] == "X":
            o["x"] += r["rms"]
    return {"anterior": c[T - 1], "anio": c[T]}


# ───────────────────────────── alertas ─────────────────────────────
def alertas(ctx: Contexto, P: dict, kind: str) -> list[dict]:
    out = []
    T = P["T"]
    for k in ("total", "rooms"):
        days = ctx.dias(k)
        for y in anios_en(days):
            for i, o in enumerate(mensual(days, y)):
                if o["neg"]:
                    out.append({"nivel": "corregir", "clave": "ingresoNegativo",
                                "datos": {"tipo": k, "mes": i, "anio": y, "dias": o["neg"], "monto": o["neg_rev"]}})
                if k == "rooms" and o["rn"] >= 20 and o["rev"] > 0 and o["rev"] / o["rn"] < 150:
                    out.append({"nivel": "revisar", "clave": "adrBajo",
                                "datos": {"mes": i, "anio": y, "adr": o["rev"] / o["rn"], "rn": o["rn"]}})
                if k == "total" and o["rn"] >= 20 and o["comp"] / o["rn"] > 0.15:
                    out.append({"nivel": "revisar", "clave": "cortesias",
                                "datos": {"mes": i, "anio": y, "comp": o["comp"], "pct": o["comp"] / o["rn"]}})
                if k == "total" and y >= T and o["rn"] >= 30 and o["grp"] / o["rn"] > 0.6 and o["h"] < o["n"]:
                    out.append({"nivel": "revisar", "clave": "grupos",
                                "datos": {"mes": i, "anio": y, "grp": o["grp"], "pct": o["grp"] / o["rn"]}})
                if k == "total" and o["ooo"] > 0:
                    out.append({"nivel": "info", "clave": "fueraDeServicio",
                                "datos": {"mes": i, "anio": y, "ooo": o["ooo"], "cerrado": o["inv"] == 0 and o["n"] > 0}})
    ct, cr = ctx.corte("total"), ctx.corte("rooms")
    if ct and cr and ct != cr:
        out.append({"nivel": "revisar", "clave": "cortesDistintos", "datos": {"total": ct, "rooms": cr}})
    if P["st"] and P["st"].get("gap") and abs(P["st"]["gap"]) > 7:
        out.append({"nivel": "info", "clave": "stlyLejos", "datos": {"dias": P["st"]["gap"]}})
    corte = P["corte"]
    if corte:
        rm = stly_rm(ctx.config, kind, T - 1, corte)
        rv = stly_reservas(ctx.noches, kind, T - 1, corte, P["ly"])
        if rm and rv:
            a = sum(o["rn"] for o in rm["m"]); b = sum(o["rn"] for o in rv["m"])
            if b and abs(a / b - 1) > 0.15:
                out.append({"nivel": "corregir", "clave": "stlyNoCuadra",
                            "datos": {"rm": a, "rm_fecha": rm["as_of"], "opera": b, "opera_fecha": rv["as_of"]}})
    if kind == "total" and P["tot"]["adr"]:
        lr = sum(o["rn"] for o in P["ly"]); lt = sum(o["rev"] for o in P["ly"])
        if lr and lt / lr > P["tot"]["adr"] * 1.1:
            out.append({"nivel": "info", "clave": "consumoEnSitio",
                        "datos": {"real": lt / lr, "otb": P["tot"]["adr"]}})
    orden = {"corregir": 0, "revisar": 1, "info": 2}
    out.sort(key=lambda a: orden[a["nivel"]])
    return out


# ───────────────────────────── todo junto ─────────────────────────────
def analisis(snaps: list[dict], reservas: list[dict], config: dict, *, kind: str = "total",
             year: int | None = None, escenario: str = "avail", fuente: str = "auto") -> dict:
    ctx = Contexto(snaps=snaps, noches=expandir(reservas), config=config or {},
                   escenario=escenario if escenario in ESCENARIOS else "avail",
                   fuente=fuente if fuente in FUENTES_STLY else "auto")
    days = ctx.dias(kind)
    anios = anios_en(days)
    corte = ctx.corte(kind)
    if not anios:
        return {"vacio": True, "anios": [], "fotos": _fotos(snaps), "reservas": _resumen_reservas(ctx.noches),
                "config": config or {}}
    if year is None or year not in anios:
        pref = int(corte[:4]) + 1 if corte else anios[-1]
        year = pref if pref in anios else anios[-1]
    P = con_en_sitio(ctx, construir(ctx, kind, year), kind)
    for r in P["rows"]:
        r["estado"] = estado(r)
    B_ly = meta_de(ctx.config, kind, year - 1)
    historico = []
    for y in anios[-3:]:
        historico.append({"anio": y, "meses": [{"rn": o["rn"], "rev": o["rev"], "n": o["n"],
                                                 "dias": dias_del_mes(y, i)} for i, o in enumerate(mensual(days, y))]})
    evolucion = []
    for s in reversed(fotos_de(snaps, kind)):
        m = mensual(s["days"], year)
        evolucion.append({"id": s.get("id"), "as_of": s["as_of"], "rn": sum(o["rn"] for o in m),
                          "rev": sum(o["rev"] for o in m), "has_forecast": s.get("has_forecast", True),
                          "file_name": s.get("file_name"), "desde": s.get("date_from"), "hasta": s.get("date_to")})
    return {
        "vacio": False, "anio": year, "anios": anios, "kind": kind, "corte": corte,
        "escenario": ctx.escenario, "fuente": ctx.fuente, "en_sitio": ctx.en_sitio(),
        "posicion": P, "meta_anterior": B_ly, "cierre_meta": cierre_contra_meta(ctx, kind),
        "curva": curva(ctx, year, corte), "pickup": pickup_reciente(ctx, year, corte),
        "canales": canales(ctx, year), "cancelaciones": cancelaciones(ctx, year),
        "historico": historico, "evolucion": evolucion, "alertas": alertas(ctx, P, kind),
        "fotos": _fotos(snaps), "reservas": _resumen_reservas(ctx.noches), "config": config or {},
    }


def _fotos(snaps):
    return [{"id": s.get("id"), "kind": s["kind"], "as_of": s["as_of"], "file_name": s.get("file_name"),
             "has_forecast": s.get("has_forecast", True), "desde": s.get("date_from"), "hasta": s.get("date_to")}
            for s in sorted(snaps, key=lambda s: (s["as_of"], s["kind"]), reverse=True)]


def _resumen_reservas(N: Noches) -> dict:
    return {"cuenta": N.cuenta, "desde": N.min_ins, "hasta": N.max_ins}


def limpiar(obj: Any) -> Any:
    """Redondea floats para que el JSON no viaje con 15 decimales."""
    if isinstance(obj, float):
        return round(obj, 4)
    if isinstance(obj, dict):
        return {k: limpiar(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [limpiar(v) for v in obj]
    return obj
