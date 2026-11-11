# -*- coding: utf-8 -*-
"""Posiciones, checkbook de planilla y checkbook de OPEX para el Excel en vivo.

Owner, 2026-11-11: *«puedes meter el tab de posiciones por mes y su costo y
además el checkbook de gastos y checkbook de planilla»*.

⚠️ **Esto cambia una regla del consolidado, y la cambió el owner.** El
`consolidado_api` nació (2026-08-14) diciendo que por la llave de solo lectura
NO salían planilla por persona ni nombres. El 2026-11-11, preguntado
explícitamente —«un puesto con una sola persona muestra el salario de esa
persona a cualquiera que tenga la llave»—, el owner eligió **«con nombre y
salario»**. Quien tenga la llave ve la planilla persona por persona: la llave
se reparte con ese cuidado.

**Las cifras salen del MISMO armado que la pantalla.** Posiciones y planilla
reusan `payroll_position_report_api.planilla_por_posicion` —el reporte
«Planilla por código de posición»—; el OPEX lee `opex_entries` como el
checkbook. Una segunda lectura «que hace lo mismo» termina dando otra cifra el
día que una de las dos cambia.

Se resuelve por **año + tipo + versión**, con el mismo criterio del resto del
consolidado (`_escoger_escenario`): el ★ Current del forecast, el ACTUAL real.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.errores import ErrorApi
from app.auth import lector_del_consolidado
from app.db import get_session
from app.hotel_actual import HOTEL_ID, HOTEL_NAME
from app.models.scenario import Scenario

router = APIRouter()

TIPOS = ("BUDGET", "FORECAST", "ACTUAL")
CONTRATO = 1


async def _escenario(session, year: int, tipo: str, version: str | None) -> Scenario:
    from app.api.consolidado_api import _escoger_escenario

    tipo = tipo.upper()
    if tipo not in TIPOS:
        raise ErrorApi(422, "consolidado.tipo_invalido", tipos=", ".join(TIPOS))
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
    return escenario


def _cabecera(escenario: Scenario, tipo: str) -> dict:
    return {
        "contrato": CONTRATO,
        "hotel_id": HOTEL_ID,
        "hotel_name": HOTEL_NAME,
        "year": escenario.year,
        "tipo": tipo.upper(),
        "escenario": {"id": escenario.id, "version": escenario.version,
                      "status": escenario.status,
                      "actuals_through": escenario.actuals_through or 0},
    }


# ── Armado puro (sin base): lo que se prueba ─────────────────────────────────

def filas_posiciones(reporte: dict) -> list[dict]:
    """Una fila por posición: FTE y costo de cada mes.

    El costo del mes es la suma de los 17 conceptos de ESE mes, el mismo número
    que viaja al P&L. El anual es la suma de los doce meses ya redondeados, así
    la fila cuadra contra sus propias columnas.
    """
    claves = [c["key"] for c in reporte["conceptos"]]
    out = []
    for f in reporte["rows"]:
        costo = [round(sum(f["meses"][k][m] for k in claves), 2) for m in range(12)]
        out.append({
            "dept": f["dept_code"], "dept_name": f["dept_name"],
            "codigo": f["position_code"], "puesto": f["position_name"],
            "empleado": f["employee_name"], "tipo_plaza": f.get("employee_type", ""),
            "moneda": f["salary_currency"], "salario": f["salary_amount"],
            "fte": f["fte"], "fte_prom": f["fte_prom"],
            "costo": costo, "costo_anual": round(sum(costo), 2),
            "devengado": f["devengado"], "cargas": f["cargas"],
            "beneficios": f["beneficios"],
        })
    return out


def filas_planilla(reporte: dict) -> list[dict]:
    """El checkbook de planilla: posición × concepto × mes.

    Solo los conceptos con alguna cifra en el año: los 17 conceptos de cada
    posición, la mayoría en cero, harían una tabla de miles de filas vacías.
    """
    out = []
    for f in reporte["rows"]:
        for c in reporte["conceptos"]:
            meses = f["meses"][c["key"]]
            if not any(abs(v) > 0.004 for v in meses):
                continue
            out.append({
                "dept": f["dept_code"], "dept_name": f["dept_name"],
                "codigo": f["position_code"], "puesto": f["position_name"],
                "empleado": f["employee_name"],
                "cuenta": c["code"], "concepto": c["label"], "grupo": c["grupo"],
                "meses": [round(v, 2) for v in meses],
                "anual": round(sum(round(v, 2) for v in meses), 2),
            })
    return out


def filas_opex(entradas, nombres_dept: dict[str, str]) -> list[dict]:
    """El checkbook de OPEX: cuenta × detalle × mes, en USD.

    Una línea en colones trae el dólar DERIVADO con el TC de cada mes (mig 077)
    — el mismo que suma el P&L —; la moneda va en su columna para que se sepa.
    """
    out = []
    for e in entradas:
        meses = [round(float(e.get_month(m) or 0), 2) for m in range(1, 13)]
        out.append({
            "dept": e.dept_code, "dept_name": nombres_dept.get(e.dept_code, ""),
            "cuenta": e.account_code, "nombre": e.account_name or "",
            "detalle": e.detail_code or "", "detalle_desc": e.detail_desc or "",
            "moneda": e.currency or "USD",
            "meses": meses, "anual": round(sum(meses), 2),
        })
    out.sort(key=lambda r: (r["dept"], r["cuenta"], r["detalle"]))
    return out


def filas_costos(entradas, nombres_dept: dict[str, str]) -> list[dict]:
    """El checkbook de costo de ventas (clase 5): depto × cuenta × mes, en USD.

    Owner, 2026-11-11 (Ojochal): «mete tambien el checkbook de costos de
    ventas». Los montos son los guardados —los que suma el P&L—: una línea con
    driver ya viene recalculada (% del ingreso, por noche, por huésped…), y el
    modo y el driver van en sus columnas para que se vea de dónde sale la cifra.
    Una línea en colones trae el dólar derivado con el TC de cada mes, como el OPEX.
    """
    out = []
    for e in entradas:
        meses = [round(float(e.get_month(m) or 0), 2) for m in range(1, 13)]
        out.append({
            "dept": e.dept_code, "dept_name": nombres_dept.get(e.dept_code, ""),
            "cuenta": e.account_code, "nombre": e.account_name or "",
            "modo": e.calc_mode or "MANUAL", "driver": e.driver_type or "",
            "tasa": float(e.driver_pct_or_rate or 0),
            "linea_ingreso": e.revenue_line_ref or "",
            "moneda": e.currency or "USD",
            "meses": meses, "anual": round(sum(meses), 2),
        })
    out.sort(key=lambda r: (r["dept"], r["cuenta"]))
    return out


# ── Endpoints ────────────────────────────────────────────────────────────────

async def _reporte_planilla(session, escenario: Scenario) -> dict:
    from app.api.payroll_position_report_api import planilla_por_posicion
    from app.models.payroll_position import PayrollPosition

    rep = await planilla_por_posicion(escenario.id, dept="", db=session)
    # El reporte de la pantalla no trae el tipo de plaza; se agrega acá sin
    # tocar su contrato.
    tipos = dict((await session.execute(
        select(PayrollPosition.id, PayrollPosition.employee_type)
        .where(PayrollPosition.scenario_id == escenario.id))).all())
    for f in rep["rows"]:
        f["employee_type"] = tipos.get(f["position_id"], "") or ""
    return rep


@router.get("/consolidado/posiciones/")
async def consolidado_posiciones(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Posiciones por mes: FTE y costo, con nombre y salario (owner, 2026-11-11)."""
    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        rep = await _reporte_planilla(session, escenario)
    return {**_cabecera(escenario, tipo), "posiciones": filas_posiciones(rep)}


