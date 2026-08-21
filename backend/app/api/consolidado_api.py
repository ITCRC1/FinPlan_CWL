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

**Qué NO sale por acá:** detalle de cuentas, planilla, nombres de personas,
ninguna fila del GL. Totales por línea y nada más.
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
