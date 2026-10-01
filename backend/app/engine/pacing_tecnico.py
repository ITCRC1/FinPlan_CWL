# -*- coding: utf-8 -*-
"""Análisis técnico del año: mes por mes, el general, y por qué creerle al proyectado.

Owner, 2026-09-30, sobre «Posición mensual»: *«puedes hacer un análisis técnico
acá para todo el año… por mes y después en forma general. Empezando del 2026 y
mirando el pace las oportunidades que hay para poder lograr el proyectado, y por
qué el proyectado es un buen parámetro… que quede claro por qué podemos confiar
en el proyectado. Además que se pueda bajar a Excel en forma profesional… listo
para compartir con la Junta.»*

Puro Python. No calcula una proyección nueva: lee la de `pacing.construir`
(la misma de la tabla de Posición) y la pone a prueba contra tres cosas:

1. **El año base.** Cada mes del año anterior: cuánto había en libros a la misma
   fecha (STLY), con cuánto cerró y qué parte de las habitaciones LIBRES se
   llenó después. Esa tasa de llenado es lo único que la proyección supone.
2. **El esfuerzo que pide.** «Pickup necesario» (proyectado − en libros) contra
   el pickup que el año anterior SÍ logró desde la misma fecha. Si pide menos
   de lo que ya se hizo, el número es alcanzable con el ritmo conocido.
3. **Los otros métodos.** El mismo motor con «sumar pickup» y «multiplicar por
   pace». Dónde cae el proyectado dentro de ese rango dice si es prudente.

⚠️ **Los textos salen de acá, en español o inglés (`lang`).** La pantalla y el
Excel de la Junta tienen que decir EXACTAMENTE lo mismo; si cada uno armara su
redacción, la Junta podría leer una cifra en el Excel que no está en pantalla.

⚠️ **Ventanas de pickup largas contra el año anterior.** Las reservas arrancan
con una carga de migración (todo lo que había en libros ese día entra con la
misma fecha de creación). Una ventana del año anterior que la contiene no es
comparable y se marca `comparable: False` en vez de mostrarse como caída.
"""
from __future__ import annotations

from datetime import date

from app.engine.pacing import (
    ESCENARIOS, FUENTES_STLY, Contexto, anios_en, con_en_sitio, construir, dias_del_mes, estado,
    expandir, mas_dias, meta_de, mensual, pickup_reciente, reservas_mensual, un_anio_antes,
)

METODOS = ("avail", "add", "mult")
#: Días antes de la primera noche del mes para la «ventana de reserva».
LEADS = (180, 120, 90, 60, 30)

MESES = {
    "es": ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
           "Septiembre", "Octubre", "Noviembre", "Diciembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
}


def _n(v) -> str:
    return f"{round(v or 0):,}"


def _u(v) -> str:
    return f"${round(v or 0):,}"


def _p(v, d=0) -> str:
    return "—" if v is None else f"{v * 100:.{d}f}%"


def _div(a, b):
    return a / b if b else None


# ───────────────────────────── el año base ─────────────────────────────
def _base(ctx: Contexto, kind: str, T: int, P: dict) -> dict:
    """El año anterior visto desde la proyección del año T."""
    B = T - 1
    PB = con_en_sitio(ctx, construir(ctx, kind, B, P["escenario"]), kind)
    hf = mensual(ctx.dias(kind), B)
    rv = reservas_mensual(ctx.noches, B, lambda x: x["st"] == "A") if ctx.noches.cuenta else None
    meta = meta_de(ctx.config, kind, B)
    filas = []
    for i, x in enumerate(P["rows"]):
        b = PB["rows"][i]
        cerrado = b["cerrado"]
        recon = _div(rv[i]["rn"], hf[i]["rn"]) if rv and cerrado and hf[i]["rn"] else None
        filas.append({
            "i": i, "cerrado": cerrado, "abierto": not cerrado and bool(b["otb_rn"] or b["proj"]),
            "cap": b["cap"], "rn": b["proj"], "rev": b["proj_rev"], "occ": _div(b["proj"], b["cap"]),
            "adr": _div(b["proj_rev"], b["proj"]), "otb_hoy": b["otb_rn"],
            "meta_rn": meta["rn"][i] if meta else None, "meta_rev": meta["rev"][i] if meta else None,
            "stly": x["st_rn"], "pick": x["pick"], "tasa": x["tasa"], "cap_ly": x["cap_ly"],
            "reconcilia": recon,
        })
    cer = [f for f in filas if f["cerrado"] and f["rn"]]
    rec = [f for f in cer if f["reconcilia"] is not None]
    tot = {k: sum((f[k] or 0) for f in filas) for k in ("cap", "rn", "rev", "otb_hoy")}
    tot["occ"] = _div(tot["rn"], tot["cap"]); tot["adr"] = _div(tot["rev"], tot["rn"])
    tot["meta_rn"] = sum(f["meta_rn"] or 0 for f in filas) if meta else None
    tot["meta_rev"] = sum(f["meta_rev"] or 0 for f in filas) if meta else None
    tot["real_rn"] = sum(f["rn"] for f in filas if f["cerrado"])
    tot["real_rev"] = sum(f["rev"] for f in filas if f["cerrado"])
    tot["meses_reales"] = len(cer)
    tot["meses_abiertos"] = sum(1 for f in filas if f["abierto"])
    tot["reconcilia"] = _div(sum(rv[f["i"]]["rn"] for f in rec), sum(hf[f["i"]]["rn"] for f in rec)) if rec else None
    tot["reconcilia_meses"] = len(rec)
    return {"anio": B, "filas": filas, "tot": tot, "ventana": _ventana(ctx, B, filas)}


