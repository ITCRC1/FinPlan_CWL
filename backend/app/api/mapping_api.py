"""
Admin endpoints for report_line_config and account_mapping.

GET  /mapping/lines/                   → all report lines (optionally filtered by report_id)
GET  /mapping/accounts/                → all account mappings
POST /mapping/accounts/                → create new mapping rule
PUT  /mapping/accounts/{id}/           → update a rule (activate/deactivate/edit)
DELETE /mapping/accounts/{id}/         → delete a rule
GET  /mapping/unmapped/                → GL accounts in actual_entries with no mapping rule
POST /mapping/reload/                  → re-load from Excel file (admin only)
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.auth import get_current_admin
from app.db import get_db
from app.models.mapping import AccountMapping, ReportLineConfig
from app.hotel_actual import HOTEL_ID

router = APIRouter(prefix="/mapping", tags=["mapping"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ReportLineOut(BaseModel):
    id: str
    report_id: str
    display_order: int
    line_code: str
    section: str
    line_name: str
    line_type: str
    parent_line_code: Optional[str]
    calculation_logic: Optional[str]
    format_hint: Optional[str]
    active: bool

    class Config:
        from_attributes = True


class AccountMappingOut(BaseModel):
    id: str
    active_status: str
    report_id: str
    report_line_code: str
    report_line_name: Optional[str]
    report_section: Optional[str]
    display_order: Optional[int]
    source_origin: Optional[str]
    source_department: Optional[str]
    dept_code: Optional[str]
    account_code: str
    account_name_example: Optional[str]
    financial_nature: str
    rollup_operator: str
    sign_rule: Optional[str]
    notes: Optional[str]

    class Config:
        from_attributes = True


class AccountMappingCreate(BaseModel):
    active_status: str = "YES"
    report_id: str = "P&L_DETAIL_OWNERS"
    report_line_code: str
    report_line_name: Optional[str] = None
    report_section: Optional[str] = None
    display_order: Optional[int] = None
    source_origin: Optional[str] = None
    source_department: Optional[str] = None
    dept_code: Optional[str] = None
    account_code: str
    account_name_example: Optional[str] = None
    financial_nature: str = "Expense"
    rollup_operator: str = "SUM"
    sign_rule: Optional[str] = None
    notes: Optional[str] = None


class AccountMappingUpdate(BaseModel):
    active_status: Optional[str] = None
    report_line_code: Optional[str] = None
    source_origin: Optional[str] = None
    source_department: Optional[str] = None
    dept_code: Optional[str] = None
    account_code: Optional[str] = None
    account_name_example: Optional[str] = None
    financial_nature: Optional[str] = None
    rollup_operator: Optional[str] = None
    sign_rule: Optional[str] = None
    notes: Optional[str] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/lines/", response_model=list[ReportLineOut])
async def get_report_lines(
    report_id: str = "P&L_DETAIL_OWNERS",
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ReportLineConfig)
        .where(ReportLineConfig.report_id == report_id)
        .order_by(ReportLineConfig.display_order)
    )
    return result.scalars().all()


@router.get("/accounts/", response_model=list[AccountMappingOut])
async def get_account_mappings(
    report_id: str = "P&L_DETAIL_OWNERS",
    report_line_code: Optional[str] = None,
    active_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    q = select(AccountMapping).where(AccountMapping.report_id == report_id)
    if report_line_code:
        q = q.where(AccountMapping.report_line_code == report_line_code)
    if active_only:
        q = q.where(AccountMapping.active_status == "YES")
    q = q.order_by(AccountMapping.display_order, AccountMapping.source_department, AccountMapping.account_code)
    result = await db.execute(q)
    return result.scalars().all()


def _ensure_dept_code(obj: AccountMapping) -> None:
    """El P&L rutea por dept_code. Si la regla trae el nombre del depto pero no el
    código, se deriva — si no, la cuenta cae en la línea del primer depto (misruteo)."""
    if not (obj.dept_code or "").strip() and (obj.source_department or "").strip():
        from app.importers.gl_detail_importer import dept_code_from_name
        obj.dept_code = dept_code_from_name(obj.source_department.strip()) or None


# ⚠️ **Escribir el mapeo exige ADMIN** (owner, 2026-08-20: «mover tabs a admin
# para proteger la información»). Medido ese día: los cinco endpoints de
# escritura de esta pantalla no pedían nada más que sesión, y acá **mover UNA
# cuenta de $6.500 re-expresó 102 líneas del reporte** — y `foto_pl_totales`
# habría dicho «IDÉNTICO».
#
# Leer sigue abierto a propósito: entender por qué una cuenta cae donde cae es
# trabajo de todos los días, y esconderlo obligaría a preguntar en vez de mirar.
@router.post("/accounts/", response_model=AccountMappingOut, status_code=201, dependencies=[Depends(get_current_admin)])
async def create_account_mapping(
    body: AccountMappingCreate,
    db: AsyncSession = Depends(get_db),
):
    obj = AccountMapping(id=str(uuid.uuid4()), **body.model_dump())
    _ensure_dept_code(obj)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.put("/accounts/{mapping_id}/", response_model=AccountMappingOut, dependencies=[Depends(get_current_admin)])
async def update_account_mapping(
    mapping_id: str,
    body: AccountMappingUpdate,
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(AccountMapping, mapping_id)
    if not obj:
        raise ErrorApi(404, "mapeo.no_encontrado")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(obj, field, val)
    _ensure_dept_code(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/accounts/{mapping_id}/", status_code=204, dependencies=[Depends(get_current_admin)])
async def delete_account_mapping(
    mapping_id: str,
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(AccountMapping, mapping_id)
    if not obj:
        raise ErrorApi(404, "mapeo.no_encontrado")
    await db.delete(obj)
    await db.commit()


@router.get("/unmapped/")
async def get_unmapped_accounts(
    hotel_id: str = HOTEL_ID,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns GL (dept_code, account_code) combinations that exist in actual_entries
    but have no active row in account_mapping. These are accounts that won't appear
    in the P&L report.
    """
    sql = text("""
        SELECT DISTINCT
            ae.dept_code,
            ae.account_code,
            ae.account_name,
            SUM(ae.jan + ae.feb + ae.mar + ae.apr + ae.may + ae.jun +
                ae.jul + ae.aug + ae.sep + ae.oct + ae.nov + ae.dec) AS total_activity
        FROM actual_entries ae
        LEFT JOIN account_mapping am
            ON am.account_code = ae.account_code
            AND am.active_status = 'YES'
        WHERE ae.hotel_id = :hotel_id
          AND am.id IS NULL
        GROUP BY ae.dept_code, ae.account_code, ae.account_name
        HAVING SUM(ae.jan + ae.feb + ae.mar + ae.apr + ae.may + ae.jun +
                   ae.jul + ae.aug + ae.sep + ae.oct + ae.nov + ae.dec) != 0
        ORDER BY total_activity DESC
    """)
    rows = (await db.execute(sql, {"hotel_id": hotel_id})).fetchall()
    return [
        {
            "dept_code": r.dept_code,
            "account_code": r.account_code,
            "account_name": r.account_name,
            "total_activity": float(r.total_activity or 0),
        }
        for r in rows
    ]


