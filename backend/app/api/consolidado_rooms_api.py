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


# ── Los supuestos del ingreso, para reconstruirlo en el Excel ────────────────
#
# Owner, 2026-11-28, sobre el libro que reconstruye cada línea de ingreso del
# Budget 2027 (Standard vs Villas): *«como puedo mantener este excel para correr
# cuando yo quiera pero que la informacion se calcule en forma automatica»*, y
# después *«metelo en el master file»*.
#
# Esta ruta entrega los INSUMOS, no el resultado: ocupación %, rack, neta fijada
# a mano, pax por habitación, unidades, meses abiertos, factor neto, las
# perillas del Revenue Checkbook, y lo guardado en el checkbook para cuadrar.
# El cálculo lo hace el libro con fórmulas, y por eso el owner puede poner sus
# propios supuestos al lado sin tocar FinPlan.
#
# La forma es una tabla LARGA `clave · valor · texto`: el libro lee por clave
# con INDEX/MATCH y no depende del orden. Las claves:
#
#     INFO|<campo>|0                texto del escenario (fuente, versión…)
#     ORDEN|<n>|0                   texto = código de la categoría n (1, 2, …)
#     UNID|<cod>|0 · NOMBRE|<cod>|0 · SET|<cod>|0
#     OCC|<cod>|<m> · RACK|<cod>|<m> · PAX|<cod>|<m>
#     NETMAN|<cod>|<m>              solo si la neta está fijada a mano
#     DIAS|-|<m> · ABRE|-|<m> (1/0) · NF|-|<m> (factor neto de canales)
#     CANAL|<n>|0 · MIX|<canal>|<m> · COM|<canal>|<m>
#     PERILLA|<nombre>|0            food, tours, transport, nights_per_stay…
#     CB|<LÍNEA>|<m>                lo guardado en el Revenue Checkbook
#     OTRO|<LÍNEA>|<m>              montos de `revenue_other`
#
# ⚠️ Las perillas siguen el MISMO orden que la pantalla del checkbook: semilla
# del hotel, luego paquete del escenario, luego lo guardado a mano. Si el libro
# las tomara de otro lado, «Fill from drivers» y el Excel dirían cosas distintas.

def nombre_del_set(dept_code: str | None) -> str:
    """El set de una categoría, con el mismo criterio del Revenue Checkbook:
    lo que no es Villas ni Residencias cae en Standard, asignado o no."""
    dc = (dept_code or "").strip()
    return {"0115": "Villas", "0116": "Residences"}.get(dc, "Standard")


def filas_supuestos(info: dict, tipos: list[dict], por_tipo_mes: dict, dias: list[int],
                    abiertos: list[int], canales: list[dict], factor_neto: list[float],
                    perillas: dict, checkbook: dict, otros: dict) -> list[dict]:
    """La tabla larga. Puro, sin base, para poder probarlo solo.

    `tipos`: [{codigo, nombre, depto, unidades}] en el orden de la pantalla.
    `por_tipo_mes[(codigo, mes)]`: {occ, rack, pax, neta, manual}.
    """
    filas: list[dict] = []

    def add(clave: str, valor=None, texto=None):
        filas.append({"clave": clave,
                      "valor": None if valor is None else float(valor),
                      "texto": texto})

    for k, v in info.items():
        add(f"INFO|{k}|0", None, None if v is None else str(v))
    for n, t in enumerate(tipos, start=1):
        c = t["codigo"]
        add(f"ORDEN|{n}|0", None, c)
        add(f"UNID|{c}|0", t["unidades"])
        add(f"NOMBRE|{c}|0", None, t["nombre"])
        add(f"SET|{c}|0", None, nombre_del_set(t.get("depto")))
        for m in range(1, 13):
            d = por_tipo_mes.get((c, m)) or {}
            add(f"OCC|{c}|{m}", d.get("occ") or 0)
            add(f"RACK|{c}|{m}", d.get("rack") or 0)
            add(f"PAX|{c}|{m}", d.get("pax") or 0)
            if d.get("manual"):
                add(f"NETMAN|{c}|{m}", d.get("neta") or 0)
    for m in range(1, 13):
        add(f"DIAS|-|{m}", dias[m - 1])
        add(f"ABRE|-|{m}", abiertos[m - 1])
        add(f"NF|-|{m}", factor_neto[m - 1])
    for n, ch in enumerate(canales, start=1):
        add(f"CANAL|{n}|0", None, ch["channel"])
        for m in range(1, 13):
            add(f"MIX|{ch['channel']}|{m}", ch["mix"][m - 1])
            add(f"COM|{ch['channel']}|{m}", ch["comm"][m - 1])
    for k, v in perillas.items():
        add(f"PERILLA|{k}|0", v)
    for linea, meses in checkbook.items():
        for m in range(1, 13):
            add(f"CB|{linea}|{m}", meses[m - 1])
    for linea, meses in otros.items():
        for m in range(1, 13):
            add(f"OTRO|{linea}|{m}", meses[m - 1])
    return filas