def _ventana(ctx: Contexto, B: int, filas: list[dict]) -> list[dict]:
    """% de las noches con que cerró cada mes que ya estaba reservado X días antes.

    Sólo se publica un punto si es OBSERVABLE: si la fecha cae antes de la carga
    de migración, todo lo anterior aparece creado ese día y el % sería falso.
    """
    N = ctx.noches
    if not N.cuenta:
        return []
    out = []
    for f in filas:
        if not f["cerrado"] or not f["rn"]:
            continue
        ini = date(B, f["i"] + 1, 1).isoformat()
        noches = [x for x in N.lista if x["y"] == B and x["m"] == f["i"] and x["st"] == "A"]
        total = sum(x["rms"] for x in noches)
        if not total:
            continue
        puntos = {}
        for L in LEADS:
            corte = mas_dias(ini, -L)
            if corte <= N.min_ins:
                puntos[str(L)] = None
                continue
            puntos[str(L)] = sum(x["rms"] for x in noches if x["ins"] <= corte) / total
        out.append({"i": f["i"], "puntos": puntos})
    return out


# ───────────────────────────── cada mes ─────────────────────────────
def _confianza(m: dict) -> tuple[str, int, list[str]]:
    """Puntaje simple y explicable. Cada punto tiene su razón (clave)."""
    if m["sin_operacion"]:
        return "sin_operacion", 0, []
    pts, razones = 0, []
    a = m["asegurado"]
    if a is not None and a >= 0.6:
        pts += 2; razones.append("asegurado_alto")
    elif a is not None and a >= 0.3:
        pts += 1; razones.append("asegurado_medio")
    r = m["esfuerzo"]
    if r is not None and r <= 0.9:
        pts += 2; razones.append("esfuerzo_bajo")
    elif r is not None and r <= 1.1:
        pts += 1; razones.append("esfuerzo_igual")
    if m["ly_base"] == "real":
        pts += 1; razones.append("base_real")
    if m["pace"] is not None and m["pace"] >= 1:
        pts += 1; razones.append("pace_arriba")
    if m["bloqueos_pct"] is not None and m["bloqueos_pct"] > 0.25:
        pts -= 2 if m["bloqueos_pct"] > 0.5 else 1; razones.append("bloqueos_altos")
    if m["tarifa_atipica"]:
        pts -= 1; razones.append("tarifa_atipica")
    nivel = "alta" if pts >= 5 else "media" if pts >= 3 else "baja"
    return nivel, pts, razones


