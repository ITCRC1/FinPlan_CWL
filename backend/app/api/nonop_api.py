"""
Non-operating (below-GOP / owner) checkbook API.

The "mini checkbooks" of the below-GOP section: each 8xxx account (rent,
insurance, capital, financial, depreciation, other) is broken into a few named
detail lines that sum to the account total, which feeds the matching P&L line
through the same DB-driven mapping engine as the operating checkbooks.

Management fees (revenue × %) and income tax (EBT × %) are NOT here — they are
computed drivers (see pl_engine.calculate_budget_pl_from_mapping).

Endpoints:
  GET    /api/nonop/{scenario_id}/                 all entries, grouped by account
  PUT    /api/nonop/{scenario_id}/bulk/            bulk replace (parsed client-side)
  PUT    /api/nonop/{scenario_id}/entry/{id}/      update one detail line's months
  DELETE /api/nonop/{scenario_id}/entry/{id}/
  GET    /api/nonop/{scenario_id}/summary/         monthly + annual totals per account
"""
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.importers.registro_dep import registro_de_subida
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.db import get_db
from app.models.scenario import Scenario
from app.models.nonop_entry import NonOpEntry
from app.export.nonop_excel import export_nonop_to_excel, import_nonop_from_excel

router = APIRouter(tags=["nonop"])

MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"]


# ── Schemas ───────────────────────────────────────────────────────────────────
class NonOpBulkRow(BaseModel):
    report_line_code: str
    account_code: str = ""
    account_name: str = ""
    detail_code: str = ""
    detail_desc: str = ""
    jan: Decimal = Decimal("0"); feb: Decimal = Decimal("0")
    mar: Decimal = Decimal("0"); apr: Decimal = Decimal("0")
    may: Decimal = Decimal("0"); jun: Decimal = Decimal("0")
    jul: Decimal = Decimal("0"); aug: Decimal = Decimal("0")
    sep: Decimal = Decimal("0"); oct: Decimal = Decimal("0")
    nov: Decimal = Decimal("0"); dec: Decimal = Decimal("0")


class EntryUpdate(BaseModel):
    jan: Optional[Decimal] = None; feb: Optional[Decimal] = None
    mar: Optional[Decimal] = None; apr: Optional[Decimal] = None
    may: Optional[Decimal] = None; jun: Optional[Decimal] = None
    jul: Optional[Decimal] = None; aug: Optional[Decimal] = None
    sep: Optional[Decimal] = None; oct: Optional[Decimal] = None
    nov: Optional[Decimal] = None; dec: Optional[Decimal] = None
    detail_desc: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _get_scenario_or_404(scenario_id: str, db: AsyncSession) -> Scenario:
    s = await db.get(Scenario, scenario_id)
    if not s:
        raise ErrorApi(404, "escenario.no_encontrado")
    return s


def _entry_dict(e: NonOpEntry) -> dict:
    return {
        "id": e.id, "report_line_code": e.report_line_code,
        "account_code": e.account_code, "account_name": e.account_name,
        "detail_code": e.detail_code, "detail_desc": e.detail_desc,
        **{mk: str(getattr(e, mk)) for mk in MONTH_ATTRS},
        "annual": str(sum((getattr(e, mk) or Decimal("0")) for mk in MONTH_ATTRS)),
    }


def _group_by_line(entries: list[NonOpEntry]) -> list[dict]:
    """Group detail lines by report_line_code (the P&L line they feed)."""
    groups: dict[str, dict] = {}
    for e in entries:
        g = groups.setdefault(e.report_line_code, {
            "report_line_code": e.report_line_code, "account_code": e.account_code,
            "lines": [], "monthly_totals": {mk: Decimal("0") for mk in MONTH_ATTRS},
        })
        g["lines"].append(_entry_dict(e))
        for mk in MONTH_ATTRS:
            g["monthly_totals"][mk] += (getattr(e, mk) or Decimal("0"))
    out = []
    for g in groups.values():
        g["annual_total"] = str(sum(g["monthly_totals"].values()))
        g["monthly_totals"] = {mk: str(v) for mk, v in g["monthly_totals"].items()}
        out.append(g)
    return sorted(out, key=lambda x: x["report_line_code"])


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("/nonop/{scenario_id}/")
async def list_nonop(scenario_id: str, db: AsyncSession = Depends(get_db)):
    await _get_scenario_or_404(scenario_id, db)
    entries = (await db.execute(
        select(NonOpEntry)
        .where(NonOpEntry.scenario_id == scenario_id)
        .order_by(NonOpEntry.report_line_code, NonOpEntry.detail_code)
    )).scalars().all()
    return {"scenario_id": scenario_id, "lines": _group_by_line(list(entries))}


@router.post("/nonop/{scenario_id}/bulk/")
async def bulk_replace_nonop(
    scenario_id: str,
    rows: list[NonOpBulkRow],
    db: AsyncSession = Depends(get_db),
):
    """Bulk replace all below-GOP detail entries for a scenario.

    Valida el `report_line_code` contra el reporte: estas filas NO pasan por el
    mapeo de cuentas, siembran la línea del P&L directamente. Un código que no
    exista se descartaba en silencio y ese monto no llegaba al P&L.
    """
    scenario = await _get_scenario_or_404(scenario_id, db)
    scenario.assert_editable()

    from app.engine.recalculate import load_report_line_config
    validas = {r["line_code"] for r in await load_report_line_config(db)}
    if validas:
        invalidas = sorted({(r.report_line_code or "").strip() for r in rows
                            if (r.report_line_code or "").strip() not in validas})
        if invalidas:
            raise ErrorApi(422, "nonop.lineas_inexistentes",
                           lineas=", ".join(invalidas))

    await db.execute(delete(NonOpEntry).where(NonOpEntry.scenario_id == scenario_id))
    await db.flush()
    for r in rows:
        db.add(NonOpEntry(
            scenario_id=scenario_id, hotel_id=scenario.hotel_id,
            report_line_code=r.report_line_code,
            account_code=r.account_code, account_name=r.account_name,
            detail_code=r.detail_code, detail_desc=r.detail_desc,
            **{mk: getattr(r, mk) for mk in MONTH_ATTRS},
        ))
    await db.commit()
    return {"imported": len(rows), "scenario_id": scenario_id}


