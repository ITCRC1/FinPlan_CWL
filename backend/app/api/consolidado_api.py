# -*- coding: utf-8 -*-
"""P&L de ESTA propiedad, por API, de solo lectura.

**Para qué (owner, 2026-08-14).** Las propiedades son despliegues aparte con
bases aparte, y eso no se toca. Lo que faltaba era poder *jalar* el resultado de
cada una desde afuera para sumarlas donde el dueño quiera — Excel, Power BI, un
tablero propio, o la app de otra propiedad.

**Por qué así y no con un recolector.** La primera idea era que un backend fuera
a buscar a los otros tres; eso obliga a que UN hotel guarde las llaves de los
demás, y si lo comprometen se ven los cuatro. Acá cada propiedad solo sabe
responder por lo suyo: nadie guarda llaves ajenas, y quien consolida es el de
afuera. Además sirve desde el primer hotel, no desde el segundo.

**El contrato.** Este formato es el mismo en las cuatro propiedades: identidad,
escenario usado, y cada línea del P&L con sus 12 meses y el anual, en USD, más
los KPIs. Si cambia, cambia en las cuatro — por eso hay prueba de su forma.

**Qué NO sale por acá:** planilla por persona, nombres de personas, ninguna
fila del GL. Totales por línea; y, en `/consolidado/propia/cuentas/`, el
P&L por (departamento, cuenta) —sumas, nunca movimientos—.

**Por qué ahora sale por cuenta (owner, 2026-10-26).** «Que vengan de FinPlan de
una, y también todo». El Owner Dashboard deja de recibir el libro del P&L en
Excel: toma el Actual y el Forecast vigente de acá. Ese tablero muestra el P&L
por departamento y por GL, así que necesita el mismo detalle que el P&L Full
Detail de esta app, con la misma mezcla real + proyección del forecast.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.errores import ErrorApi
from app.auth import lector_del_consolidado
from app.db import get_session
from app.hotel_actual import HOTEL_ID, HOTEL_NAME
from app.models.scenario import Scenario

router = APIRouter()

TIPOS = ("BUDGET", "FORECAST", "ACTUAL")

# Versión del contrato. Sube cuando cambie la FORMA de la respuesta, para que un
# consolidador viejo pueda darse cuenta en vez de leer campos que ya no están.
CONTRATO = 1


@router.get("/consolidado/propia/")
async def consolidado_propia(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto, la más reciente"),
    quien: str = Depends(lector_del_consolidado),
):
    """El P&L de esta propiedad, listo para consolidar."""
    tipo = tipo.upper()
    if tipo not in TIPOS:
        raise ErrorApi(422, "consolidado.tipo_invalido", tipos=", ".join(TIPOS))

    from app.api import pl_api

    async with get_session() as session:
        q = select(Scenario).where(
            Scenario.hotel_id == HOTEL_ID,
            Scenario.year == year,
            Scenario.type == tipo,
        )
        if version:
            q = q.where(Scenario.version == version)
        escenario = (await session.execute(
            q.order_by(Scenario.created_at.desc()))).scalars().first()

        if escenario is None:
            # 404 y no una respuesta vacía: un consolidador que recibe ceros los
            # suma como si fueran ceros de verdad, y el grupo queda mal sin que
            # nada lo delate.
            if version:
                raise ErrorApi(404, "consolidado.sin_escenario_version",
                               propiedad=HOTEL_NAME, tipo=tipo,
                               version=version, anio=year)
            raise ErrorApi(404, "consolidado.sin_escenario",
                           propiedad=HOTEL_NAME, tipo=tipo, anio=year)

        mensual = await pl_api._monthly_results(session, escenario)
        anual = pl_api._aggregate(mensual, 12)

        # Se arma por CÓDIGO de línea, no por posición: dos propiedades pueden
        # tener líneas distintas (una sin Spa, otra sin Club) y la suma del que
        # consolida tiene que cuadrar igual.
        por_mes: dict[str, list[float]] = {}
        for m in mensual:
            for ln in m["lines"]:
                serie = por_mes.setdefault(ln.line_code, [0.0] * 12)
                serie[m["month"] - 1] += float(ln.amount_usd)

        lineas = [{
            "line_code": ln["line_code"],
            "line_name": ln["line_name"],
            "section": ln["section"],
            "meses": por_mes.get(ln["line_code"], [0.0] * 12),
            "anual": float(ln["amount_usd"]),
        } for ln in anual["lines"]]

        return {
            "contrato": CONTRATO,
            "hotel_id": HOTEL_ID,
            "hotel_name": HOTEL_NAME,
            "year": year,
            "tipo": tipo,
            "escenario": {
                "id": escenario.id,
                "version": escenario.version,
                "status": escenario.status,
                # Cuál es el último mes con dato real. Un consolidador que mezcla
                # propiedades con cortes distintos tiene que poder verlo.
                "actuals_through": getattr(escenario, "actuals_through", None),
            },
            "moneda": "USD",
            "kpis": anual.get("kpis", {}),
            # Noches de cada mes (Hotel Consolidation, 2026-10-14): con el
            # anual solo, el ADR y la ocupación mensual de un Forecast que vive
            # en el P&L —sin detalle por tipo— no se pueden reconstruir. Campo
            # nuevo; no cambia ninguno de los que ya estaban.
            "kpis_mes": [{
                "month": m["month"],
                "rooms_available": float((m["kpis"] or {}).get("rooms_available") or 0),
                "rooms_occupied": float((m["kpis"] or {}).get("rooms_occupied") or 0),
                "guests": float((m["kpis"] or {}).get("guests") or 0),
            } for m in mensual],
            "lineas": lineas,
            "leido_por": quien,
        }


@router.get("/consolidado/escenarios/")
async def consolidado_escenarios(quien: str = Depends(lector_del_consolidado)):
    """Qué hay para jalar. Sin esto, el de afuera tiene que adivinar años y tipos."""
    async with get_session() as session:
        filas = (await session.execute(
            select(Scenario).where(Scenario.hotel_id == HOTEL_ID)
            .order_by(Scenario.year.desc(), Scenario.type, Scenario.created_at.desc())
        )).scalars().all()
    return {
        "contrato": CONTRATO,
        "hotel_id": HOTEL_ID,
        "hotel_name": HOTEL_NAME,
        "escenarios": [{
            "year": e.year, "tipo": e.type, "version": e.version, "status": e.status,
        } for e in filas],
    }


@router.get("/consolidado/revenue-checkbook/{scenario_id}/")
async def consolidado_revenue_checkbook(
    scenario_id: str,
    quien: str = Depends(lector_del_consolidado),
):
    """El Revenue Checkbook del escenario: cada línea con sus 12 meses, en USD.

    Hotel Consolidation, 2026-10-23: el owner carga los ingresos del Budget en
    el Checkbook (Laundry, Retail % of Room net, Beverage % of Food…) y quiere
    ver ESE dato aunque el escenario siga en fuente Drivers. Solo lectura,
    totales por línea; `source` dice qué fuente usa hoy el P&L del escenario.
    """
    from app.models.revenue_entry import RevenueEntry, REVENUE_LINES, REVENUE_LINE_LABELS
    async with get_session() as session:
        escenario = await session.get(Scenario, scenario_id)
        if escenario is None or escenario.hotel_id != HOTEL_ID:
            raise ErrorApi(404, "escenario.no_encontrado")
        entradas = (await session.execute(
            select(RevenueEntry).where(RevenueEntry.scenario_id == scenario_id)
        )).scalars().all()
    por_linea = {e.line.upper(): e for e in entradas}
    return {
        "contrato": CONTRATO,
        "hotel_id": HOTEL_ID,
        "escenario": {"id": escenario.id, "year": escenario.year, "tipo": escenario.type,
                      "version": escenario.version},
        "source": getattr(escenario, "revenue_source", "drivers"),
        "moneda": "USD",
        "lineas": [{
            "line": ln,
            "label": REVENUE_LINE_LABELS.get(ln, ln.title()),
            "meses": [float(por_linea[ln].get_month(m)) if ln in por_linea else 0.0
                      for m in range(1, 13)],
        } for ln in REVENUE_LINES],
        "leido_por": quien,
    }


def _escoger_escenario(escenarios: list, tipo: str, version: str | None):
    """El escenario a entregar. Sin versión: para FORECAST el marcado ★ Current
    (o el más reciente si no hay marca); para ACTUAL el real, nunca el espejo del
    Pre-Cierre (trae un solo mes y es siempre lo último creado)."""
    if version:
        return next((e for e in escenarios if e.version == version), None)
    if tipo == "ACTUAL":
        escenarios = [e for e in escenarios if not getattr(e, "es_precierre", False)]
    if tipo == "FORECAST":
        marcado = [e for e in escenarios if getattr(e, "is_current_forecast", False)]
        if marcado:
            return marcado[0]
    return escenarios[0] if escenarios else None


@router.get("/consolidado/propia/cuentas/")
async def consolidado_cuentas(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("FORECAST", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """El P&L por (departamento, cuenta) × mes, más las líneas y los KPIs del mes.

    Las cuentas salen del mismo armado que el P&L Full Detail (`_detalle_propio`)
    con la misma mezcla del forecast: meses 1..actuals_through del ACTUAL real,
    el resto de la proyección. Las líneas salen del motor (`_monthly_results`),
    así que quien consume puede comprobar que la suma de las cuentas cuadra con el
    P&L —y ver lo que el motor calcula sin cuenta (honorarios, reserva, renta)—.
    """
    tipo = tipo.upper()
    if tipo not in TIPOS:
        raise ErrorApi(422, "consolidado.tipo_invalido", tipos=", ".join(TIPOS))

    from app.api import pl_api
    from app.api.pl_full_detail_api import _cargar_detalle
    from app.engine import pl_engine
    from app.engine.recalculate import load_report_line_config

    async with get_session() as session:
        escenarios = (await session.execute(
            select(Scenario).where(Scenario.hotel_id == HOTEL_ID, Scenario.year == year,
                                   Scenario.type == tipo)
            .order_by(Scenario.created_at.desc()))).scalars().all()
        escenario = _escoger_escenario(list(escenarios), tipo, version)
        if escenario is None:
            if version:
                raise ErrorApi(404, "consolidado.sin_escenario_version",
                               propiedad=HOTEL_NAME, tipo=tipo, version=version, anio=year)
            raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo=tipo, anio=year)

        acum = await _cargar_detalle(session, escenario)
        mensual = await pl_api._monthly_results(session, escenario)
        config = {r["line_code"]: r for r in await load_report_line_config(session)}

        por_mes: dict[str, list[float]] = {}
        for m in mensual:
            for ln in m["lines"]:
                serie = por_mes.setdefault(ln.line_code, [0.0] * 12)
                serie[m["month"] - 1] += float(ln.amount_usd)

        cuentas = [{
            "dept": d,
            "dept_padre": pl_engine.consolidate_dept_raiz(d),
            "cuenta": c,
            "nombre": acum.nombres.get((d, c), ""),
            "meses": [round(v, 6) for v in meses],
        } for (d, c), meses in sorted(acum.datos.items()) if any(abs(v) > 0.000001 for v in meses)]

        return {
            "contrato": CONTRATO,
            "hotel_id": HOTEL_ID,
            "hotel_name": HOTEL_NAME,
            "year": year,
            "tipo": tipo,
            "escenario": {
                "id": escenario.id,
                "version": escenario.version,
                "status": escenario.status,
                "actuals_through": int(getattr(escenario, "actuals_through", 0) or 0),
                "is_current_forecast": bool(getattr(escenario, "is_current_forecast", False)),
                "es_precierre": bool(getattr(escenario, "es_precierre", False)),
            },
            "moneda": "USD",
            "kpis_mes": [{
                "month": m["month"],
                "rooms_available": float((m["kpis"] or {}).get("rooms_available") or 0),
                "rooms_occupied": float((m["kpis"] or {}).get("rooms_occupied") or 0),
                "guests": float((m["kpis"] or {}).get("guests") or 0),
                "adr": float((m["kpis"] or {}).get("adr") or 0),
            } for m in mensual],
            "lineas": [{
                "line_code": code,
                "line_name": (config.get(code) or {}).get("line_name", code),
                "section": (config.get(code) or {}).get("section", ""),
                "line_type": (config.get(code) or {}).get("line_type", ""),
                "meses": serie,
            } for code, serie in por_mes.items()],
            "cuentas": cuentas,
            "leido_por": quien,
        }