def _mes(x: dict, P: dict, alt: dict, corte: str, ritmo30: list[float], T: int, tar: dict | None) -> dict:
    i = x["i"]
    otb, proj, cap = x["otb_rn"], x["proj"], x["cap"]
    falta = max(0.0, proj - otb)
    fin = date(T, i + 1, dias_del_mes(T, i))
    dias = (fin - date.fromisoformat(corte)).days if corte else None
    semanas = max(1.0, dias / 7) if dias and dias > 0 else None
    proj_adr = _div(x["proj_rev"], proj)
    ly_adr = x["ly_adr"]
    # Tarifa reservada contra tarifa reservada: las dos de las reservas, sin consumo
    # en sitio. El STLY de Total Revenue trae el consumo del año anterior prorrateado
    # y compararlo con lo reservado hoy daría caídas de tarifa que no existen.
    otb_adr = _div(tar["hoy"][i]["amt"], tar["hoy"][i]["rn"]) if tar else None
    st_adr = _div(tar["ly"][i]["amt"], tar["ly"][i]["rn"]) if tar else None
    anio_adr = _div(P["tot"]["proj_rev"], P["tot"]["proj"])
    n5 = min(libres_ := max(0.0, cap - proj), cap * 0.05)
    libres = libres_
    ly_base = "alcance" if x["ly_alcance"] else "reservas" if x["ly_de_reservas"] else "real" if x["ly_rn"] else "sin"
    m = {
        "i": i, "cerrado": x["cerrado"], "cap": cap, "otb": otb, "otb_rev": x["otb_rev"],
        "occ_otb": _div(otb, cap), "stly": x["st_rn"], "pace": x["pace"],
        "ly": x["ly_rn"], "ly_rev": x["ly_rev"], "ly_occ": _div(x["ly_rn"], x["cap_ly"]), "ly_base": ly_base,
        "proj": proj, "proj_rev": x["proj_rev"], "proj_occ": x["proj_occ"],
        "proj_vs_ly": _div(proj, x["ly_rn"]), "rev_vs_ly": _div(x["proj_rev"], x["ly_rev"]),
        "falta": falta, "asegurado": _div(otb, proj) if proj else None,
        "ly_pick": x["pick"], "esfuerzo": _div(falta, x["pick"]) if x["pick"] and x["pick"] > 0 else None,
        "tasa": x["tasa"], "dias": dias, "semanas": semanas,
        "por_semana": falta / semanas if semanas else None,
        "ritmo_semana": ritmo30[i] * 7 / 30 if ritmo30 else None,
        "otb_adr": otb_adr, "st_adr": st_adr,
        "tarifa_vs_stly": otb_adr / st_adr - 1 if otb_adr and st_adr and tar["hoy"][i]["rn"] >= 30 and tar["ly"][i]["rn"] >= 30 else None,
        "tarifa_atipica": bool(proj_adr and anio_adr and proj > 0 and proj_adr < 0.4 * anio_adr),
        "base_pace": x["base_pace"], "dif_stly": x["base_pace"] - x["st_rn"] if x["st_rn"] is not None else None,
        "proj_adr": proj_adr, "ly_adr": ly_adr,
        "libres": libres, "valor_libres": libres * (proj_adr or 0),
        "rn_5pp": n5, "valor_5pp": n5 * (proj_adr or 0),
        "valor_tarifa_5": falta * (proj_adr or 0) * 0.05,
        "anio_adr": anio_adr, "bloqueos": x["bloqueos"], "bloqueos_pct": _div(x["bloqueos"], otb) if x["bloqueos"] is not None and otb else None,
        "metodos": {k: alt[k]["rows"][i]["proj"] for k in alt}, "metodos_rev": {k: alt[k]["rows"][i]["proj_rev"] for k in alt},
        "estado": estado(x),
        "sin_operacion": not cap or (not otb and not proj and not x["ly_rn"]),
    }
    nivel, pts, razones = _confianza(m)
    m.update(confianza=nivel, puntos=pts, razones=razones)
    return m


