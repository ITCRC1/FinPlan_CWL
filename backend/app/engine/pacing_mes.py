# -*- coding: utf-8 -*-
"""Análisis profundo de UN mes: el estudio de diciembre 2026, para cualquier mes.

Owner, 2026-09-30: el estudio «Pacing Diciembre 2026» (Word para Revenue y
Ventas) pasa a vivir en FinPlan como tab, y el mismo análisis para noviembre.
*«Mismo análisis, debe darme igual al que compartí»*: con los XML del corte
30-sep-2026 este módulo reproduce las cifras del Word (395 RN en libros contra
723 de meta, ~627 RN y ~$621,330 de alcance, 25 RN/semana necesarias, nueve
reservas marcadas por tarifa con potencial de $6,994–$14,448).
`tests/test_pacing_mes.py` lo fija.

Puro Python, como `pacing.py`: recibe fotos, reservas COMPLETAS (con huésped,
garantía, pax, grupo, tipo de habitación y tarifa noche) y la configuración.

⚠️ **Dos fuentes de room nights, a propósito.** «En libros» es el History &
Forecast (incluye bloqueos de grupo sin rooming list). El ritmo, el STLY, los
canales y las tarifas salen de Reservations Entered On, que es lo único que
trae fecha de creación. La diferencia entre las dos se muestra como bloqueos.

⚠️ **El ingreso de las noches nuevas** se valora como en el Word: valor Total
Revenue actual por noche en libros, más el % de consumo en sitio sobre un Room
Revenue valorado al valor reservado por noche del mismo mes del año anterior.
No es la valoración de la proyección general (`pacing.con_en_sitio`), por eso
el alcance de este tab puede diferir en unos dólares del de «Posición mensual».
"""
from __future__ import annotations

import calendar
import math
import re
from collections import defaultdict
from datetime import date, timedelta
from statistics import median
from typing import Iterable

from app.engine.pacing import (
    INV, REV, RN, combinar, dias_entre, mas_dias, meta_de, ultimo_corte, un_anio_antes,
)

#: Garantías que no aseguran la reserva.
GARANTIA_DEBIL = ("NON", "HOLD72", "HOLD")
VENTANAS = (7, 14, 30, 60, 90)
LEAD = ((0, 14), (15, 30), (31, 60), (61, 90), (91, 10_000))


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _canal(ch: str | None) -> str:
    """`C- COSTA RICA SUN TOU` → `COSTA RICA SUN TOU`; directo y vacío juntos."""
    c = (ch or "").strip()
    for p in ("C- ", "T- ", "A- ", "S- "):
        if c.upper().startswith(p):
            c = c[len(p):]
            break
    if not c or c.upper() in ("DIRECTO", "SIN AGENCIA / DIRECTO"):
        return "Directo / sin agencia"
    return c


_HOLD = re.compile(r"\bHOLD\b")


def _es_hold(r: dict) -> bool:
    """Perfil sin nombre: «HOLD, HOLD» en el huésped o en el itinerario.
    Palabra entera — «Holden» es un nombre, no un bloqueo."""
    return bool(_HOLD.search((r.get("guest") or "").upper()) or _HOLD.search((r.get("grupo") or "").upper()))


def _noches_en(r: dict, y: int, m: int) -> list[date]:
    a = _d(r["arr"])
    return [a + timedelta(days=k) for k in range(int(r.get("nts") or 0))
            if (a + timedelta(days=k)).year == y and (a + timedelta(days=k)).month == m]


