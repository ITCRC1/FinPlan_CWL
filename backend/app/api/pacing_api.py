# -*- coding: utf-8 -*-
"""API del módulo PACING.

    POST   /api/pacing/preview                  qué es cada XML (no guarda nada)
    POST   /api/pacing/upload                   guarda fotos H&F y reservas
    GET    /api/pacing/snapshots                fotos guardadas
    DELETE /api/pacing/snapshots/{id}
    GET    /api/pacing/reservations/summary     cargas de reservas
    DELETE /api/pacing/reservations             borra TODAS las reservas
    GET    /api/pacing/config                   STLY RM, metas, consumo en sitio
    PUT    /api/pacing/config
    POST   /api/pacing/meta-from-scenario/{scenario_id}?year=   copia la meta de un P&L
    GET    /api/pacing/analisis?year&kind&escenario&fuente      todo el análisis

⚠️ **Nada de esto es del escenario.** Las fotos y las reservas son hechos de
Opera, llave el HOTEL (igual que el On the Books, ver migración 126). Por eso
ninguna ruta lleva `{scenario_id}` salvo la que copia una meta — y esa sólo LEE
el escenario: el candado no tiene nada que frenar.

⚠️ **El cálculo vive en `app/engine/pacing.py`**, puro Python, sin base ni
idioma. Esta capa sólo lee filas, arma los dicts que el motor espera y le pasa
la configuración.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.engine import pacing as motor
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID
from app.importers.registro_dep import registro_de_subida
from app.importers import pacing_xml as px
from app.models.pacing import (
    KINDS, ONSITE_MODOS, PacingConfig, PacingReservation, PacingResvLoad, PacingSnapshot)

router = APIRouter(tags=["pacing"])

_CAMPOS_RESV = ("ins", "arr", "nts", "rms", "amt", "st", "fl", "ch", "rate", "blk",
                "room_type", "guest", "grupo", "garantia", "pax", "tarifa_noche")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _quien(user) -> str | None:
    return getattr(user, "email", None)


# ───────────────────────────── lectura de archivos ─────────────────────────────
async def _leer(files: list[UploadFile]) -> list[dict]:
    """Cada archivo → `{nombre, tipo, ...}` o `{nombre, error}`. No lanza."""
    out = []
    for f in files:
        raw = await f.read()
        item: dict = {"nombre": f.filename, "_raw": raw}
        try:
            tipo = px.tipo_de(raw)
            item["tipo"] = tipo
            if tipo == px.TIPO_HF:
                r = px.leer_history_forecast(raw)
                if not r.get("days"):
                    item["error"] = "sin_dias"
                else:
                    item.update({k: r[k] for k in ("as_of", "has_forecast", "date_from", "date_to",
                                                   "total_revenue")})
                    item["dias"] = len(r["days"])
                    item["_days"] = r["days"]
            else:
                r = px.leer_reservas(raw)
                item.update({k: r[k] for k in ("cuenta", "descartadas_pi", "min_ins", "max_ins")})
                item["_reservas"] = r["reservas"]
        except px.XmlNoReconocido as e:
            item["error"] = "no_reconocido"
            item["detalle"] = str(e)
        except Exception as e:  # noqa: BLE001 — un archivo malo no tumba a los demás
            item["error"] = "ilegible"
            item["detalle"] = str(e)
        out.append(item)
    px.asignar_tipos(out)
    return out


def _publico(item: dict) -> dict:
    return {k: v for k, v in item.items() if not k.startswith("_")}


@router.post("/pacing/preview")
async def preview(files: list[UploadFile] = File(...)):
    """Qué es cada archivo, qué corte trae y si es Rooms o Total. No guarda."""
    return {"archivos": [_publico(a) for a in await _leer(files)]}


@router.post("/pacing/upload",
             dependencies=[Depends(registro_de_subida)])
async def upload(
    files: list[UploadFile] = File(...),
    #: JSON opcional `{"<nombre de archivo>": "rooms"|"total"}` para corregir la
    #: detección cuando se sube UN solo History & Forecast.
    kinds: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    archivos = await _leer(files)
    try:
        forzados = json.loads(kinds) if kinds else {}
    except ValueError:
        forzados = {}
    if not any("error" not in a for a in archivos):
        raise ErrorApi(422, "pacing.nada_valido")

    resultado = []
    for a in archivos:
        if a.get("error"):
            resultado.append(_publico(a))
            continue
        if a["tipo"] == px.TIPO_HF:
            kind = forzados.get(a["nombre"]) or a.get("kind") or "total"
            if kind not in KINDS:
                raise ErrorApi(422, "pacing.kind_invalido", kind=kind)
            previa = (await db.execute(select(PacingSnapshot).where(
                PacingSnapshot.hotel_id == HOTEL_ID, PacingSnapshot.kind == kind,
                PacingSnapshot.as_of == a["as_of"]))).scalar_one_or_none()
            # Mismo corte y mismo tipo: la nueva reemplaza (se volvió a exportar).
            s = previa or PacingSnapshot(hotel_id=HOTEL_ID, kind=kind, as_of=a["as_of"])
            s.date_from, s.date_to = a["date_from"], a["date_to"]
            s.has_forecast, s.file_name = a["has_forecast"], a["nombre"]
            s.total_revenue, s.days = a["total_revenue"], a["_days"]
            s.uploaded_at, s.uploaded_by = _ahora(), _quien(user)
            if previa is None:
                db.add(s)
            resultado.append({**_publico(a), "kind": kind, "reemplazo": previa is not None})
        else:
            resultado.append({**_publico(a), **await _guardar_reservas(db, a, user)})
    await db.commit()
    return {"archivos": resultado}


async def _guardar_reservas(db: AsyncSession, a: dict, user) -> dict:
    existentes = {r.resv_id: r for r in (await db.execute(select(PacingReservation).where(
        PacingReservation.hotel_id == HOTEL_ID))).scalars()}
    carga = PacingResvLoad(hotel_id=HOTEL_ID, file_name=a["nombre"], cuenta=a["cuenta"],
                           descartadas_pi=a["descartadas_pi"], min_ins=a["min_ins"],
                           max_ins=a["max_ins"], uploaded_at=_ahora(), uploaded_by=_quien(user))
    db.add(carga)
    await db.flush()
    nuevas = act = 0
    vistos: set[str] = set()
    for r in a["_reservas"]:
        if r["id"] in vistos:  # la misma reserva dos veces en el archivo: gana la primera
            continue
        vistos.add(r["id"])
        fila = existentes.get(r["id"])
        if fila is None:
            fila = PacingReservation(hotel_id=HOTEL_ID, resv_id=r["id"])
            db.add(fila)
            nuevas += 1
        else:
            act += 1
        for k in _CAMPOS_RESV:
            setattr(fila, k, r.get(k))
        fila.load_id, fila.updated_at = carga.id, _ahora()
    carga.nuevas, carga.actualizadas = nuevas, act
    return {"nuevas": nuevas, "actualizadas": act}


# ───────────────────────────── fotos y reservas ─────────────────────────────
@router.get("/pacing/snapshots")
async def list_snapshots(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(PacingSnapshot).where(PacingSnapshot.hotel_id == HOTEL_ID)
                             .order_by(PacingSnapshot.as_of.desc(), PacingSnapshot.kind))).scalars()
    return [{"id": s.id, "kind": s.kind, "as_of": s.as_of, "date_from": s.date_from,
             "date_to": s.date_to, "has_forecast": s.has_forecast, "file_name": s.file_name,
             "total_revenue": float(s.total_revenue or 0), "dias": len(s.days or {}),
             "uploaded_at": s.uploaded_at.isoformat() if s.uploaded_at else None,
             "uploaded_by": s.uploaded_by} for s in rows]


@router.delete("/pacing/snapshots/{snapshot_id}")
async def delete_snapshot(snapshot_id: str, db: AsyncSession = Depends(get_db)):
    s = await db.get(PacingSnapshot, snapshot_id)
    if s is None or s.hotel_id != HOTEL_ID:
        raise ErrorApi(404, "pacing.foto_no_encontrada")
    await db.delete(s)
    await db.commit()
    return {"ok": True}


@router.get("/pacing/reservations/summary")
async def reservations_summary(db: AsyncSession = Depends(get_db)):
    filas = (await db.execute(select(PacingReservation.ins, PacingReservation.st).where(
        PacingReservation.hotel_id == HOTEL_ID))).all()
    cargas = (await db.execute(select(PacingResvLoad).where(PacingResvLoad.hotel_id == HOTEL_ID)
                               .order_by(PacingResvLoad.uploaded_at.desc()))).scalars()
    return {
        "cuenta": len(filas),
        "activas": sum(1 for f in filas if f.st == "A"),
        "canceladas": sum(1 for f in filas if f.st == "X"),
        "desde": min((f.ins for f in filas), default=None),
        "hasta": max((f.ins for f in filas), default=None),
        "cargas": [{"id": c.id, "file_name": c.file_name, "cuenta": c.cuenta, "nuevas": c.nuevas,
                    "actualizadas": c.actualizadas, "descartadas_pi": c.descartadas_pi,
                    "min_ins": c.min_ins, "max_ins": c.max_ins,
                    "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
                    "uploaded_by": c.uploaded_by} for c in cargas],
    }


@router.delete("/pacing/reservations")
async def delete_reservations(db: AsyncSession = Depends(get_db)):
    await db.execute(delete(PacingReservation).where(PacingReservation.hotel_id == HOTEL_ID))
    await db.execute(delete(PacingResvLoad).where(PacingResvLoad.hotel_id == HOTEL_ID))
    await db.commit()
    return {"ok": True}


# ───────────────────────────── configuración ─────────────────────────────
class ConfigIn(BaseModel):
    stly: dict | None = None
    meta: dict | None = None
    onsite_mode: str | None = None
    onsite_pct: float | None = None


def _valores_iniciales() -> dict:
    """Meta 2026 (P&L Full Year Forecast) y STLY de RM para CWL, la primera vez.

    ⚠️ Sólo se leen al CREAR la fila. Después manda lo editado en pantalla: a
    diferencia del seed del mapeo, esto NO se re-afirma en cada deploy.
    """
    ruta = Path(__file__).resolve().parent.parent / "seed_data" / f"pacing_{HOTEL_ID.lower()}.json"
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


async def _config(db: AsyncSession) -> PacingConfig:
    c = await db.get(PacingConfig, HOTEL_ID)
    if c is None:
        ini = _valores_iniciales()
        c = PacingConfig(hotel_id=HOTEL_ID, stly=ini.get("stly") or {"years": {}},
                         meta=ini.get("meta") or {"years": {}},
                         onsite_mode=ini.get("onsite_mode", "pct"),
                         onsite_pct=ini.get("onsite_pct", 12))
        db.add(c)
        await db.flush()
    return c


def _config_dict(c: PacingConfig) -> dict:
    return {"stly": c.stly or {"years": {}}, "meta": c.meta or {"years": {}},
            "onsite_mode": c.onsite_mode or "pct", "onsite_pct": float(c.onsite_pct or 0),
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            "updated_by": c.updated_by}


def _validar_anios(bloque: dict, nombre: str) -> dict:
    if not isinstance(bloque, dict) or not isinstance(bloque.get("years", {}), dict):
        raise ErrorApi(422, "pacing.config_invalida", campo=nombre)
    for y, v in bloque.get("years", {}).items():
        if not str(y).isdigit() or not isinstance(v, dict):
            raise ErrorApi(422, "pacing.config_invalida", campo=f"{nombre}.{y}")
        for k in ("rn", "rooms", "total", "avail"):
            if k in v and (not isinstance(v[k], list) or len(v[k]) != 12):
                raise ErrorApi(422, "pacing.doce_meses", campo=f"{nombre}.{y}.{k}")
    return {"years": dict(bloque.get("years", {}))}


@router.get("/pacing/config")
async def get_config(db: AsyncSession = Depends(get_db)):
    c = await _config(db)
    await db.commit()
    return _config_dict(c)


@router.put("/pacing/config")
async def put_config(body: ConfigIn, db: AsyncSession = Depends(get_db),
                     user=Depends(get_current_user)):
    c = await _config(db)
    if body.stly is not None:
        c.stly = _validar_anios(body.stly, "stly")
    if body.meta is not None:
        c.meta = _validar_anios(body.meta, "meta")
    if body.onsite_mode is not None:
        if body.onsite_mode not in ONSITE_MODOS:
            raise ErrorApi(422, "pacing.onsite_modo", modo=body.onsite_mode)
        c.onsite_mode = body.onsite_mode
    if body.onsite_pct is not None:
        if not 0 <= body.onsite_pct <= 100:
            raise ErrorApi(422, "pacing.onsite_pct")
        c.onsite_pct = body.onsite_pct
    c.updated_at, c.updated_by = _ahora(), _quien(user)
    await db.commit()
    return _config_dict(c)


@router.post("/pacing/meta-from-scenario/{scenario_id}")
async def meta_from_scenario(scenario_id: str, year: int | None = Query(None),
                             db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """Copia a la meta del pacing las noches, disponibles, Rooms y Total de un P&L.

    Se COPIA: el pacing no queda atado al escenario. Si el escenario cambia, se
    vuelve a tomar con este mismo botón.
    """
    from app.api.pl_api import get_pl_monthly
    from app.models.scenario import Scenario
    sc = await db.get(Scenario, scenario_id)
    if sc is None:
        raise ErrorApi(404, "escenario.no_encontrado")
    pl = await get_pl_monthly(scenario_id)
    meses = sorted(pl.get("months") or [], key=lambda m: m["month"])
    if len(meses) != 12:
        raise ErrorApi(422, "pacing.pl_incompleto")

    def linea(m, code):
        return round(float(next((l.get("amount_usd") or 0 for l in m["lines"]
                                 if l.get("line_code") == code), 0) or 0), 2)
    bloque = {
        "rn": [round(float(m["kpis"].get("rooms_occupied") or 0), 2) for m in meses],
        "avail": [round(float(m["kpis"].get("rooms_available") or 0), 2) for m in meses],
        "rooms": [linea(m, "REV_ROOMS") for m in meses],
        "total": [linea(m, "TOTAL_REVENUES") for m in meses],
        "source": " ".join(str(x) for x in (sc.type, sc.version, sc.year) if x),
        "scenario_id": sc.id,
        "actualMonths": int(getattr(sc, "actuals_through", 0) or 0),
        "tomado": _ahora().isoformat(),
    }
    y = str(year or sc.year)
    c = await _config(db)
    meta = dict(c.meta or {"years": {}})
    anios = dict(meta.get("years") or {})
    anios[y] = bloque
    c.meta = {"years": anios}
    c.updated_at, c.updated_by = _ahora(), _quien(user)
    await db.commit()
    return {"anio": int(y), "meta": bloque}


# ───────────────────────────── el análisis ─────────────────────────────
@router.get("/pacing/analisis")
async def get_analisis(
    year: int | None = Query(None),
    kind: str = Query("total"),
    escenario: str = Query("avail"),
    fuente: str = Query("auto"),
    db: AsyncSession = Depends(get_db),
):
    if kind not in KINDS:
        raise ErrorApi(422, "pacing.kind_invalido", kind=kind)
    snaps = [{"id": s.id, "kind": s.kind, "as_of": s.as_of, "date_from": s.date_from,
              "date_to": s.date_to, "has_forecast": s.has_forecast, "file_name": s.file_name,
              "days": s.days or {}}
             for s in (await db.execute(select(PacingSnapshot).where(
                 PacingSnapshot.hotel_id == HOTEL_ID))).scalars()]
    reservas = [{"id": r.resv_id, "ins": r.ins, "arr": r.arr, "nts": r.nts, "rms": r.rms,
                 "amt": float(r.amt or 0), "st": r.st, "fl": r.fl, "ch": r.ch, "blk": r.blk}
                for r in (await db.execute(select(PacingReservation).where(
                    PacingReservation.hotel_id == HOTEL_ID))).scalars()]
    # La primera vez crea la configuración con los valores iniciales (meta 2026 y
    # STLY de RM de CWL): sin esto el análisis arrancaría sin meta hasta que
    # alguien abriera la pantalla de Cargas.
    config = _config_dict(await _config(db))
    await db.commit()
    return motor.limpiar(motor.analisis(snaps, reservas, config, kind=kind, year=year,
                                        escenario=escenario, fuente=fuente))


@router.get("/pacing/reservations/flagged")
async def flagged(year: int | None = Query(None), month: int | None = Query(None, ge=1, le=12),
                  db: AsyncSession = Depends(get_db)):
    """Reservas activas sin tarifa o con tarifa muy baja: lo que hay que corregir.

    «Muy baja» = menos del 40% de la tarifa noche mediana de su mes de llegada.
    Las cortesías (`COMP_HOUSE_YN`) se listan aparte: pueden ser correctas.
    """
    q = select(PacingReservation).where(PacingReservation.hotel_id == HOTEL_ID,
                                        PacingReservation.st == "A")
    rows = list((await db.execute(q)).scalars())
    if year:
        rows = [r for r in rows if r.arr[:4] == str(year)]
    if month and year:
        rows = [r for r in rows if r.arr[:7] == f"{year}-{month:02d}"]
    por_mes: dict[str, list[float]] = {}
    for r in rows:
        if r.nts and r.amt and float(r.amt) > 0:
            por_mes.setdefault(r.arr[:7], []).append(float(r.amt) / r.nts)
    mediana = {m: sorted(v)[len(v) // 2] for m, v in por_mes.items() if v}
    out = []
    for r in rows:
        noche = float(r.amt or 0) / r.nts if r.nts else 0.0
        med = mediana.get(r.arr[:7])
        if (r.fl or "").upper().startswith(("C", "H")):
            motivo = "cortesia"
        elif noche <= 0:
            motivo = "sin_tarifa"
        elif med and noche < 0.4 * med:
            motivo = "tarifa_baja"
        else:
            continue
        out.append({"id": r.resv_id, "guest": r.guest, "arr": r.arr, "nts": r.nts, "rms": r.rms,
                    "amt": float(r.amt or 0), "noche": round(noche, 2),
                    "mediana_mes": round(med, 2) if med else None,
                    "potencial": round(max((med or 0) - noche, 0) * r.nts * r.rms, 2),
                    "rate": r.rate, "ch": r.ch, "grupo": r.grupo, "ins": r.ins, "motivo": motivo})
    out.sort(key=lambda x: (x["arr"], x["id"]))
    return {"reservas": out, "potencial": round(sum(x["potencial"] for x in out
                                                    if x["motivo"] != "cortesia"), 2)}