# ───────────────────────────── textos ─────────────────────────────
TXT = {
    "es": {
        "sin_op": "{mes}: sin operación prevista (sin noches en libros, sin año anterior y sin proyección).",
        "cerrado": "{mes}: mes cerrado — {rn} RN reales, {rev}.",
        "libros": "{mes}: {otb} RN en libros ({occ} de ocupación)",
        "pace": "; las reservas individuales llevan {dif} RN {dir} que a la misma fecha del año anterior (pace {pace}).",
        "solo_bloqueos": "; todo lo que hay en libros son bloqueos de grupo: 0 reservas individuales contra {st} hace un año.",
        "sin_stly": "; sin dato comparable del año anterior a la misma fecha.",
        "proj": " El proyectado es {proj} RN ({pocc}) y {prev}; {vs}.",
        "vs_ly": "{x} contra el cierre {ly} del año anterior ({lyrn} RN)",
        "base_real": "real", "base_alcance": "proyectado", "base_reservas": "reconstruido de reservas",
        "falta": " Faltan {falta} RN: {esf} de lo que el año anterior recogió desde esta misma fecha ({pick} RN), ~{sem} RN por semana.",
        "falta_sin": " Faltan {falta} RN, ~{sem} RN por semana.",
        "asegurado": " Ya está asegurado el {a} del proyectado.",
        "tarifa": " Tarifa en libros {otb} por noche, {dif} contra la del año anterior a la misma fecha ({st}).",
        "oport": " Oportunidad: cada 5 puntos de ocupación sobre el proyectado (~{n5} RN) valen ~{v5}, y +5% de tarifa en lo que falta vender ~{t5}; quedan {libres} noches libres.",
        "atipica": " Ojo: la tarifa de referencia de este mes ({adr}) es atípica frente al promedio del año ({anio}); revisar el ingreso cargado del año anterior.",
        "riesgo_pace": " Riesgo: el ritmo va por debajo del año anterior; conviene acción comercial temprana.",
        "riesgo_alcance": " Ojo: el año anterior de este mes todavía es una proyección, no un cierre real.",
        "riesgo_bloq": " Riesgo: {b} RN ({bp}) son bloqueos de grupo sin rooming list; vigilar la liberación.",
        "conf": " Confianza {n}.",
        "niveles": {"alta": "alta", "media": "media", "baja": "baja", "sin_operacion": "sin operación"},
        "mas": "más", "menos": "menos",
        "razones": {
            "asegurado_alto": "60% o más del proyectado ya está en libros",
            "asegurado_medio": "entre 30% y 60% del proyectado ya está en libros",
            "esfuerzo_bajo": "pide menos pickup del que el año anterior logró desde la misma fecha",
            "esfuerzo_igual": "pide un pickup similar al que el año anterior logró",
            "base_real": "la referencia del año anterior es un cierre real",
            "pace_arriba": "el ritmo de reservas va por encima del año anterior",
            "bloqueos_altos": "más del 25% de lo que está en libros son bloqueos de grupo",
            "tarifa_atipica": "la tarifa de referencia del año anterior es atípica",
        },
    },
    "en": {
        "sin_op": "{mes}: no operation expected (no nights on the books, no prior year and no projection).",
        "cerrado": "{mes}: closed month — {rn} actual RN, {rev}.",
        "libros": "{mes}: {otb} RN on the books ({occ} occupancy)",
        "pace": "; individual reservations are {dif} RN {dir} than at the same date last year (pace {pace}).",
        "solo_bloqueos": "; everything on the books is group blocks: 0 individual reservations versus {st} a year ago.",
        "sin_stly": "; no comparable prior-year figure at the same date.",
        "proj": " The projection is {proj} RN ({pocc}) and {prev}; {vs}.",
        "vs_ly": "{x} versus last year's {ly} close ({lyrn} RN)",
        "base_real": "actual", "base_alcance": "projected", "base_reservas": "rebuilt from reservations",
        "falta": " {falta} RN to go: {esf} of what last year picked up from this same date ({pick} RN), ~{sem} RN per week.",
        "falta_sin": " {falta} RN to go, ~{sem} RN per week.",
        "asegurado": " {a} of the projection is already secured.",
        "tarifa": " Rate on the books {otb} per night, {dif} versus last year at the same date ({st}).",
        "oport": " Opportunity: every 5 occupancy points above the projection (~{n5} RN) is worth ~{v5}, and +5% rate on what is still to be sold ~{t5}; {libres} nights remain unsold.",
        "atipica": " Note: this month's reference rate ({adr}) is atypical against the year average ({anio}); check last year's loaded revenue.",
        "riesgo_pace": " Risk: booking pace is behind last year; early commercial action is advised.",
        "riesgo_alcance": " Note: last year's figure for this month is still a projection, not an actual close.",
        "riesgo_bloq": " Risk: {b} RN ({bp}) are group blocks without a rooming list; watch the release.",
        "conf": " Confidence {n}.",
        "niveles": {"alta": "high", "media": "medium", "baja": "low", "sin_operacion": "no operation"},
        "mas": "more", "menos": "fewer",
        "razones": {
            "asegurado_alto": "60% or more of the projection is already on the books",
            "asegurado_medio": "30%–60% of the projection is already on the books",
            "esfuerzo_bajo": "it needs less pickup than last year achieved from the same date",
            "esfuerzo_igual": "it needs a pickup similar to what last year achieved",
            "base_real": "the prior-year reference is an actual close",
            "pace_arriba": "booking pace is ahead of last year",
            "bloqueos_altos": "more than 25% of the books are group blocks",
            "tarifa_atipica": "last year's reference rate is atypical",
        },
    },
}