class _Mes:
    """Las reservas de un mes de llegada, abiertas por noche."""

    def __init__(self, reservas: Iterable[dict], y: int, m: int):
        self.y, self.m = y, m
        self.filas = []
        for r in reservas:
            n = _noches_en(r, y, m)
            if not n:
                continue
            rms = int(r.get("rms") or 1)
            nts = int(r.get("nts") or 0) or 1
            self.filas.append({**r, "_n": n, "_rn": len(n) * rms,
                               "_val": float(r.get("amt") or 0) / nts * len(n) * rms,
                               "_lead": (_d(r["arr"]) - _d(r["ins"])).days})

    def activas(self, hasta: str | None = None):
        return [r for r in self.filas if r["st"] == "A" and (hasta is None or r["ins"] <= hasta)]

    def canceladas(self):
        return [r for r in self.filas if r["st"] == "X"]

    @staticmethod
    def rn(lista):
        return sum(r["_rn"] for r in lista)

    @staticmethod
    def val(lista):
        return sum(r["_val"] for r in lista)


def _hf_mes(days: dict, y: int, m: int) -> dict:
    pref = f"{y}-{m:02d}-"
    out = {"rn": 0.0, "rev": 0.0, "cap": 0.0, "por_dia": {}}
    for d, v in days.items():
        if d.startswith(pref):
            out["rn"] += v[RN]; out["rev"] += v[REV]; out["cap"] += v[INV]
            out["por_dia"][int(d[8:])] = v
    return out


def _periodos(y: int, m: int) -> list[tuple[int, int]]:
    fin = calendar.monthrange(y, m)[1]
    if m == 12:   # el corte del Word: la temporada festiva va aparte
        return [(1, 7), (8, 14), (15, 19), (20, 24), (25, 31)]
    return [(a, min(a + 6, fin)) for a in range(1, fin + 1, 7)]


def _hitos(corte: str, y: int, m: int) -> list[str]:
    """El 15 y el último día de cada mes, desde el corte hasta el fin del mes analizado."""
    out, c = [], _d(corte)
    yy, mm = c.year, c.month
    while (yy, mm) <= (y, m):
        for d in (date(yy, mm, 15), date(yy, mm, calendar.monthrange(yy, mm)[1])):
            if d > c:
                out.append(d.isoformat())
        yy, mm = (yy + 1, 1) if mm == 12 else (yy, mm + 1)
    return out


