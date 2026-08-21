"""
Cost of Sales API — Phase 5.

Endpoints:
  GET  /api/costs/{scenario_id}/depts/
  GET  /api/costs/{scenario_id}/dept/{dept_code}/
  POST /api/costs/{scenario_id}/dept/{dept_code}/entry/       create a new entry
  PUT  /api/costs/{scenario_id}/entry/{entry_id}/             update mode/driver/rate or monthly amounts
  DELETE /api/costs/{scenario_id}/entry/{entry_id}/
  GET  /api/costs/{scenario_id}/dept/{dept_code}/summary/     monthly totals + gross profit
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

from app.db import get_db
from app.errores import ErrorApi
from app.textos import Idioma, t
from app.models.scenario import Scenario
from app.models.cost_entry import CostEntry, DRIVER_TYPES, REVENUE_LINES
from app.importers.gl_detail_importer import ALLOC_EXCL_COST
from app.engine.cost_calculator import calculate_cost_amount, recalculate_cost_entries
from app.api._nombres_de_depto import nombres_de_depto
from app.export.costs_excel import export_costs_to_excel, import_costs_from_excel
from app.engine.revenue_calculator import calculate_annual_revenue, RevenueResult
from app.models.sales_channel_config import SalesChannelConfig
from app.models.rate_card import RateCard
from app.models.occupancy_budget import OccupancyBudget
from app.models.package_config import PackageConfig
from app.models.revenue_other import RevenueOther
from app.models.room_type_config import RoomTypeConfig
from app.models.mapping import AccountMapping
from app.api._allocated import lineas_del_allocation

router = APIRouter(tags=["costs"])

MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"]


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class EntryCreate(BaseModel):
    dept_code: str
    account_code: str
    account_name: str = ""
    calc_mode: str = "MANUAL"
    driver_type: str = ""
    driver_pct_or_rate: Decimal = Decimal("0")
    revenue_line_ref: str = ""
    jan: Decimal = Decimal("0"); feb: Decimal = Decimal("0")
    mar: Decimal = Decimal("0"); apr: Decimal = Decimal("0")
    may: Decimal = Decimal("0"); jun: Decimal = Decimal("0")
    jul: Decimal = Decimal("0"); aug: Decimal = Decimal("0")
    sep: Decimal = Decimal("0"); oct: Decimal = Decimal("0")
    nov: Decimal = Decimal("0"); dec: Decimal = Decimal("0")
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


class EntryUpdate(BaseModel):
    account_name: Optional[str] = None
    calc_mode: Optional[str] = None
    driver_type: Optional[str] = None
    driver_pct_or_rate: Optional[Decimal] = None
    revenue_line_ref: Optional[str] = None
    jan: Optional[Decimal] = None; feb: Optional[Decimal] = None
    mar: Optional[Decimal] = None; apr: Optional[Decimal] = None
    may: Optional[Decimal] = None; jun: Optional[Decimal] = None
    jul: Optional[Decimal] = None; aug: Optional[Decimal] = None
    sep: Optional[Decimal] = None; oct: Optional[Decimal] = None
    nov: Optional[Decimal] = None; dec: Optional[Decimal] = None
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
    # Per-month driver rate (% as fraction). None leaves it unchanged on update.
    rate_jan: Optional[Decimal] = None; rate_feb: Optional[Decimal] = None
    rate_mar: Optional[Decimal] = None; rate_apr: Optional[Decimal] = None
    rate_may: Optional[Decimal] = None; rate_jun: Optional[Decimal] = None
    rate_jul: Optional[Decimal] = None; rate_aug: Optional[Decimal] = None
    rate_sep: Optional[Decimal] = None; rate_oct: Optional[Decimal] = None
    rate_nov: Optional[Decimal] = None; rate_dec: Optional[Decimal] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_scenario_or_404(scenario_id: str, db: AsyncSession) -> Scenario:
    s = await db.get(Scenario, scenario_id)
    if not s:
        raise ErrorApi(404, "escenario.no_encontrado")
    return s


def _entry_to_dict(e: CostEntry) -> dict:
    return {
        "id": e.id,
        "scenario_id": e.scenario_id,
        "hotel_id": e.hotel_id,
        "dept_code": e.dept_code,
        "account_code": e.account_code,
        "account_name": e.account_name,
        "calc_mode": e.calc_mode,
        "driver_type": e.driver_type,
        "currency": e.currency or "USD",
        **{f"crc_{m}": str(getattr(e, f"crc_{m}") or 0) for m in MONTH_ATTRS},
        "driver_pct_or_rate": str(e.driver_pct_or_rate),
        "revenue_line_ref": e.revenue_line_ref,
        "months": {m: str(e.get_month(i + 1)) for i, m in enumerate(MONTH_ATTRS)},
        # monthly rate: the value if set, else null (means "use base rate")
        "rates": {m: (str(getattr(e, f"rate_{m}")) if getattr(e, f"rate_{m}") is not None else None)
                  for m in MONTH_ATTRS},
        "annual_total": str(sum(e.get_month(m) for m in range(1, 13))),
    }


async def _load_revenue_results(scenario_id: str, scenario: Scenario, db: AsyncSession) -> list[RevenueResult]:
    """Load and calculate revenue for all 12 months."""
    channels = (await db.execute(select(SalesChannelConfig).where(SalesChannelConfig.scenario_id == scenario_id))).scalars().all()
    rate_cards = (await db.execute(select(RateCard).where(RateCard.scenario_id == scenario_id))).scalars().all()
    occs = (await db.execute(select(OccupancyBudget).where(OccupancyBudget.scenario_id == scenario_id))).scalars().all()
    pkgs = (await db.execute(select(PackageConfig).where(PackageConfig.scenario_id == scenario_id))).scalars().all()
    others = (await db.execute(select(RevenueOther).where(RevenueOther.scenario_id == scenario_id))).scalars().all()
    room_types = (await db.execute(
        select(RoomTypeConfig)
        .where(RoomTypeConfig.hotel_id == scenario.hotel_id)
        .order_by(RoomTypeConfig.sort_order)
    )).scalars().all()

    # Group by month (current calculate_annual_revenue signature)
    rates_by_month: dict[int, list] = {}
    occ_by_month: dict[int, list] = {}
    other_by_month: dict[int, list] = {}
    for rc in rate_cards:
        rates_by_month.setdefault(rc.month, []).append(rc)
    for ob in occs:
        occ_by_month.setdefault(ob.month, []).append(ob)
    for ot in others:
        other_by_month.setdefault(ot.month, []).append(ot)
    room_type_units = {rt.id: rt.units for rt in room_types}

    return calculate_annual_revenue(
        year=scenario.year,
        rate_cards_by_month=rates_by_month,
        occ_by_month=occ_by_month,
        channels=channels,
        pkg_configs=pkgs,
        other_by_month=other_by_month,
        room_type_units=room_type_units,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

class CostBulkRow(BaseModel):
    dept_code: str
    account_code: str
    account_name: str = ""
    calc_mode: str = "MANUAL"
    driver_type: str = ""
    driver_pct_or_rate: Decimal = Decimal("0")
    revenue_line_ref: str = ""
    # Moneda de la línea (mig 077). En CRC el dato maestro son los colones y el
    # dólar de cada mes lo deriva el recálculo con el TC de ese mes. Faltaba en
    # este schema —lo declaraba `OpexBulkRow` y no su gemelo—, así que la carga
    # masiva de costos ni siquiera tenía dónde recibir la moneda: un viaje
    # redondo devolvía en dólares una línea que se planificó en colones.
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


@router.post("/costs/{scenario_id}/bulk/")
async def bulk_replace_costs(
    scenario_id: str,
    rows: list[CostBulkRow],
    db: AsyncSession = Depends(get_db),
):
    """Bulk replace all cost detail entries for a scenario (parsed client-side)."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    # Una version enllavada no se puede sobreescribir.
    scenario.assert_editable()
    await db.execute(delete(CostEntry).where(CostEntry.scenario_id == scenario_id))
    await db.flush()
    for r in rows:
        db.add(CostEntry(
            scenario_id=scenario_id, hotel_id=scenario.hotel_id,
            dept_code=r.dept_code, account_code=r.account_code,
            account_name=r.account_name, calc_mode=r.calc_mode,
            driver_type=r.driver_type, driver_pct_or_rate=r.driver_pct_or_rate,
            revenue_line_ref=r.revenue_line_ref,
            # La moneda y los colones se ESCRIBEN. Este endpoint borra todo el
            # escenario antes de insertar, así que un viaje redondo —bajo,
            # corrijo, subo— borraba la marca de colones sin reventar: quedaban
            # los dólares del archivo, el P&L cuadraba consigo mismo, y la línea
            # dejaba de acompañar al tipo de cambio de ahí en adelante.
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


def _clean_cost_name(raw: str) -> str:
    """'Food CostCostos Alimentos' → 'Food Cost'; 'Cost of Internet' stays."""
    raw = (raw or "").strip()
    if "Costos" in raw:
        before = raw.split("Costos")[0].strip()
        if before:
            return before
    return raw


@router.get("/costs/catalog/")
async def cost_catalog(db: AsyncSession = Depends(get_db)):
    """Valid Class-5 (cost of sales) accounts per dept, with a suggested name.
    Used to make the account a constrained dropdown with an auto-filled description."""
    rows = (await db.execute(
        select(AccountMapping).where(AccountMapping.active_status == "YES")
    )).scalars().all()
    seen: set = set()
    out: list[dict] = []
    for m in rows:
        ac = (m.account_code or "").strip()
        if not ac.startswith("5"):
            continue
        dc = (m.dept_code or "").strip()
        key = (dc, ac)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "dept_code": dc,
            "line_name": m.report_line_name or "",
            "account_code": ac,
            "name": _clean_cost_name(m.account_name_example),
        })
    out.sort(key=lambda x: (x["dept_code"], x["account_code"]))
    return out