def _comentario(m: dict, T: int, lang: str) -> str:
    L = TXT[lang]
    mes = f"{MESES[lang][m['i']]} {T}"
    if m["sin_operacion"]:
        return L["sin_op"].format(mes=mes)
    if m["cerrado"]:
        return L["cerrado"].format(mes=mes, rn=_n(m["otb"]), rev=_u(m["otb_rev"]))
    s = L["libros"].format(mes=mes, otb=_n(m["otb"]), occ=_p(m["occ_otb"], 1))
    if m["stly"] is not None and m["otb"] and not m["base_pace"] and m["stly"]:
        s += L["solo_bloqueos"].format(st=_n(m["stly"]))
    elif m["stly"] is not None and m["pace"] is not None:
        d = m["dif_stly"]
        s += L["pace"].format(dif=_n(abs(d)), dir=L["mas"] if d >= 0 else L["menos"], pace=_p(m["pace"]))
    else:
        s += L["sin_stly"]
    vs = (L["vs_ly"].format(x=_signo(m["proj_vs_ly"]), ly=L.get("base_" + m["ly_base"], ""), lyrn=_n(m["ly"]))
          if m["ly"] else "—")
    s += L["proj"].format(proj=_n(m["proj"]), pocc=_p(m["proj_occ"], 1), prev=_u(m["proj_rev"]), vs=vs)
    if m["falta"] > 0:
        sem = _n(m["por_semana"]) if m["por_semana"] is not None else "—"
        if m["esfuerzo"] is not None:
            s += L["falta"].format(falta=_n(m["falta"]), esf=_p(m["esfuerzo"]), pick=_n(m["ly_pick"]), sem=sem)
        else:
            s += L["falta_sin"].format(falta=_n(m["falta"]), sem=sem)
    if m["asegurado"] is not None:
        s += L["asegurado"].format(a=_p(m["asegurado"]))
    if m["tarifa_vs_stly"] is not None:
        t = m["tarifa_vs_stly"]
        s += L["tarifa"].format(otb=_u(m["otb_adr"]), dif=("+" if t >= 0 else "−") + _p(abs(t), 1), st=_u(m["st_adr"]))
    if m["libres"] >= 1:
        s += L["oport"].format(n5=_n(m["rn_5pp"]), v5=_u(m["valor_5pp"]), t5=_u(m["valor_tarifa_5"]), libres=_n(m["libres"]))
    if m["tarifa_atipica"]:
        s += L["atipica"].format(adr=_u(m["proj_adr"]), anio=_u(m["anio_adr"]))
    if m["pace"] is not None and m["pace"] < 1:
        s += L["riesgo_pace"]
    if m["ly_base"] == "alcance":
        s += L["riesgo_alcance"]
    if "bloqueos_altos" in m["razones"]:
        s += L["riesgo_bloq"].format(b=_n(m["bloqueos"]), bp=_p(m["bloqueos_pct"]))
    s += L["conf"].format(n=L["niveles"][m["confianza"]])
    return s


# ───────────────────────────── lo general ─────────────────────────────
def _general(P: dict, alt: dict, meses: list[dict], base: dict, pick: dict | None, lang: str) -> dict:
    t = P["tot"]
    abiertos = [m for m in meses if not m["cerrado"] and not m["sin_operacion"]]
    falta = sum(m["falta"] for m in abiertos)
    ly_pick = sum(m["ly_pick"] or 0 for m in abiertos if m["ly_pick"] is not None)
    metodos = {k: {"rn": alt[k]["tot"]["proj"], "rev": alt[k]["tot"]["proj_rev"]} for k in alt}
    orden = sorted(metodos, key=lambda k: metodos[k]["rn"])
    vent = []
    if pick:
        for f in pick["ventanas"]:
            vent.append({"dias": f["dias"], "rn": f["anio"]["rn"], "ly": f["anterior"]["rn"],
                         "comparable": not f["anterior"]["migracion"]})
    # Donde más capacidad libre queda: meses de temporada media/baja con occ proyectada < 60%.
    oportunidades = sorted((m for m in abiertos if m["libres"] >= 1 and (m["proj_occ"] or 0) < 0.6),
                           key=lambda m: -m["libres"])[:4]
    riesgos = [m for m in abiertos if (m["pace"] is not None and m["pace"] < 1)
               or m["confianza"] == "baja" or m["ly_base"] == "alcance"]
    g = {
        "cap": t["cap"], "otb": t["otb_rn"], "otb_rev": t["otb_rev"], "occ_otb": t["occ"],
        "stly": t["st_rn"], "pace": t["pace"], "base_pace": t["base_pace"], "bloqueos": t["bloqueos"], "ly": t["ly_rn"], "ly_rev": t["ly_rev"],
        "proj": t["proj"], "proj_rev": t["proj_rev"], "proj_occ": t["proj_occ"],
        "proj_vs_ly": _div(t["proj"], t["ly_rn"]), "rev_vs_ly": _div(t["proj_rev"], t["ly_rev"]),
        "asegurado": _div(t["otb_rn"], t["proj"]), "falta": falta, "ly_pick": ly_pick,
        "esfuerzo": _div(falta, ly_pick) if ly_pick > 0 else None,
        "libres": sum(m["libres"] for m in abiertos), "valor_libres": sum(m["valor_libres"] for m in abiertos),
        "rn_5pp": sum(m["rn_5pp"] for m in abiertos), "valor_5pp": sum(m["valor_5pp"] for m in abiertos),
        "valor_tarifa_5": sum(m["valor_tarifa_5"] for m in abiertos),
        "metodos": metodos, "orden": orden, "posicion_metodo": orden.index(P["escenario"]) if P["escenario"] in orden else None,
        "ventanas": vent, "oportunidades": [m["i"] for m in oportunidades], "riesgos": [m["i"] for m in riesgos],
        "confianza": {n: sum(1 for m in abiertos if m["confianza"] == n) for n in ("alta", "media", "baja")},
    }
    g["conclusiones"] = _conclusiones(g, P, base, meses, lang)
    g["porque"] = _porque(g, P, base, lang)
    g["limites"] = _limites(g, P, base, lang)
    return g


