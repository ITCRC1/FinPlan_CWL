"""
OPEX API — Phase 6 + Fase 10 (Excel export/import).

Endpoints:
  GET  /api/opex/{scenario_id}/export/excel/        download .xlsx template
  POST /api/opex/{scenario_id}/import/excel/        upload filled .xlsx
  POST /api/opex/{scenario_id}/import/              import all OPEX files from base_dir
  POST /api/opex/{scenario_id}/import-file/         import a single file (body: {key})
  GET  /api/opex/{scenario_id}/depts/               list distinct dept_codes
  GET  /api/opex/{scenario_id}/dept/{dept_code}/    all entries for a dept (grouped by account)
  PUT  /api/opex/{scenario_id}/entry/{entry_id}/    update monthly amounts
  DELETE /api/opex/{scenario_id}/entry/{entry_id}/
  GET  /api/opex/{scenario_id}/summary/             monthly totals per dept
  GET  /api/opex/{scenario_id}/dept/{dept_code}/summary/  monthly totals for one dept
"""
import os
import traceback
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.importers.registro_dep import registro_de_subida
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.errores import ErrorApi
from app.models.scenario import Scenario
from app.models.opex_entry import OpexEntry
from app.importers.opex_importer import import_opex_for_scenario, import_single_opex_file, OPEX_FILE_MAP
from app.importers.gl_detail_importer import ALLOC_EXCL_OPEX
from app.api._nombres_de_depto import nombres_de_depto
from app.export.opex_excel import export_opex_to_excel, import_opex_from_excel
from app.api._allocated import lineas_del_allocation

router = APIRouter(tags=["opex"])

OPEX_BASE_DIR = Path(os.getenv("DATA_DIR", "C:/FinPlan_CWL"))
MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"]


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class EntryUpdate(BaseModel):
    jan: Optional[Decimal] = None; feb: Optional[Decimal] = None
    mar: Optional[Decimal] = None; apr: Optional[Decimal] = None
    may: Optional[Decimal] = None; jun: Optional[Decimal] = None
    jul: Optional[Decimal] = None; aug: Optional[Decimal] = None
    sep: Optional[Decimal] = None; oct: Optional[Decimal] = None
    nov: Optional[Decimal] = None; dec: Optional[Decimal] = None
    detail_desc: Optional[str] = None
    currency: Optional[str] = None
    crc_jan: Optional[Decimal] = None
    crc_feb: Optional[Decimal] = None
    crc_mar: Optional[Decimal] = None
    crc_apr: Optional[Decimal] = None
    crc_may: Optional[Decimal] = None
    crc_jun: Optional[Decimal] = None
    crc_jul: Optional[Decimal] = None
    crc_aug: Optional[Decimal] = None
    crc_sep: Optional[Decimal] = None
    crc_oct: Optional[Decimal] = None
    crc_nov: Optional[Decimal] = None
    crc_dec: Optional[Decimal] = None


class ImportFileBody(BaseModel):
    key: str          # one of the keys in OPEX_FILE_MAP, e.g. 'F_B', 'ROOMS'
    dept_override: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_scenario_or_404(scenario_id: str, db: AsyncSession) -> Scenario:
    s = await db.get(Scenario, scenario_id)
    if not s:
        raise ErrorApi(404, "escenario.no_encontrado")
    return s


def _entry_to_dict(e: OpexEntry) -> dict:
    return {
        "id": e.id,
        "scenario_id": e.scenario_id,
        "dept_code": e.dept_code,
        "account_code": e.account_code,
        "account_name": e.account_name,
        "detail_code": e.detail_code,
        "detail_desc": e.detail_desc,
        "months": {m: str(e.get_month(i + 1)) for i, m in enumerate(MONTH_ATTRS)},
        "annual_total": str(sum(e.get_month(m) for m in range(1, 13))),
        # Moneda de la línea: en CRC los colones son el dato maestro y `months`
        # trae el dólar DERIVADO con el TC de cada mes (mig 077).
        "currency": e.currency or "USD",
        "crc_months": {m: str(getattr(e, f"crc_{m}") or 0) for m in MONTH_ATTRS},
        "crc_annual": str(sum(e.get_crc(m) for m in range(1, 13))),
    }