@router.get("/costs/{scenario_id}/depts/")
async def list_cost_depts(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Return distinct dept_codes that have cost entries for this scenario."""
    await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(
        select(CostEntry.dept_code, CostEntry.hotel_id)
        .where(CostEntry.scenario_id == scenario_id)
        .distinct()
        .order_by(CostEntry.dept_code)
    )
    from app.api.payroll_api import _esconder_apagados
    depts = [{"dept_code": r.dept_code} for r in q.all()]
    return {"depts": await _esconder_apagados(db, scenario_id, "COST", depts)}


@router.get("/costs/{scenario_id}/dept/{dept_code}/")
async def get_dept_checkbook(scenario_id: str, dept_code: str, db: AsyncSession = Depends(get_db)):
    """Return all cost entries for a dept, with reference revenue for context."""
    scenario = await _get_scenario_or_404(scenario_id, db)

    q = await db.execute(
        select(CostEntry)
        .where(CostEntry.scenario_id == scenario_id, CostEntry.dept_code == dept_code)
        .order_by(CostEntry.account_code)
    )
    entries = q.scalars().all()

    # Load revenue results for reference display
    rev_results = await _load_revenue_results(scenario_id, scenario, db)
    rev_by_month = {r.month: r for r in rev_results}

    return {
        "scenario_id": scenario_id,
        "dept_code": dept_code,
        "entries": [_entry_to_dict(e) for e in entries],
        # Lo que le cae por reparto. Va aparte de `entries` porque no se edita,
        # pero el P&L SI lo suma: sin esto la pantalla y el P&L no coinciden.
        "allocated": await lineas_del_allocation(db, scenario_id, dept_code, "5"),
        "revenue_reference": {
            m: {
                "rooms": str(rev_by_month[m].rooms) if m in rev_by_month else "0",
                "food": str(rev_by_month[m].food) if m in rev_by_month else "0",
                "beverage": str(rev_by_month[m].beverage) if m in rev_by_month else "0",
                "activities": str(rev_by_month[m].activities) if m in rev_by_month else "0",
                "transport": str(rev_by_month[m].transport) if m in rev_by_month else "0",
                "sustainability": str(rev_by_month[m].sustainability) if m in rev_by_month else "0",
                "innoceana": str(rev_by_month[m].innoceana) if m in rev_by_month else "0",
                "retail": str(rev_by_month[m].retail) if m in rev_by_month else "0",
                "spa": str(rev_by_month[m].spa) if m in rev_by_month else "0",
                "total": str(rev_by_month[m].total_revenue) if m in rev_by_month else "0",
                "rooms_occupied": str(rev_by_month[m].rooms_occupied) if m in rev_by_month else "0",
                "guests": str(rev_by_month[m].guests) if m in rev_by_month else "0",
                "rooms_available": rev_by_month[m].rooms_available if m in rev_by_month else 0,
            }
            for m in range(1, 13)
        },
    }


@router.get("/costs/{scenario_id}/report/")
async def costs_report(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Costos de venta por departamento → cuentas con total anual (reporte C6)."""
    await _get_scenario_or_404(scenario_id, db)
    _M = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
    entries = (await db.execute(
        select(CostEntry).where(CostEntry.scenario_id == scenario_id)
        .order_by(CostEntry.dept_code, CostEntry.account_code)
    )).scalars().all()
    by_dept: dict[str, list] = {}
    for e in entries:
        if e.dept_code in ALLOC_EXCL_COST:
            continue  # solo Employee Dining (0220): allocation. 0161 conserva su costo de venta
        by_dept.setdefault(e.dept_code, []).append(e)
    depts = []
    for dept in sorted(by_dept):
        accounts = [{
            "account_code": e.account_code,
            "account_name": e.account_name,
            "annual": round(float(sum(getattr(e, m) for m in _M)), 2),
        } for e in by_dept[dept]]
        depts.append({"dept_code": dept,
                      "annual": round(sum(a["annual"] for a in accounts), 2),
                      "accounts": accounts})
    return {"scenario_id": scenario_id, "depts": depts}


@router.get("/costs/{scenario_id}/dept/{dept_code}/summary/")
async def get_dept_cost_summary(scenario_id: str, dept_code: str, db: AsyncSession = Depends(get_db)):
    """
    Monthly CoS totals + gross profit (revenue - costs) for the dept.
    Gross Profit = relevant revenue − total CoS.
    """
    scenario = await _get_scenario_or_404(scenario_id, db)

    q = await db.execute(
        select(CostEntry)
        .where(CostEntry.scenario_id == scenario_id, CostEntry.dept_code == dept_code)
    )
    entries = q.scalars().all()

    rev_results = await _load_revenue_results(scenario_id, scenario, db)
    rev_by_month = {r.month: r for r in rev_results}

    monthly = []
    for m in range(1, 13):
        total_cos = sum(e.get_month(m) for e in entries)
        rev = rev_by_month.get(m)
        # For F&B dept (0120): use food + beverage; for others: use total_revenue
        if dept_code == "0120":
            relevant_rev = (rev.food + rev.beverage) if rev else Decimal("0")
        elif dept_code in ("0140", "0141"):  # Spa / Retail
            relevant_rev = (rev.spa + rev.retail) if rev else Decimal("0")
        elif dept_code in ("0150", "0151"):  # Activities / Innoceana
            relevant_rev = (rev.activities + rev.innoceana) if rev else Decimal("0")
        elif dept_code == "0152":  # Transport
            relevant_rev = rev.transport if rev else Decimal("0")
        else:
            relevant_rev = rev.total_revenue if rev else Decimal("0")
        gross_profit = relevant_rev - total_cos
        margin_pct = (gross_profit / relevant_rev) if relevant_rev else Decimal("0")
        monthly.append({
            "month": m,
            "total_cos": str(total_cos),
            "relevant_revenue": str(relevant_rev),
            "gross_profit": str(gross_profit),
            "margin_pct": str(margin_pct.quantize(Decimal("0.0001"))),
        })

    return {"scenario_id": scenario_id, "dept_code": dept_code, "monthly": monthly}


@router.post("/costs/{scenario_id}/dept/{dept_code}/entry/")
async def create_cost_entry(
    scenario_id: str,
    dept_code: str,
    body: EntryCreate,
    db: AsyncSession = Depends(get_db),
):
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    if body.calc_mode == "DRIVER" and body.driver_type not in DRIVER_TYPES:
        raise ErrorApi(422, "costos.driver_type_invalido", validos=DRIVER_TYPES)
    if body.driver_type == "REVENUE_LINE" and body.revenue_line_ref.upper() not in REVENUE_LINES:
        raise ErrorApi(422, "costos.revenue_line_ref_invalido", validos=REVENUE_LINES)

    entry = CostEntry(
        id=str(uuid.uuid4()),
        scenario_id=scenario_id,
        hotel_id=scenario.hotel_id,
        dept_code=dept_code,
        account_code=body.account_code,
        account_name=body.account_name,
        calc_mode=body.calc_mode,
        driver_type=body.driver_type,
        driver_pct_or_rate=body.driver_pct_or_rate,
        revenue_line_ref=body.revenue_line_ref.upper() if body.revenue_line_ref else "",
        jan=body.jan, feb=body.feb, mar=body.mar, apr=body.apr,
        may=body.may, jun=body.jun, jul=body.jul, aug=body.aug,
        sep=body.sep, oct=body.oct, nov=body.nov, dec=body.dec,
        currency=(body.currency or "USD").upper(),
        **{f"crc_{m}": getattr(body, f"crc_{m}") for m in MONTH_ATTRS},
    )
    # Si la linea esta en colones, el dolar se deriva ya con el TC de cada mes:
    # asi no queda en cero hasta que alguien recalcule.
    await _derivar_si_es_crc(db, scenario_id, entry)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _entry_to_dict(entry)


@router.put("/costs/{scenario_id}/entry/{entry_id}/")
async def update_cost_entry(
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

    entry = await db.get(CostEntry, entry_id)
    if not entry or entry.scenario_id != scenario_id:
        raise ErrorApi(404, "entrada.no_encontrada")

    if body.account_name is not None:
        entry.account_name = body.account_name
    if body.calc_mode is not None:
        entry.calc_mode = body.calc_mode
    if body.driver_type is not None:
        entry.driver_type = body.driver_type
    if body.driver_pct_or_rate is not None:
        entry.driver_pct_or_rate = body.driver_pct_or_rate
    if body.revenue_line_ref is not None:
        entry.revenue_line_ref = body.revenue_line_ref.upper()

    if body.currency is not None:
        entry.currency = body.currency.upper()

    # Update individual month amounts (MANUAL) if provided
    for attr in MONTH_ATTRS:
        val = getattr(body, attr, None)
        if val is not None:
            setattr(entry, attr, val)

    # Montos en colones: son el dato maestro de una linea CRC.
    toco_crc = False
    for attr in MONTH_ATTRS:
        val = getattr(body, f"crc_{attr}", None)
        if val is not None:
            setattr(entry, f"crc_{attr}", val)
            toco_crc = True
    if toco_crc or body.currency is not None:
        await _derivar_si_es_crc(db, scenario_id, entry)

    # Update per-month driver rates if provided (DRIVER % por mes)
    for attr in MONTH_ATTRS:
        val = getattr(body, f"rate_{attr}", None)
        if val is not None:
            setattr(entry, f"rate_{attr}", val)

    await db.commit()
    await db.refresh(entry)
    return _entry_to_dict(entry)


@router.delete("/costs/{scenario_id}/entry/{entry_id}/")
async def delete_cost_entry(scenario_id: str, entry_id: str, db: AsyncSession = Depends(get_db)):
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    entry = await db.get(CostEntry, entry_id)
    if not entry or entry.scenario_id != scenario_id:
        raise ErrorApi(404, "entrada.no_encontrada")

    await db.delete(entry)
    await db.commit()
    return {"deleted": entry_id}


@router.post("/costs/{scenario_id}/recalculate/")
async def recalculate_costs(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """
    Recalculate all DRIVER cost entries using current revenue data.
    MANUAL entries are not modified.

    ⚠️ Reescribe los DOCE meses. Era el único recálculo de su familia SIN candado:
    corría igual sobre una versión enllavada, que es justo lo que un `locked`
    promete que no puede pasar.
    """
    scenario = await _get_scenario_or_404(scenario_id, db)
    scenario.assert_editable()

    q = await db.execute(
        select(CostEntry).where(
            CostEntry.scenario_id == scenario_id,
            CostEntry.calc_mode == "DRIVER",
        )
    )
    entries = list(q.scalars().all())

    rev_results = await _load_revenue_results(scenario_id, scenario, db)
    rev_by_month = {r.month: r for r in rev_results}

    # FTE por mes: base del driver FTE. Para la cafetería (0220) cuenta solo la
    # gente que COME —los departamentos marcados en Allocation—, porque no se le
    # da almuerzo a quien está excluido. Para cualquier otro departamento se toma
    # el FTE completo del escenario.
    fte_por_mes = await _fte_por_mes(db, scenario_id, entries)

    for m in range(1, 13):
        rev = rev_by_month.get(m)
        rooms_occupied = rev.rooms_occupied if rev else None
        guests = rev.guests if rev else None
        rooms_available = rev.rooms_available if rev else None
        recalculate_cost_entries(
            entries=entries,
            month=m,
            rev=rev,
            rooms_occupied=rooms_occupied,
            guests=guests,
            rooms_available=rooms_available,
            fte=fte_por_mes.get(m),
        )

    await db.commit()
    return {"recalculated": len(entries), "scenario_id": scenario_id}


@router.get("/costs/{scenario_id}/export/excel/")
async def export_costs_excel(scenario_id: str, db: AsyncSession = Depends(get_db)):
    scenario = await _get_scenario_or_404(scenario_id, db)
    entries = (await db.execute(
        select(CostEntry).where(CostEntry.scenario_id == scenario_id)
        .order_by(CostEntry.dept_code, CostEntry.account_code)
    )).scalars().all()

    by_dept: dict[str, list[dict]] = {}
    for e in entries:
        by_dept.setdefault(e.dept_code, []).append({
            "account_code": e.account_code,
            "account_name": e.account_name,
            "driver_type": getattr(e, "calc_mode", "MANUAL"),
            **{mk: float(getattr(e, mk) or 0) for mk in MONTH_ATTRS},
            # La moneda y los colones viajan al Excel: sin esto, bajarlo y volver
            # a subirlo borraria la marca de colones y la linea volveria a dolares.
            "currency": e.currency or "USD",
            **{f"crc_{mk}": float(getattr(e, f"crc_{mk}") or 0) for mk in MONTH_ATTRS},
        })

    label = f"{scenario.hotel_id} {scenario.version}"
    xlsx = export_costs_to_excel(by_dept, label, getattr(scenario, "year", 2026),
                                 dept_names=await nombres_de_depto(db))
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="costs_{scenario_id}.xlsx"'},
    )


@router.post("/costs/{scenario_id}/import/excel/", dependencies=[Depends(registro_de_subida)])
async def import_costs_excel(
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

    rows = import_costs_from_excel(await file.read())
    if not rows:
        raise ErrorApi(422, "costos.sin_filas_validas")

    if replace:
        affected = {r["dept_code"] for r in rows}
        for dc in affected:
            await db.execute(
                delete(CostEntry).where(
                    CostEntry.scenario_id == scenario_id,
                    CostEntry.dept_code == dc,
                    CostEntry.calc_mode == "MANUAL",
                )
            )
        await db.flush()

    for r in rows:
        db.add(CostEntry(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            hotel_id=scenario.hotel_id,
            dept_code=r["dept_code"],
            account_code=r["account_code"],
            account_name=r["account_name"],
            calc_mode="MANUAL",
            # Sin esto la fila en colones entraba en ceros y perdia su moneda:
            # no reventaba, que es peor — nadie se enteraba.
            currency=(r.get("currency") or "USD").upper(),
            **{mk: r.get(mk, Decimal("0")) for mk in MONTH_ATTRS},
            **{f"crc_{mk}": r.get(f"crc_{mk}", Decimal("0")) for mk in MONTH_ATTRS},
        ))

    await db.flush()
    await _derivar_importadas(db, scenario_id)
    await db.commit()
    return {"imported": len(rows), "scenario_id": scenario_id}


async def _fte_por_mes(db, scenario_id: str, entries) -> dict[int, Decimal]:
    """FTE por mes que sirve de base al driver FTE.

    Si hay alguna línea de la CAFETERÍA (depto 0220) con driver FTE, la base son
    solo los departamentos que COMEN —los marcados en Allocation—, porque no se
    le da almuerzo a quien está excluido. Si no, el FTE completo del escenario.
    """
    from app.models.payroll_position import PayrollPosition, get_fte
    from app.models.cafeteria_allocation_config import CafeteriaAllocationConfig

    usa_fte = [e for e in entries if (e.driver_type or "").upper() == "FTE"]
    if not usa_fte:
        return {}

    posiciones = (await db.execute(
        select(PayrollPosition).where(PayrollPosition.scenario_id == scenario_id)
    )).scalars().all()

    if any((e.dept_code or "") == "0220" for e in usa_fte):
        comen = {c.dept_code for c in (await db.execute(
            select(CafeteriaAllocationConfig).where(
                CafeteriaAllocationConfig.scenario_id == scenario_id)
        )).scalars().all() if c.participates}
        if comen:
            posiciones = [p for p in posiciones if (p.dept_code or "") in comen]

    return {m: sum((get_fte(p, m) for p in posiciones), Decimal("0"))
            for m in range(1, 13)}



async def _derivar_si_es_crc(db, scenario_id: str, entry) -> None:
    """Pasa los colones de la linea a dolares con el TC de cada mes.

    El recalculo del escenario tambien lo hace, pero hacerlo aqui evita que la
    linea se vea en cero entre que se guarda y que alguien recalcula.
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


@router.get("/checkbook/{scenario_id}/moneda/estado/")
async def estado_moneda(scenario_id: str, db: AsyncSession = Depends(get_db),
                        idioma: str = Idioma):
    """¿Hay líneas en colones cuyo dólar quedó viejo respecto al tipo de cambio?

    Es el control que faltaba: si el owner mueve el TC de un mes y nadie recalcula,
    el P&L sigue mostrando el dólar anterior y nada lo avisa. Esto lo detecta y la
    pantalla ofrece el botón para empujarlo.
    """
    from app.models.exchange_rate import ExchangeRate, get_tc_for_month
    from app.models.opex_entry import OpexEntry

    await _get_scenario_or_404(scenario_id, db)
    rates = (await db.execute(
        select(ExchangeRate).where(ExchangeRate.scenario_id == scenario_id)
    )).scalars().all()

    en_colones = 0
    desactualizadas = 0
    detalle: list[dict] = []
    CENTAVO = Decimal("0.01")

    for Model, cual in ((OpexEntry, "OPEX"), (CostEntry, "Costos")):
        filas = (await db.execute(
            select(Model).where(Model.scenario_id == scenario_id)
        )).scalars().all()
        for e in filas:
            if not getattr(e, "en_colones", False):
                continue
            en_colones += 1
            if not rates:
                desactualizadas += 1
                detalle.append({"tipo": cual, "dept_code": e.dept_code,
                                "account_code": e.account_code,
                                "motivo": t(idioma, "moneda.sin_tipo_de_cambio")})
                continue
            meses = []
            for m in range(1, 13):
                esperado = e.derivar_usd(m, get_tc_for_month(rates, m))
                if abs((e.get_month(m) or Decimal("0")) - esperado) > CENTAVO:
                    meses.append(m)
            if meses:
                desactualizadas += 1
                detalle.append({"tipo": cual, "dept_code": e.dept_code,
                                "account_code": e.account_code,
                                "account_name": e.account_name,
                                "meses": meses})

    return {
        "scenario_id": scenario_id,
        "lineas_en_colones": en_colones,
        "desactualizadas": desactualizadas,
        "sin_tipo_de_cambio": not rates,
        "detalle": detalle[:20],
    }


async def _derivar_importadas(db, scenario_id: str) -> int:
    """Pasa a dólares las líneas en colones recién importadas."""
    from app.models.exchange_rate import ExchangeRate, get_tc_for_month
    rates = (await db.execute(
        select(ExchangeRate).where(ExchangeRate.scenario_id == scenario_id)
    )).scalars().all()
    if not rates:
        return 0
    filas = (await db.execute(
        select(CostEntry).where(CostEntry.scenario_id == scenario_id,
                                CostEntry.currency == "CRC")
    )).scalars().all()
    for e in filas:
        for m in range(1, 13):
            e.set_month(m, e.derivar_usd(m, get_tc_for_month(rates, m)))
    return len(filas)