def _conclusiones(g, P, base, meses, lang) -> list[str]:
    T, M = P["T"], MESES[lang]
    es = lang == "es"
    out = []
    bt = base["tot"]
    if bt["rn"]:
        out.append((f"Base {T-1}: {_n(bt['rn'])} RN y {_u(bt['rev'])} ({_p(bt['occ'], 1)} de ocupación); "
                    f"{bt['meses_reales']} meses son cierre real y {bt['meses_abiertos']} están en curso con su proyección.")
                   if es else
                   (f"{T-1} base: {_n(bt['rn'])} RN and {_u(bt['rev'])} ({_p(bt['occ'], 1)} occupancy); "
                    f"{bt['meses_reales']} months are actual closes and {bt['meses_abiertos']} are still open with their projection."))
        if bt["meta_rn"]:
            out.append((f"Contra el presupuesto {T-1} ({_n(bt['meta_rn'])} RN / {_u(bt['meta_rev'])}) el año cierra en "
                        f"{_p(_div(bt['rn'], bt['meta_rn']))} de las noches y {_p(_div(bt['rev'], bt['meta_rev']))} del ingreso.")
                       if es else
                       (f"Against the {T-1} budget ({_n(bt['meta_rn'])} RN / {_u(bt['meta_rev'])}) the year closes at "
                        f"{_p(_div(bt['rn'], bt['meta_rn']))} of the nights and {_p(_div(bt['rev'], bt['meta_rev']))} of the revenue."))
    if g["stly"]:
        d = g["base_pace"] - g["stly"]
        b = g["otb"] - g["base_pace"]
        out.append((f"{T} hoy: {_n(g['otb'])} RN en libros ({_p(g['occ_otb'], 1)}), de ellos {_n(b)} en bloqueos de grupo. "
                    f"Las reservas individuales ({_n(g['base_pace'])}) van {'+' if d >= 0 else '−'}{_n(abs(d))} RN contra las "
                    f"{_n(g['stly'])} que había hace un año a la misma fecha (pace {_p(g['pace'])}).")
                   if es else
                   (f"{T} today: {_n(g['otb'])} RN on the books ({_p(g['occ_otb'], 1)}), {_n(b)} of them group blocks. "
                    f"Individual reservations ({_n(g['base_pace'])}) are {'+' if d >= 0 else '−'}{_n(abs(d))} RN versus the "
                    f"{_n(g['stly'])} on the books a year ago at the same date (pace {_p(g['pace'])})."))
    out.append((f"Proyectado {T}: {_n(g['proj'])} RN ({_p(g['proj_occ'], 1)}) y {_u(g['proj_rev'])}; "
                f"{_signo(g['proj_vs_ly'])} en noches y {_signo(g['rev_vs_ly'])} en ingreso contra {T-1}.")
               if es else
               (f"{T} projection: {_n(g['proj'])} RN ({_p(g['proj_occ'], 1)}) and {_u(g['proj_rev'])}; "
                f"{_signo(g['proj_vs_ly'])} in nights and {_signo(g['rev_vs_ly'])} in revenue versus {T-1}."))
    if g["esfuerzo"] is not None:
        out.append((f"Para llegar faltan {_n(g['falta'])} RN: el {_p(g['esfuerzo'])} de lo que {T-1} recogió desde "
                    f"la misma fecha ({_n(g['ly_pick'])} RN). Ya está asegurado el {_p(g['asegurado'])}.")
                   if es else
                   (f"{_n(g['falta'])} RN still to book: {_p(g['esfuerzo'])} of what {T-1} picked up from the same date "
                    f"({_n(g['ly_pick'])} RN). {_p(g['asegurado'])} is already secured."))
    if g["oportunidades"]:
        lst = ", ".join(f"{M[i]} ({_p(meses[i]['proj_occ'])}, {_n(meses[i]['libres'])} libres)" if es else
                        f"{M[i]} ({_p(meses[i]['proj_occ'])}, {_n(meses[i]['libres'])} unsold)" for i in g["oportunidades"])
        out.append((f"Donde más espacio hay para crecer: {lst}. Cada 5 puntos de ocupación sobre el proyectado en los meses "
                    f"abiertos valen ~{_u(g['valor_5pp'])} ({_n(g['rn_5pp'])} RN); +5% de tarifa en lo que falta vender, ~{_u(g['valor_tarifa_5'])}.")
                   if es else
                   (f"Most room to grow: {lst}. Every 5 occupancy points above the projection in the open months is worth "
                    f"~{_u(g['valor_5pp'])} ({_n(g['rn_5pp'])} RN); +5% rate on what is still to be sold, ~{_u(g['valor_tarifa_5'])}."))
    comp = [v for v in g["ventanas"] if v["comparable"] and v["ly"]]
    if comp:
        v = comp[-1]
        out.append((f"Ritmo reciente: en los últimos {v['dias']} días entraron {_n(v['rn'])} RN para {T}, contra {_n(v['ly'])} "
                    f"en la misma ventana del año anterior ({_signo(_div(v['rn'], v['ly']))}).")
                   if es else
                   (f"Recent pace: in the last {v['dias']} days {_n(v['rn'])} RN were booked for {T}, versus {_n(v['ly'])} "
                    f"in the same window last year ({_signo(_div(v['rn'], v['ly']))})."))
    if g["riesgos"]:
        lst = ", ".join(M[i] for i in g["riesgos"])
        out.append((f"Meses a vigilar: {lst} (ritmo bajo el año anterior, confianza baja o referencia aún proyectada)."
                    if es else
                    f"Months to watch: {lst} (pace behind last year, low confidence or a reference that is still projected)."))
    return out


