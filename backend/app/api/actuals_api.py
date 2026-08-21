"""
Actuals API — recorded ACTUAL totals per account × dept × month.

Actuals do not use the budget checkbooks. They are loaded as plain totals
(one row per account_code × dept_code, 12 monthly columns) and the P&L engine
reads them directly for ACTUAL scenarios.

GET    /api/actuals/{scenario_id}/        list entries
PUT    /api/actuals/{scenario_id}/        bulk upsert rows
DELETE /api/actuals/{scenario_id}/        clear all entries for the scenario

The Excel importer (meses en columnas, códigos USALI por fila) will parse the
user's file and feed this same bulk-upsert path — pending the real file format.
"""
from decimal import Decimal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete

from app.errores import ErrorApi
from app.db import get_session
from app.models.scenario import Scenario, ScenarioLockedError
from app.models.actual_entry import ActualEntry
from app.models.actual_pl_line import ActualPLLine
from app.importers.actual_workbook_loader import load_actuals_workbook
from app.hotel_actual import HOTEL_ID

router = APIRouter(tags=["actuals"])

MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"]


class ActualRow(BaseModel):
    dept_code: str = ""
    account_code: str
    account_name: str = ""
    # Punto de venta dentro del departamento. Vacío en todo menos A&B.
    outlet: str = ""
    jan: Decimal = Decimal("0")
    feb: Decimal = Decimal("0")
    mar: Decimal = Decimal("0")
    apr: Decimal = Decimal("0")
    may: Decimal = Decimal("0")
    jun: Decimal = Decimal("0")
    jul: Decimal = Decimal("0")
    aug: Decimal = Decimal("0")
    sep: Decimal = Decimal("0")
    oct: Decimal = Decimal("0")
    nov: Decimal = Decimal("0")
    dec: Decimal = Decimal("0")


async def _get_scenario_or_404(session, scenario_id: str) -> Scenario:
    s = await session.get(Scenario, scenario_id)
    if not s:
        raise ErrorApi(404, "escenario.no_encontrado")
    return s


def _to_dict(e: ActualEntry) -> dict:
    d = {"dept_code": e.dept_code, "account_code": e.account_code,
         "account_name": e.account_name, "outlet": e.outlet or ""}
    for m in MONTH_ATTRS:
        d[m] = str(getattr(e, m))
    return d


@router.get("/actuals/{scenario_id}/")
async def list_actuals(scenario_id: str):
    async with get_session() as session:
        await _get_scenario_or_404(session, scenario_id)
        rows = (await session.execute(
            select(ActualEntry).where(ActualEntry.scenario_id == scenario_id)
            .order_by(ActualEntry.account_code, ActualEntry.dept_code)
        )).scalars().all()
        return [_to_dict(e) for e in rows]


@router.put("/actuals/{scenario_id}/")
async def upsert_actuals(scenario_id: str, rows: list[ActualRow], replace: bool = False):
    """
    Upsert actual rows. With replace=true, clears the scenario's actuals first
    (the importer uses replace=true for a clean re-load).
    """
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        try:
            scenario.assert_editable()
        except ScenarioLockedError as e:
            raise HTTPException(409, str(e))

        if replace:
            await session.execute(
                delete(ActualEntry).where(ActualEntry.scenario_id == scenario_id)
            )
            await session.flush()
            existing = {}
        else:
            cur = (await session.execute(
                select(ActualEntry).where(ActualEntry.scenario_id == scenario_id)
            )).scalars().all()
            existing = {(e.dept_code, e.account_code, e.outlet or ""): e for e in cur}

        for row in rows:
            # El outlet va en la llave: el GL de A&B trae la MISMA cuenta una vez
            # por punto de venta. Sin él, las cuatro filas comparten llave y el
            # `setattr` de abajo —que ASIGNA, no acumula— deja viva solo la
            # última: la plata de los otros tres outlets se perdería sin error.
            key = (row.dept_code, row.account_code, getattr(row, "outlet", "") or "")
            entry = existing.get(key)
            if entry is None:
                entry = ActualEntry(
                    scenario_id=scenario_id, hotel_id=scenario.hotel_id,
                    dept_code=row.dept_code, account_code=row.account_code,
                    account_name=row.account_name, outlet=key[2],
                )
                session.add(entry)
                existing[key] = entry
            else:
                entry.account_name = row.account_name or entry.account_name
            for m in MONTH_ATTRS:
                setattr(entry, m, getattr(row, m))

        await session.commit()
    return {"ok": True, "upserted": len(rows), "replaced": replace}