@router.post("/reload/", dependencies=[Depends(get_current_admin)])
async def reload_mapping_from_excel(
    file_path: str,
    db: AsyncSession = Depends(get_db),
):
    """Re-load mapping from an Excel file on the server. Admin only."""
    from pathlib import Path
    from app.importers.mapping_loader import load_mapping_workbook

    if not Path(file_path).exists():
        raise ErrorApi(400, "archivo.no_encontrado", archivo=file_path)

    result = await load_mapping_workbook(db, file_path)
    return result


# ── Bulk load (used by local loader script via HTTP) ──────────────────────────

class ReportLineIn(BaseModel):
    report_id: str
    display_order: int
    line_code: str
    section: str
    line_name: str
    line_type: str
    parent_line_code: Optional[str] = None
    calculation_logic: Optional[str] = None
    format_hint: Optional[str] = None
    active: bool = True


class AccountMappingIn(BaseModel):
    active_status: str = "YES"
    report_id: str
    report_line_code: str
    report_line_name: Optional[str] = None
    report_section: Optional[str] = None
    display_order: Optional[int] = None
    source_origin: Optional[str] = None
    source_department: Optional[str] = None
    dept_code: Optional[str] = None
    account_code: str
    account_name_example: Optional[str] = None
    financial_nature: str
    rollup_operator: str = "SUM"
    sign_rule: Optional[str] = None
    notes: Optional[str] = None


class BulkLoadBody(BaseModel):
    report_lines: list[ReportLineIn] = []
    account_mappings: list[AccountMappingIn] = []
    replace: bool = True   # if True, delete existing rows first


@router.post("/bulk-load/", dependencies=[Depends(get_current_admin)])
async def bulk_load_mapping(
    body: BulkLoadBody,
    db: AsyncSession = Depends(get_db),
):
    """
    Load report_line_config + account_mapping in one JSON call.
    Used by local scripts that can't connect to Postgres directly.
    """
    report_ids = {r.report_id for r in body.report_lines} | {m.report_id for m in body.account_mappings}

    if body.replace:
        for rid in report_ids:
            await db.execute(delete(ReportLineConfig).where(ReportLineConfig.report_id == rid))
            await db.execute(delete(AccountMapping).where(AccountMapping.report_id == rid))
        await db.flush()

    for r in body.report_lines:
        stmt = pg_insert(ReportLineConfig).values(id=str(uuid.uuid4()), **r.model_dump())
        stmt = stmt.on_conflict_do_nothing(constraint="uq_report_line_code")
        await db.execute(stmt)

    mapping_loaded = 0
    for m in body.account_mappings:
        if not m.account_code or not m.report_line_code:
            continue
        stmt = pg_insert(AccountMapping).values(id=str(uuid.uuid4()), **m.model_dump())
        stmt = stmt.on_conflict_do_nothing(constraint="uq_account_mapping")
        await db.execute(stmt)
        mapping_loaded += 1

    await db.commit()
    return {
        "report_lines_loaded": len(body.report_lines),
        "mappings_loaded": mapping_loaded,
    }
