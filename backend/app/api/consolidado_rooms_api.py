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