def _signo(r) -> str:
    if r is None:
        return "—"
    v = r - 1
    return ("+" if v >= 0 else "−") + f"{abs(v) * 100:.0f}%"


def _porque(g, P, base, lang) -> list[dict]:
    """Las razones para confiar, cada una con su evidencia en números."""
    T, es = P["T"], lang == "es"
    bt = base["tot"]
    nom = {"es": {"avail": "disponibilidad", "add": "sumar pickup", "mult": "multiplicar por pace"},
           "en": {"avail": "availability", "add": "add pickup", "mult": "multiply by pace"}}[lang]
    m = g["metodos"]
    out = []
    out.append({"titulo": "Sale del comportamiento real, no de un supuesto" if es else "It comes from actual behaviour, not an assumption",
                "texto": (f"Cada mes parte de lo que ya está en libros y le suma sólo la parte de las habitaciones libres que {T-1} "
                          f"llenó desde esta misma fecha. No hay porcentajes de crecimiento puestos a mano.")
                if es else
                (f"Each month starts from what is already on the books and adds only the share of free rooms that {T-1} "
                 f"filled from this same date. There are no hand-entered growth rates.")})
    if bt["reconcilia"] is not None:
        out.append({"titulo": "Los datos cuadran entre sí" if es else "The data reconciles",
                    "texto": (f"En los {bt['reconcilia_meses']} meses cerrados de {T-1}, las reservas (de donde salen el STLY y el ritmo) "
                              f"suman el {_p(bt['reconcilia'], 1)} de las noches del History & Forecast de Opera.")
                    if es else
                    (f"In the {bt['reconcilia_meses']} closed months of {T-1}, the reservations (source of STLY and pace) add up to "
                     f"{_p(bt['reconcilia'], 1)} of the room nights in Opera's History & Forecast.")})
    if g["posicion_metodo"] is not None:
        rango = " · ".join(f"{nom[k]} {_n(m[k]['rn'])} RN" for k in g["orden"])
        pos = {0: ("el más conservador" if es else "the most conservative"),
               1: ("el del medio" if es else "the middle one"),
               2: ("el más alto" if es else "the highest")}[g["posicion_metodo"]]
        out.append({"titulo": "Es prudente frente a otros métodos" if es else "It is prudent against other methods",
                    "texto": (f"Con los mismos datos, tres métodos estándar dan: {rango}. El proyectado usado ({nom[P['escenario']]}) es {pos}: "
                              f"no multiplica el pace y no puede pasar de las habitaciones disponibles.")
                    if es else
                    (f"With the same data, three standard methods give: {rango}. The projection used ({nom[P['escenario']]}) is {pos}: "
                     f"it does not multiply the pace and cannot exceed available rooms.")})
    if g["esfuerzo"] is not None:
        out.append({"titulo": "Pide menos de lo que ya se hizo" if es and g["esfuerzo"] <= 1 else
                    "Pide un esfuerzo conocido" if es else
                    "It asks for less than was already achieved" if g["esfuerzo"] <= 1 else "It asks for a known effort",
                    "texto": (f"El pickup que falta ({_n(g['falta'])} RN) es el {_p(g['esfuerzo'])} del que {T-1} logró desde la misma fecha "
                              f"({_n(g['ly_pick'])} RN).")
                    if es else
                    (f"The pickup still needed ({_n(g['falta'])} RN) is {_p(g['esfuerzo'])} of what {T-1} achieved from the same date "
                     f"({_n(g['ly_pick'])} RN).")})
    out.append({"titulo": "Una parte importante ya está asegurada" if es else "A large part is already secured",
                "texto": (f"{_n(g['otb'])} de los {_n(g['proj'])} RN proyectados ({_p(g['asegurado'])}) ya son reservas en libros "
                          f"por {_u(g['otb_rev'])}.")
                if es else
                (f"{_n(g['otb'])} of the {_n(g['proj'])} projected RN ({_p(g['asegurado'])}) are already reservations on the books "
                 f"worth {_u(g['otb_rev'])}.")})
    c = g["confianza"]
    out.append({"titulo": "Se mide mes por mes" if es else "It is scored month by month",
                "texto": (f"Confianza por mes: {c['alta']} alta, {c['media']} media, {c['baja']} baja (ver «Análisis por mes»).")
                if es else
                (f"Confidence by month: {c['alta']} high, {c['media']} medium, {c['baja']} low (see 'Monthly analysis').")})
    return out


