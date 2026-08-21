"""
API de cuentas contables (catálogo USALI).

Endpoints:
  GET  /api/accounts/                lista con filtros
  GET  /api/accounts/{code_full}/    detalle de cuenta
  POST /api/import/catalog/          importa Excel del catálogo
  POST /api/import/payroll-catalog/  importa Excel del catálogo de planilla
  GET  /api/payroll-catalog/         lista del catálogo de planilla
"""
import os
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from app.db import get_db
from app.errores import ErrorApi
from app.models.account import Account
from app.models.payroll_catalog import PayrollAccount
from app.importers.catalog_importer import import_catalog
from app.importers.payroll_catalog_importer import import_payroll_catalog

router = APIRouter()

DATA_DIR = os.getenv("DATA_DIR", "C:/FinPlan_CWL")


# ─── Catálogo de cuentas ───────────────────────────────────────────────────

@router.get("/accounts/")
async def list_accounts(
    seg1: Optional[str] = Query(None, description="Filtrar por clase (4000, 6000, 9000...)"),
    seg2: Optional[str] = Query(None, description="Filtrar por departamento (0110, 0120...)"),
    tipo: Optional[str] = Query(None, description="Tipo: I, G, T"),
    acepta_mov: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Account)
    if seg1:
        stmt = stmt.where(Account.seg1 == seg1)
    if seg2:
        stmt = stmt.where(Account.seg2 == seg2)
    if tipo:
        stmt = stmt.where(Account.tipo == tipo)
    if acepta_mov is not None:
        stmt = stmt.where(Account.acepta_mov == acepta_mov)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    stmt = stmt.offset(skip).limit(limit).order_by(Account.code_full)
    result = await db.execute(stmt)
    accounts = result.scalars().all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": [
            {
                "code_full": a.code_full,
                "seg1": a.seg1,
                "seg2": a.seg2,
                "descripcion": a.descripcion,
                "tipo": a.tipo,
                "estado": a.estado,
                "acepta_mov": a.acepta_mov,
            }
            for a in accounts
        ],
    }


@router.get("/accounts/{code_full:path}")
async def get_account(code_full: str, db: AsyncSession = Depends(get_db)):
    acc = await db.get(Account, code_full)
    if not acc:
        raise ErrorApi(404, "cuenta.no_encontrada", cuenta=code_full)
    return {
        "code_full": acc.code_full,
        "seg1": acc.seg1, "seg2": acc.seg2, "seg3": acc.seg3,
        "seg4": acc.seg4, "seg5": acc.seg5, "seg6": acc.seg6, "seg7": acc.seg7,
        "descripcion": acc.descripcion,
        "tipo": acc.tipo,
        "estado": acc.estado,
        "acepta_mov": acc.acepta_mov,
        "usa_cc": acc.usa_cc,
        "aplica_diferencial": acc.aplica_diferencial,
    }


@router.get("/accounts/stats/summary")
async def accounts_summary(db: AsyncSession = Depends(get_db)):
    """Totales por tipo y seg1 — útil para verificar la importación."""
    by_tipo = await db.execute(
        select(Account.tipo, func.count()).group_by(Account.tipo)
    )
    by_seg1 = await db.execute(
        select(Account.seg1, func.count()).group_by(Account.seg1).order_by(Account.seg1)
    )
    total = (await db.execute(select(func.count()).select_from(Account))).scalar()

    return {
        "total": total,
        "by_tipo": dict(by_tipo.all()),
        "by_seg1": dict(by_seg1.all()),
    }


# ─── Importadores ─────────────────────────────────────────────────────────

@router.post("/import/catalog/")
async def run_import_catalog(
    truncate: bool = Query(False, description="Borrar todo antes de importar"),
    db: AsyncSession = Depends(get_db),
):
    """Importa el catálogo de cuentas desde el Excel en DATA_DIR."""
    try:
        result = await import_catalog(db, DATA_DIR, truncate=truncate)
        return {"status": "ok", **result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/payroll-catalog/")
async def run_import_payroll_catalog(
    truncate: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Importa el catálogo de planilla desde el Excel en DATA_DIR."""
    try:
        result = await import_payroll_catalog(db, DATA_DIR, truncate=truncate)
        return {"status": "ok", **result}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Catálogo de planilla ──────────────────────────────────────────────────

@router.get("/payroll-catalog/")
async def list_payroll_catalog(
    nivel1: Optional[str] = Query(None, description="Concepto (6000, 6021...)"),
    nivel2: Optional[str] = Query(None, description="Departamento (0111, 0120...)"),
    acepta_mov: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PayrollAccount)
    if nivel1:
        stmt = stmt.where(PayrollAccount.nivel1 == nivel1)
    if nivel2:
        stmt = stmt.where(PayrollAccount.nivel2 == nivel2)
    if acepta_mov is not None:
        stmt = stmt.where(PayrollAccount.acepta_mov == acepta_mov)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar()

    stmt = stmt.offset(skip).limit(limit).order_by(PayrollAccount.code_full)
    result = await db.execute(stmt)
    accounts = result.scalars().all()

    return {
        "total": total,
        "items": [
            {
                "code_full": a.code_full,
                "nivel1": a.nivel1,
                "nivel2": a.nivel2,
                "nivel3": a.nivel3,
                "nivel4": a.nivel4,
                "nivel5": a.nivel5,
                "descripcion": a.descripcion,
                "concepto_nombre": a.concepto_nombre,
                "dept_nombre": a.dept_nombre,
                "posicion_nombre": a.posicion_nombre,
            }
            for a in accounts
        ],
    }
