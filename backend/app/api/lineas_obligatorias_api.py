# -*- coding: utf-8 -*-
"""Lineas obligatorias: la lista, el aviso por escenario y el reporte de todos.

Ver `app/engine/lineas_obligatorias.py` para el porque. Aca solo estan las tres
puertas:

    GET /api/lineas-obligatorias/lista/            la lista tal cual, para revisarla
    GET /api/lineas-obligatorias/reporte/          todos los escenarios (lento: calcula)
    GET /api/lineas-obligatorias/{scenario_id}/    el aviso de UNO

⚠️ El orden de las rutas importa: `/lista/` y `/reporte/` van ANTES que
`/{scenario_id}/`, o FastAPI se los traga como si fueran un id.

**Todo se calcula en vivo.** Ver la nota del engine: `pl_lines` esta vacio o
viejo en 6 de los 20 escenarios de produccion, y avisar desde ahi inventaria
agujeros. Calcular cuesta segundos por escenario; equivocarse cuesta una
propiedad clonada con la luz en cero.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.db import get_db
from app.engine import lineas_obligatorias as obligatorias
from app.models.scenario import Scenario

router = APIRouter()


async def _por_mes(db: AsyncSession, escenario: Scenario) -> dict[int, dict[str, float]]:
    """El P&L calculado del escenario: {mes: {line_code: usd}}.

    Se importa `_monthly_results` adentro de la funcion a proposito: es el mismo
    motor que usa el reporte que el owner mira, y importarlo arriba ataria el
    arranque de la API a que ese modulo cargue.
    """
    from app.api.pl_api import _monthly_results
    meses = await _monthly_results(db, escenario)
    return {m["month"]: {ln.line_code: float(ln.amount_usd) for ln in m["lines"]}
            for m in meses}


def _etiqueta(s: Scenario) -> str:
    return f"{s.type} {s.version} {s.year}"


@router.get("/lineas-obligatorias/lista/")
async def get_lista():
    """La lista del repo, tal cual. Es lo que el owner revisa y edita."""
    return obligatorias.lista()


@router.get("/lineas-obligatorias/reporte/")
async def get_reporte(
    anio: int | None = Query(None, description="filtra por ano"),
    tipo: str | None = Query(None, description="ACTUAL | BUDGET | FORECAST"),
    db: AsyncSession = Depends(get_db),
):
    """Que le falta a CADA escenario, ordenado por lo que vale en el historico.

    Es el reporte que contesta «que tengo que cargar y en que orden». Calcula el
    P&L de cada escenario, asi que tarda: se puede acotar con `anio` y `tipo`.
    """
    q = select(Scenario)
    if anio is not None:
        q = q.where(Scenario.year == anio)
    if tipo:
        q = q.where(Scenario.type == tipo.upper())
    escs = (await db.execute(q)).scalars().all()
    escs.sort(key=lambda s: (s.year, s.type, s.version))

    filas = []
    for e in escs:
        try:
            rep = obligatorias.revisar(await _por_mes(db, e), e.type, e.actuals_through)
        except Exception as ex:                             # noqa: BLE001
            # Un escenario que no calcula no puede tumbar el reporte de los
            # otros diecinueve — se dice cual y se sigue.
            filas.append({"scenario_id": e.id, "etiqueta": _etiqueta(e),
                          "error": str(ex)[:200]})
            continue
        filas.append({
            "scenario_id": e.id,
            "etiqueta": _etiqueta(e),
            "type": e.type, "version": e.version, "year": e.year,
            "status": e.status,
            "actuals_through": e.actuals_through,
            **rep,
        })
    lista = obligatorias.lista()
    return {
        "generado": lista.get("generado", ""),
        "criterio": lista.get("criterio", {}),
        "obligatorias": len(lista.get("lineas", [])),
        "escenarios": filas,
    }


@router.get("/lineas-obligatorias/{scenario_id}/")
async def get_aviso(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """El aviso de UN escenario. Es lo que se pinta al abrirlo o recalcularlo."""
    esc = await db.get(Scenario, scenario_id)
    if esc is None:
        raise ErrorApi(404, "escenario.no_encontrado")
    rep = obligatorias.revisar(await _por_mes(db, esc), esc.type, esc.actuals_through)
    return {
        "scenario_id": esc.id,
        "etiqueta": _etiqueta(esc),
        "type": esc.type, "version": esc.version, "year": esc.year,
        "actuals_through": esc.actuals_through,
        "texto": obligatorias.resumen_texto(rep, _etiqueta(esc)),
        **rep,
    }