def _limites(g, P, base, lang) -> list[str]:
    T, es = P["T"], lang == "es"
    bt = base["tot"]
    out = []
    if bt["meses_abiertos"]:
        out.append(f"{bt['meses_abiertos']} meses de {T-1} todavía no cierran: su referencia es la proyección de {T-1}, no un real."
                   if es else
                   f"{bt['meses_abiertos']} months of {T-1} have not closed yet: their reference is the {T-1} projection, not an actual.")
    out.append(("Una prueba completa hacia atrás (proyectar un año ya cerrado y compararlo) necesita dos años de historia de reservas; "
                "hoy hay una. Al cerrar cada mes de " + str(T) + " se podrá medir el acierto del método.")
               if es else
               ("A full back-test (projecting a closed year and comparing) needs two years of reservation history; there is one today. "
                "As each month of " + str(T) + " closes, the method's accuracy can be measured."))
    if any(not v["comparable"] for v in g["ventanas"]):
        out.append("Las ventanas de pickup de 30 días o más del año anterior incluyen la carga inicial de reservas y no son comparables."
                   if es else
                   "Prior-year pickup windows of 30 days or more include the initial reservation load and are not comparable.")
    out.append("El ingreso incluye una estimación del consumo en sitio (configurable en Cargas)."
               if es else "Revenue includes an estimate of on-site spend (configurable in Uploads).")
    return out


# ───────────────────────────── todo junto ─────────────────────────────
def analisis_tecnico(snaps: list[dict], reservas: list[dict], config: dict, *, year: int | None = None,
                     kind: str = "total", escenario: str = "avail", fuente: str = "auto", lang: str = "es") -> dict:
    lang = lang if lang in TXT else "es"
    esc = escenario if escenario in METODOS else "avail"
    ctx = Contexto(snaps=snaps, noches=expandir(reservas), config=config or {}, escenario=esc,
                   fuente=fuente if fuente in FUENTES_STLY else "auto")
    anios = anios_en(ctx.dias(kind))
    corte = ctx.corte(kind)
    if not anios or not corte:
        return {"vacio": True}
    if year is None or year not in anios:
        pref = int(corte[:4]) + 1
        year = pref if pref in anios else anios[-1]
    alt = {k: con_en_sitio(ctx, construir(ctx, kind, year, k), kind) for k in METODOS}
    P = alt[esc]
    for r in P["rows"]:
        r["estado"] = estado(r)
    pick = pickup_reciente(ctx, year, corte)
    ritmo = pick["ultimos_30_por_mes"] if pick else []
    tar = None
    if ctx.noches.cuenta:
        D = un_anio_antes(corte)
        tar = {"hoy": reservas_mensual(ctx.noches, year, lambda x: x["st"] == "A" and x["ins"] <= corte),
               "ly": reservas_mensual(ctx.noches, year - 1, lambda x: x["st"] == "A" and x["ins"] <= D)}
    meses = [_mes(x, P, alt, corte, ritmo, year, tar) for x in P["rows"]]
    for m in meses:
        m["comentario"] = _comentario(m, year, lang)
        m["razones_txt"] = [TXT[lang]["razones"][r] for r in m["razones"]]
        m["confianza_txt"] = TXT[lang]["niveles"][m["confianza"]]
    base = _base(ctx, kind, year, P)
    g = _general(P, alt, meses, base, pick, lang)
    return {"vacio": False, "anio": year, "corte": corte, "kind": kind, "escenario": esc, "lang": lang,
            "stly": {k: P["st"].get(k) for k in ("src", "as_of", "gap")} if P["st"] else None,
            "meses": meses, "base": base, "general": g, "posicion": P}
