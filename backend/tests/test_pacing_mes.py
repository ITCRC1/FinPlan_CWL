# -*- coding: utf-8 -*-
"""El análisis de un mes (`app/engine/pacing_mes.py`).

Las cifras del estudio «Pacing Diciembre 2026» (corte 30-sep-2026) se
verificaron contra los XML reales al construir el módulo; acá se fijan las
reglas con datos sintéticos.
"""
from datetime import date, timedelta

from app.engine.pacing_mes import _canal, _es_hold, analisis_mes


def _dias(desde, hasta, rn, rev, hist):
    out, d = {}, desde
    while d <= hasta:
        out[d.isoformat()] = [rn, rev, 30, 0, 0, 0, 1, rn * 2, 1 if hist else 0]
        d += timedelta(days=1)
    return out


def _snaps():
    corte = date(2026, 9, 30)
    t = {**_dias(date(2026, 9, 1), corte - timedelta(days=1), 10, 5000, True),
         **_dias(corte, date(2026, 12, 31), 12, 9000, False)}
    r = {k: [v[0], v[1] * 0.7, *v[2:]] for k, v in t.items()}
    base = {"as_of": "2026-09-30", "date_from": "2026-09-01", "date_to": "2026-12-31", "has_forecast": True}
    return [{**base, "id": "t", "kind": "total", "days": t}, {**base, "id": "r", "kind": "rooms", "days": r}]


def _r(i, ins, arr, nts, amt, st="A", **kw):
    return {"id": str(i), "ins": ins, "arr": arr, "nts": nts, "rms": 1, "amt": amt, "st": st,
            "fl": "", "ch": kw.get("ch", "C- AGENCIA X"), "blk": 0, "rate": kw.get("rate", "BAR"),
            "room_type": "THKB", "guest": kw.get("guest", f"Huesped,{i}"), "grupo": kw.get("grupo", ""),
            "garantia": kw.get("garantia", "CC"), "pax": kw.get("pax", 2),
            "tarifa_noche": amt / nts if nts else 0}


def _reservas():
    out = [
        # año anterior: 2 en libros al 30-sep-2025 y 1 que entró después
        _r(1, "2025-09-01", "2025-12-10", 3, 1800),
        _r(2, "2025-09-15", "2025-12-20", 2, 1200),
        _r(3, "2025-11-10", "2025-12-24", 4, 2400),
        _r(4, "2025-10-01", "2025-12-05", 2, 1000, st="X"),
        # este año
        _r(10, "2026-03-01", "2026-12-08", 3, 1800, rate="PMTR"),
        _r(11, "2026-09-25", "2026-12-15", 2, 1300, rate="PMTR"),
        _r(12, "2026-08-01", "2026-12-20", 3, 0, rate="PMTR", guest="HOLD,HOLD", garantia="HOLD72"),
        _r(13, "2026-08-02", "2026-12-21", 2, 200, rate="PMTR", pax=4),
        _r(14, "2026-08-03", "2026-12-22", 2, 1200, rate="PMTR", garantia="NON"),
        _r(15, "2026-07-01", "2026-12-26", 2, 0, st="X"),
    ]
    return out


CFG = {"meta": {"years": {"2026": {"rn": [0] * 11 + [400], "total": [0] * 11 + [400000],
                                   "rooms": [0] * 11 + [250000], "avail": [0] * 11 + [930]}}},
       "onsite_mode": "pct", "onsite_pct": 12}


def test_libros_stly_y_alcance():
    a = analisis_mes(_snaps(), _reservas(), CFG, 2026, 12)
    assert a["libros"]["rn"] == 12 * 31
    assert a["anterior"]["rn"] == 9 and a["anterior"]["stly"] == 5 and a["anterior"]["pickup"] == 4
    esc = {e["clave"]: e for e in a["escenarios"]}
    # ritmo del año anterior: 4 RN sobre (930 − 5) libres → la misma tasa sobre lo libre hoy
    libres = 930 - 372
    assert esc["ritmoLy"]["rn"] == int(372 + 4 / 925 * libres)
    assert esc["libros"]["ingreso"] == a["libros"]["ingreso"]
    assert a["cancelaciones"]["rn"] == 2


def test_tarifas_marcadas():
    a = analisis_mes(_snaps(), _reservas(), CFG, 2026, 12)
    motivos = {f["id"]: f["motivo"] for f in a["tarifas"]["filas"]}
    assert motivos["12"] == "cero"
    assert motivos["13"] == "por_persona"
    assert motivos["14"] == "sin_garantia"
    assert "10" not in motivos and "11" not in motivos


def test_hitos_y_ritmo_necesario():
    a = analisis_mes(_snaps(), _reservas(), CFG, 2026, 12)
    assert a["hitos"][0]["fecha"] == "2026-10-15" and a["hitos"][-1]["fecha"] == "2026-12-31"
    assert a["ritmo"]["necesario"] == (400 - 372) / (92 / 7)


def test_canal_y_hold():
    assert _canal("C- COSTA RICA SUN TOU") == "COSTA RICA SUN TOU"
    assert _canal("") == _canal("C- DIRECTO") == "Directo / sin agencia"
    assert _es_hold({"guest": "HOLD,HOLD"}) and _es_hold({"grupo": "598729141 HOLD, HOLD"})
    assert not _es_hold({"guest": "Ackerman,Holden"})


def test_sin_fotos():
    assert analisis_mes([], [], {}, 2026, 12)["vacio"] is True


def test_meta_manual_reemplaza_la_meta_solo_en_la_consulta():
    snaps, reservas, cfg = _snaps(), _reservas(), CFG
    base = analisis_mes(snaps, reservas, cfg, 2026, 12)
    m = analisis_mes(snaps, reservas, cfg, 2026, 12, {"rn": 500, "total": 450000})
    assert m["meta"]["rn"] == 500 and m["meta"]["total"] == 450000
    assert m["meta"]["manual"] is True and m["meta"]["source"] == "manual"
    assert m["libros"]["rn"] == base["libros"]["rn"]          # lo de libros no cambia
    # Sólo RN: el ingreso queda el de la meta cargada.
    solo_rn = analisis_mes(snaps, reservas, cfg, 2026, 12, {"rn": 500, "total": None})
    assert solo_rn["meta"]["total"] == base["meta"]["total"] == 400000
    # Un mes sin meta cargada también acepta la meta a medida.
    sin = analisis_mes(snaps, reservas, cfg, 2027, 1, {"rn": 300, "total": 250000})
    assert sin["meta"]["rn"] == 300 and sin["ritmo"]["necesario"] is not None


def test_mismo_mes_del_anio_anterior():
    a = analisis_mes(_snaps(), _reservas(), CFG, 2026, 12)
    P = a["anterior"]
    assert P["stly"] == 5 and P["stly_valor"] == 3000      # 1800 + 1200 en libros al 30-sep-2025
    assert set(P["hf"]) == {"rn", "total", "rooms", "cap"}
    # Para sep-2027 el cierre del año anterior sale de las fotos de sep-2026:
    # 29 noches históricas × 10 RN + el día 30 (12 RN).
    b = analisis_mes(_snaps(), _reservas(), CFG, 2027, 9)
    assert b["anterior"]["hf"]["rn"] == 29 * 10 + 12
    assert b["anterior"]["hf"]["total"] == 29 * 5000 + 9000
