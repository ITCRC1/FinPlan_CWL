"""
Payroll checkbook API — Phase 4.

Endpoints:
  GET  /api/payroll/{scenario_id}/depts/
  GET  /api/payroll/{scenario_id}/dept/{dept_code}/
  POST /api/payroll/{scenario_id}/dept/{dept_code}/position/
  PUT  /api/payroll/{scenario_id}/position/{id}/
  DELETE /api/payroll/{scenario_id}/position/{id}/
  PUT  /api/payroll/{scenario_id}/position/{id}/month/{month}/base-concepts/
  PUT  /api/payroll/{scenario_id}/position/{id}/month/{month}/benefit-concepts/
  GET  /api/payroll/{scenario_id}/summary/
  GET  /api/payroll/{scenario_id}/dept/{dept_code}/summary/
  GET  /api/payroll/{scenario_id}/fte-report/
  POST /api/payroll/{scenario_id}/import-codificacion/
  POST /api/scenarios/{scenario_id}/recalculate/
"""
import os
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.importers.registro_dep import registro_de_subida
from fastapi.responses import Response
from pydantic import BaseModel, field_validator
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api._candado import candado
from app.db import get_db
from app.errores import ErrorApi
from app.textos import Idioma, t
from app.models.payroll_position import PayrollPosition, get_fte
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.actual_dept_fte import ActualDeptFte
from app.models.scenario import Scenario
from app.api._nombres_de_depto import nombres_de_depto
from app.export.payroll_excel import export_payroll_to_excel, import_payroll_from_excel
from app.models.exchange_rate import get_tc_for_month, ExchangeRate
from app.models.payroll_params import (
    PayrollParams, DEFAULT_CCSS_RATE, DEFAULT_AGUINALDO_DIVISOR,
)
from app.engine.payroll_calculator import (
    recalculate_entry, summarize_dept, build_fte_report,
    DeptPayrollSummary, FTEReport, total_entry,
)
from app.importers.codificacion_importer import import_codificacion
from app.importers.gl_detail_importer import ALLOC_EXCL_PAYROLL
from app.api._allocated import lineas_del_allocation

router = APIRouter(tags=["payroll"])

CODIFICACION_DEFAULT_PATH = Path(os.getenv("DATA_DIR", "C:/FinPlan_CWL")) / "Codificacion Planilla 11 de febrero 0850am (enviado).xlsx"


async def _payroll_rates(db, scenario_id: str):
    """(ccss_rate, aguinaldo_divisor) del escenario, o defaults históricos."""
    pp = (await db.execute(
        select(PayrollParams).where(PayrollParams.scenario_id == scenario_id)
    )).scalar_one_or_none()
    if pp:
        return pp.ccss_rate, pp.aguinaldo_divisor
    return DEFAULT_CCSS_RATE, DEFAULT_AGUINALDO_DIVISOR


async def _payroll_cfg(db, scenario_id: str):
    """(ccss_rate, aguinaldo_divisor, params) — `params` trae además los drivers
    de los conceptos que se calculan por regla (overtime, feriados, cafetería…).
    Sin fila de parámetros va None y solo se mueven 6000/6020/6021, como antes."""
    pp = (await db.execute(
        select(PayrollParams).where(PayrollParams.scenario_id == scenario_id)
    )).scalar_one_or_none()
    if pp:
        return pp.ccss_rate, pp.aguinaldo_divisor, pp
    return DEFAULT_CCSS_RATE, DEFAULT_AGUINALDO_DIVISOR, None


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class PositionCreate(BaseModel):
    dept_code: str
    dept_name: str = ""
    position_code: str = ""
    position_name: str
    employee_name: str = "VACANTE"
    employee_type: str = "1-Permanente"
    class_code: str = "013"
    category_code: str = "015"
    salary_amount: Decimal = Decimal("0")
    salary_currency: str = "CRC"
    fte_jan: Decimal = Decimal("1.0")
    fte_feb: Decimal = Decimal("1.0")
    fte_mar: Decimal = Decimal("1.0")
    fte_apr: Decimal = Decimal("1.0")
    fte_may: Decimal = Decimal("1.0")
    fte_jun: Decimal = Decimal("1.0")
    fte_jul: Decimal = Decimal("1.0")
    fte_aug: Decimal = Decimal("1.0")
    fte_sep: Decimal = Decimal("1.0")
    fte_oct: Decimal = Decimal("0.0")
    fte_nov: Decimal = Decimal("1.0")
    fte_dec: Decimal = Decimal("1.0")

    @field_validator("fte_jan", "fte_feb", "fte_mar", "fte_apr", "fte_may", "fte_jun",
                     "fte_jul", "fte_aug", "fte_sep", "fte_oct", "fte_nov", "fte_dec",
                     mode="before")
    @classmethod
    def validate_fte(cls, v):
        v = Decimal(str(v))
        if v < Decimal("0") or v > Decimal("1"):
            raise ValueError("FTE must be between 0.00 and 1.00")
        return v

    @field_validator("salary_currency")
    @classmethod
    def validate_currency(cls, v):
        if v not in ("CRC", "USD"):
            raise ValueError("salary_currency must be 'CRC' or 'USD'")
        return v


class PositionUpdate(BaseModel):
    position_name: Optional[str] = None
    employee_name: Optional[str] = None
    employee_type: Optional[str] = None
    salary_amount: Optional[Decimal] = None
    salary_currency: Optional[str] = None
    fte_jan: Optional[Decimal] = None
    fte_feb: Optional[Decimal] = None
    fte_mar: Optional[Decimal] = None
    fte_apr: Optional[Decimal] = None
    fte_may: Optional[Decimal] = None
    fte_jun: Optional[Decimal] = None
    fte_jul: Optional[Decimal] = None
    fte_aug: Optional[Decimal] = None
    fte_sep: Optional[Decimal] = None
    fte_oct: Optional[Decimal] = None
    fte_nov: Optional[Decimal] = None
    fte_dec: Optional[Decimal] = None

    @field_validator("fte_jan", "fte_feb", "fte_mar", "fte_apr", "fte_may", "fte_jun",
                     "fte_jul", "fte_aug", "fte_sep", "fte_oct", "fte_nov", "fte_dec",
                     mode="before")
    @classmethod
    def validate_fte(cls, v):
        if v is None:
            return v
        v = Decimal(str(v))
        if v < Decimal("0") or v > Decimal("1"):
            raise ValueError("FTE must be between 0.00 and 1.00")
        return v


class BaseConceptsUpdate(BaseModel):
    """Manual group-base concepts (6001/6002/6003/6010/6024/6027)."""
    c6001_overtime: Optional[Decimal] = None
    c6002_day_off: Optional[Decimal] = None
    c6003_working_holiday: Optional[Decimal] = None
    c6010_commissions: Optional[Decimal] = None
    c6024_vacations_taken: Optional[Decimal] = None
    c6027_incentive_bonus: Optional[Decimal] = None


class BenefitConceptsUpdate(BaseModel):
    """Manual benefit concepts (6004/6022-6030 except 6024/6027 which are in base)."""
    c6004_disabilities: Optional[Decimal] = None
    c6022_occ_hazard: Optional[Decimal] = None
    c6023_vacation_prov: Optional[Decimal] = None
    c6025_cafeteria: Optional[Decimal] = None
    c6026_severance: Optional[Decimal] = None
    c6028_housing: Optional[Decimal] = None
    c6029_transport: Optional[Decimal] = None
    c6030_other: Optional[Decimal] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_position_or_404(
    db: AsyncSession, scenario_id: str, position_id: str
) -> PayrollPosition:
    pos = await db.get(PayrollPosition, position_id)
    if not pos or pos.scenario_id != scenario_id:
        raise ErrorApi(404, "posicion.no_encontrada", posicion=position_id)
    return pos


