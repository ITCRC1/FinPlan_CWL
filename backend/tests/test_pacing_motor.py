# -*- coding: utf-8 -*-
"""Motor del PACING (`app/engine/pacing.py`) con datos sintéticos.

No reemplaza la verificación contra los archivos reales de CWL (corte
30-sep-2026: 2027 OTB 2.437 RN, proyección 5.786 RN, cierre 2026 4.958 RN),
que se hizo al portar el motor desde el tablero; acá se fijan las reglas.
"""
from datetime import date, timedelta

from app.engine import pacing as m


def _dias(desde: date, hasta: date, rn, rev, hist):
    out, d = {}, desde
    while d <= hasta:
        out[d.isoformat()] = [rn, rev, 30, 0, 0, 0, 1, rn * 2, 1 if hist else 0]
        d += timedelta(days=1)
    return out


def _snap(as_of: str, days: dict, kind="total"):
    return {"id": as_of + kind, "kind": kind, "as_of": as_of, "date_from": min(days),
            "date_to": max(days), "has_forecast": any(not v[8] for v in days.values()), "days": days}


def _escenario():
    corte = date(2026, 6, 1)
    # 2025 completo en historia (20 RN/día); 2026: historia hasta mayo, forecast (OTB) con 5 RN/día.
    ly = _dias(date(2025, 1, 1), date(2025, 12, 31), 20, 10000, True)
    h = _dias(date(2026, 1, 1), corte - timedelta(days=1), 18, 9000, True)
    f = _dias(corte, date(2026, 12, 31), 5, 2500, False)
    # Foto de hace un año: el STLY exacto (4 RN/día a esa altura).
    stly = _dias(date(2025, 6, 1), date(2025, 12, 31), 4, 2000, False)
    return [_snap("2025-06-01", {**_dias(date(2025, 1, 1), date(2025, 5, 31), 20, 10000, True), **stly}),
            _snap("2026-06-01", {**ly, **h, **f})]


def test_meses_cerrados_son_el_real_y_los_abiertos_no_pasan_la_capacidad():
    a = m.analisis(_escenario(), [], {}, kind="total", year=2026)
    assert a["vacio"] is False and a["corte"] == "2026-06-01"
    filas = a["posicion"]["rows"]
    for r in filas[:5]:                      # ene–may: cerrados
        assert r["cerrado"] and abs(r["proj"] - r["otb_rn"]) < 1e-6
    for r in filas[6:]:                      # jul–dic: abiertos
        assert not r["cerrado"]
        assert r["otb_rn"] - 1e-6 <= r["proj"] <= r["cap"] + 1e-6


def test_el_stly_sale_de_la_foto_de_hace_un_anio():
    a = m.analisis(_escenario(), [], {}, kind="total", year=2026, fuente="snap")
    assert a["posicion"]["st"]["src"] == "snap"
    dic = a["posicion"]["rows"][11]
    assert dic["st_rn"] == 4 * 31
    # OTB 5/día contra STLY 4/día: va adelante.
    assert dic["pace"] > 1


def test_la_meta_de_la_configuracion_llega_al_cierre():
    meta = {"meta": {"years": {"2026": {"rn": [500] * 12, "rooms": [1] * 12, "total": [300000] * 12,
                                        "avail": [900] * 12, "source": "prueba"}}}}
    a = m.analisis(_escenario(), [], meta, kind="total", year=2026)
    cm = a["cierre_meta"]
    assert cm["year"] == 2026 and cm["meta"]["source"] == "prueba"
    assert len(cm["filas"]) == 12


def test_sin_fotos_no_revienta():
    a = m.analisis([], [], {}, kind="total")
    assert a["vacio"] is True


def test_consumo_en_sitio_suma_al_ingreso_de_habitaciones():
    snaps = _escenario()
    rooms = [dict(s, kind="rooms", id=s["id"] + "r") for s in snaps]
    cfg = {"onsite_mode": "pct", "onsite_pct": 12}
    a = m.analisis(snaps + rooms, [], cfg, kind="total", year=2026)
    assert a["en_sitio"] == {"modo": "pct", "pct": 0.12}
    assert a["posicion"]["tot"]["en_sitio"] > 0