@router.put("/nonop/{scenario_id}/entry/{entry_id}/")
async def update_nonop_entry(
    scenario_id: str, entry_id: str, body: EntryUpdate,
    db: AsyncSession = Depends(get_db),
):
    scenario = await _get_scenario_or_404(scenario_id, db)
    scenario.assert_editable()
    entry = await db.get(NonOpEntry, entry_id)
    if not entry or entry.scenario_id != scenario_id:
        raise ErrorApi(404, "renglon.no_encontrado")
    for mk in MONTH_ATTRS:
        v = getattr(body, mk)
        if v is not None:
            setattr(entry, mk, v)
    if body.detail_desc is not None:
        entry.detail_desc = body.detail_desc
    await db.commit()
    return _entry_dict(entry)


@router.delete("/nonop/{scenario_id}/entry/{entry_id}/")
async def delete_nonop_entry(
    scenario_id: str, entry_id: str, db: AsyncSession = Depends(get_db),
):
    scenario = await _get_scenario_or_404(scenario_id, db)
    scenario.assert_editable()
    entry = await db.get(NonOpEntry, entry_id)
    if not entry or entry.scenario_id != scenario_id:
        raise ErrorApi(404, "renglon.no_encontrado")
    await db.delete(entry)
    await db.commit()
    return {"deleted": entry_id}


@router.get("/nonop/{scenario_id}/export/excel/")
async def export_nonop_excel(scenario_id: str, db: AsyncSession = Depends(get_db)):
    scenario = await _get_scenario_or_404(scenario_id, db)
    entries = (await db.execute(
        select(NonOpEntry)
        .where(NonOpEntry.scenario_id == scenario_id)
        .order_by(NonOpEntry.report_line_code, NonOpEntry.detail_code)
    )).scalars().all()

    by_line: dict[str, list[dict]] = {}
    for e in entries:
        by_line.setdefault(e.report_line_code, []).append({
            "detail_code": e.detail_code, "account_code": e.account_code,
            "detail_desc": e.detail_desc,
            **{mk: float(getattr(e, mk) or 0) for mk in MONTH_ATTRS},
        })

    label = f"{scenario.hotel_id} {scenario.version}"
    xlsx = export_nonop_to_excel(by_line, label, getattr(scenario, "year", 2026))
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="nonop_{scenario_id}.xlsx"'},
    )


@router.post("/nonop/{scenario_id}/import/excel/", dependencies=[Depends(registro_de_subida)])
async def import_nonop_excel(
    scenario_id: str,
    file: UploadFile = File(...),
    replace: bool = True,
    db: AsyncSession = Depends(get_db),
):
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    rows = import_nonop_from_excel(await file.read())
    if not rows:
        raise ErrorApi(422, "nonop.sin_filas_validas")

    if replace:
        affected = {r["report_line_code"] for r in rows}
        for lc in affected:
            await db.execute(
                delete(NonOpEntry).where(
                    NonOpEntry.scenario_id == scenario_id,
                    NonOpEntry.report_line_code == lc,
                )
            )
        await db.flush()

    # El archivo vuelve como se subió: se baja, se corrige y se sube. Lo que la
    # plantilla trae se RESPETA, no se regenera.
    #
    # Antes el correlativo se recalculaba en cada importación, así que el código
    # de una fila cambiaba según en qué posición hubiera quedado en el Excel —
    # y `account_code` ni se leía, así que el viaje de ida y vuelta dejaba en
    # blanco la cuenta 8xxx de toda línea below-GOP. Ninguna de las dos cosas
    # daba error: la línea del P&L la decide `report_line_code`, no la cuenta.
    counter: dict[str, int] = {}
    for r in rows:
        key = r["report_line_code"]
        counter[key] = counter.get(key, 0) + 1
        # Si la fila trae código, es el suyo. El correlativo es solo para las
        # filas nuevas, que el usuario agregó sin código.
        detail_code = (r.get("detail_code") or "").strip() or str(counter[key]).zfill(3)
        db.add(NonOpEntry(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            hotel_id=scenario.hotel_id,
            report_line_code=key,
            detail_code=detail_code,
            account_code=(r.get("account_code") or "").strip(),
            detail_desc=r.get("detail_desc", ""),
            **{mk: r.get(mk, Decimal("0")) for mk in MONTH_ATTRS},
        ))

    await db.commit()
    return {"imported": len(rows), "scenario_id": scenario_id}


@router.get("/nonop/{scenario_id}/summary/")
async def nonop_summary(scenario_id: str, db: AsyncSession = Depends(get_db)):
    await _get_scenario_or_404(scenario_id, db)
    entries = (await db.execute(
        select(NonOpEntry).where(NonOpEntry.scenario_id == scenario_id)
    )).scalars().all()
    lines = _group_by_line(list(entries))
    grand = {mk: Decimal("0") for mk in MONTH_ATTRS}
    for a in lines:
        for mk in MONTH_ATTRS:
            grand[mk] += Decimal(a["monthly_totals"][mk])
    return {
        "scenario_id": scenario_id,
        "lines": lines,
        "monthly_totals": {mk: str(v) for mk, v in grand.items()},
        "annual_total": str(sum(grand.values())),
    }