@router.get("/consolidado/revenue-supuestos/")
async def revenue_supuestos(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST"),
    version: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    quien: str = Depends(lector_del_consolidado),
):
    """Los insumos del ingreso de un escenario, en tabla larga clave · valor · texto."""
    import calendar
    import datetime as _dt

    from app.api import revenue_api as rv
    from app.api.consolidado_planilla_api import _escenario
    from app.engine.tarifas_del_paquete import experiencias_del_escenario, tarifas_del_paquete
    from app.models.occupancy_budget import OccupancyBudget
    from app.models.rate_card import RateCard
    from app.models.revenue_entry import REVENUE_LINES, RevenueEntry
    from app.models.revenue_other import RevenueOther
    from app.models.scenario_master import ScenarioMaster
    from app.seed_data import semilla

    esc = await _escenario(db, year, tipo, version)
    rt = await rv.get_room_types(HOTEL_ID, scenario_id=esc.id, include_inactive=False, db=db)
    tipos = [{"codigo": r["code"] or r["id"], "nombre": r["name"], "depto": r["dept_code"],
              "unidades": int(r["units"] or 0), "id": r["id"]}
             for r in rt["room_types"] if r.get("active", True) and int(r["units"] or 0) > 0]
    codigo_de = {t["id"]: t["codigo"] for t in tipos}

    por_tipo_mes: dict = {}
    for rc in (await db.execute(select(RateCard).where(RateCard.scenario_id == esc.id))).scalars():
        c = codigo_de.get(rc.room_type_id)
        if c:
            por_tipo_mes.setdefault((c, rc.month), {}).update({
                "rack": rc.rack_rate, "pax": rc.pax_per_room, "neta": rc.net_rate,
                "manual": bool(getattr(rc, "net_rate_manual", False))})
    for ob in (await db.execute(select(OccupancyBudget).where(
            OccupancyBudget.scenario_id == esc.id))).scalars():
        c = codigo_de.get(ob.room_type_id)
        if c:
            por_tipo_mes.setdefault((c, ob.month), {})["occ"] = ob.occupancy_pct

    cerrados = set(rt["closed_months"] or [])
    dias = [calendar.monthrange(esc.year, m)[1] for m in range(1, 13)]
    abiertos = [0 if m in cerrados else 1 for m in range(1, 13)]
    ch = await rv.get_channels_config(esc.id, db)
    canales = [{"channel": c["channel"], "mix": [float(x) for x in c["mix"]],
                "comm": [float(x) for x in c["comm"]]} for c in ch["channels"]]
    factor_neto = [float(x) for x in ch["net_factor"]]

    # Perillas: semilla, luego paquete, luego guardadas, como la pantalla.
    perillas: dict = {k: float(v) for k, v in
                      (((semilla("driver_rates") or {}).get("tarifas")) or {}).items()
                      if k in rv.PERILLAS and isinstance(v, (int, float))}
    paquete = tarifas_del_paquete(await experiencias_del_escenario(db, esc.id))
    if paquete.get("disponible"):
        for k in ("food", "tours", "transport", "sust_rate", "nights_per_stay"):
            v = (paquete.get("tarifas") or {}).get(k)
            if v is not None:
                perillas[k] = float(v)
    sm = (await db.execute(select(ScenarioMaster).where(
        ScenarioMaster.scenario_id == esc.id))).scalar_one_or_none()
    perillas.update(rv._perillas_guardadas(sm))
    for k in rv.PERILLAS:
        perillas.setdefault(k, 0.0)

    entradas = {e.line.upper(): e for e in (await db.execute(
        select(RevenueEntry).where(RevenueEntry.scenario_id == esc.id))).scalars()}
    checkbook = {ln: [float(entradas[ln].get_month(m)) if ln in entradas else 0.0
                      for m in range(1, 13)] for ln in REVENUE_LINES}
    otros: dict = {}
    for o in (await db.execute(select(RevenueOther).where(
            RevenueOther.scenario_id == esc.id))).scalars():
        otros.setdefault(o.line.upper(), [0.0] * 12)[o.month - 1] += float(o.amount_usd or 0)

    info = {"escenario": f"{esc.type} {esc.version} {esc.year}", "tipo": esc.type,
            "version": esc.version, "anio": esc.year,
            "fuente": getattr(esc, "revenue_source", "drivers") or "drivers",
            "categorias": len(tipos),
            "leido": _dt.datetime.now().strftime("%Y-%m-%d %H:%M")}
    return {"contrato": CONTRATO, "hotel_id": HOTEL_ID, "hotel_name": HOTEL_NAME,
            "escenario": {"id": esc.id, "year": esc.year, "type": esc.type, "version": esc.version},
            "filas": filas_supuestos(info, tipos, por_tipo_mes, dias, abiertos, canales,
                                     factor_neto, perillas, checkbook, otros),
            "leido_por": quien}