async def _get_or_create_entry(
    db: AsyncSession,
    scenario_id: str,
    position: PayrollPosition,
    month: int,
    year: int,
) -> PayrollConceptEntry:
    result = await db.execute(
        select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id,
            PayrollConceptEntry.position_id == position.id,
            PayrollConceptEntry.month == month,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        entry = PayrollConceptEntry(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            position_id=position.id,
            dept_code=position.dept_code,
            month=month,
            year=year,
        )
        db.add(entry)
    return entry


async def _estrenar_posicion(db, scenario_id: str, pos, year: int) -> int:
    """Le crea a una posición recién nacida sus 12 filas de planilla, ya calculadas.

    Sin esto la posición existe pero no tiene meses: no aparece con FTE en el
    reporte de FTEs, ni suma salario, ni CCSS, hasta que alguien recuerde apretar
    «Recalcular». Una posición nueva debe nacer completa.
    """
    rates = await _get_exchange_rates(db, scenario_id)
    ccss, agu, pp = await _payroll_cfg(db, scenario_id)
    for month in range(1, 13):
        tc = get_tc_for_month(rates, month) if rates else Decimal("1")
        entry = await _get_or_create_entry(db, scenario_id, pos, month, year)
        recalculate_entry(entry, pos, month, tc, ccss, agu, params=pp)
    return 12


async def _get_exchange_rates(db: AsyncSession, scenario_id: str) -> list[ExchangeRate]:
    result = await db.execute(
        select(ExchangeRate).where(ExchangeRate.scenario_id == scenario_id)
    )
    return result.scalars().all()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/payroll/{scenario_id}/depts/")
async def list_depts(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """List unique department codes that have positions in this scenario."""
    result = await db.execute(
        select(PayrollPosition.dept_code, PayrollPosition.dept_name)
        .where(PayrollPosition.scenario_id == scenario_id)
        .distinct()
        .order_by(PayrollPosition.dept_code)
    )
    depts = [{"dept_code": r[0], "dept_name": r[1]} for r in result.all()]
    depts = await _esconder_apagados(db, scenario_id, "PAYROLL", depts)
    return {"scenario_id": scenario_id, "depts": depts}


async def _esconder_apagados(db, scenario_id: str, dimension: str, depts: list[dict]):
    """Saca del selector los departamentos que esta PROPIEDAD apagó para esta
    dimensión en el provisionamiento.

    ⚠️ Esconde de la LISTA, no del cálculo: si el departamento tiene datos, esos
    datos siguen sumando en el P&L. La pantalla de provisionamiento avisa antes
    de dejar apagar algo que tiene líneas cargadas.
    """
    from app.api.provisioning_api import depts_habilitados
    esc = await db.get(Scenario, scenario_id)
    if esc is None:
        return depts
    apagados = await depts_habilitados(db, esc.hotel_id, dimension)
    if not apagados:
        return depts
    return [d for d in depts if d.get("dept_code") not in apagados]


@router.get("/payroll/{scenario_id}/dept/{dept_code}/")
async def get_dept_checkbook(
    scenario_id: str,
    dept_code: str,
    db: AsyncSession = Depends(get_db),
):
    """List all positions and their concept entries for a department."""
    result = await db.execute(
        select(PayrollPosition)
        .where(
            PayrollPosition.scenario_id == scenario_id,
            PayrollPosition.dept_code == dept_code,
        )
        .order_by(PayrollPosition.position_code, PayrollPosition.employee_name)
    )
    positions = result.scalars().all()

    entries_result = await db.execute(
        select(PayrollConceptEntry)
        .where(
            PayrollConceptEntry.scenario_id == scenario_id,
            PayrollConceptEntry.dept_code == dept_code,
        )
    )
    entries = entries_result.scalars().all()
    entries_by_pos_month = {(e.position_id, e.month): e for e in entries}

    pos_data = []
    for pos in positions:
        months_data = []
        for m in range(1, 13):
            entry = entries_by_pos_month.get((pos.id, m))
            months_data.append({
                "month": m,
                "fte": float(get_fte(pos, m)),
                "entry": _entry_to_dict(entry) if entry else None,
            })
        pos_data.append({
            "id": pos.id,
            "dept_code": pos.dept_code,
            "dept_name": pos.dept_name,
            "position_code": pos.position_code,
            "position_name": pos.position_name,
            "employee_name": pos.employee_name,
            "employee_type": pos.employee_type,
            "salary_amount": float(pos.salary_amount),
            "salary_currency": pos.salary_currency,
            "months": months_data,
        })
    return {"scenario_id": scenario_id, "dept_code": dept_code, "positions": pos_data}


def _entry_to_dict(e: PayrollConceptEntry) -> dict:
    return {
        "id": e.id,
        "month": e.month,
        "c6000_sw": float(e.c6000_sw),
        "c6001_overtime": float(e.c6001_overtime),
        "c6002_day_off": float(e.c6002_day_off),
        "c6003_working_holiday": float(e.c6003_working_holiday),
        "c6010_commissions": float(e.c6010_commissions),
        "c6024_vacations_taken": float(e.c6024_vacations_taken),
        "c6027_incentive_bonus": float(e.c6027_incentive_bonus),
        "c6020_ccss": float(e.c6020_ccss),
        "c6021_aguinaldo": float(e.c6021_aguinaldo),
        "c6004_disabilities": float(e.c6004_disabilities),
        "c6022_occ_hazard": float(e.c6022_occ_hazard),
        "c6023_vacation_prov": float(e.c6023_vacation_prov),
        "c6025_cafeteria": float(e.c6025_cafeteria),
        "c6026_severance": float(e.c6026_severance),
        "c6028_housing": float(e.c6028_housing),
        "c6029_transport": float(e.c6029_transport),
        "c6030_other": float(e.c6030_other),
        "total": float(total_entry(e)),
    }


@router.post("/payroll/{scenario_id}/dept/{dept_code}/position/", status_code=201)
async def create_position(
    scenario_id: str,
    dept_code: str,
    body: PositionCreate,
    db: AsyncSession = Depends(get_db),
):
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    data = body.model_dump()
    data.pop("dept_code", None)   # dept_code viene del path; evitar pasarlo dos veces
    pos = PayrollPosition(
        id=str(uuid.uuid4()),
        scenario_id=scenario_id,
        hotel_id=scenario.hotel_id,
        dept_code=dept_code,
        **data,
    )
    db.add(pos)
    await db.flush()
    # Nace con sus 12 meses ya calculados: así entra de una al reporte de FTEs y
    # al costo de planilla, sin depender de que alguien recalcule después.
    meses = await _estrenar_posicion(db, scenario_id, pos, getattr(scenario, "year", 2027))
    await db.commit()
    return {"id": pos.id, "position_name": pos.position_name, "dept_code": pos.dept_code,
            "meses_creados": meses}


@router.put("/payroll/{scenario_id}/position/{position_id}/")
async def update_position(
    scenario_id: str,
    position_id: str,
    body: PositionUpdate,
    db: AsyncSession = Depends(get_db),
):
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    pos = await _get_position_or_404(db, scenario_id, position_id)
    changed = body.model_dump(exclude_none=True)
    for field, value in changed.items():
        setattr(pos, field, value)
    # Si tocó salario/moneda/FTE, recalcular SW+CCSS+aguinaldo de esa posición.
    n = 0
    if any(k in changed for k in ("salary_amount", "salary_currency", *_FTE_MONTHS)):
        await db.flush()
        n = await _recalc_positions(db, scenario_id, [pos])
    await db.commit()
    return {"id": pos.id, "updated": True, "entries_recalculated": n}


@router.post("/payroll/{scenario_id}/position/{position_id}/duplicate/", status_code=201)
async def duplicate_position(
    scenario_id: str,
    position_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Copia una posición (mismo dept/código/salario/FTE) como una persona nueva.
    employee_name = 'VACANTE N+1' según cuántas haya ya de esa posición."""
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    from sqlalchemy.orm import class_mapper
    src = await _get_position_or_404(db, scenario_id, position_id)

    # ¿Cuántas personas hay ya de esta (dept, position_code, position_name)?
    siblings = (await db.execute(
        select(PayrollPosition).where(
            PayrollPosition.scenario_id == scenario_id,
            PayrollPosition.dept_code == src.dept_code,
            PayrollPosition.position_code == src.position_code,
            PayrollPosition.position_name == src.position_name,
        )
    )).scalars().all()
    n = len(siblings) + 1

    cols = [c.key for c in class_mapper(PayrollPosition).columns]
    data = {c: getattr(src, c) for c in cols}
    data["id"] = str(uuid.uuid4())
    data["employee_name"] = f"VACANTE {n}"
    # El código NO se copia: es único por posición y es la llave de los reportes
    # de planilla. Copiarlo metía dos personas bajo el mismo código y el reporte
    # las sumaba en un renglón sin decir nada.
    from app.api.payroll_position_report_api import siguiente_codigo
    nuevo = (await siguiente_codigo(scenario_id, dept=src.dept_code, count=1, db=db))
    data["position_code"] = nuevo["codes"][0]
    nueva = PayrollPosition(**data)
    db.add(nueva)
    await db.flush()
    esc = await db.get(Scenario, scenario_id)
    await _estrenar_posicion(db, scenario_id, nueva, getattr(esc, "year", 2027))
    await db.commit()
    return {"id": data["id"], "employee_name": data["employee_name"],
            "position_name": src.position_name}


@router.delete("/payroll/{scenario_id}/position/{position_id}/", status_code=204)
async def delete_position(
    scenario_id: str,
    position_id: str,
    db: AsyncSession = Depends(get_db),
):
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    pos = await _get_position_or_404(db, scenario_id, position_id)
    await db.execute(
        delete(PayrollConceptEntry).where(PayrollConceptEntry.position_id == position_id)
    )
    await db.delete(pos)
    await db.commit()


@router.put("/payroll/{scenario_id}/position/{position_id}/month/{month}/base-concepts/")
async def update_base_concepts(
    scenario_id: str,
    position_id: str,
    month: int,
    body: BaseConceptsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update manual group-base concepts (6001/6002/6003/6010/6024/6027)."""
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    if month < 1 or month > 12:
        raise ErrorApi(400, "mes.fuera_de_rango")
    pos = await _get_position_or_404(db, scenario_id, position_id)

    # Get scenario year from scenario table
    from app.models.scenario import Scenario
    scenario = await db.get(Scenario, scenario_id)
    year = scenario.year if scenario else 2026

    entry = await _get_or_create_entry(db, scenario_id, pos, month, year)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(entry, field, value)

    # Recompute automatics after manual base change
    rates = await _get_exchange_rates(db, scenario_id)
    tc = get_tc_for_month(rates, month)
    ccss, agu, pp = await _payroll_cfg(db, scenario_id)
    recalculate_entry(entry, pos, month, tc, ccss, agu, params=pp)

    await db.commit()
    return _entry_to_dict(entry)


@router.put("/payroll/{scenario_id}/position/{position_id}/month/{month}/benefit-concepts/")
async def update_benefit_concepts(
    scenario_id: str,
    position_id: str,
    month: int,
    body: BenefitConceptsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update manual benefit concepts (6004/6022-6030)."""
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    if month < 1 or month > 12:
        raise ErrorApi(400, "mes.fuera_de_rango")
    pos = await _get_position_or_404(db, scenario_id, position_id)

    from app.models.scenario import Scenario
    scenario = await db.get(Scenario, scenario_id)
    year = scenario.year if scenario else 2026

    entry = await _get_or_create_entry(db, scenario_id, pos, month, year)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(entry, field, value)
    await db.commit()
    return _entry_to_dict(entry)


@router.get("/payroll/{scenario_id}/dept/{dept_code}/summary/")
async def get_dept_summary(
    scenario_id: str,
    dept_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Aggregated payroll totals for a department × 12 months."""
    result = await db.execute(
        select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id,
            PayrollConceptEntry.dept_code == dept_code,
        )
    )
    entries = result.scalars().all()

    year = entries[0].year if entries else 2026
    summaries = []
    for m in range(1, 13):
        month_entries = [e for e in entries if e.month == m]
        s = summarize_dept(month_entries, dept_code, m, year)
        summaries.append({
            "month": s.month,
            "c6000": float(s.c6000), "c6001": float(s.c6001),
            "c6002": float(s.c6002), "c6003": float(s.c6003),
            "c6010": float(s.c6010), "c6024": float(s.c6024),
            "c6027": float(s.c6027), "base": float(s.base),
            "c6020": float(s.c6020), "c6021": float(s.c6021),
            "c6004": float(s.c6004), "c6022": float(s.c6022),
            "c6023": float(s.c6023), "c6025": float(s.c6025),
            "c6026": float(s.c6026), "c6028": float(s.c6028),
            "c6029": float(s.c6029), "c6030": float(s.c6030),
            "total": float(s.total),
        })
    # Los repartos de PLANILLA (clase 6) de este departamento: cafetería 6025 y
    # salarios reasignados 6000. No están en `monthly` —eso es la planilla
    # propia, la gente que sí está en el departamento— pero el P&L los suma.
    # Van aquí y no en un checkbook: la clase 6 no es gasto operativo ni costo
    # de venta, así que no tiene checkbook donde vivir.
    repartido = await lineas_del_allocation(db, scenario_id, dept_code, "6")

    return {
        "scenario_id": scenario_id, "dept_code": dept_code, "monthly": summaries,
        "allocated": repartido,
        "allocated_annual_total": str(sum(Decimal(r["total"]) for r in repartido)),
    }


@router.get("/payroll/{scenario_id}/summary/")
async def get_scenario_summary(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Aggregated payroll totals across all departments × 12 months."""
    result = await db.execute(
        select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id
        )
    )
    entries = result.scalars().all()

    year = entries[0].year if entries else 2026
    summaries = []
    for m in range(1, 13):
        month_entries = [e for e in entries if e.month == m]
        s = summarize_dept(month_entries, "ALL", m, year)
        summaries.append({
            "month": s.month,
            "base": float(s.base),
            "c6020": float(s.c6020),
            "c6021": float(s.c6021),
            "total": float(s.total),
        })
    return {"scenario_id": scenario_id, "monthly": summaries}


@router.get("/payroll/{scenario_id}/fte-report/")
async def get_fte_report(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
):
    """FTE aggregated by department × 12 months."""
    result = await db.execute(
        select(PayrollPosition).where(PayrollPosition.scenario_id == scenario_id)
    )
    positions = result.scalars().all()
    if not positions:
        return {"scenario_id": scenario_id, "by_dept": {}, "totals": {}}

    report = build_fte_report(list(positions))
    return {
        "scenario_id": scenario_id,
        "by_dept": {
            dept: {str(m): float(fte) for m, fte in months.items()}
            for dept, months in report.by_dept.items()
        },
        "totals": {str(m): float(fte) for m, fte in report.totals.items()},
        "annual_avg": {dept: float(avg) for dept, avg in report.annual_avg.items()},
    }


async def _dept_fte_override(scenario_id: str, db: AsyncSession) -> dict[str, dict[int, float]]:
    """`{dept_code: {month: fte}}` de `actual_dept_fte`, si hay algo cargado.

    Existe para el caso donde el costo es real (vía GL/`PayrollConceptEntry`)
    pero no hay `PayrollPosition` cargada al detalle para ese mes: el FTE
    calculado da 0 aunque el costo sea positivo. Cuando hay una fila acá para
    (dept, month), GANA sobre lo que saldría de sumar posiciones."""
    rows = (await db.execute(
        select(ActualDeptFte).where(ActualDeptFte.scenario_id == scenario_id)
    )).scalars().all()
    out: dict[str, dict[int, float]] = {}
    for r in rows:
        out.setdefault(r.dept_code, {})[r.month] = float(r.fte)
    return out


@router.get("/payroll/{scenario_id}/dept-report/")
async def get_dept_report(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Reporte de planilla por departamento (USD anual): headcount (# posiciones),
    FTE promedio, salario base (S&W) y costo total con cargas. Base de los
    reportes de Headcount / FTE / Salarios por depto."""
    positions = (await db.execute(
        select(PayrollPosition).where(PayrollPosition.scenario_id == scenario_id)
    )).scalars().all()
    entries = (await db.execute(
        select(PayrollConceptEntry).where(PayrollConceptEntry.scenario_id == scenario_id)
    )).scalars().all()
    override = await _dept_fte_override(scenario_id, db)

    depts: dict[str, dict] = {}
    def row(code: str, name: str = "") -> dict:
        return depts.setdefault(code, {
            "dept_code": code, "dept_name": name or code,
            "headcount": 0, "fte_avg": 0.0, "sw_annual": 0.0, "total_annual": 0.0})

    for p in positions:
        if p.dept_code in ALLOC_EXCL_PAYROLL:
            continue  # Employee Dining / Laundry interna: allocation → fuera de planilla
        d = row(p.dept_code, p.dept_name)
        if p.position_code == "GL":
            continue  # posición sintética del GL (actuales): aporta costo, no headcount
        if p.dept_code not in override:
            d["headcount"] += 1
            d["fte_avg"] += sum(float(get_fte(p, m)) for m in range(1, 13)) / 12.0
    for e in entries:
        if e.dept_code in ALLOC_EXCL_PAYROLL:
            continue
        d = row(e.dept_code)
        d["sw_annual"] += float(e.c6000_sw)
        d["total_annual"] += float(total_entry(e))
    # El override reemplaza el FTE del depto entero (no se mezcla mes a mes
    # con lo calculado): o viene de posiciones, o viene de la carga manual.
    for code, meses in override.items():
        d = row(code)
        d["fte_avg"] = sum(meses.get(m, 0.0) for m in range(1, 13)) / 12.0

    rows = sorted(depts.values(), key=lambda r: r["dept_code"])
    totals = {
        "headcount": sum(r["headcount"] for r in rows),
        "fte_avg": round(sum(r["fte_avg"] for r in rows), 2),
        "sw_annual": round(sum(r["sw_annual"] for r in rows), 2),
        "total_annual": round(sum(r["total_annual"] for r in rows), 2),
    }
    for r in rows:
        r["fte_avg"] = round(r["fte_avg"], 2)
        r["sw_annual"] = round(r["sw_annual"], 2)
        r["total_annual"] = round(r["total_annual"], 2)
    return {"scenario_id": scenario_id, "depts": rows, "totals": totals}


@router.get("/payroll/{scenario_id}/dept-report-monthly/")
async def get_dept_report_monthly(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Headcount / FTE / costo por departamento × mes (1..12).

    headcount[m] = # de posiciones reales (no 'GL') con FTE>0 ese mes.
    fte[m]       = suma de FTE del mes (o el override de `actual_dept_fte` si
    ese depto tiene carga manual — ver `_dept_fte_override`). total[m] = suma
    de los 17 conceptos de ese mes. Excluye deptos de allocation (Employee
    Dining / Laundry)."""
    positions = (await db.execute(
        select(PayrollPosition).where(PayrollPosition.scenario_id == scenario_id)
    )).scalars().all()
    entries = (await db.execute(
        select(PayrollConceptEntry).where(PayrollConceptEntry.scenario_id == scenario_id)
    )).scalars().all()
    override = await _dept_fte_override(scenario_id, db)

    depts: dict[str, dict] = {}
    def row(code: str, name: str = "") -> dict:
        return depts.setdefault(code, {
            "dept_code": code, "dept_name": name or code,
            "headcount": [0] * 12, "fte": [0.0] * 12, "total": [0.0] * 12})

    for p in positions:
        if p.dept_code in ALLOC_EXCL_PAYROLL:
            continue
        d = row(p.dept_code, p.dept_name)
        if p.position_code == "GL":
            continue  # sintética del GL: aporta costo (vía entries), no headcount/FTE
        if p.dept_code in override:
            continue  # ese depto lo manda la carga manual, no las posiciones
        for m in range(1, 13):
            f = float(get_fte(p, m))
            if f > 0:
                d["headcount"][m - 1] += 1
                d["fte"][m - 1] += f
    for code, meses in override.items():
        d = row(code)
        for m, f in meses.items():
            d["fte"][m - 1] = f
    for e in entries:
        if e.dept_code in ALLOC_EXCL_PAYROLL:
            continue
        if not (1 <= e.month <= 12):
            continue
        d = row(e.dept_code)
        d["total"][e.month - 1] += float(total_entry(e))

    rows = sorted(depts.values(), key=lambda r: r["dept_code"])
    for r in rows:
        r["fte"] = [round(v, 2) for v in r["fte"]]
        r["total"] = [round(v, 2) for v in r["total"]]
        r["total_annual"] = round(sum(r["total"]), 2)
    totals = {
        "headcount": [sum(r["headcount"][m] for r in rows) for m in range(12)],
        "fte": [round(sum(r["fte"][m] for r in rows), 2) for m in range(12)],
        "total": [round(sum(r["total"][m] for r in rows), 2) for m in range(12)],
        "total_annual": round(sum(r["total_annual"] for r in rows), 2),
    }
    return {"scenario_id": scenario_id, "depts": rows, "totals": totals}


# ── Carga manual/Excel de FTE real por depto (cuando no hay posiciones) ──────

class DeptFteRowIn(BaseModel):
    dept_code: str
    dept_name: str = ""
    fte: float = 0


class DeptFteEntryIn(BaseModel):
    rows: list[DeptFteRowIn]


@router.get("/payroll/{scenario_id}/dept-fte-actuals/{month}/")
async def get_dept_fte_entry(scenario_id: str, month: int, db: AsyncSession = Depends(get_db)):
    """Filas editables para cargar a mano el FTE real de un mes: un depto por
    fila (los que ya tiene el reporte), con el valor guardado si hay."""
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")
    report = await get_dept_report(scenario_id, db)
    existing = {r.dept_code: r for r in (await db.execute(select(ActualDeptFte).where(
        ActualDeptFte.scenario_id == scenario_id, ActualDeptFte.month == month))).scalars().all()}
    rows = [{"dept_code": d["dept_code"], "dept_name": d["dept_name"],
             "fte": float(existing[d["dept_code"]].fte) if d["dept_code"] in existing else 0.0}
            for d in report["depts"]]
    return {"scenario_id": scenario_id, "month": month, "rows": rows}


@router.put("/payroll/{scenario_id}/dept-fte-actuals/{month}/")
async def put_dept_fte_entry(
    scenario_id: str, month: int, body: DeptFteEntryIn, db: AsyncSession = Depends(get_db)
):
    """Guarda (upsert) el FTE real por depto de un mes. Reemplaza solo ese mes
    (los demás quedan intactos → el anual acumula solo)."""
    await candado(db, scenario_id)
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")
    await db.execute(delete(ActualDeptFte).where(
        ActualDeptFte.scenario_id == scenario_id, ActualDeptFte.month == month))
    saved = 0
    for r in body.rows:
        if not r.fte:
            continue  # fila vacía
        db.add(ActualDeptFte(
            scenario_id=scenario_id, dept_code=r.dept_code, dept_name=r.dept_name,
            month=month, fte=r.fte))
        saved += 1
    await db.commit()
    return {"scenario_id": scenario_id, "month": month, "rows_saved": saved}


@router.get("/payroll/{scenario_id}/dept-fte-template/")
async def get_dept_fte_template(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Baja un Excel con un bloque por mes (Enero..Diciembre), un depto por
    fila — mismo departamento que ya muestra el reporte. Los meses que ya
    tienen carga manual salen prellenados; el resto en blanco para completar.
    Se sube entera por `POST .../import-dept-fte/`: reemplaza SOLO los meses
    que trae el archivo."""
    from app.export.dept_fte_excel import export_dept_fte_template
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    report = await get_dept_report(scenario_id, db)
    depts = [(d["dept_code"], d["dept_name"]) for d in report["depts"]]
    existentes = (await db.execute(select(ActualDeptFte).where(
        ActualDeptFte.scenario_id == scenario_id))).scalars().all()
    prellenado: dict[tuple[str, int], float] = {
        (r.dept_code, r.month): float(r.fte) for r in existentes}
    scn_label = f"{scenario.type} {scenario.version} {scenario.year}"
    xlsx = export_dept_fte_template(depts, prellenado, scn_label)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="FTE_Real_{scenario_id[:8]}.xlsx"'},
    )


@router.post("/payroll/{scenario_id}/import-dept-fte/", dependencies=[Depends(registro_de_subida)])
async def import_dept_fte(
    scenario_id: str, file: UploadFile = File(...),
    dry_run: bool = False, db: AsyncSession = Depends(get_db),
):
    """Sube el Excel de FTE real por depto (bloques por mes). Merge por mes:
    reemplaza SOLO los meses presentes en el archivo, preserva los demás."""
    await candado(db, scenario_id)
    from app.importers.dept_fte_importer import parse_dept_fte
    raw = await file.read()
    try:
        flat = parse_dept_fte(raw)
    except Exception as e:  # noqa: BLE001
        raise ErrorApi(422, "archivo.no_se_pudo_leer", detalle=str(e))
    if not flat:
        raise ErrorApi(422, "fte.archivo_sin_bloques")

    months_present = sorted({r["month"] for r in flat})
    preview = {"scenario_id": scenario_id, "months_present": months_present, "rows": len(flat)}
    if dry_run:
        return {"dry_run": True, **preview}

    await db.execute(delete(ActualDeptFte).where(
        ActualDeptFte.scenario_id == scenario_id, ActualDeptFte.month.in_(months_present)))
    for r in flat:
        if not r["fte"]:
            continue
        db.add(ActualDeptFte(
            scenario_id=scenario_id, dept_code=r["dept_code"], dept_name=r["dept_name"],
            month=r["month"], fte=r["fte"]))
    await db.commit()
    return {"dry_run": False, "imported": True, **preview}


_FTE_MONTHS = ["fte_jan", "fte_feb", "fte_mar", "fte_apr", "fte_may", "fte_jun",
               "fte_jul", "fte_aug", "fte_sep", "fte_oct", "fte_nov", "fte_dec"]


class PayrollBulkRow(BaseModel):
    dept_code: str
    dept_name: str = ""
    position_code: str = ""
    position_name: str
    employee_name: str = "VACANTE"
    employee_type: str = "1-Permanente"
    class_code: str = "013"
    category_code: str = "015"
    salary_amount: Decimal = Decimal("0")
    salary_currency: str = "CRC"
    fte_jan: Decimal = Decimal("1.0"); fte_feb: Decimal = Decimal("1.0")
    fte_mar: Decimal = Decimal("1.0"); fte_apr: Decimal = Decimal("1.0")
    fte_may: Decimal = Decimal("1.0"); fte_jun: Decimal = Decimal("1.0")
    fte_jul: Decimal = Decimal("1.0"); fte_aug: Decimal = Decimal("1.0")
    fte_sep: Decimal = Decimal("1.0"); fte_oct: Decimal = Decimal("0.0")
    fte_nov: Decimal = Decimal("1.0"); fte_dec: Decimal = Decimal("1.0")

    @field_validator(*_FTE_MONTHS)
    @classmethod
    def _fte_range(cls, v):
        if v is not None and (v < 0 or v > 1):
            raise ValueError("FTE debe estar entre 0 y 1")
        return v


class SalaryRow(BaseModel):
    dept_code: str
    position_code: str = ""
    position_name: str = ""
    employee_name: str = ""   # distingue personas dentro de la misma posición
    salary_amount: Decimal
    salary_currency: str = "CRC"
    # FTE por mes (opcional). Si se envía, se actualiza la dimensión mensual.
    fte_jan: Optional[Decimal] = None; fte_feb: Optional[Decimal] = None
    fte_mar: Optional[Decimal] = None; fte_apr: Optional[Decimal] = None
    fte_may: Optional[Decimal] = None; fte_jun: Optional[Decimal] = None
    fte_jul: Optional[Decimal] = None; fte_aug: Optional[Decimal] = None
    fte_sep: Optional[Decimal] = None; fte_oct: Optional[Decimal] = None
    fte_nov: Optional[Decimal] = None; fte_dec: Optional[Decimal] = None

    @field_validator(*_FTE_MONTHS)
    @classmethod
    def _fte_range(cls, v):
        # FTE libre entre 0 y 1 (0=no trabaja, 0.25=1/4, 0.5=medio, 1=completo)
        if v is not None and (v < 0 or v > 1):
            raise ValueError("FTE debe estar entre 0 y 1")
        return v


@router.put("/payroll/{scenario_id}/salaries/")
async def update_salaries(
    scenario_id: str,
    rows: list[SalaryRow],
    db: AsyncSession = Depends(get_db),
    idioma: str = Idioma,
):
    """
    Bulk-update salary amount + currency (+ optional monthly FTE) on existing
    positions, matched by (dept_code, position_code) or, if position_code is
    blank, (dept_code, position_name, case-insensitive). Salary upload-file flow.
    """
    from app.models.scenario import Scenario
    escenario = await db.get(Scenario, scenario_id)
    if not escenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    # Una versión enllavada no se puede sobreescribir.
    escenario.assert_editable()
    result = await db.execute(
        select(PayrollPosition).where(PayrollPosition.scenario_id == scenario_id)
    )
    positions = result.scalars().all()

    def emp(p): return (p.employee_name or "").strip().lower()
    def pname(p): return (p.position_name or "").strip().lower()
    # Person-level keys (distinguish N people in the same position by employee_name)
    by_person_code = {(p.dept_code, p.position_code, emp(p)): p for p in positions if p.position_code}
    by_person_name = {(p.dept_code, pname(p), emp(p)): p for p in positions}
    # Position-level fallbacks (when no employee_name given and no duplicates)
    by_code = {(p.dept_code, p.position_code): p for p in positions if p.position_code}
    by_name = {(p.dept_code, pname(p)): p for p in positions}

    updated, unmatched, touched = 0, [], []
    for r in rows:
        emp_l = (r.employee_name or "").strip().lower()
        pos = None
        if emp_l and r.position_code:
            pos = by_person_code.get((r.dept_code, r.position_code, emp_l))
        if pos is None and emp_l and r.position_name:
            pos = by_person_name.get((r.dept_code, r.position_name.strip().lower(), emp_l))
        if pos is None and r.position_code:
            pos = by_code.get((r.dept_code, r.position_code))
        if pos is None and r.position_name:
            pos = by_name.get((r.dept_code, r.position_name.strip().lower()))
        if pos is None:
            unmatched.append({"dept_code": r.dept_code,
                              "position_code": r.position_code,
                              "position_name": r.position_name,
                              "employee_name": r.employee_name})
            continue
        pos.salary_amount = r.salary_amount
        pos.salary_currency = r.salary_currency
        for fk in _FTE_MONTHS:
            val = getattr(r, fk, None)
            if val is not None:
                setattr(pos, fk, val)
        touched.append(pos)
        updated += 1

    # Cambió el salario/FTE → recalcular SW, CCSS y aguinaldo en el acto.
    await db.flush()
    entries = await _recalc_positions(db, scenario_id, touched)
    await db.commit()
    out = {"updated": updated, "unmatched": unmatched, "scenario_id": scenario_id,
           "entries_recalculated": entries}
    if touched and not entries:
        # Sin tipos de cambio no se puede convertir el salario: el dato quedó
        # guardado pero SW/CCSS/aguinaldo siguen con el valor anterior.
        out["aviso"] = t(idioma, "planilla.salarios_sin_recalcular")
    return out


class PositionsAdd(BaseModel):
    dept_code: str
    dept_name: str = ""
    position_name: str
    position_code: str = ""          # vacío = se generan correlativos del depto
    count: int = 1
    salary_amount: Decimal = Decimal("0")
    salary_currency: str = "CRC"


@router.post("/payroll/{scenario_id}/positions/add/", status_code=201)
async def add_positions(
    scenario_id: str,
    body: PositionsAdd,
    db: AsyncSession = Depends(get_db),
):
    """Agrega N personas de una posición SIN tocar el resto de la planilla.

    Existe porque la pantalla agregaba posiciones mandando el roster completo a
    `PUT /bulk/`, y ese endpoint BORRA todas las posiciones antes de recrearlas.
    Como `payroll_concept_entries` cuelga de la posición con ON DELETE CASCADE,
    agregar una persona borraba las horas extra, comisiones, bonos, transporte y
    vivienda DIGITADOS de las otras 129 — y el recálculo solo repone 6000, 6020
    y 6021, así que el resto no volvía. El total bajaba y no había nada que
    dijera por qué.

    Cada persona nace con su propio código correlativo del departamento
    (`0111-06`, `0111-07`…). Si se manda un código explícito y ya está usado, se
    rechaza: el código es la llave de los reportes de planilla y dos personas
    bajo el mismo código salen sumadas en un renglón.
    """
    from app.api.payroll_position_report_api import siguiente_codigo

    await candado(db, scenario_id)
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    if body.count < 1:
        raise ErrorApi(422, "posiciones.cantidad_minima")

    if body.position_code.strip():
        usado = (await db.execute(select(PayrollPosition).where(
            PayrollPosition.scenario_id == scenario_id,
            PayrollPosition.position_code == body.position_code.strip(),
        ))).scalars().first()
        if usado:
            raise ErrorApi(
                409, "posicion.codigo_ya_usado",
                codigo=body.position_code.strip(),
                puesto=usado.position_name, empleado=usado.employee_name)
        if body.count > 1:
            raise ErrorApi(
                422, "posicion.codigo_explicito_una_sola", cantidad=body.count)
        codigos = [body.position_code.strip()]
    else:
        codigos = (await siguiente_codigo(
            scenario_id, dept=body.dept_code, count=body.count, db=db))["codes"]

    creadas = []
    for i, cod in enumerate(codigos, start=1):
        p = PayrollPosition(
            id=str(uuid.uuid4()), scenario_id=scenario_id, hotel_id=scenario.hotel_id,
            dept_code=body.dept_code, dept_name=body.dept_name,
            position_code=cod, position_name=body.position_name,
            employee_name=f"VACANTE {i}" if len(codigos) > 1 else "VACANTE",
            salary_amount=body.salary_amount, salary_currency=body.salary_currency,
            **{f"fte_{m}": Decimal("1.0") for m in
               ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]},
        )
        db.add(p)
        creadas.append(p)
    await db.flush()
    for p in creadas:
        await _estrenar_posicion(db, scenario_id, p, getattr(scenario, "year", 2027))
    await db.commit()
    return {"created": len(creadas), "codes": codigos,
            "ids": [p.id for p in creadas]}


@router.put("/payroll/{scenario_id}/bulk/")
async def bulk_replace_payroll(
    scenario_id: str,
    rows: list[PayrollBulkRow],
    db: AsyncSession = Depends(get_db),
):
    """REEMPLAZA la planilla entera (para la carga desde Excel).

    ⚠️ Borra todas las posiciones y las recrea. Como `payroll_concept_entries`
    cuelga de la posición con ON DELETE CASCADE, esto se lleva TODOS los
    conceptos digitados —horas extra, comisiones, bonos, transporte, vivienda— y
    el recálculo solo repone 6000, 6020 y 6021.

    Es lo correcto cuando la intención es «esta planilla reemplaza a la que
    había». NO lo es para agregar una persona: para eso está
    `POST /payroll/{id}/positions/add/`, que solo inserta.
    """
    from app.models.scenario import Scenario
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    # Una versión enllavada no se puede sobreescribir.
    scenario.assert_editable()
    await db.execute(
        delete(PayrollPosition).where(PayrollPosition.scenario_id == scenario_id)
    )
    await db.flush()
    created = []
    for r in rows:
        p = PayrollPosition(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id, hotel_id=scenario.hotel_id,
            **r.model_dump(),
        )
        db.add(p)
        created.append(p)
    # Reemplazo masivo → generar SW/CCSS/aguinaldo de las posiciones nuevas.
    await db.flush()
    entries = await _recalc_positions(db, scenario_id, created)
    await db.commit()
    return {"imported": len(rows), "scenario_id": scenario_id,
            "entries_recalculated": entries}


@router.post("/payroll/{scenario_id}/import-codificacion/")
async def import_codificacion_endpoint(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
    idioma: str = Idioma,
):
    """
    Import position templates from the Codificacion Planilla Excel.
    Clears existing positions for this scenario before importing.
    """
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    xlsx_path = CODIFICACION_DEFAULT_PATH
    if not xlsx_path.exists():
        raise ErrorApi(404, "codificacion.archivo_no_encontrado", ruta=str(xlsx_path))

    # Clear existing positions (cascades to concept entries)
    await db.execute(
        delete(PayrollPosition).where(PayrollPosition.scenario_id == scenario_id)
    )
    await db.commit()

    positions = import_codificacion(str(xlsx_path), scenario_id, scenario.hotel_id)
    for pos in positions:
        db.add(pos)
    await db.commit()

    return {
        "scenario_id": scenario_id,
        "positions_imported": len(positions),
        "message": t(idioma, "planilla.plantillas_creadas"),
    }


async def _recalc_positions(db: AsyncSession, scenario_id: str,
                            positions: list[PayrollPosition]) -> int:
    """Recalcula SW (6000), CCSS (6020) y aguinaldo (6021) de las posiciones dadas,
    en los 12 meses. Se llama AUTOMÁTICAMENTE al tocar salario/FTE: sin esto el
    salario cambia pero la CCSS y el aguinaldo quedan con el valor viejo y el P&L
    muestra una planilla desactualizada hasta que alguien apriete «Recalcular»."""
    if not positions:
        return 0
    rates = await _get_exchange_rates(db, scenario_id)
    if not rates:
        return 0
    from app.models.scenario import Scenario
    scenario = await db.get(Scenario, scenario_id)
    year = scenario.year if scenario else 2026
    ccss, agu, pp = await _payroll_cfg(db, scenario_id)
    n = 0
    for pos in positions:
        for month in range(1, 13):
            tc = get_tc_for_month(rates, month)
            entry = await _get_or_create_entry(db, scenario_id, pos, month, year)
            recalculate_entry(entry, pos, month, tc, ccss, agu, params=pp)
            n += 1
    return n


@router.post("/scenarios/{scenario_id}/recalculate/")
async def recalculate_scenario(
    scenario_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Recalculate all automatic payroll fields (6000/6020/6021) for every
    position × month in the scenario using the stored exchange rates.
    Manual fields are preserved.
    """
    rates = await _get_exchange_rates(db, scenario_id)
    if not rates:
        raise ErrorApi(400, "tc.sin_tipos_de_cambio")

    pos_result = await db.execute(
        select(PayrollPosition).where(PayrollPosition.scenario_id == scenario_id)
    )
    positions = pos_result.scalars().all()

    from app.models.scenario import Scenario
    scenario = await db.get(Scenario, scenario_id)
    year = scenario.year if scenario else 2026

    ccss, agu, pp = await _payroll_cfg(db, scenario_id)
    updated = 0
    for pos in positions:
        for month in range(1, 13):
            tc = get_tc_for_month(rates, month)
            entry = await _get_or_create_entry(db, scenario_id, pos, month, year)
            recalculate_entry(entry, pos, month, tc, ccss, agu, params=pp)
            updated += 1

    await db.commit()
    return {
        "scenario_id": scenario_id,
        "positions": len(positions),
        "entries_updated": updated,
        "status": "recalculated",
    }


# ── Parámetros de planilla por escenario (CCSS, aguinaldo) ────────────────────

class PayrollParamsBody(BaseModel):
    ccss_rate: Decimal
    aguinaldo_divisor: Decimal
    # Drivers de los conceptos que se calculan por regla. Opcionales: si no vienen,
    # se deja lo que ya estaba (una pantalla vieja no borra lo que no conoce).
    overtime_pct: Optional[Decimal] = None
    bonus_pct: Optional[Decimal] = None
    vacaciones_rate: Optional[Decimal] = None
    severance_annual_rate: Optional[Decimal] = None
    cafeteria_daily_crc: Optional[Decimal] = None
    transport_monthly_crc: Optional[Decimal] = None
    housing_monthly_crc: Optional[Decimal] = None
    other_monthly_crc: Optional[Decimal] = None
    ins_annual_crc: Optional[Decimal] = None
    working_days: Optional[list[int]] = None
    holidays: Optional[list[int]] = None
    days_off: Optional[list[int]] = None
    calendar_days: Optional[list[int]] = None


DRIVERS_NUM = ["overtime_pct", "bonus_pct", "vacaciones_rate", "severance_annual_rate",
               "cafeteria_daily_crc", "transport_monthly_crc", "housing_monthly_crc",
               "other_monthly_crc", "ins_annual_crc"]
DRIVERS_CAL = ["working_days", "holidays", "days_off", "calendar_days"]


@router.get("/scenarios/{scenario_id}/payroll/params/")
async def get_payroll_params(scenario_id: str, db: AsyncSession = Depends(get_db)):
    pp = (await db.execute(
        select(PayrollParams).where(PayrollParams.scenario_id == scenario_id)
    )).scalar_one_or_none()
    import json as _json
    out = {
        "scenario_id": scenario_id,
        "ccss_rate": str(pp.ccss_rate if pp else DEFAULT_CCSS_RATE),
        "aguinaldo_divisor": str(pp.aguinaldo_divisor if pp else DEFAULT_AGUINALDO_DIVISOR),
        "seeded": pp is None,
    }
    for c in DRIVERS_NUM:
        out[c] = str(getattr(pp, c, 0) if pp else 0)
    for c in DRIVERS_CAL:
        crudo = getattr(pp, c, None) if pp else None
        try:
            out[c] = _json.loads(crudo) if crudo else [0] * 12
        except ValueError:
            out[c] = [0] * 12
    return out


@router.put("/scenarios/{scenario_id}/payroll/params/")
async def put_payroll_params(
    scenario_id: str, body: PayrollParamsBody, db: AsyncSession = Depends(get_db),
    idioma: str = Idioma,
):
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    pp = (await db.execute(
        select(PayrollParams).where(PayrollParams.scenario_id == scenario_id)
    )).scalar_one_or_none()
    if pp is None:
        pp = PayrollParams(scenario_id=scenario_id)
        db.add(pp)
    import json as _json
    pp.ccss_rate = body.ccss_rate
    pp.aguinaldo_divisor = body.aguinaldo_divisor
    for c in DRIVERS_NUM:
        v = getattr(body, c)
        if v is not None:
            setattr(pp, c, v)
    for c in DRIVERS_CAL:
        v = getattr(body, c)
        if v is not None:
            if len(v) != 12:
                raise ErrorApi(422, "driver.doce_valores", driver=c)
            setattr(pp, c, _json.dumps([int(x) for x in v]))
    await db.commit()
    return {"saved": True, "scenario_id": scenario_id,
            "ccss_rate": str(pp.ccss_rate), "aguinaldo_divisor": str(pp.aguinaldo_divisor),
            "aviso": t(idioma, "planilla.drivers_guardados_falta_recalcular")}


@router.get("/payroll/{scenario_id}/export/excel/")
async def export_payroll_excel(scenario_id: str, db: AsyncSession = Depends(get_db)):
    from app.models.scenario import Scenario
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")

    positions = (await db.execute(
        select(PayrollPosition)
        .where(PayrollPosition.scenario_id == scenario_id)
        .order_by(PayrollPosition.dept_code, PayrollPosition.position_code)
    )).scalars().all()

    FTE_ATTRS = ["fte_jan","fte_feb","fte_mar","fte_apr","fte_may","fte_jun",
                 "fte_jul","fte_aug","fte_sep","fte_oct","fte_nov","fte_dec"]

    by_dept: dict[str, list[dict]] = {}
    for p in positions:
        by_dept.setdefault(p.dept_code, []).append({
            "dept_name": p.dept_name,
            "position_code": p.position_code,
            "position_name": p.position_name,
            "employee_name": p.employee_name,
            "employee_type": p.employee_type,
            "salary_amount": float(p.salary_amount or 0),
            "salary_currency": p.salary_currency,
            **{attr: float(getattr(p, attr) or 0) for attr in FTE_ATTRS},
        })

    # ⚠️ El TC de CADA mes, no solo enero — «SW Anual USD*» tiene que sumar
    # los doce con el TC de cada uno, igual que `calc_sw` en el motor. Con TC
    # móvil, un solo mes no representa al año.
    rates = await _get_exchange_rates(db, scenario_id)
    tc_por_mes = [float(get_tc_for_month(rates, m)) if rates else 640.0
                 for m in range(1, 13)]
    tc_usd = tc_por_mes[0]

    label = f"{scenario.hotel_id} {scenario.version}"
    xlsx = export_payroll_to_excel(by_dept, label, scenario.year, tc_usd=tc_usd,
                                   dept_names=await nombres_de_depto(db),
                                   tc_por_mes=tc_por_mes)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="payroll_{scenario_id}.xlsx"'},
    )


@router.post("/payroll/{scenario_id}/import/excel/", dependencies=[Depends(registro_de_subida)])
async def import_payroll_excel(
    scenario_id: str,
    file: UploadFile = File(...),
    replace: bool = True,
    db: AsyncSession = Depends(get_db),
    idioma: str = Idioma,
):
    from app.models.scenario import Scenario
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(409, str(e))

    rows = import_payroll_from_excel(await file.read())
    if not rows:
        raise ErrorApi(422, "planilla.sin_posiciones_validas")

    if replace:
        affected = {r["dept_code"] for r in rows}
        for dc in affected:
            # delete concept entries first (FK), then positions
            pos_ids = (await db.execute(
                select(PayrollPosition.id)
                .where(PayrollPosition.scenario_id == scenario_id,
                       PayrollPosition.dept_code == dc)
            )).scalars().all()
            for pid in pos_ids:
                await db.execute(
                    delete(PayrollConceptEntry).where(PayrollConceptEntry.position_id == pid)
                )
            await db.execute(
                delete(PayrollPosition).where(
                    PayrollPosition.scenario_id == scenario_id,
                    PayrollPosition.dept_code == dc,
                )
            )
        await db.flush()

    FTE_ATTRS = ["fte_jan","fte_feb","fte_mar","fte_apr","fte_may","fte_jun",
                 "fte_jul","fte_aug","fte_sep","fte_oct","fte_nov","fte_dec"]

    for r in rows:
        db.add(PayrollPosition(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            hotel_id=scenario.hotel_id,
            dept_code=r["dept_code"],
            dept_name=r.get("dept_name", ""),
            position_code=r.get("position_code", ""),
            position_name=r["position_name"],
            employee_name=r.get("employee_name", "VACANTE"),
            employee_type=r.get("employee_type", "1-Permanente"),
            salary_amount=r.get("salary_amount", Decimal("0")),
            salary_currency=r.get("salary_currency", "CRC"),
            **{attr: r.get(attr, Decimal("0")) for attr in FTE_ATTRS},
        ))

    await db.commit()
    return {"imported": len(rows), "scenario_id": scenario_id,
            "note": t(idioma, "planilla.recalcular_despues_del_import")}


# ── Reparto de beneficios ─────────────────────────────────────────────────────
# Un solo mecanismo para llenar cualquier cuenta 60xx de beneficio: se declara de
# dónde sale la plata, cómo se reparte y a qué nivel. Reemplaza los tres caminos
# sueltos que había (allocation de cafetería, per diem en planilla, reparto del INS).
from app.models.benefit_allocation_config import (   # noqa: E402
    BenefitAllocationConfig, CUENTAS_BENEFICIO, ORIGENES, BASES, NIVELES,
)


class RepartoBody(BaseModel):
    account: str
    label: str = ""
    source_type: str = "MONTO"      # MONTO | DEPTO
    source_dept: str = ""
    amount_crc: Decimal = Decimal("0")
    basis: str = "FTE"              # FTE | HEADCOUNT
    level: str = "POSITION"         # POSITION | DEPT
    active: bool = True


@router.get("/scenarios/{scenario_id}/payroll/repartos/")
async def listar_repartos(scenario_id: str, db: AsyncSession = Depends(get_db)):
    filas = (await db.execute(
        select(BenefitAllocationConfig)
        .where(BenefitAllocationConfig.scenario_id == scenario_id)
        .order_by(BenefitAllocationConfig.account)
    )).scalars().all()
    return {
        "scenario_id": scenario_id,
        "cuentas": [{"account": k, "nombre": v} for k, v in sorted(CUENTAS_BENEFICIO.items())],
        "repartos": [{
            "id": r.id, "account": r.account,
            "nombre": CUENTAS_BENEFICIO.get(r.account, r.account),
            "label": r.label, "source_type": r.source_type, "source_dept": r.source_dept,
            "amount_crc": str(r.amount_crc), "basis": r.basis, "level": r.level,
            "active": r.active,
        } for r in filas],
    }


@router.put("/scenarios/{scenario_id}/payroll/repartos/")
async def guardar_repartos(
    scenario_id: str, filas: list[RepartoBody], db: AsyncSession = Depends(get_db),
    idioma: str = Idioma,
):
    """Reemplaza la configuración de repartos del escenario."""
    # Una versión enllavada no se puede editar.
    await candado(db, scenario_id)

    malas = [f.account for f in filas if f.account not in CUENTAS_BENEFICIO]
    if malas:
        raise ErrorApi(422, "repartos.cuentas_no_beneficio",
                       cuentas=", ".join(malas))
    for campo, validos in (("source_type", ORIGENES), ("basis", BASES), ("level", NIVELES)):
        raras = {getattr(f, campo) for f in filas} - set(validos)
        if raras:
            raise ErrorApi(422, "repartos.campo_invalido", campo=campo,
                           valores=", ".join(sorted(raras)),
                           validos=", ".join(validos))
    repetidas = [a for a in {f.account for f in filas}
                 if [f.account for f in filas].count(a) > 1]
    if repetidas:
        raise ErrorApi(422, "repartos.cuenta_repetida",
                       cuentas=", ".join(sorted(set(repetidas))))
    sin_dept = [f.account for f in filas
                if f.source_type == "DEPTO" and not f.source_dept.strip()]
    if sin_dept:
        raise ErrorApi(422, "repartos.falta_departamento_origen",
                       cuentas=", ".join(sin_dept))

    await db.execute(delete(BenefitAllocationConfig).where(
        BenefitAllocationConfig.scenario_id == scenario_id))
    await db.flush()
    for f in filas:
        db.add(BenefitAllocationConfig(
            scenario_id=scenario_id, account=f.account,
            label=f.label or CUENTAS_BENEFICIO.get(f.account, ""),
            source_type=f.source_type, source_dept=f.source_dept.strip(),
            amount_crc=f.amount_crc, basis=f.basis, level=f.level, active=f.active,
        ))
    await db.commit()
    return {"saved": len(filas), "scenario_id": scenario_id,
            "aviso": t(idioma, "planilla.recalcular_para_que_apliquen")}


# ── Excel de conceptos manuales, por departamento y posición ──────────────────
from app.export.beneficios_excel import (            # noqa: E402
    export_beneficios, import_beneficios, CONCEPTOS_MANUALES,
)


async def _posiciones_ordenadas(db, scenario_id: str):
    return (await db.execute(
        select(PayrollPosition)
        .where(PayrollPosition.scenario_id == scenario_id)
        .order_by(PayrollPosition.dept_code, PayrollPosition.position_name)
    )).scalars().all()


@router.get("/payroll/{scenario_id}/beneficios/excel/")
async def bajar_beneficios_excel(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Baja el Excel con lo que hay cargado hoy, una hoja por concepto."""
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    posiciones = await _posiciones_ordenadas(db, scenario_id)
    entradas = (await db.execute(
        select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id)
    )).scalars().all()
    por_pos: dict[tuple[str, int], PayrollConceptEntry] = {
        (e.position_id, e.month): e for e in entradas}

    datos: dict[str, list[dict]] = {}
    for columna, _, _ in CONCEPTOS_MANUALES:
        filas = []
        for p in posiciones:
            meses = []
            for m in range(1, 13):
                e = por_pos.get((p.id, m))
                meses.append(getattr(e, columna, Decimal("0")) or Decimal("0")
                             if e else Decimal("0"))
            filas.append({
                "dept_code": p.dept_code or "", "dept_name": p.dept_name or "",
                "position_code": p.position_code or "",
                "position_name": p.position_name or "",
                "employee_name": p.employee_name or "",
                "meses": meses,
            })
        datos[columna] = filas

    xlsx = export_beneficios(datos, f"{scenario.hotel_id} {scenario.version}",
                             getattr(scenario, "year", 2027))
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="beneficios_{scenario.version}.xlsx"'},
    )


@router.post("/payroll/{scenario_id}/beneficios/excel/", dependencies=[Depends(registro_de_subida)])
async def subir_beneficios_excel(
    scenario_id: str, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    idioma: str = Idioma,
):
    """Sube el Excel llenado. Las filas se amarran por Depto + Codigo de puesto."""
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    # Una versión enllavada no se puede editar.
    await candado(db, scenario_id)

    datos, avisos = import_beneficios(await file.read())
    posiciones = await _posiciones_ordenadas(db, scenario_id)
    por_llave = {((p.dept_code or "").strip(), (p.position_code or "").strip()): p
                 for p in posiciones}

    ccss, agu, pp = await _payroll_cfg(db, scenario_id)
    rates = await _get_exchange_rates(db, scenario_id)
    year = getattr(scenario, "year", 2027)

    # Un driver con tasa PISA lo manual: hay que decirlo, no dejar que el owner
    # suba un monto y luego no lo vea.
    driver_de = {"c6001_overtime": "overtime_pct", "c6027_incentive_bonus": "bonus_pct",
                 "c6002_day_off": "days_off",
                 "c6026_severance": "severance_annual_rate",
                 "c6029_transport": "transport_monthly_crc",
                 "c6028_housing": "housing_monthly_crc",
                 "c6030_other": "other_monthly_crc"}

    escritas = 0
    sin_match: list[str] = []
    tocadas: set[str] = set()
    for columna, filas in datos.items():
        if not filas:
            continue
        if pp is not None and getattr(pp, driver_de.get(columna, ""), None):
            avisos.append(t(idioma, "planilla.driver_pisa_lo_manual", columna=columna))
        for f in filas:
            pos = por_llave.get((f["dept_code"], f["position_code"]))
            if pos is None:
                sin_match.append(f"{f['dept_code']}/{f['position_code']}")
                continue
            tocadas.add(pos.id)
            for m in range(1, 13):
                entry = await _get_or_create_entry(db, scenario_id, pos, m, year)
                setattr(entry, columna, f["meses"][m - 1])
                escritas += 1

    # La CCSS y el aguinaldo tienen que moverse: horas extra, bono, comisiones y
    # vacaciones tomadas ENTRAN a la BASE.
    for pid in tocadas:
        pos = next((p for p in posiciones if p.id == pid), None)
        if pos is None:
            continue
        for m in range(1, 13):
            tc = get_tc_for_month(rates, m) if rates else Decimal("1")
            entry = await _get_or_create_entry(db, scenario_id, pos, m, year)
            recalculate_entry(entry, pos, m, tc, ccss, agu, params=pp)

    await db.commit()
    if sin_match:
        avisos.append(t(idioma, "planilla.filas_sin_puesto",
                        n=len(sin_match),
                        puestos=", ".join(sorted(set(sin_match))[:8])
                        + (" …" if len(set(sin_match)) > 8 else "")))
    return {
        "celdas_escritas": escritas,
        "posiciones_tocadas": len(tocadas),
        "conceptos": [c for c, f in datos.items() if f],
        "avisos": avisos,
        "aviso": t(idioma, "planilla.recalcular_para_verlo"),
    }