def _group_by_account(entries: list[OpexEntry]) -> list[dict]:
    """Group detail lines by account_code and return a nested structure."""
    by_account: dict[str, dict] = {}
    for e in entries:
        if e.account_code not in by_account:
            by_account[e.account_code] = {
                "account_code": e.account_code,
                "account_name": e.account_name,
                "lines": [],
            }
        by_account[e.account_code]["lines"].append(_entry_to_dict(e))

    result = []
    for acct in by_account.values():
        # compute account subtotal per month
        lines = acct["lines"]
        monthly_totals = {}
        for mk in MONTH_ATTRS:
            monthly_totals[mk] = str(sum(
                Decimal(ln["months"][mk]) for ln in lines
            ))
        acct["monthly_totals"] = monthly_totals
        acct["annual_total"] = str(sum(Decimal(v) for v in monthly_totals.values()))
        result.append(acct)

    return sorted(result, key=lambda a: a["account_code"])


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/opex/{scenario_id}/import/")
async def import_all_opex(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """
    Import all OPEX checkbook files for this scenario.
    Clears existing opex_entries for this scenario first.
    """
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    await db.execute(
        delete(OpexEntry).where(OpexEntry.scenario_id == scenario_id)
    )
    await db.flush()

    entries = import_opex_for_scenario(scenario_id, scenario.hotel_id, OPEX_BASE_DIR)
    for e in entries:
        db.add(e)

    await db.commit()
    return {"imported": len(entries), "scenario_id": scenario_id}


@router.post("/opex/{scenario_id}/import-file/")
async def import_one_opex_file(
    scenario_id: str,
    body: ImportFileBody,
    db: AsyncSession = Depends(get_db),
):
    """Import (or re-import) a single OPEX department file."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    if body.key not in OPEX_FILE_MAP:
        # `llave` y no `clave`: `clave` es el segundo argumento de ErrorApi y
        # pasarlo por nombre lo duplica — TypeError, o sea 500 en vez del 422.
        raise ErrorApi(422, "opex.clave_de_archivo_desconocida",
                       llave=body.key, validas=list(OPEX_FILE_MAP))

    filename, default_dept = OPEX_FILE_MAP[body.key]
    filepath = OPEX_BASE_DIR / filename
    if not filepath.exists():
        raise ErrorApi(404, "opex.archivo_no_encontrado", archivo=filename)

    # Remove existing entries from this file's dept(s) first
    entries = import_single_opex_file(
        filepath, scenario_id, scenario.hotel_id,
        dept_override=body.dept_override or default_dept,
    )
    if entries:
        # Remove existing entries for these (dept_code, account_code) combos
        dept_codes = list({e.dept_code for e in entries})
        for dc in dept_codes:
            await db.execute(
                delete(OpexEntry).where(
                    OpexEntry.scenario_id == scenario_id,
                    OpexEntry.dept_code == dc,
                )
            )
        await db.flush()
        for e in entries:
            db.add(e)

    await db.commit()
    return {"imported": len(entries), "key": body.key}


class OpexBulkRow(BaseModel):
    dept_code: str
    account_code: str
    account_name: str = ""
    detail_code: str = ""
    detail_desc: str = ""
    # Moneda de la línea. En CRC el dato maestro son los colones y el dólar de
    # cada mes lo deriva el recálculo con el TC de ese mes (mig 077).
    currency: str = "USD"
    crc_jan: Decimal = Decimal("0")
    crc_feb: Decimal = Decimal("0")
    crc_mar: Decimal = Decimal("0")
    crc_apr: Decimal = Decimal("0")
    crc_may: Decimal = Decimal("0")
    crc_jun: Decimal = Decimal("0")
    crc_jul: Decimal = Decimal("0")
    crc_aug: Decimal = Decimal("0")
    crc_sep: Decimal = Decimal("0")
    crc_oct: Decimal = Decimal("0")
    crc_nov: Decimal = Decimal("0")
    crc_dec: Decimal = Decimal("0")
    jan: Decimal = Decimal("0"); feb: Decimal = Decimal("0")
    mar: Decimal = Decimal("0"); apr: Decimal = Decimal("0")
    may: Decimal = Decimal("0"); jun: Decimal = Decimal("0")
    jul: Decimal = Decimal("0"); aug: Decimal = Decimal("0")
    sep: Decimal = Decimal("0"); oct: Decimal = Decimal("0")
    nov: Decimal = Decimal("0"); dec: Decimal = Decimal("0")


@router.put("/opex/{scenario_id}/bulk/")
async def bulk_replace_opex(
    scenario_id: str,
    rows: list[OpexBulkRow],
    db: AsyncSession = Depends(get_db),
):
    """Bulk replace all OPEX detail entries for a scenario (parsed client-side)."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    # Una version enllavada no se puede sobreescribir.
    scenario.assert_editable()
    await db.execute(delete(OpexEntry).where(OpexEntry.scenario_id == scenario_id))
    await db.flush()
    for r in rows:
        db.add(OpexEntry(
            scenario_id=scenario_id, hotel_id=scenario.hotel_id,
            dept_code=r.dept_code, account_code=r.account_code,
            account_name=r.account_name, detail_code=r.detail_code,
            detail_desc=r.detail_desc,
            # ── La moneda y los colones se ESCRIBEN ──────────────────────────
            # `OpexBulkRow` los declara desde la mig 077, pero el INSERT no los
            # copiaba: la fila entraba siempre en dólares y con los colones en
            # cero. Y como este endpoint BORRA todo el escenario antes de
            # escribir, un viaje redondo —bajo, corrijo, subo, que es la norma
            # de trabajo— dejaba la línea en colones marcada como USD y sin su
            # dato maestro. No revienta: los dólares que venían en el archivo
            # quedan, así que el P&L cuadra consigo mismo hasta que se mueve el
            # tipo de cambio y esa línea ya no acompaña.
            currency=(r.currency or "USD").upper(),
            **{mk: getattr(r, mk) for mk in MONTH_ATTRS},
            **{f"crc_{mk}": getattr(r, f"crc_{mk}") for mk in MONTH_ATTRS},
        ))
    # Igual que la carga por Excel: los dólares de una línea CRC se derivan con
    # el TC de cada mes, para que no se vea en cero hasta que alguien recalcule.
    await db.flush()
    await _derivar_importadas(db, scenario_id)
    await db.commit()
    return {"imported": len(rows), "scenario_id": scenario_id}


# ── Excel export / import (Fase 10) ──────────────────────────────────────────

@router.get("/opex/{scenario_id}/export/excel/")
async def export_opex_excel(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Download all OPEX entries as a formatted .xlsx (one sheet per dept)."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(
        select(OpexEntry)
        .where(OpexEntry.scenario_id == scenario_id)
        .order_by(OpexEntry.dept_code, OpexEntry.account_code, OpexEntry.detail_code)
    )
    entries = q.scalars().all()

    # Group by dept
    by_dept: dict[str, list[dict]] = {}
    for e in entries:
        by_dept.setdefault(e.dept_code, []).append({
            "account_code": e.account_code,
            "account_name": e.account_name,
            "detail_desc":  e.detail_desc,
            "detail_code":  e.detail_code,
            **{mk: float(e.get_month(i + 1)) for i, mk in enumerate(MONTH_ATTRS)},
            # La moneda y los colones viajan al Excel: sin esto, bajarlo y volver
            # a subirlo borraria la marca de colones y la linea volveria a dolares.
            "currency": e.currency or "USD",
            **{f"crc_{mk}": float(getattr(e, f"crc_{mk}") or 0) for mk in MONTH_ATTRS},
        })

    label = f"{scenario.type.title()} {scenario.year} · {scenario.version}"
    try:
        xlsx_bytes = export_opex_to_excel(by_dept, label, scenario.year,
                                          dept_names=await nombres_de_depto(db))
    except Exception as exc:
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}\n\n{tb}")

    filename = f"OPEX_{scenario.year}_{scenario.version}.xlsx"
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/opex/{scenario_id}/import/excel/", dependencies=[Depends(registro_de_subida)])
async def import_opex_excel(
    scenario_id: str,
    file: UploadFile = File(...),
    replace: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a filled OPEX .xlsx (generated by the export endpoint).
    replace=True (default): clears existing entries for the affected depts before inserting.
    """
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    file_bytes = await file.read()
    rows = import_opex_from_excel(file_bytes)
    if not rows:
        raise ErrorApi(422, "opex.sin_filas_validas")

    # Collect affected depts
    affected_depts = {r["dept_code"] for r in rows}

    if replace:
        for dept in affected_depts:
            await db.execute(
                delete(OpexEntry).where(
                    OpexEntry.scenario_id == scenario_id,
                    OpexEntry.dept_code == dept,
                )
            )
        await db.flush()

    # El archivo vuelve como se subio: lo que la plantilla trae se RESPETA. El
    # correlativo es solo para las filas NUEVAS, que el usuario agrego sin
    # codigo. Antes se recalculaba siempre, asi que reordenar el Excel le
    # cambiaba el `#` a una fila que nadie habia tocado.
    detail_counter: dict[tuple, int] = {}
    for r in rows:
        key = (r["dept_code"], r["account_code"])
        detail_counter[key] = detail_counter.get(key, 0) + 1
        detail_code = (r.get("detail_code") or "").strip() or str(detail_counter[key]).zfill(3)

        db.add(OpexEntry(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            hotel_id=scenario.hotel_id,
            dept_code=r["dept_code"],
            account_code=r["account_code"],
            account_name=r["account_name"],
            detail_code=detail_code,
            detail_desc=r["detail_desc"],
            # `.get` y no `r[mk]`: una fila en COLONES trae sus montos en crc_* y
            # no en jan..dec. Con acceso directo esto lanzaba KeyError y el
            # navegador mostraba «Failed to fetch» sin decir por que.
            currency=(r.get("currency") or "USD").upper(),
            **{mk: r.get(mk, Decimal("0")) for mk in MONTH_ATTRS},
            **{f"crc_{mk}": r.get(f"crc_{mk}", Decimal("0")) for mk in MONTH_ATTRS},
        ))

    await db.flush()
    await _derivar_importadas(db, scenario_id)
    await db.commit()
    return {
        "imported": len(rows),
        "depts": sorted(affected_depts),
        "scenario_id": scenario_id,
    }


class AddLinesBody(BaseModel):
    account_code: str
    account_name: str = ""
    count: int = 10


@router.post("/opex/{scenario_id}/dept/{dept_code}/add-lines/")
async def add_blank_lines(
    scenario_id: str,
    dept_code: str,
    body: AddLinesBody,
    db: AsyncSession = Depends(get_db),
):
    """Append N blank detail lines to an account in a dept."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Find the current max detail_code for this (scenario, dept, account)
    q = await db.execute(
        select(OpexEntry.detail_code)
        .where(
            OpexEntry.scenario_id == scenario_id,
            OpexEntry.dept_code == dept_code,
            OpexEntry.account_code == body.account_code,
        )
    )
    existing_codes = [row[0] for row in q.all()]
    max_seq = 0
    for code in existing_codes:
        try:
            max_seq = max(max_seq, int(code))
        except ValueError:
            pass

    added = []
    for i in range(body.count):
        new_code = str(max_seq + i + 1).zfill(3)
        entry = OpexEntry(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            hotel_id=scenario.hotel_id,
            dept_code=dept_code,
            account_code=body.account_code,
            account_name=body.account_name,
            detail_code=new_code,
            detail_desc="",
        )
        db.add(entry)
        added.append(new_code)

    await db.commit()
    return {"added": len(added), "dept_code": dept_code, "account_code": body.account_code}


#: El catalogo de arranque de OPEX ya no vive aca: es la semilla
#: `seed_data/<HOTEL_ID>/opex_accounts.json`. Estaba escrito a mano en este
#: archivo y este endpoint se lo servia a cualquier propiedad con la tabla
#: vacia — Amarena habria abierto sus departamentos con las 27 cuentas de
#: Corcovado, sin error y sin aviso.
def _catalogo_de_arranque() -> list[tuple[str, str]] | None:
    """Las cuentas con que nace un departamento en ESTA propiedad.

    `None` —no una lista vacia— si la propiedad no trae semilla: quien llama
    tiene que pedir las cuentas explicitamente en vez de recibir las de otro.
    """
    from app.seed_data import semilla_cruda
    d = semilla_cruda("opex_accounts")
    if not d:
        return None
    return [(str(c["code"]), c["name"]) for c in d["cuentas"]]


class SeedAccount(BaseModel):
    code: str
    name: str


class SeedBody(BaseModel):
    dept_codes: list[str]
    skip_existing: bool = True
    accounts: list[SeedAccount] | None = None  # None = catalogo de arranque de la propiedad


@router.post("/opex/{scenario_id}/seed-accounts/")
async def seed_opex_accounts(
    scenario_id: str,
    body: SeedBody,
    db: AsyncSession = Depends(get_db),
):
    """
    Create one blank entry per account for each dept_code.
    Pass 'accounts' to use a custom list; omit to use this property's starter
    catalog (`seed_data/<HOTEL_ID>/opex_accounts.json`). A property without that
    file MUST pass 'accounts': it does not inherit another hotel's chart.
    If skip_existing=True (default), accounts already present in that dept are skipped.
    """
    arranque = None if body.accounts else _catalogo_de_arranque()
    if not body.accounts and arranque is None:
        raise ErrorApi(400, "opex.sin_catalogo_de_arranque")
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    created = 0
    skipped = 0

    for dept_code in body.dept_codes:
        # Get existing account_codes for this dept
        q = await db.execute(
            select(OpexEntry.account_code)
            .where(OpexEntry.scenario_id == scenario_id, OpexEntry.dept_code == dept_code)
            .distinct()
        )
        existing_accounts = {str(row[0]) for row in q.all()}

        catalog = [(a.code, a.name) for a in body.accounts] if body.accounts else arranque
        for acct_code, acct_name in catalog:
            acct_str = str(acct_code)
            if body.skip_existing and acct_str in existing_accounts:
                skipped += 1
                continue
            entry = OpexEntry(
                id=str(uuid.uuid4()),
                scenario_id=scenario_id,
                hotel_id=scenario.hotel_id,
                dept_code=dept_code,
                account_code=acct_str,
                account_name=acct_name,
                detail_code="001",
                detail_desc="",
            )
            db.add(entry)
            created += 1

    await db.commit()
    return {
        "created": created,
        "skipped": skipped,
        "dept_codes": body.dept_codes,
    }


@router.get("/opex/{scenario_id}/depts/")
async def list_opex_depts(scenario_id: str, db: AsyncSession = Depends(get_db)):
    await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(
        select(OpexEntry.dept_code)
        .where(OpexEntry.scenario_id == scenario_id)
        .distinct()
        .order_by(OpexEntry.dept_code)
    )
    from app.api.payroll_api import _esconder_apagados
    depts = [{"dept_code": row[0]} for row in q.all()]
    return {"depts": await _esconder_apagados(db, scenario_id, "OPEX", depts)}


@router.get("/opex/{scenario_id}/dept/{dept_code}/")
async def get_dept_opex(scenario_id: str, dept_code: str, db: AsyncSession = Depends(get_db)):
    """Return all OPEX entries for a dept, grouped by account_code."""
    await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(
        select(OpexEntry)
        .where(OpexEntry.scenario_id == scenario_id, OpexEntry.dept_code == dept_code)
        .order_by(OpexEntry.account_code, OpexEntry.detail_code)
    )
    entries = q.scalars().all()
    grouped = _group_by_account(list(entries))

    # Dept-level monthly totals
    dept_monthly = {}
    for mk in MONTH_ATTRS:
        dept_monthly[mk] = str(sum(
            Decimal(acct["monthly_totals"][mk]) for acct in grouped
        ))
    dept_annual = str(sum(Decimal(v) for v in dept_monthly.values()))

    repartido = await lineas_del_allocation(db, scenario_id, dept_code, "7")

    return {
        "scenario_id": scenario_id,
        "dept_code": dept_code,
        "accounts": grouped,
        "dept_monthly_totals": dept_monthly,
        "dept_annual_total": dept_annual,
        # Lo que le cae por reparto: no se edita, pero el P&L lo suma. Los
        # totales de arriba son solo del checkbook; estos van aparte para que
        # la pantalla pueda enseñar el gran total que si coincide con el P&L.
        "allocated": repartido,
        "allocated_annual_total": str(sum(Decimal(r["total"]) for r in repartido)),
    }


@router.get("/opex/{scenario_id}/report/")
async def opex_report(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """OPEX por departamento → cuentas con total anual (reporte C6)."""
    await _get_scenario_or_404(scenario_id, db)
    entries = (await db.execute(
        select(OpexEntry).where(OpexEntry.scenario_id == scenario_id)
        .order_by(OpexEntry.dept_code, OpexEntry.account_code)
    )).scalars().all()
    by_dept: dict[str, list] = {}
    for e in entries:
        if e.dept_code in ALLOC_EXCL_OPEX:
            continue  # Employee Dining / Laundry interna: allocation → fuera del OpEx
        by_dept.setdefault(e.dept_code, []).append(e)
    depts = []
    for dept in sorted(by_dept):
        accounts = [{
            "account_code": a["account_code"],
            "account_name": a["account_name"],
            "annual": round(float(Decimal(a["annual_total"])), 2),
        } for a in _group_by_account(by_dept[dept])]
        depts.append({"dept_code": dept,
                      "annual": round(sum(a["annual"] for a in accounts), 2),
                      "accounts": accounts})
    return {"scenario_id": scenario_id, "depts": depts}


@router.put("/opex/{scenario_id}/entry/{entry_id}/")
async def update_opex_entry(
    scenario_id: str,
    entry_id: str,
    body: EntryUpdate,
    db: AsyncSession = Depends(get_db),
):
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    entry = await db.get(OpexEntry, entry_id)
    if not entry or entry.scenario_id != scenario_id:
        raise ErrorApi(404, "entrada.no_encontrada")

    if body.detail_desc is not None:
        entry.detail_desc = body.detail_desc
    if body.currency is not None:
        entry.currency = body.currency.upper()

    for attr in MONTH_ATTRS:
        val = getattr(body, attr, None)
        if val is not None:
            setattr(entry, attr, val)

    # Colones: son el dato maestro de una línea CRC.
    toco_crc = False
    for attr in MONTH_ATTRS:
        val = getattr(body, f"crc_{attr}", None)
        if val is not None:
            setattr(entry, f"crc_{attr}", val)
            toco_crc = True
    if toco_crc or body.currency is not None:
        await _derivar_si_es_crc(db, scenario_id, entry)

    await db.commit()
    await db.refresh(entry)
    return _entry_to_dict(entry)


@router.delete("/opex/{scenario_id}/entry/{entry_id}/")
async def delete_opex_entry(scenario_id: str, entry_id: str, db: AsyncSession = Depends(get_db)):
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    entry = await db.get(OpexEntry, entry_id)
    if not entry or entry.scenario_id != scenario_id:
        raise ErrorApi(404, "entrada.no_encontrada")
    await db.delete(entry)
    await db.commit()
    return {"deleted": entry_id}


@router.get("/opex/{scenario_id}/summary/")
async def opex_summary_all_depts(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Monthly OPEX totals per dept across all departments."""
    await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(
        select(OpexEntry).where(OpexEntry.scenario_id == scenario_id)
    )
    entries = q.scalars().all()

    by_dept: dict[str, dict] = {}
    for e in entries:
        if e.dept_code not in by_dept:
            by_dept[e.dept_code] = {mk: Decimal("0") for mk in MONTH_ATTRS}
        for i, mk in enumerate(MONTH_ATTRS):
            by_dept[e.dept_code][mk] += e.get_month(i + 1)

    result = []
    for dept_code, monthly in sorted(by_dept.items()):
        result.append({
            "dept_code": dept_code,
            "monthly": {mk: str(v) for mk, v in monthly.items()},
            "annual_total": str(sum(monthly.values())),
        })
    return {"depts": result}


@router.get("/opex/{scenario_id}/dept/{dept_code}/summary/")
async def opex_dept_summary(scenario_id: str, dept_code: str, db: AsyncSession = Depends(get_db)):
    """Monthly OPEX totals per account_code for one dept."""
    await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(
        select(OpexEntry)
        .where(OpexEntry.scenario_id == scenario_id, OpexEntry.dept_code == dept_code)
    )
    entries = q.scalars().all()

    by_account: dict[str, dict] = {}
    for e in entries:
        key = e.account_code
        if key not in by_account:
            by_account[key] = {"account_name": e.account_name, "monthly": {mk: Decimal("0") for mk in MONTH_ATTRS}}
        for i, mk in enumerate(MONTH_ATTRS):
            by_account[key]["monthly"][mk] += e.get_month(i + 1)

    dept_total = {mk: Decimal("0") for mk in MONTH_ATTRS}
    accounts = []
    for acct_code, data in sorted(by_account.items()):
        row = {"account_code": acct_code, "account_name": data["account_name"],
               "monthly": {mk: str(v) for mk, v in data["monthly"].items()},
               "annual_total": str(sum(data["monthly"].values()))}
        accounts.append(row)
        for mk in MONTH_ATTRS:
            dept_total[mk] += data["monthly"][mk]

    return {
        "dept_code": dept_code,
        "accounts": accounts,
        "dept_monthly_totals": {mk: str(v) for mk, v in dept_total.items()},
        "dept_annual_total": str(sum(dept_total.values())),
    }



async def _derivar_si_es_crc(db, scenario_id: str, entry) -> None:
    """Pasa los colones de la línea a dólares con el TC de cada mes.

    El recálculo del escenario también lo hace; hacerlo aquí evita que la línea
    se vea en cero entre que se guarda y que alguien recalcula.
    """
    if not getattr(entry, "en_colones", False):
        return
    from app.models.exchange_rate import ExchangeRate, get_tc_for_month
    rates = (await db.execute(
        select(ExchangeRate).where(ExchangeRate.scenario_id == scenario_id)
    )).scalars().all()
    if not rates:
        return
    for m in range(1, 13):
        entry.set_month(m, entry.derivar_usd(m, get_tc_for_month(rates, m)))


async def _derivar_importadas(db, scenario_id: str) -> int:
    """Pasa a dólares las líneas en colones recién importadas.

    Sin esto, una línea CRC queda con sus colones pero con el dólar en cero hasta
    que alguien recalcule — y el P&L la mostraría como si no existiera.
    """
    from app.models.exchange_rate import ExchangeRate, get_tc_for_month
    rates = (await db.execute(
        select(ExchangeRate).where(ExchangeRate.scenario_id == scenario_id)
    )).scalars().all()
    if not rates:
        return 0
    filas = (await db.execute(
        select(OpexEntry).where(OpexEntry.scenario_id == scenario_id,
                                OpexEntry.currency == "CRC")
    )).scalars().all()
    for e in filas:
        for m in range(1, 13):
            e.set_month(m, e.derivar_usd(m, get_tc_for_month(rates, m)))
    return len(filas)
