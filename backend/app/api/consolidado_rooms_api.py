# -*- coding: utf-8 -*-
"""Rooms Revenue de ESTA propiedad, por API, de solo lectura, para consolidar.

**Para qué (owner, 2026-10-14).** La app *Hotel Consolidation* junta el
Forecast vs Budget de habitaciones de las cuatro propiedades y lo presenta a
los dueños. Con un botón tiene que poder traer los datos al día de cualquier
hotel sin que el usuario inicie sesión en cada FinPlan.

**Por qué así.** Es la misma puerta que `consolidado_api.py`: la llave de solo
lectura `CONSOLIDADO_API_KEY` (encabezado `X-Api-Key`) o una sesión normal.
Cada propiedad responde solo por lo suyo y nadie guarda llaves ajenas; el que
consolida es el de afuera.

**Qué sale.** Lo mismo que ya muestran las pantallas de Revenue, sin calcular
nada nuevo: estadísticas por tipo de habitación (mes a mes), tarifas rack,
revenue mensual con su net factor, canales y, si la propiedad tiene pacing de
Opera, el análisis técnico por mes. **Qué NO sale:** reservas, huéspedes,
tarifas por reserva, planilla ni nada del GL.

**Solo lectura.** Ninguna ruta de este archivo escribe.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import lector_del_consolidado
from app.db import get_db
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID, HOTEL_NAME
from app.models.scenario import Scenario

router = APIRouter(tags=["consolidado"])

# Sube cuando cambie la FORMA de la respuesta.
CONTRATO = 1
TIPOS = ("FORECAST", "BUDGET", "ACTUAL")


def _tiene_pacing() -> bool:
    try:
        from app.api import pacing_api  # noqa: F401
        return True
    except Exception:
        return False


async def _escenario_propio(db: AsyncSession, scenario_id: str) -> Scenario:
    esc = await db.get(Scenario, scenario_id)
    # ⚠️ Se valida la propiedad: la llave abre ESTE hotel, no un id cualquiera.
    if esc is None or esc.hotel_id != HOTEL_ID:
        raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo=scenario_id, anio="")
    return esc


@router.get("/consolidado/rooms/escenarios/")
async def rooms_escenarios(db: AsyncSession = Depends(get_db),
                           quien: str = Depends(lector_del_consolidado)):
    """Qué Forecast / Budget / Actual hay, para elegir sin adivinar."""
    q = select(Scenario).where(Scenario.hotel_id == HOTEL_ID, Scenario.type.in_(TIPOS))
    if hasattr(Scenario, "es_precierre"):
        q = q.where(Scenario.es_precierre.is_(False))
    filas = (await db.execute(q.order_by(Scenario.year.desc(), Scenario.created_at.desc()))).scalars().all()
    return {
        "contrato": CONTRATO, "hotel_id": HOTEL_ID, "hotel_name": HOTEL_NAME,
        "tiene_pacing": _tiene_pacing(),
        "escenarios": [{
            "id": e.id, "year": e.year, "type": e.type, "version": e.version, "status": e.status,
            "is_current_forecast": bool(getattr(e, "is_current_forecast", False)),
            "actuals_through": getattr(e, "actuals_through", None),
            "created_at": e.created_at.isoformat() if getattr(e, "created_at", None) else None,
        } for e in filas],
        "leido_por": quien,
    }


@router.get("/consolidado/rooms/escenario/{scenario_id}/")
async def rooms_escenario(scenario_id: str, db: AsyncSession = Depends(get_db),
                          quien: str = Depends(lector_del_consolidado)):
    """Rooms de un escenario: por tipo, rack, mensual y canales."""
    from app.api import revenue_api as rv
    esc = await _escenario_propio(db, scenario_id)

    async def _o_nada(fn):
        # Un bloque que falla no tumba los demás: el consolidador ve `null` y lo dice.
        try:
            return await fn(scenario_id, db)
        except Exception:
            return None

    return {
        "contrato": CONTRATO, "hotel_id": HOTEL_ID, "hotel_name": HOTEL_NAME,
        "escenario": {"id": esc.id, "year": esc.year, "type": esc.type, "version": esc.version,
                      "status": esc.status, "actuals_through": getattr(esc, "actuals_through", None)},
        "by_room_type": await rv.get_revenue_by_room_type(scenario_id, db),
        "rack_rates": await _o_nada(rv.get_rack_rates),
        "monthly": await _o_nada(rv.get_monthly_revenue),
        "channels": await _o_nada(rv.get_channels_config),
        "leido_por": quien,
    }


@router.get("/consolidado/rooms/pacing/")
async def rooms_pacing(year: int = Query(..., ge=2000, le=2100), db: AsyncSession = Depends(get_db),
                       quien: str = Depends(lector_del_consolidado)):
    """Análisis técnico de pacing (Opera) por mes, el de «Posición mensual».

    Solo los números por mes; sin reservas ni huéspedes.
    """
    if not _tiene_pacing():
        raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo="PACING", anio=year)
    from app.api import pacing_api
    t = await pacing_api._tecnico(db, year, "rooms", "avail", "auto", "es")
    if not t or t.get("vacio"):
        raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo="PACING", anio=year)
    campos = ("i", "cerrado", "cap", "otb", "otb_rev", "stly", "pace", "ly", "ly_rev", "ly_base",
              "proj", "proj_rev", "ly_pick", "tasa", "bloqueos", "otb_adr", "st_adr", "confianza",
              "metodos", "metodos_rev", "sin_operacion")
    return {
        "contrato": CONTRATO, "hotel_id": HOTEL_ID, "hotel_name": HOTEL_NAME,
        "anio": t.get("anio"), "corte": t.get("corte"),
        "meses": [{k: m.get(k) for k in campos} for m in t.get("meses", [])],
        "leido_por": quien,
    }


@router.get("/consolidado/rooms/pickup/")
async def rooms_pickup(year: int = Query(..., ge=2000, le=2100), db: AsyncSession = Depends(get_db),
                       quien: str = Depends(lector_del_consolidado)):
    """Pickup reciente y canales, los de «Pickup & channels» (Hotel Consolidation, 2026-10-14).

    Solo totales: ventanas de 7/14/30/60/90 días contra el año anterior, el pickup
    de los últimos 30 días por mes de estadía y RN/tarifa por canal. Sin reservas
    ni huéspedes.
    """
    if not _tiene_pacing():
        raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo="PACING", anio=year)
    from app.api import pacing_api
    a = await pacing_api.get_analisis(year=year, kind="rooms", escenario="avail", fuente="auto", db=db)
    if not a or a.get("vacio") or a.get("anio") != year:
        raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo="PACING", anio=year)
    return {
        "contrato": CONTRATO, "hotel_id": HOTEL_ID, "hotel_name": HOTEL_NAME,
        "anio": a.get("anio"), "corte": a.get("corte"),
        "pickup": a.get("pickup"), "canales": a.get("canales") or [],
        "leido_por": quien,
    }


@router.get("/consolidado/rooms/rack-rooms/{scenario_id}/")
async def rooms_rack_rooms(scenario_id: str, db: AsyncSession = Depends(get_db),
                           quien: str = Depends(lector_del_consolidado)):
    """Rack contra neto y ventas por segmento («Rack Rooms»), para Hotel Consolidation (2026-10-16).

    El mismo cuadro de la pantalla Rack Rooms: RAC ponderado, ingreso a precio
    rack y neto, comisión/descuento, % del rack retenido y noches/ingreso por
    segmento de venta. Solo totales por mes y segmento; sin reservas ni
    huéspedes. 404 en las propiedades que no tienen ese modelo.
    """
    await _escenario_propio(db, scenario_id)
    try:
        from app.api import rack_rooms_api
    except Exception:
        raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo="RACK_ROOMS", anio="")
    d = await rack_rooms_api._ver(db, scenario_id)
    if not d.get("hay_tarifario") and not d.get("entradas"):
        raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo="RACK_ROOMS", anio=d.get("year") or "")
    return {
        "contrato": CONTRATO, "hotel_id": HOTEL_ID, "hotel_name": HOTEL_NAME,
        "year": d.get("year"), "conectado": d.get("conectado"), "hay_tarifario": d.get("hay_tarifario"),
        "villas": d.get("villas") or [], "temporadas": d.get("temporadas") or [],
        "segmentos": d.get("segmentos") or [], "comisiones": d.get("comisiones") or [],
        "meses": d.get("meses") or [], "total": d.get("total") or {}, "controles": d.get("controles") or {},
        "leido_por": quien,
    }


@router.get("/consolidado/country-mix/")
async def country_mix(year: int = Query(..., ge=2000, le=2100), metric: str = Query("rooms"),
                      db: AsyncSession = Depends(get_db), quien: str = Depends(lector_del_consolidado)):
    """Country mix mes a mes de los escenarios del año que tengan datos (para el Owner Dashboard).

    Mismo dato que la pantalla Marketing → Country Mix, sin calcular nada nuevo: el que consume
    arma el Mes y el YTD. Solo lectura; solo escenarios de ESTA propiedad.
    """
    from app.models.country_mix import COUNTRY_METRICS, CountryMixEntry
    metric = (metric or "rooms").lower()
    if metric not in COUNTRY_METRICS:
        metric = "rooms"
    q = select(Scenario).where(Scenario.hotel_id == HOTEL_ID, Scenario.year == year, Scenario.type.in_(TIPOS))
    if hasattr(Scenario, "es_precierre"):
        q = q.where(Scenario.es_precierre.is_(False))
    salida = []
    for e in (await db.execute(q.order_by(Scenario.created_at.desc()))).scalars().all():
        filas = (await db.execute(select(CountryMixEntry).where(
            CountryMixEntry.scenario_id == e.id, CountryMixEntry.metric == metric))).scalars().all()
        if not filas:
            continue
        salida.append({
            "scenario": {"id": e.id, "year": e.year, "type": e.type, "version": e.version},
            "entries": [{"month": f.month, "country": f.country, "value": float(f.value)} for f in filas],
        })
    return {"contrato": CONTRATO, "hotel_id": HOTEL_ID, "hotel_name": HOTEL_NAME, "year": year,
            "metric": metric, "scenarios": salida, "leido_por": quien}


@router.get("/consolidado/channel-mix/")
async def channel_mix(year: int = Query(..., ge=2000, le=2100), metric: str = Query("rooms"),
                      db: AsyncSession = Depends(get_db), quien: str = Depends(lector_del_consolidado)):
    """Channel mix mes a mes de los escenarios del año que tengan datos (sección 2.5 del Owner Dashboard).

    Mismo dato que Marketing → Channel Mix (`channel_mix_entries`), sin calcular nada nuevo: el que consume
    arma el Mes y el YTD (Σ meses ÷ total, igual que la pantalla). Solo lectura; solo escenarios de ESTA propiedad.
    """
    from app.models.channel_mix import CHANNEL_METRICS, ChannelMixEntry
    metric = (metric or "rooms").lower()
    if metric not in CHANNEL_METRICS:
        metric = "rooms"
    q = select(Scenario).where(Scenario.hotel_id == HOTEL_ID, Scenario.year == year, Scenario.type.in_(TIPOS))
    if hasattr(Scenario, "es_precierre"):
        q = q.where(Scenario.es_precierre.is_(False))
    salida = []
    for e in (await db.execute(q.order_by(Scenario.created_at.desc()))).scalars().all():
        filas = (await db.execute(select(ChannelMixEntry).where(
            ChannelMixEntry.scenario_id == e.id, ChannelMixEntry.metric == metric))).scalars().all()
        if not filas:
            continue
        salida.append({
            "scenario": {"id": e.id, "year": e.year, "type": e.type, "version": e.version},
            "entries": [{"month": f.month, "channel": f.channel, "value": float(f.value)} for f in filas],
        })
    return {"contrato": CONTRATO, "hotel_id": HOTEL_ID, "hotel_name": HOTEL_NAME, "year": year,
            "metric": metric, "scenarios": salida, "leido_por": quien}