def _tarifas(act: list[dict]) -> dict:
    """Reservas con tarifa en cero, por persona fuera de rango, distinta dentro de su
    itinerario, sin garantía o con perfil «HOLD».

    Mediana por código de tarifa sobre las reservas activas del mes con tarifa.
    Potencial bajo = llevar la noche a la mediana del código (como máximo a dos
    personas a la mediana por persona); alto = llevar cada persona a la mediana
    por persona del código.

    ⚠️ El potencial es por línea de reserva y por noche, como en el estudio de
    diciembre: no se multiplica por `NO_OF_ROOMS`. Un bloqueo de 3 habitaciones
    en una sola línea cuenta una.
    """
    por_cod: dict[str, list[float]] = defaultdict(list)
    pp_cod: dict[str, list[float]] = defaultdict(list)
    for r in act:
        t = float(r.get("tarifa_noche") or 0)
        if t > 0:
            por_cod[r.get("rate") or ""].append(t)
            pp_cod[r.get("rate") or ""].append(t / max(int(r.get("pax") or 1), 1))
    med = {k: median(v) for k, v in por_cod.items()}
    med_pp = {k: median(v) for k, v in pp_cod.items()}
    grupos: dict[str, list[dict]] = defaultdict(list)
    for r in act:
        if r.get("grupo"):
            grupos[r["grupo"]].append(r)

    filas = []
    for r in act:
        t = float(r.get("tarifa_noche") or 0)
        cod = r.get("rate") or ""
        pax = max(int(r.get("pax") or 1), 1)
        n, rms = len(r["_n"]), int(r.get("rms") or 1)
        uno = 1  # ver docstring: potencial por línea, no por habitación
        m, mp = med.get(cod), med_pp.get(cod)
        f = {"id": r["id"], "guest": r.get("guest"), "canal": _canal(r.get("ch")), "rate": cod,
             "arr": r["arr"], "nts": n, "rms": rms, "pax": pax, "tarifa": round(t, 2),
             "pp": round(t / pax, 2), "mediana": m, "mediana_pp": mp, "grupo": r.get("grupo"),
             "garantia": r.get("garantia"), "bajo": 0.0, "alto": 0.0}
        hermanos = [x for x in grupos.get(r.get("grupo") or "", []) if x["id"] != r["id"]]
        tope = max((float(x.get("tarifa_noche") or 0) for x in hermanos), default=0)
        if t <= 0 and (r.get("fl") or "").upper()[:1] not in ("C", "H") and m:
            f.update(motivo="cero", bajo=m * n * uno, alto=m * n * uno)
        elif t > 0 and mp and t / pax < 0.6 * mp:
            ref = min(m or 0, 2 * mp)
            f.update(motivo="por_persona", bajo=max(0.0, ref - t) * n * uno,
                     alto=max(0.0, mp * pax - t) * n * uno)
        elif t > 0 and tope and t < 0.8 * tope and _es_hold(r):
            # Itinerario sin nombre («HOLD»): una habitación paga menos que la otra.
            f.update(motivo="itinerario", bajo=(tope - t) * n * uno, alto=(tope - t) * n * uno, tope=tope)
        elif (r.get("garantia") or "").upper() == "NON":
            f.update(motivo="sin_garantia")
        elif _es_hold(r):
            f.update(motivo="perfil_hold")
        else:
            continue
        filas.append(f)
    # Un perfil «HOLD» cuyo itinerario ya quedó marcado por tarifa no se repite.
    marcados = {f["grupo"] for f in filas if f["motivo"] != "perfil_hold" and f["grupo"]}
    filas = [f for f in filas if not (f["motivo"] == "perfil_hold" and f["grupo"] in marcados)]
    con_monto = [f for f in filas if f["alto"] > 0]
    return {"filas": sorted(filas, key=lambda f: (-f["alto"], f["arr"], f["id"])),
            "bajo": sum(f["bajo"] for f in con_monto), "alto": sum(f["alto"] for f in con_monto),
            "por_motivo": {k: sum(1 for f in filas if f["motivo"] == k)
                           for k in ("cero", "por_persona", "itinerario", "sin_garantia", "perfil_hold")}}