class WorkbookImportPayload(BaseModel):
    path: str                      # server-side path to the .xlsx
    hotel_id: str = HOTEL_ID
    sheet: str = "Budget 2025W"
    blocks: list[str] | None = None  # optional subset of version blocks


@router.post("/actuals/import-workbook/")
async def import_workbook(payload: WorkbookImportPayload):
    """
    Parse the CWL working workbook and load every version block into its
    scenario's account-level detail (ActualEntry), creating scenarios as needed.
    """
    import os
    if not os.path.exists(payload.path):
        raise ErrorApi(404, "archivo.no_encontrado", archivo=payload.path)
    async with get_session() as session:
        summary = await load_actuals_workbook(
            session, payload.path, payload.hotel_id, payload.sheet, payload.blocks
        )
    return {"ok": True, "scenarios": summary}


@router.delete("/actuals/{scenario_id}/")
async def clear_actuals(scenario_id: str):
    async with get_session() as session:
        # Una versión enllavada no se puede borrar.
        (await _get_scenario_or_404(session, scenario_id)).assert_editable()
        await session.execute(
            delete(ActualEntry).where(ActualEntry.scenario_id == scenario_id)
        )
        await session.commit()
    return {"ok": True}


# ─── Line-level actuals (macro P&L, no account detail) ────────────────────────
class ActualPLLinePayload(BaseModel):
    line_code: str
    amount_usd: Decimal = Decimal("0")


@router.get("/actuals/{scenario_id}/pl-lines/")
async def list_actual_pl_lines(scenario_id: str):
    """Line-level actuals grouped by month: {month: {line_code: amount}}."""
    async with get_session() as session:
        await _get_scenario_or_404(session, scenario_id)
        rows = (await session.execute(
            select(ActualPLLine).where(ActualPLLine.scenario_id == scenario_id)
            .order_by(ActualPLLine.month, ActualPLLine.line_code)
        )).scalars().all()
    out: dict[int, dict[str, str]] = {}
    for r in rows:
        out.setdefault(r.month, {})[r.line_code] = str(r.amount_usd)
    return out


@router.put("/actuals/{scenario_id}/pl-lines/{month}/")
async def upsert_actual_pl_lines(
    scenario_id: str, month: int, lines: list[ActualPLLinePayload], replace: bool = True
):
    """Upsert line-level actuals for one month. replace=true clears the month first."""
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")
    async with get_session() as session:
        scenario = await _get_scenario_or_404(session, scenario_id)
        try:
            scenario.assert_editable()
        except ScenarioLockedError as e:
            raise HTTPException(409, str(e))

        if replace:
            await session.execute(
                delete(ActualPLLine).where(
                    ActualPLLine.scenario_id == scenario_id,
                    ActualPLLine.month == month,
                )
            )
            await session.flush()
            existing = {}
        else:
            cur = (await session.execute(
                select(ActualPLLine).where(
                    ActualPLLine.scenario_id == scenario_id,
                    ActualPLLine.month == month,
                )
            )).scalars().all()
            existing = {r.line_code: r for r in cur}

        for ln in lines:
            row = existing.get(ln.line_code)
            if row is None:
                session.add(ActualPLLine(
                    scenario_id=scenario_id, month=month,
                    line_code=ln.line_code, amount_usd=ln.amount_usd,
                ))
                existing[ln.line_code] = True
            else:
                row.amount_usd = ln.amount_usd

        await session.commit()
    return {"ok": True, "month": month, "upserted": len(lines)}