@router.get("/consolidado/planilla/")
async def consolidado_planilla(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Checkbook de planilla: posición × concepto (6000–6030) × mes."""
    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        rep = await _reporte_planilla(session, escenario)
    return {**_cabecera(escenario, tipo), "lineas": filas_planilla(rep)}


@router.get("/consolidado/opex/")
async def consolidado_opex(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Checkbook de OPEX: departamento × cuenta × detalle × mes, en USD."""
    from app.models.department_catalog import DepartmentCatalog
    from app.models.opex_entry import OpexEntry

    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        entradas = (await session.execute(
            select(OpexEntry).where(OpexEntry.scenario_id == escenario.id))).scalars().all()
        nombres = dict((await session.execute(
            select(DepartmentCatalog.dept_code, DepartmentCatalog.dept_name))).all())
    return {**_cabecera(escenario, tipo), "lineas": filas_opex(entradas, nombres)}


@router.get("/consolidado/costos/")
async def consolidado_costos(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Checkbook de costo de ventas (clase 5): departamento × cuenta × mes, en USD."""
    from app.models.cost_entry import CostEntry
    from app.models.department_catalog import DepartmentCatalog

    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        entradas = (await session.execute(
            select(CostEntry).where(CostEntry.scenario_id == escenario.id))).scalars().all()
        nombres = dict((await session.execute(
            select(DepartmentCatalog.dept_code, DepartmentCatalog.dept_name))).all())
    return {**_cabecera(escenario, tipo), "lineas": filas_costos(entradas, nombres)}