def analisis_mes(snaps: list[dict], reservas: list[dict], config: dict, year: int, month: int) -> dict:
    cfg = config or {}
    pct = float(cfg.get("onsite_pct") or 0) / 100 if (cfg.get("onsite_mode") or "pct") == "pct" else 0.12
    corte = ultimo_corte(snaps, "total") or ultimo_corte(snaps, "rooms")
    if not corte:
        return {"vacio": True}
    D = un_anio_antes(corte)
    tot, rooms = combinar(snaps, "total"), combinar(snaps, "rooms")
    hf, hr = _hf_mes(tot, year, month), _hf_mes(rooms, year, month)
    dias_mes = calendar.monthrange(year, month)[1]
    cap = hf["cap"] or 30 * dias_mes
    fin_mes = date(year, month, dias_mes).isoformat()
    semanas = max(dias_entre(fin_mes, corte), 0) / 7

    M, L = _Mes(reservas, year, month), _Mes(reservas, year - 1, month)
    act, act_ly = M.activas(), L.activas()
    rn_res, rn_ly = M.rn(act), L.rn(act_ly)
    st = L.rn(L.activas(D))
    val_res, val_ly = M.val(act), L.val(act_ly)
    adr_val_ly = val_ly / rn_ly if rn_ly else (val_res / rn_res if rn_res else 0)

    meta = meta_de(cfg, "total", year)
    meta_rn = meta["rn"][month - 1] if meta else 0.0
    meta_tot = meta["total"][month - 1] if meta else 0.0
    meta_rooms = meta["rooms"][month - 1] if meta else 0.0
    meta_cap = (meta["avail"][month - 1] if meta else 0) or cap

    otb = hf["rn"]
    t_adr = hf["rev"] / otb if otb else 0.0

    def ingreso(rn: float) -> float:
        p = max(rn - otb, 0)
        return hf["rev"] + p * t_adr + pct * (hr["rev"] + p * adr_val_ly)

    ing_otb = ingreso(otb)

    # ── ritmo ─────────────────────────────────────────
    def ventana(lista, fin, w):
        ini = mas_dias(fin, -w)
        return sum(r["_rn"] for r in lista if ini < r["ins"] <= fin)
    ventanas = [{"dias": w, "rn": ventana(act, corte, w), "por_semana": ventana(act, corte, w) / (w / 7)}
                for w in VENTANAS]
    pick_ly = [r for r in act_ly if r["ins"] > D]
    rn_pick_ly = L.rn(pick_ly)
    sem_ly = max(dias_entre(date(year - 1, month, dias_mes).isoformat(), D), 1) / 7
    necesario = (meta_rn - otb) / semanas if semanas and meta else None

    por_mes_ly: dict[str, float] = defaultdict(float)
    for r in pick_ly:
        por_mes_ly[r["ins"][:7]] += r["_rn"]
    llenado_ly, acum = [], st
    llenado_ly.append({"mes": None, "rn": st, "acum": st, "pct": st / rn_ly if rn_ly else 0})
    for k in sorted(por_mes_ly):
        acum += por_mes_ly[k]
        llenado_ly.append({"mes": k, "rn": por_mes_ly[k], "acum": acum, "pct": acum / rn_ly if rn_ly else 0})
    lead_ly = [{"desde": a, "hasta": b, "rn": sum(r["_rn"] for r in pick_ly if a <= r["_lead"] <= b)}
               for a, b in LEAD]

    creadas: dict[str, dict] = defaultdict(lambda: {"activas": 0.0, "canceladas": 0.0})
    for r in M.filas:
        if r["st"] == "A":
            creadas[r["ins"][:7]]["activas"] += r["_rn"]
        elif r["st"] == "X":
            creadas[r["ins"][:7]]["canceladas"] += r["_rn"]

    # curva: días antes del día 1 del mes
    ini_mes, ini_ly = date(year, month, 1), date(year - 1, month, 1)
    migracion = min((r["ins"] for r in reservas), default=None)
    curva = []
    for o in range(150, -dias_mes - 1, -1):
        c_t, c_l = (ini_mes - timedelta(days=o)).isoformat(), (ini_ly - timedelta(days=o)).isoformat()
        curva.append({"dias": -o,
                      "anio": M.rn(M.activas(c_t)) if c_t <= corte else None,
                      "anterior": L.rn(L.activas(c_l)) if migracion and c_l >= migracion else None})

    # ── escenarios ────────────────────────────────────
    libre_ly = cap - st
    tasa_ly = rn_pick_ly / libre_ly if libre_ly > 0 else 0
    rn_ly_esc = min(cap, otb + tasa_ly * max(cap - otb, 0))
    esc = [{"clave": "libros", "rn": otb},
           {"clave": "ritmo30", "rn": min(cap, otb + ventanas[2]["por_semana"] * semanas), "por_semana": ventanas[2]["por_semana"]},
           {"clave": "ritmo90", "rn": min(cap, otb + ventanas[4]["por_semana"] * semanas), "por_semana": ventanas[4]["por_semana"]},
           {"clave": "ritmoLy", "rn": rn_ly_esc, "tasa": tasa_ly}]
    if meta:
        esc.append({"clave": "meta", "rn": meta_rn, "por_semana": necesario})
    for e in esc:
        # Noches enteras hacia abajo, como en el estudio: una noche a medio vender
        # no se cuenta.
        e["rn"] = math.floor(e["rn"] + 1e-9)
        e["ingreso"] = ingreso(e["rn"])
        e["occ"] = e["rn"] / cap if cap else 0
        e["vs_meta"] = e["ingreso"] - meta_tot if meta else None
    p_meta = meta_rn - otb
    noche_meta = ((meta_tot - hf["rev"] - pct * (hr["rev"] + p_meta * adr_val_ly)) / p_meta) if meta and p_meta > 0 else None

    # hitos
    hitos = []
    nec_red = round(necesario) if necesario else 0
    for h in _hitos(corte, year, month):
        hd = _d(h)
        mes_ly = f"{hd.year - 1}-{hd.month:02d}"
        frac = 0.5 if hd.day == 15 else 1.0
        previo = sum(v for k, v in por_mes_ly.items() if k < mes_ly)
        ritmo = otb + previo + por_mes_ly.get(mes_ly, 0) * frac
        ruta = min(meta_rn, otb + nec_red * dias_entre(h, corte) / 7) if meta else None
        # Redondeo bancario (432.5 → 432), como en el estudio de diciembre.
        hitos.append({"fecha": h, "ritmo": round(ritmo), "ruta": ruta if h != fin_mes else meta_rn or None,
                      "alerta": math.floor(ritmo * 0.985 / 10) * 10 if h != fin_mes else None})
        # Alerta = 1.5% de tolerancia bajo el ritmo del año anterior, en decenas.

    # ── noche por noche ───────────────────────────────
    ly_dia: dict[int, float] = defaultdict(float)
    res_dia: dict[int, float] = defaultdict(float)
    for r in act_ly:
        for d in r["_n"]:
            ly_dia[d.day] += int(r.get("rms") or 1)
    for r in act:
        for d in r["_n"]:
            res_dia[d.day] += int(r.get("rms") or 1)
    noches = []
    for d in range(1, dias_mes + 1):
        v = hf["por_dia"].get(d)
        rv = hr["por_dia"].get(d)
        rn_d = v[RN] if v else 0
        noches.append({"dia": d, "rn": rn_d, "cap": (v[INV] if v else 30) or 30, "ly": ly_dia[d],
                       "reservas": res_dia[d], "adr_rooms": (rv[REV] / rv[RN]) if rv and rv[RN] else None,
                       "bloqueo": max(rn_d - res_dia[d], 0)})
    periodos = []
    for a, b in _periodos(year, month):
        sel = [n for n in noches if a <= n["dia"] <= b]
        periodos.append({"desde": a, "hasta": b, "noches": len(sel), "cap": sum(n["cap"] for n in sel),
                         "rn": sum(n["rn"] for n in sel), "ly": sum(n["ly"] for n in sel)})

    # ── canales ───────────────────────────────────────
    ch: dict[str, dict] = defaultdict(lambda: {"rn": 0.0, "valor": 0.0, "rn_ly": 0.0, "pick_ly": 0.0, "canc": 0.0})
    for r in act:
        c = ch[_canal(r.get("ch"))]; c["rn"] += r["_rn"]; c["valor"] += r["_val"]
    for r in act_ly:
        c = ch[_canal(r.get("ch"))]; c["rn_ly"] += r["_rn"]
        if r["ins"] > D:
            c["pick_ly"] += r["_rn"]
    canc = M.canceladas()
    for r in canc:
        ch[_canal(r.get("ch"))]["canc"] += r["_rn"]
    orden = sorted(((k, v) for k, v in ch.items() if v["rn"] or v["rn_ly"]),
                   key=lambda kv: -(kv[1]["rn"] + kv[1]["rn_ly"]))
    sin_noches = [v for v in ch.values() if not (v["rn"] or v["rn_ly"])]
    canales = [{"canal": k, **v} for k, v in orden[:11]]
    resto = orden[11:]
    if resto:
        canales.append({"canal": None, "otros": len(resto),
                        **{f: sum(v[f] for _, v in resto) + sum(v[f] for v in sin_noches)
                           for f in ("rn", "valor", "rn_ly", "pick_ly", "canc")}})
    canc_canal = sorted(((k, v["canc"]) for k, v in ch.items() if v["canc"]), key=lambda x: -x[1])[:5]
    hold_canc = [r for r in canc if _es_hold(r)]

    # ── garantía, tipos, bloqueos, riesgos ────────────
    gar: dict[str, float] = defaultdict(float)
    tipos: dict[str, float] = defaultdict(float)
    for r in act:
        gar[(r.get("garantia") or "—").upper()] += r["_rn"]
        tipos[r.get("room_type") or "—"] += r["_rn"]
    debil = sum(v for k, v in gar.items() if k in GARANTIA_DEBIL)
    bloq = [n for n in noches if n["bloqueo"] > 0]
    semana_max = max(periodos, key=lambda p: p["rn"]) if periodos else None
    canc_rn, canc_ly = M.rn(canc), L.rn(L.canceladas())
    tasa_c = canc_rn / (canc_rn + rn_res) if canc_rn + rn_res else 0
    tasa_c_ly = canc_ly / (canc_ly + rn_ly) if canc_ly + rn_ly else 0

    return {
        "vacio": False, "anio": year, "mes": month, "corte": corte, "stly_fecha": D, "pct_en_sitio": pct,
        "migracion": migracion, "semanas": semanas, "cap": cap, "dias": dias_mes,
        "meta": {"rn": meta_rn, "total": meta_tot, "rooms": meta_rooms, "avail": meta_cap,
                 "source": meta.get("source") if meta else None} if meta else None,
        "libros": {"rn": otb, "rn_reservas": rn_res, "bloqueos": otb - rn_res, "occ": otb / cap if cap else 0,
                   "reservas": len(act), "estancia": rn_res / len(act) if act else 0,
                   "rooms": hr["rev"], "adr_rooms": hr["rev"] / hr["rn"] if hr["rn"] else 0,
                   "total": hf["rev"], "en_sitio": pct * hr["rev"], "ingreso": ing_otb,
                   "valor_noche": val_res / rn_res if rn_res else 0, "valor_total": val_res},
        "anterior": {"rn": rn_ly, "occ": rn_ly / cap if cap else 0, "stly": st,
                     "valor_noche": adr_val_ly, "valor_total": val_ly, "pickup": rn_pick_ly,
                     "por_semana": rn_pick_ly / sem_ly, "cancel_rn": canc_ly, "cancel_tasa": tasa_c_ly},
        "ritmo": {"ventanas": ventanas, "necesario": necesario, "llenado_ly": llenado_ly, "lead_ly": lead_ly,
                  "creadas": [{"mes": k, **v} for k, v in sorted(creadas.items())], "curva": curva},
        "escenarios": esc, "noche_para_meta": noche_meta, "t_adr": t_adr, "hitos": hitos,
        "noches": noches, "periodos": periodos,
        "garantias": sorted(({"codigo": k, "rn": v} for k, v in gar.items()), key=lambda x: -x["rn"]),
        "tipos": sorted(({"tipo": k, "rn": v} for k, v in tipos.items()), key=lambda x: -x["rn"]),
        "canales": canales, "canc_por_canal": [{"canal": k, "rn": v} for k, v in canc_canal],
        "cancelaciones": {"rn": canc_rn, "tasa": tasa_c, "hold_reservas": len(hold_canc), "hold_rn": M.rn(hold_canc)},
        "tarifas": _tarifas(act),
        "bloqueos": {"rn": sum(n["bloqueo"] for n in bloq), "desde": bloq[0]["dia"] if bloq else None,
                     "hasta": bloq[-1]["dia"] if bloq else None,
                     "por_noche": max((n["bloqueo"] for n in bloq), default=0)},
        "riesgo": {"garantia_debil": debil, "agencia": gar.get("LA", 0.0),
                   "semana_max": semana_max, "en_sitio_punto": 0.01 * (hr["rev"] + max(rn_ly_esc - otb, 0) * adr_val_ly)},
    }
