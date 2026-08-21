# -*- coding: utf-8 -*-
"""El panorama de canales: las tres listas juntas, y dónde no coinciden.

**Por qué existe (owner, 2026-08-14).** «Necesito lo pongas ahí mismo para ver
todo el panorama y revisemos.» En el sistema hay **tres listas de canales**, cada
una respondiendo una pregunta distinta:

| Lista | Pregunta | Cuántos |
|---|---|---|
| Market codes de Opera | ¿Cómo entró la reserva? | 13 → 5 canales |
| `SalesChannelConfig`  | ¿Cuánta comisión pago? | 3 (TA/OTA/DIRECT) |
| `CanalComercial`      | ¿Quién cobra? | 7 |

**Este endpoint no las fusiona: las CONFRONTA.** Fusionarlas sería elegir una
verdad y tapar las otras dos. Lo que hace es ponerlas lado a lado y decir dónde
no dicen lo mismo, que es lo que el owner tiene que decidir.

Los descuadres se calculan, no se escriben a mano: el día que alguien cambie una
comisión, este endpoint lo dice solo.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.auth import get_current_user
from app.db import get_session
from app.textos import Idioma, t
from app.models.canal_comercial import CanalComercial
from app.models.market_code import CANAL_A_COMISION, CANALES, MarketCode
from app.models.sales_channel_config import SalesChannelConfig

router = APIRouter()

#: Cómo se llama en `SalesChannelConfig` el canal de comisión de cada entrada.
#: Es el puente entre «por dónde entró» y «cuánto comisiona».
COMISION_POR_ENTRADA = CANAL_A_COMISION

#: Debajo de esto es redondeo, no discrepancia. Un cuarto de punto.
TOLERANCIA = Decimal("0.0025")


@router.get("/canales/panorama/")
async def panorama(scenario_id: str = Query(""), _=Depends(get_current_user),
                   idioma: str = Idioma):
    """Las tres listas y sus discrepancias."""
    async with get_session() as s:
        mcodes = (await s.execute(select(MarketCode)
                                  .order_by(MarketCode.orden, MarketCode.code))
                  ).scalars().all()
        canales = (await s.execute(select(CanalComercial)
                                   .order_by(CanalComercial.orden))
                   ).scalars().all()
        # La comisión de FinPlan es por mes; se toma enero, que es la que el
        # owner ve en la pantalla de Sales Channels.
        comision_finplan: dict[str, Decimal] = {}
        if scenario_id:
            for c in (await s.execute(select(SalesChannelConfig).where(
                    SalesChannelConfig.scenario_id == scenario_id,
                    SalesChannelConfig.month == 1))).scalars().all():
                comision_finplan[c.channel] = c.commission_pct

    # ── Los market codes, con su canal y a qué canal de comisión ruedan ──────
    codigos = [{
        "code": m.code, "nombre": m.nombre, "canal": m.canal,
        "canal_comision": CANAL_A_COMISION.get(m.canal, ""),
        "activo": m.activo,
    } for m in mcodes]
    sin_canal = [m.code for m in mcodes if not m.canal]

    # ── Los canales comerciales, separados por eje ──────────────────────────
    comerciales = [{
        "code": c.code, "nombre": c.nombre,
        "comision_pct": float(c.comision_pct),
        "entrada": c.entrada,
        # Un canal sin `entrada` describe QUIÉN trajo la reserva, no por dónde
        # entró. Opera no lo sabe: no se puede derivar del market code.
        "eje": "entrada" if c.entrada else "atribucion",
    } for c in canales]

    # ── Las discrepancias, calculadas ───────────────────────────────────────
    discrepancias = []

    if sin_canal:
        discrepancias.append({
            "tipo": "market_code_sin_canal",
            "gravedad": "alta",
            "detalle": t(idioma, "canales.market_code_sin_canal",
                         n=len(sin_canal), codes=", ".join(sin_canal)),
            "porque": t(idioma, "canales.market_code_sin_canal_porque"),
        })

    # El reverso del hueco de arriba, que nadie estaba mirando: un market code
    # SI tiene canal, pero ningún canal comercial entra por ahí. Sus noches
    # llegan al KPI group y ahí se quedan — no hay quién cobre la comisión.
    #
    # Hoy le pasa a INHOUSE: los siete canales comerciales entran por Travel
    # Agent, Website, Direct Client y OTA, y ninguno por INHOUSE. Se calcula, no
    # se escribe: el día que el owner cree el canal, esta línea desaparece sola.
    entradas = {c.entrada for c in canales if c.entrada}
    huerfanos_canal = sorted({m.canal for m in mcodes if m.canal and m.canal not in entradas})
    if huerfanos_canal:
        afectados = sorted(m.code for m in mcodes if m.canal in huerfanos_canal)
        discrepancias.append({
            "tipo": "canal_sin_canal_comercial",
            "gravedad": "media",
            "detalle": t(idioma, "canales.canal_sin_comercial",
                         n=len(huerfanos_canal),
                         canales=", ".join(huerfanos_canal),
                         codes=", ".join(afectados)),
            "porque": t(idioma, "canales.canal_sin_comercial_porque"),
        })

    # Comisión de FinPlan contra la de la app de compensación, por canal de
    # comisión. Se compara la MÁS ALTA de las comerciales que ruedan a ese
    # canal: es la que marca el techo de lo que se paga.
    if comision_finplan:
        por_comision: dict[str, list] = {}
        for c in canales:
            destino = COMISION_POR_ENTRADA.get(c.entrada, "")
            if destino:
                por_comision.setdefault(destino, []).append(c)
        for destino, lista in sorted(por_comision.items()):
            fp = comision_finplan.get(destino)
            if fp is None:
                continue
            for c in lista:
                dif = c.comision_pct - fp
                if abs(dif) > TOLERANCIA:
                    discrepancias.append({
                        "tipo": "comision_distinta",
                        "gravedad": "alta",
                        "detalle": t(idioma, "canales.comision_distinta",
                                     canal=c.nombre,
                                     real=f"{float(c.comision_pct):.0%}",
                                     finplan=f"{float(fp):.0%}",
                                     destino=destino,
                                     dif=f"{float(dif):+.0%}"),
                        "porque": t(idioma, "canales.comision_distinta_porque"),
                    })
        # Los canales de comisión que FinPlan tiene y nadie alimenta.
        huerfanos = sorted(set(comision_finplan) - set(por_comision))
        if huerfanos:
            discrepancias.append({
                "tipo": "canal_de_comision_sin_origen",
                "gravedad": "media",
                "detalle": t(idioma, "canales.comision_sin_origen",
                             canales=", ".join(huerfanos)),
                "porque": t(idioma, "canales.comision_sin_origen_porque"),
            })

    # Los canales que describen QUIÉN trajo la reserva no se pueden atribuir
    # desde Opera. Es la discrepancia estructural, no un error de dato.
    atribucion = [c["nombre"] for c in comerciales if c["eje"] == "atribucion"]
    if atribucion:
        discrepancias.append({
            "tipo": "sin_origen_en_el_pms",
            "gravedad": "estructural",
            "detalle": t(idioma, "canales.sin_origen_en_el_pms",
                         n=len(atribucion), canales=", ".join(atribucion)),
            "porque": t(idioma, "canales.sin_origen_en_el_pms_porque"),
        })

    return {
        "canales_pms": list(CANALES),
        "market_codes": codigos,
        "comerciales": comerciales,
        "comision_finplan": {k: float(v) for k, v in comision_finplan.items()},
        "discrepancias": discrepancias,
    }
