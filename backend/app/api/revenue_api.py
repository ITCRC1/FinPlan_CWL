"""
Revenue API endpoints.

POST /api/scenarios/{id}/revenue/import/
  Import revenue data from Budget2026_Revenue_CORCO.xlsx.

GET  /api/scenarios/{id}/revenue/monthly/
  Return revenue results for all 12 months.

GET  /api/scenarios/{id}/revenue/{month}/
  Return revenue result for a single month.

GET  /api/scenarios/{id}/revenue/rate-cards/
  Return rate cards (rack + net rates) for viewing/editing.

PUT  /api/scenarios/{id}/revenue/rate-cards/{room_type_id}/{month}/
  Update a rate card entry.

GET  /api/scenarios/{id}/revenue/occupancy/
  Return occupancy budgets for all months.

PUT  /api/scenarios/{id}/revenue/occupancy/{room_type_id}/{month}/
  Update a room type occupancy for a month.
"""
import calendar
import os
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from app.importers.registro_dep import registro_de_subida
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, delete, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID
from app.api._candado import candado
from app.api._ingreso_de_driver import persistir_ingreso_de_driver
from app.api._llega_al_pl import llega_al_pl, modo_ingresos
from app.db import get_db
from app.models.scenario import Scenario
from app.models.hotel import Hotel
from app.models.room_type_config import RoomTypeConfig
from app.models.component_label import (
    ComponentLabel, ETIQUETAS_POR_DEFECTO, KIND_PACKAGE,
)
from app.models.sales_channel_config import SalesChannelConfig
from app.models.rate_card import RateCard
from app.models.occupancy_budget import OccupancyBudget
from app.models.package_config import PackageConfig
from app.models.revenue_other import RevenueOther
from app.models.revenue_entry import (
    RevenueEntry, REVENUE_LINES, REVENUE_LINE_LABELS, REVENUE_LINE_ACCOUNT)
from app.models.spa_budget import SpaBudget
from app.models.scenario_master import ScenarioMaster
from app.models.historical_kpi import HistoricalKpi
from app.models.scenario_stat import ScenarioStat
from app.models.actual_room_stat import ActualRoomStat
from app.models.on_the_books import OnTheBooksEntry
from app.models.otb_daily_occ import OtbDailyOcc
from app.models.otb_week_param import OtbWeekParam
from app.models.channel_mix import ChannelMixEntry, ChannelMixDetail, CHANNEL_METRICS
from app.models.country_mix import CountryMixEntry, COUNTRY_METRICS

#: Para nombrar meses en los mensajes de error. Un «los meses 3, 7» no le
#: dice nada a nadie; «Mar, Jul» sí.
_MES_CORTO = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
              "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
from app.models.ops_kpi import OpsKpiEntry
from app.models.balance_sheet_line import BalanceSheetLine
from app.engine.revenue_calculator import (
    calculate_annual_revenue, RevenueResult, room_type_breakdown,
)
from app.importers.revenue_importer import import_revenue, repartir_tipos_para_el_excel
from app.importers.historical_kpi_importer import import_historical_kpi
from app.export.stats_excel import export_stats_to_excel, import_stats_from_excel

router = APIRouter()

EXCEL_PATH = Path(os.getenv("DATA_DIR", "C:/FinPlan_CWL")) / "Budget2026_Revenue_CORCO.xlsx"


async def _get_scenario_or_404(scenario_id: str, db: AsyncSession) -> Scenario:
    s = await db.get(Scenario, scenario_id)
    if not s:
        raise ErrorApi(404, "escenario.no_encontrado")
    return s


# ─── Inventario de habitaciones (Units Category) ──────────────────────────────
# Hotel-level config: tipos de habitación × unidades. Es la base del revenue —
# rooms_available = Σ(units × días del mes). No depende del escenario.

# Departamento de habitaciones: el padre bajo el que cuelgan Villas y
# Residencias. El gasto entra acá desde el GL y de acá se reparte.
ROOMS_DEPT = "0110"


def _room_type_to_dict(rt: RoomTypeConfig) -> dict:
    return {
        "id": rt.id,
        "code": rt.code,
        "sort_order": rt.sort_order,
        "name": rt.name,
        "short_name": rt.short_name,
        "units": rt.units,
        "pax_min": rt.pax_min,
        "pax_max": rt.pax_max,
        "dept_code": rt.dept_code or "",
        "active": rt.active,
    }


@router.get("/hotels/{hotel_id}/room-types/")
async def get_room_types(
    hotel_id: str,
    scenario_id: str | None = None,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Tipos de habitación + total unidades + meses cerrados + factor pax.

    Por defecto solo las ACTIVAS (las ocultas no afectan revenue). include_inactive
    =true trae también las ocultas (para gestionarlas en Master Data).
    Si se pasa `scenario_id` y ese escenario tiene master data propia, se usan
    sus valores (units por tipo / meses cerrados / pax)."""
    stmt = select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == hotel_id)
    if not include_inactive:
        stmt = stmt.where(RoomTypeConfig.active == True)  # noqa: E712
    rows = (await db.execute(stmt.order_by(RoomTypeConfig.sort_order))).scalars().all()
    hotel = await db.get(Hotel, hotel_id)

    closed = hotel.closed_months_list if hotel else []
    pax = str(hotel.pax_per_night) if hotel else "1.8"
    units_override: dict[str, int] = {}
    if scenario_id:
        sm = (await db.execute(
            select(ScenarioMaster).where(ScenarioMaster.scenario_id == scenario_id)
        )).scalar_one_or_none()
        if sm:
            if sm.closed_months is not None:
                closed = [int(m) for m in sm.closed_months.split(",") if m.strip().isdigit()]
            if sm.pax_per_night is not None:
                pax = str(sm.pax_per_night)
            if sm.units_json:
                import json
                try:
                    units_override = {k: int(v) for k, v in json.loads(sm.units_json).items()}
                except (ValueError, TypeError):
                    units_override = {}

    def rt_dict(rt):
        d = _room_type_to_dict(rt)
        if rt.id in units_override:
            d["units"] = units_override[rt.id]
        return d

    room_types = [rt_dict(rt) for rt in rows]
    return {
        "hotel_id": hotel_id,
        "room_types": room_types,
        "total_units": sum(r["units"] for r in room_types),
        "closed_months": closed,
        "pax_per_night": pax,
    }


@router.get("/scenarios/{scenario_id}/master/")
async def get_scenario_master(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Master data por escenario (resuelta): units por tipo, meses cerrados, pax."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    rt = await get_room_types(scenario.hotel_id, scenario_id=scenario_id, include_inactive=True, db=db)
    sm = (await db.execute(
        select(ScenarioMaster).where(ScenarioMaster.scenario_id == scenario_id)
    )).scalar_one_or_none()
    return {
        "scenario_id": scenario_id,
        "seeded": sm is None,
        "room_types": rt["room_types"],     # incluye units (override o default)
        "closed_months": rt["closed_months"],
        "pax_per_night": rt["pax_per_night"],
    }


class ScenarioMasterBody(BaseModel):
    closed_months: list[int]
    pax_per_night: Decimal
    units: dict[str, int]   # room_type_id -> units


@router.post("/scenarios/{scenario_id}/master/")
async def put_scenario_master(
    scenario_id: str, body: ScenarioMasterBody, db: AsyncSession = Depends(get_db),
):
    import json
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))
    sm = (await db.execute(
        select(ScenarioMaster).where(ScenarioMaster.scenario_id == scenario_id)
    )).scalar_one_or_none()
    if sm is None:
        sm = ScenarioMaster(scenario_id=scenario_id)
        db.add(sm)
    months = sorted({m for m in body.closed_months if 1 <= m <= 12})
    sm.closed_months = ",".join(str(m) for m in months)
    sm.pax_per_night = body.pax_per_night
    sm.units_json = json.dumps({k: int(v) for k, v in body.units.items()})
    await db.commit()
    return {"saved": True, "scenario_id": scenario_id}


class PaxPerNightUpdate(BaseModel):
    pax_per_night: Decimal


@router.put("/hotels/{hotel_id}/pax-per-night/")
async def set_pax_per_night(
    hotel_id: str, payload: PaxPerNightUpdate, db: AsyncSession = Depends(get_db),
):
    """Define el factor de pax por noche ocupada del hotel."""
    hotel = await db.get(Hotel, hotel_id)
    if not hotel:
        raise ErrorApi(404, "propiedad.no_encontrada")
    if payload.pax_per_night < 0:
        raise ErrorApi(422, "pax_por_noche.negativo")
    hotel.pax_per_night = payload.pax_per_night
    await db.commit()
    return {"hotel_id": hotel_id, "pax_per_night": str(hotel.pax_per_night)}


class ClosedMonthsUpdate(BaseModel):
    closed_months: list[int]   # 1-based months the hotel does not operate


@router.put("/hotels/{hotel_id}/closed-months/")
async def set_closed_months(
    hotel_id: str, payload: ClosedMonthsUpdate, db: AsyncSession = Depends(get_db),
):
    """Define los meses cerrados del hotel (no opera → noches disponibles = 0)."""
    hotel = await db.get(Hotel, hotel_id)
    if not hotel:
        raise ErrorApi(404, "propiedad.no_encontrada")
    months = sorted({m for m in payload.closed_months if 1 <= m <= 12})
    hotel.closed_months = ",".join(str(m) for m in months)
    await db.commit()
    return {"hotel_id": hotel_id, "closed_months": months}


class RoomTypeIn(BaseModel):
    name: str
    code: str = ""            # código fijo estable; auto RT## si no se da
    short_name: str = ""
    units: int = 0
    pax_min: int = 1
    pax_max: int = 2
    sort_order: int | None = None


async def _code_taken(db, hotel_id: str, code: str, exclude_id: str | None = None) -> bool:
    if not code:
        return False
    rows = (await db.execute(select(RoomTypeConfig).where(
        RoomTypeConfig.hotel_id == hotel_id, RoomTypeConfig.code == code))).scalars().all()
    return any(r.id != exclude_id for r in rows)


@router.post("/hotels/{hotel_id}/room-types/")
async def create_room_type(
    hotel_id: str, payload: RoomTypeIn, db: AsyncSession = Depends(get_db),
):
    """Agrega un tipo de habitación. sort_order = al final si no se indica.
    code = el que se pase o auto 'RT##' (fijo, estable, único por hotel)."""
    import uuid as _uuid
    existing = (await db.execute(
        select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == hotel_id))).scalars().all()
    sort_order = payload.sort_order if payload.sort_order is not None else (
        max((r.sort_order for r in existing), default=0)) + 1
    code = (payload.code or "").strip()
    if code and await _code_taken(db, hotel_id, code):
        raise ErrorApi(409, "tipo_habitacion.codigo_repetido", codigo=code)
    if not code:
        # Auto: 'SH' + (mayor número visto + 1), 2 dígitos → SH08, SH09…
        # `existing` NO filtra por `active`, y eso es a propósito: una categoría
        # oculta conserva su número, así el correlativo es una marca de agua que
        # solo sube. Como ya no se borran filas (el DELETE oculta), un código no
        # puede volver a asignarse nunca.
        import re
        nums = [int(m.group(1)) for r in existing
                if (m := re.search(r"(\d+)\s*$", r.code or ""))]
        nextn = (max(nums) + 1) if nums else 1
        code = f"SH{nextn:02d}"
        while await _code_taken(db, hotel_id, code):
            nextn += 1
            code = f"SH{nextn:02d}"
    rt = RoomTypeConfig(
        id=str(_uuid.uuid4()), hotel_id=hotel_id, sort_order=sort_order, code=code,
        name=payload.name, short_name=payload.short_name or payload.name[:30],
        units=payload.units, pax_min=payload.pax_min, pax_max=payload.pax_max,
        active=True,
    )
    db.add(rt)
    await db.commit()
    return _room_type_to_dict(rt)


class RoomTypeUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    short_name: str | None = None
    units: int | None = None
    pax_min: int | None = None
    pax_max: int | None = None
    sort_order: int | None = None
    # Departamento al que pertenece la categoría. Vacío = Rooms (0110). Es lo
    # que le dice al reparto qué noches son de Villas y cuáles de Residencias.
    dept_code: str | None = None
    active: bool | None = None   # ocultar (false) / mostrar (true) sin borrar


@router.get("/hotels/{hotel_id}/room-departments/")
async def list_room_departments(hotel_id: str, db: AsyncSession = Depends(get_db)):
    """Los SET de categorías de habitación: Rooms, Villas, Residencias.

    Filtra por la bandera `room_set`, no por parentesco: Rooms también tiene
    hijos que son FUNCIONES (Front Desk, Housekeeping) y a esos no se les asigna
    una categoría. El costo entra al GL en Rooms y de ahí se reparte a los otros
    sets según las noches vendidas de sus categorías.
    """
    from app.models.department_catalog import DepartmentCatalog
    filas = (await db.execute(
        select(DepartmentCatalog).where(
            DepartmentCatalog.active == True,       # noqa: E712
            DepartmentCatalog.room_set == True,     # noqa: E712
        ).order_by(DepartmentCatalog.dept_code))).scalars().all()
    return [{"dept_code": d.dept_code, "dept_name": d.dept_name,
             "es_padre": d.dept_code == ROOMS_DEPT} for d in filas]


@router.put("/hotels/{hotel_id}/room-types/{room_type_id}/")
async def update_room_type(
    hotel_id: str, room_type_id: str, payload: RoomTypeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Actualiza campos de un tipo de habitación (solo los enviados)."""
    rt = await db.get(RoomTypeConfig, room_type_id)
    if not rt or rt.hotel_id != hotel_id:
        raise ErrorApi(404, "tipo_habitacion.no_encontrado")

    # ── El código y la posición quedan clavados al momento de creación ──────
    # (owner, 2026-08-14: «que los códigos no se muevan nunca, y los que se
    # vayan agregando queden esclavos en sus posiciones de creación»).
    #
    # El código es lo que liga la categoría entre escenarios, entre reportes y
    # entre propiedades — el reporte de Junta cruza por código, no por id ni por
    # nombre. Moverlo no da error: reapunta historia en silencio. La POSICIÓN va
    # de la mano porque el importador del Excel mapea sus filas por `sort_order`.
    #
    # El NOMBRE sí se edita: es la etiqueta, y para eso está.
    actual = (rt.code or "").strip()
    if payload.code is not None:
        newc = payload.code.strip()
        if actual and newc != actual:
            raise ErrorApi(409, "tipo_habitacion.codigo_no_se_cambia",
                           codigo=actual)
        if newc and not actual and await _code_taken(db, hotel_id, newc, exclude_id=rt.id):
            raise ErrorApi(409, "tipo_habitacion.codigo_repetido", codigo=newc)
    if payload.sort_order is not None and payload.sort_order != rt.sort_order:
        raise ErrorApi(409, "tipo_habitacion.posicion_no_se_mueve",
                       nombre=rt.short_name, posicion=rt.sort_order)

    for field in ("name", "code", "short_name", "units", "pax_min", "pax_max",
                  "dept_code", "active"):
        val = getattr(payload, field)
        if val is not None:
            setattr(rt, field, val)
    await db.commit()
    return _room_type_to_dict(rt)


@router.delete("/hotels/{hotel_id}/room-types/{room_type_id}/")
async def delete_room_type(
    hotel_id: str, room_type_id: str, db: AsyncSession = Depends(get_db),
):
    """OCULTA la categoría. La fila nunca se borra.

    Borrarla de verdad liberaba el número para que el correlativo lo volviera a
    entregar, y entonces un `SH08` de hoy podía terminar apuntando a otra
    categoría que la de la historia ya cargada. Ocultar deja el dato donde está,
    saca la categoría de todas las pantallas (los listados piden solo las
    activas) y conserva el número para siempre.

    Se vuelve a mostrar con `PUT … {"active": true}`.
    """
    rt = await db.get(RoomTypeConfig, room_type_id)
    if not rt or rt.hotel_id != hotel_id:
        raise ErrorApi(404, "tipo_habitacion.no_encontrado")
    rt.active = False
    await db.commit()
    return {"deleted": True, "hidden": True, "id": room_type_id,
            "code": rt.code, "mensaje": f"«{rt.short_name}» quedó oculta. "
                                        f"El código {rt.code} no se reutiliza."}


async def _load_revenue_data(scenario_id: str, db: AsyncSession) -> dict:
    """Load all revenue-related data for a scenario from DB."""
    channels_q = await db.execute(
        select(SalesChannelConfig).where(SalesChannelConfig.scenario_id == scenario_id)
    )
    rate_cards_q = await db.execute(
        select(RateCard).where(RateCard.scenario_id == scenario_id)
    )
    occ_q = await db.execute(
        select(OccupancyBudget).where(OccupancyBudget.scenario_id == scenario_id)
    )
    pkg_q = await db.execute(
        select(PackageConfig).where(PackageConfig.scenario_id == scenario_id)
    )
    other_q = await db.execute(
        select(RevenueOther).where(RevenueOther.scenario_id == scenario_id)
    )
    rt_q = await db.execute(
        select(RoomTypeConfig).where(
            RoomTypeConfig.hotel_id == (await db.get(Scenario, scenario_id)).hotel_id,
            RoomTypeConfig.active == True,  # noqa: E712 — ocultar propaga a todo el revenue
        ).order_by(RoomTypeConfig.sort_order)
    )

    channels = channels_q.scalars().all()
    rate_cards = rate_cards_q.scalars().all()
    occupancies = occ_q.scalars().all()
    pkg_configs = pkg_q.scalars().all()
    other_revenues = other_q.scalars().all()
    room_types = rt_q.scalars().all()

    return {
        "channels": channels,
        "rate_cards": rate_cards,
        "occupancies": occupancies,
        "pkg_configs": pkg_configs,
        "other_revenues": other_revenues,
        "room_types": room_types,
    }


def _revenue_result_to_dict(r: RevenueResult) -> dict:
    return {
        "month": r.month,
        "year": r.year,
        "rooms": str(r.rooms),
        "food": str(r.food),
        "beverage": str(r.beverage),
        "activities": str(r.activities),
        "transport": str(r.transport),
        "sustainability": str(r.sustainability),
        "spa": str(r.spa),
        "retail": str(r.retail),
        "fnb_misc": str(r.fnb_misc),
        "innoceana": str(r.innoceana),
        "laundry": str(r.laundry),
        "total_package": str(r.total_package),
        "total_revenue": str(r.total_revenue),
        "rooms_available": r.rooms_available,
        "rooms_occupied": str(r.rooms_occupied),
        "guests": str(r.guests),
        "net_factor": str(r.net_factor),
        "occupancy_pct": str(r.occupancy_pct),
        "adr": str(r.adr),
        "revpar": str(r.revpar),
    }


@router.post("/scenarios/{scenario_id}/revenue/import/", dependencies=[Depends(registro_de_subida)])
async def import_revenue_data(
    scenario_id: str,
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Import revenue data from the budget Excel file.
    Accepts an optional file upload; falls back to server-local EXCEL_PATH for dev.
    Clears any existing revenue data for this scenario first.
    """
    import io, tempfile, os
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    if file is not None:
        contents = await file.read()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.write(contents)
        tmp.flush()
        tmp.close()
        xlsx = Path(tmp.name)
    elif EXCEL_PATH.exists():
        xlsx = EXCEL_PATH
        tmp = None
    else:
        raise ErrorApi(404, "excel.no_encontrado")

    # Load room types for this hotel
    rt_q = await db.execute(
        select(RoomTypeConfig)
        .where(RoomTypeConfig.hotel_id == scenario.hotel_id)
        .order_by(RoomTypeConfig.sort_order)
    )
    room_types = rt_q.scalars().all()

    # El archivo trae un número FIJO de filas; el hotel puede tener más tipos.
    # Tener más no es un error —Corcovado sumó Villas y Residencias— así que se
    # importa lo que el Excel cubre y se informa qué quedó sin tocar. Antes esto
    # exigía exactamente seis y se negaba entero con un mensaje que sonaba a
    # falla del sistema.
    cubiertos, sin_tocar, faltan = repartir_tipos_para_el_excel(
        [rt.sort_order for rt in room_types])
    if faltan:
        raise ErrorApi(400, "revenue.excel_faltan_tipos",
                       tipos=sorted(cubiertos + faltan), faltan=faltan)
    por_orden = {rt.sort_order: rt for rt in room_types}
    room_type_ids = [por_orden[so].id for so in cubiertos]
    nombres_sin_tocar = [por_orden[so].short_name for so in sin_tocar]

    # Clear existing data for this scenario
    for model in (SalesChannelConfig, RateCard, OccupancyBudget, PackageConfig, RevenueOther):
        existing = await db.execute(select(model).where(model.scenario_id == scenario_id))
        for obj in existing.scalars().all():
            await db.delete(obj)
    await db.flush()

    # Import from Excel
    try:
        data = import_revenue(xlsx, scenario_id, scenario.hotel_id, scenario.year, room_type_ids)
    finally:
        if file is not None and tmp is not None:
            os.unlink(tmp.name)

    for obj in (
        data["channels"] + data["rate_cards"] + data["occupancies"]
        + data["package_configs"] + data["other_revenues"]
    ):
        db.add(obj)

    await db.commit()

    return {
        "sin_tocar": nombres_sin_tocar,
        "imported": {
            "channels": len(data["channels"]),
            "rate_cards": len(data["rate_cards"]),
            "occupancies": len(data["occupancies"]),
            "package_configs": len(data["package_configs"]),
            "other_revenues": len(data["other_revenues"]),
        }
    }


@router.get("/scenarios/{scenario_id}/revenue/monthly/")
async def get_monthly_revenue(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Return revenue results for all 12 months.

    Respects scenario.revenue_source: 'checkbook' reads the direct RevenueEntry
    amounts; 'drivers' (default) derives revenue from rate cards × occupancy.
    """
    scenario = await _get_scenario_or_404(scenario_id, db)

    if getattr(scenario, "revenue_source", "drivers") == "checkbook":
        from app.engine.recalculate import revenue_results_from_checkbook
        results_by_month = await revenue_results_from_checkbook(db, scenario)
        results = [results_by_month[m] for m in range(1, 13)]
        annual_total = sum(r.total_revenue for r in results)
        return {
            "scenario_id": scenario_id,
            "year": scenario.year,
            "source": "checkbook",
            "months": [_revenue_result_to_dict(r) for r in results],
            "annual_total_revenue": str(annual_total),
        }

    data = await _load_revenue_data(scenario_id, db)

    room_type_units = {rt.id: rt.units for rt in data["room_types"]}

    # Group by month
    rates_by_month = {}
    for rc in data["rate_cards"]:
        rates_by_month.setdefault(rc.month, []).append(rc)
    occ_by_month = {}
    for ob in data["occupancies"]:
        occ_by_month.setdefault(ob.month, []).append(ob)
    other_by_month = {}
    for ot in data["other_revenues"]:
        other_by_month.setdefault(ot.month, []).append(ot)

    results = calculate_annual_revenue(
        year=scenario.year,
        rate_cards_by_month=rates_by_month,
        occ_by_month=occ_by_month,
        channels=data["channels"],
        pkg_configs=data["pkg_configs"],
        other_by_month=other_by_month,
        room_type_units=room_type_units,
    )

    annual_total = sum(r.total_revenue for r in results)
    return {
        "scenario_id": scenario_id,
        "year": scenario.year,
        "source": "drivers",
        "months": [_revenue_result_to_dict(r) for r in results],
        "annual_total_revenue": str(annual_total),
    }


@router.get("/scenarios/{scenario_id}/revenue-detail/report/")
async def revenue_detail_report(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Ingresos por departamento → cuentas con total anual (GL Clase 4)."""
    from app.models.revenue_account_entry import RevenueAccountEntry
    _M = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
    entries = (await db.execute(
        select(RevenueAccountEntry).where(RevenueAccountEntry.scenario_id == scenario_id)
        .order_by(RevenueAccountEntry.dept_code, RevenueAccountEntry.account_code)
    )).scalars().all()
    by_dept: dict[str, list] = {}
    for e in entries:
        by_dept.setdefault(e.dept_code, []).append(e)
    depts = []
    for dept in sorted(by_dept):
        accounts = [{
            "account_code": e.account_code, "account_name": e.account_name,
            "annual": round(float(sum(getattr(e, m) for m in _M)), 2),
        } for e in by_dept[dept]]
        depts.append({"dept_code": dept,
                      "annual": round(sum(a["annual"] for a in accounts), 2),
                      "accounts": accounts})
    return {"scenario_id": scenario_id, "depts": depts}


@router.get("/scenarios/{scenario_id}/belowgop-detail/report/")
async def belowgop_detail_report(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Below-GOP por departamento → cuentas con total anual (GL Clase 8)."""
    from app.models.belowgop_account_entry import BelowGopAccountEntry
    _M = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]
    entries = (await db.execute(
        select(BelowGopAccountEntry).where(BelowGopAccountEntry.scenario_id == scenario_id)
        .order_by(BelowGopAccountEntry.dept_code, BelowGopAccountEntry.account_code)
    )).scalars().all()
    by_dept: dict[str, list] = {}
    for e in entries:
        by_dept.setdefault(e.dept_code, []).append(e)
    depts = []
    for dept in sorted(by_dept):
        accounts = [{
            "account_code": e.account_code, "account_name": e.account_name,
            "annual": round(float(sum(getattr(e, m) for m in _M)), 2),
        } for e in by_dept[dept]]
        depts.append({"dept_code": dept,
                      "annual": round(sum(a["annual"] for a in accounts), 2),
                      "accounts": accounts})
    return {"scenario_id": scenario_id, "depts": depts}


def _aggregate_room_type(months: list[dict], room_type_units: dict, names: dict,
                         codes: dict | None = None) -> list[dict]:
    """Sum the per-month room-type rows into a full-year row per type, with
    occupancy/ADR recomputed and % of total revenue (the report's mix column)."""
    codes = codes or {}
    agg = {rt_id: {"revenue": 0.0, "nights_available": 0, "nights_occupied": 0.0, "pax": 0.0}
           for rt_id in room_type_units}
    for m in months:
        for r in m["rows"]:
            a = agg[r["room_type_id"]]
            a["revenue"] += r["revenue"]
            a["nights_available"] += r["nights_available"]
            a["nights_occupied"] += r["nights_occupied"]
            a["pax"] += r["pax"]
    total_rev = sum(a["revenue"] for a in agg.values())
    out = []
    for rt_id, units in room_type_units.items():
        a = agg[rt_id]
        avail, occ, rev = a["nights_available"], a["nights_occupied"], a["revenue"]
        out.append({
            "room_type_id": rt_id,
            "room_type_code": codes.get(rt_id, ""),
            "room_type_name": names.get(rt_id, rt_id),
            "units": int(units),
            "nights_available": avail,
            "nights_occupied": occ,
            "occupancy_pct": (occ / avail) if avail else 0.0,
            "revenue": round(rev, 2),
            "adr": (rev / occ) if occ else 0.0,
            "pax": a["pax"],
            "pct_of_total": (rev / total_rev) if total_rev else 0.0,
        })
    return out


async def _room_stats_from_actuals(scenario_id: str, year: int, db: AsyncSession) -> dict | None:
    """Si el escenario tiene room stats REALES cargados (de Opera/PMS), arma la
    respuesta by-room-type con esos datos. Si no hay, devuelve None."""
    stats = (await db.execute(select(ActualRoomStat).where(
        ActualRoomStat.scenario_id == scenario_id))).scalars().all()
    if not stats:
        return None
    # Mapa nombre→código FIJO desde el config del hotel (así los actuales también
    # cargan el código; el link deja de depender solo del nombre).
    scen = await db.get(Scenario, scenario_id)
    cfgs = (await db.execute(select(RoomTypeConfig).where(
        RoomTypeConfig.hotel_id == (scen.hotel_id if scen else "")))).scalars().all()
    code_by_name = {c.name: c.code for c in cfgs}
    cf = lambda nm: code_by_name.get(nm, "")
    # units por tipo = máximo visto (constante en el año)
    units_by_name: dict[str, int] = {}
    for s in stats:
        units_by_name[s.room_type_name] = max(units_by_name.get(s.room_type_name, 0), int(s.units or 0))
    names = list(units_by_name.keys())
    months = []
    for m in range(1, 13):
        rows = []
        for nm in names:
            rec = next((s for s in stats if s.room_type_name == nm and s.month == m), None)
            na = float(rec.nights_available) if rec else 0.0
            no = float(rec.nights_occupied) if rec else 0.0
            rev = float(rec.revenue) if rec else 0.0
            pax = float(rec.pax) if rec else 0.0
            rows.append({"room_type_id": nm, "room_type_code": cf(nm), "room_type_name": nm, "units": units_by_name[nm],
                         "nights_available": na, "nights_occupied": no,
                         "occupancy_pct": (no / na) if na else 0.0, "revenue": rev,
                         "adr": (rev / no) if no else 0.0, "pax": pax})
        months.append({"month": m, "rows": rows})
    # anual
    annual = []
    for nm in names:
        na = sum(float(s.nights_available) for s in stats if s.room_type_name == nm)
        no = sum(float(s.nights_occupied) for s in stats if s.room_type_name == nm)
        rev = sum(float(s.revenue) for s in stats if s.room_type_name == nm)
        pax = sum(float(s.pax) for s in stats if s.room_type_name == nm)
        annual.append({"room_type_id": nm, "room_type_code": cf(nm), "room_type_name": nm, "units": units_by_name[nm],
                       "nights_available": na, "nights_occupied": no,
                       "occupancy_pct": (no / na) if na else 0.0, "revenue": rev,
                       "adr": (rev / no) if no else 0.0, "pax": pax})
    return {"scenario_id": scenario_id, "year": year, "source": "actuals",
            "room_types": [{"id": nm, "code": cf(nm), "name": nm, "units": units_by_name[nm]} for nm in names],
            "months": months, "annual": annual}


@router.get("/scenarios/{scenario_id}/revenue/by-room-type/")
async def get_revenue_by_room_type(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Revenue por tipo de habitación, mes a mes + anual (reporte "Ingresos por
    tipo"). Si el escenario tiene room stats REALES (de Opera), los devuelve;
    si no, los calcula de los drivers (budget/forecast)."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    actuals = await _room_stats_from_actuals(scenario_id, scenario.year, db)
    if actuals is not None:
        return actuals
    data = await _load_revenue_data(scenario_id, db)
    room_type_units = {rt.id: rt.units for rt in data["room_types"]}
    names = {rt.id: rt.name for rt in data["room_types"]}
    codes = {rt.id: getattr(rt, "code", "") for rt in data["room_types"]}

    rates_by_month: dict[int, list] = {}
    for rc in data["rate_cards"]:
        rates_by_month.setdefault(rc.month, []).append(rc)
    occ_by_month: dict[int, list] = {}
    for ob in data["occupancies"]:
        occ_by_month.setdefault(ob.month, []).append(ob)

    months = []
    for m in range(1, 13):
        rows = room_type_breakdown(
            m, rates_by_month.get(m, []), occ_by_month.get(m, []), room_type_units)
        for r in rows:
            r["room_type_name"] = names.get(r["room_type_id"], r["room_type_id"])
            r["room_type_code"] = codes.get(r["room_type_id"], "")
        months.append({"month": m, "rows": rows})

    return {
        "scenario_id": scenario_id,
        "year": scenario.year,
        "room_types": [{"id": rt.id, "code": getattr(rt, "code", ""), "name": rt.name, "units": rt.units}
                       for rt in data["room_types"]],
        "months": months,
        "annual": _aggregate_room_type(months, room_type_units, names, codes),
    }


@router.post("/scenarios/{scenario_id}/import-room-stats/", dependencies=[Depends(registro_de_subida)])
async def import_room_stats(
    scenario_id: str,
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Importa la hoja 'Room Stats' (estadística REAL por tipo de habitación,
    de Opera/PMS) a un escenario. **Merge por mes:** reemplaza SOLO los meses
    presentes en el archivo y preserva los demás → cada mes se sube el mes
    cerrado y el YTD se acumula solo. `dry_run=true` muestra la vista previa sin
    guardar."""
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    from app.importers.room_stats_importer import parse_room_stats
    scenario = await _get_scenario_or_404(scenario_id, db)
    raw = await file.read()
    try:
        flat = parse_room_stats(raw)
    except Exception as e:  # noqa: BLE001
        raise ErrorApi(422, "room_stats.no_se_pudo_leer", detalle=str(e))
    if not flat:
        raise ErrorApi(422, "room_stats.sin_bloques_mensuales")

    months_present = sorted({r["month"] for r in flat})
    by_room = {}
    for r in flat:
        by_room.setdefault(r["room_type_name"], 0)
    preview = {
        "scenario_id": scenario_id, "scenario": f"{scenario.type} {scenario.version} {scenario.year}",
        "months_present": months_present, "room_types": sorted(by_room.keys()),
        "rows": len(flat),
        "total_revenue": round(sum(r["revenue"] for r in flat), 2),
        "total_nights_occupied": round(sum(r["nights_occupied"] for r in flat), 2),
    }
    if dry_run:
        return {"dry_run": True, **preview}

    # merge por mes: borrar los meses presentes y reinsertar
    await db.execute(delete(ActualRoomStat).where(
        ActualRoomStat.scenario_id == scenario_id,
        ActualRoomStat.month.in_(months_present)))
    for r in flat:
        db.add(ActualRoomStat(
            scenario_id=scenario_id, room_type_name=r["room_type_name"], month=r["month"],
            units=r["units"], nights_available=r["nights_available"],
            nights_occupied=r["nights_occupied"], revenue=r["revenue"], pax=r["pax"]))
    await db.commit()
    return {"dry_run": False, "imported": True, **preview}


# ──────────────────────── Balance Sheet (Integrity) ─────────────────────────
@router.post("/scenarios/{scenario_id}/import-balance-sheet/", dependencies=[Depends(registro_de_subida)])
async def import_balance_sheet(
    scenario_id: str,
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Importa el Balance Sheet (bloque 'Balance Sheet Summary' de la hoja
    'Balance Sheet' del Excel de contabilidad/Integrity) a un escenario.
    **Merge por (año, mes):** reemplaza solo los períodos presentes en el
    archivo y preserva los demás. `dry_run=true` = vista previa sin guardar."""
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    from app.importers.balance_sheet_importer import parse_balance_sheet
    scenario = await _get_scenario_or_404(scenario_id, db)
    raw = await file.read()
    import io
    try:
        parsed = parse_balance_sheet(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001
        raise ErrorApi(422, "balance_sheet.no_se_pudo_leer", detalle=str(e))
    periods = parsed["periods"]
    lines = parsed["lines"]
    if not periods or not lines:
        raise ErrorApi(422, "balance_sheet.sin_datos_en_el_archivo")

    def _total(ym, label_part):
        for ln in lines:
            if label_part in ln["label"].lower():
                usd = ln["values"].get((ym["year"], ym["month"]), (None, None))[0]
                return round(usd, 2) if usd is not None else None
        return None

    preview = {
        "scenario_id": scenario_id,
        "scenario": f"{scenario.type} {scenario.version} {scenario.year}",
        "periods": periods, "lines": len(lines),
        "check": [{"year": p["year"], "month": p["month"],
                   "total_assets": _total(p, "total assets"),
                   "total_liab_equity": _total(p, "capital & liab")} for p in periods[:3]],
    }
    if dry_run:
        return {"dry_run": True, **preview}

    ym_present = {(p["year"], p["month"]) for p in periods}
    for (yr, mo) in ym_present:
        await db.execute(delete(BalanceSheetLine).where(
            BalanceSheetLine.scenario_id == scenario_id,
            BalanceSheetLine.year == yr, BalanceSheetLine.month == mo))
    saved = 0
    for ln in lines:
        for (yr, mo), (usd, crc) in ln["values"].items():
            if usd is None and crc is None:
                continue
            db.add(BalanceSheetLine(
                scenario_id=scenario_id, year=yr, month=mo, order_idx=ln["order"],
                label=ln["label"][:200], indent=ln["indent"], section=ln["section"],
                is_total=ln["is_total"],
                usd=Decimal(str(round(usd or 0.0, 2))), crc=Decimal(str(round(crc or 0.0, 2)))))
            saved += 1
    await db.commit()
    return {"dry_run": False, "imported": True, "rows_saved": saved, **preview}


@router.get("/scenarios/{scenario_id}/balance-sheet/periods/")
async def get_balance_sheet_periods(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Períodos (año, mes) con Balance Sheet cargado para el escenario, desc."""
    await _get_scenario_or_404(scenario_id, db)
    recs = (await db.execute(select(BalanceSheetLine.year, BalanceSheetLine.month)
            .where(BalanceSheetLine.scenario_id == scenario_id).distinct())).all()
    periods = sorted({(r[0], r[1]) for r in recs}, reverse=True)
    return {"scenario_id": scenario_id,
            "periods": [{"year": y, "month": m} for y, m in periods]}


@router.get("/scenarios/{scenario_id}/balance-sheet/")
async def get_balance_sheet(
    scenario_id: str, year: int = Query(...), month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
):
    """Balance Sheet (Summary) de un (año, mes): líneas en orden con
    label/indent/section/is_total y montos USD + CRC."""
    await _get_scenario_or_404(scenario_id, db)
    recs = (await db.execute(select(BalanceSheetLine).where(
        BalanceSheetLine.scenario_id == scenario_id,
        BalanceSheetLine.year == year, BalanceSheetLine.month == month)
        .order_by(BalanceSheetLine.order_idx))).scalars().all()
    rows = [{"label": r.label, "indent": r.indent, "section": r.section,
             "is_total": r.is_total, "usd": float(r.usd), "crc": float(r.crc)} for r in recs]
    return {"scenario_id": scenario_id, "year": year, "month": month,
            "has_data": len(rows) > 0, "rows": rows}


@router.get("/scenarios/{scenario_id}/balance-sheet/matrix/")
async def get_balance_sheet_matrix(
    scenario_id: str, year: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Balance Sheet de TODO un año: filas en orden (label/indent/section/is_total)
    con los valores de cada mes (usd/crc) → vista de 12 columnas."""
    await _get_scenario_or_404(scenario_id, db)
    recs = (await db.execute(select(BalanceSheetLine).where(
        BalanceSheetLine.scenario_id == scenario_id,
        BalanceSheetLine.year == year)
        .order_by(BalanceSheetLine.month, BalanceSheetLine.order_idx))).scalars().all()
    months_present = sorted({r.month for r in recs})
    rowmap: dict[int, dict] = {}
    for r in recs:
        row = rowmap.get(r.order_idx)
        if row is None:
            row = {"order_idx": r.order_idx, "label": r.label, "indent": r.indent,
                   "section": r.section, "is_total": r.is_total, "usd": {}, "crc": {}}
            rowmap[r.order_idx] = row
        row["usd"][r.month] = float(r.usd)
        row["crc"][r.month] = float(r.crc)
    rows = [rowmap[k] for k in sorted(rowmap)]
    return {"scenario_id": scenario_id, "year": year,
            "months": months_present, "has_data": len(rows) > 0, "rows": rows}


@router.get("/scenarios/{scenario_id}/balance-sheet/export/excel/")
async def export_balance_sheet_excel(
    scenario_id: str,
    year: int = Query(0), month: int = Query(0, ge=0, le=12),
    db: AsyncSession = Depends(get_db),
):
    """Descarga la **plantilla Excel bloqueada** del Balance Sheet: histórico
    bloqueado + una columna del mes nuevo (editable) para llenar y volver a
    subir. `year`/`month` = mes nuevo a llenar (default = mes siguiente al
    último cargado). Round-trip con import-balance-sheet."""
    from app.export.balance_sheet_excel import export_balance_sheet_template
    from fastapi.responses import Response
    await _get_scenario_or_404(scenario_id, db)
    recs = (await db.execute(select(BalanceSheetLine).where(
        BalanceSheetLine.scenario_id == scenario_id)
        .order_by(BalanceSheetLine.order_idx))).scalars().all()
    if not recs:
        raise ErrorApi(404, "balance_sheet.no_cargado")

    periods = sorted({(r.year, r.month) for r in recs}, reverse=True)
    # mes nuevo a llenar
    if year and month:
        new_ym = (year, month)
    else:
        ly, lm = periods[0]
        new_ym = (ly + 1, 1) if lm == 12 else (ly, lm + 1)

    # plantilla de filas tomada del período más reciente
    latest = periods[0]
    template = [r for r in recs if (r.year, r.month) == latest]
    template.sort(key=lambda r: r.order_idx)
    by_order: dict[int, dict] = {}
    for r in recs:
        by_order.setdefault(r.order_idx, {})[(r.year, r.month)] = float(r.usd)

    rows = [{"label": t.label, "indent": t.indent, "is_total": t.is_total,
             "section": t.section, "values": by_order.get(t.order_idx, {})}
            for t in template]
    columns = ([{"year": new_ym[0], "month": new_ym[1], "editable": True}]
               + [{"year": y, "month": m, "editable": False} for (y, m) in periods
                  if (y, m) != new_ym])

    data = export_balance_sheet_template(columns, rows)
    fname = f"Balance_Sheet_{new_ym[0]}_{new_ym[1]:02d}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


OTROS_ROOMS = "Other Rooms Revenue"   # ingreso de habitaciones sin tipo asociado


async def _canonical_room_types(db: AsyncSession) -> list[tuple[str, int]]:
    """Tipos de habitación activos de ESTA propiedad, de la base.

    Antes salían de `CWL_ROOM_TYPES`, los seis de Corcovado con sus 30
    unidades. Esta lista alimenta la pantalla donde se digitan las
    estadísticas REALES del mes, y `room_type_name` es lo que se persiste: en
    Amarena las noches se habrían guardado bajo «Sirena Suites», un tipo de
    habitación que ese hotel no tiene. Sin error y sin aviso.

    El código de cada categoría es canónico y NO cambia entre propiedades
    (owner, 2026-08-13): lo único que cambia es la descripción. Por eso lo que
    liga es `RoomTypeConfig`, que ya lleva el código fijo.
    """
    filas = (await db.execute(
        select(RoomTypeConfig)
        .where(RoomTypeConfig.hotel_id == HOTEL_ID, RoomTypeConfig.active == True)  # noqa: E712
        .order_by(RoomTypeConfig.sort_order)
    )).scalars().all()
    return [(f.name, f.units) for f in filas] + [(OTROS_ROOMS, 0)]


async def _otb_units(db: AsyncSession) -> int:
    """Inventario de la propiedad. Estaba clavado en 30 —el de Corcovado— así
    que la ocupación y el RevPAR del On The Books de cualquier otro hotel
    salían mal, y nada lo advertía."""
    total = (await db.execute(
        select(func.coalesce(func.sum(RoomTypeConfig.units), 0))
        .where(RoomTypeConfig.hotel_id == HOTEL_ID, RoomTypeConfig.active == True)  # noqa: E712
    )).scalar_one()
    return int(total or 0)


@router.get("/scenarios/{scenario_id}/room-stats-entry/{month}/")
async def get_room_stats_entry(scenario_id: str, month: int, db: AsyncSession = Depends(get_db)):
    """Filas editables para CARGA MANUAL de room stats reales de un mes:
    tipos de habitación (con units) + 'Other Rooms Revenue', con los valores
    ya guardados (si hay). El usuario digita/pega noches ocupadas, pax y revenue."""
    import calendar
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")
    scenario = await _get_scenario_or_404(scenario_id, db)
    existing = {s.room_type_name: s for s in (await db.execute(select(ActualRoomStat).where(
        ActualRoomStat.scenario_id == scenario_id, ActualRoomStat.month == month))).scalars().all()}
    days = calendar.monthrange(scenario.year, month)[1]
    rows = []
    for nm, units in await _canonical_room_types(db):
        ex = existing.get(nm)
        rows.append({"room_type_name": nm, "units": units, "nights_available": units * days,
                     "nights_occupied": float(ex.nights_occupied) if ex else 0.0,
                     "revenue": float(ex.revenue) if ex else 0.0,
                     "pax": float(ex.pax) if ex else 0.0})
    return {"scenario_id": scenario_id, "year": scenario.year, "month": month,
            "days_in_month": days, "rows": rows}


class RoomStatRowIn(BaseModel):
    room_type_name: str
    units: int = 0
    nights_occupied: float = 0
    revenue: float = 0
    pax: float = 0


class RoomStatsEntryIn(BaseModel):
    rows: list[RoomStatRowIn]


@router.put("/scenarios/{scenario_id}/room-stats-entry/{month}/")
async def put_room_stats_entry(
    scenario_id: str, month: int, body: RoomStatsEntryIn, db: AsyncSession = Depends(get_db)
):
    """Guarda (upsert) los room stats reales de un mes. Reemplaza solo ese mes
    (los demás meses quedan intactos → YTD acumula solo)."""
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    import calendar
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")
    scenario = await _get_scenario_or_404(scenario_id, db)
    days = calendar.monthrange(scenario.year, month)[1]
    await db.execute(delete(ActualRoomStat).where(
        ActualRoomStat.scenario_id == scenario_id, ActualRoomStat.month == month))
    saved = 0
    for r in body.rows:
        if not (r.nights_occupied or r.revenue or r.pax):
            continue  # fila vacía
        db.add(ActualRoomStat(
            scenario_id=scenario_id, room_type_name=r.room_type_name, month=month,
            units=r.units, nights_available=(r.units or 0) * days,
            nights_occupied=r.nights_occupied, revenue=r.revenue, pax=r.pax))
        saved += 1
    await db.commit()
    return {"saved": True, "month": month, "rows_saved": saved}



@router.get("/scenarios/{scenario_id}/onthebooks/")
async def get_on_the_books(
    scenario_id: str, week: int = Query(20, ge=1, le=53), year: int | None = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """On The Books (reservas a la fecha) por mes para la SEMANA snapshot `week`
    y el AÑO `year` (default: el año del escenario — el XML del owner trae
    horizonte multi-año en el mismo archivo, así que `year` elige cuál de esos
    años se está mirando): total_revenue, rooms_revenue, rooms_available
    (units×días), rooms_occupied, guests, ADR, occupancy."""
    import calendar
    scenario = await _get_scenario_or_404(scenario_id, db)
    hotel = scenario.hotel_id  # el OTB es de la propiedad, no del escenario
    anio = year if year is not None else scenario.year
    rows_db = {e.month: e for e in (await db.execute(select(OnTheBooksEntry).where(
        OnTheBooksEntry.hotel_id == hotel, OnTheBooksEntry.week == week,
        OnTheBooksEntry.year == anio))).scalars().all()}
    unidades = await _otb_units(db)
    months = []
    for m in range(1, 13):
        e = rows_db.get(m)
        days = calendar.monthrange(anio, m)[1]
        avail = unidades * days
        rev = float(e.total_revenue) if e else 0.0
        rrev = float(e.rooms_revenue) if e else 0.0
        occ = float(e.rooms_occupied) if e else 0.0
        gst = float(e.guests) if e else 0.0
        months.append({"month": m, "total_revenue": rev, "rooms_revenue": rrev,
                       "rooms_available": avail, "rooms_occupied": occ, "guests": gst,
                       "adr": (rrev / occ) if occ else 0.0,
                       "occupancy_pct": (occ / avail) if avail else 0.0})
    return {"scenario_id": scenario_id, "year": anio, "week": week, "has_data": bool(rows_db), "months": months}


@router.get("/scenarios/{scenario_id}/otb-weeks/")
async def get_otb_weeks(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Semanas (snapshots) con datos OTB cargados, ascendente. Alimenta el
    selector de "comparar con semana anterior"."""
    # El OTB es de la PROPIEDAD: el escenario solo dice de dónde se pidió.
    hotel = (await _get_scenario_or_404(scenario_id, db)).hotel_id
    weeks = (await db.execute(
        select(OnTheBooksEntry.week).where(OnTheBooksEntry.hotel_id == hotel).distinct()
    )).scalars().all()
    return {"scenario_id": scenario_id, "weeks": sorted({int(w) for w in weeks})}


@router.get("/scenarios/{scenario_id}/otb-years/")
async def get_otb_years(scenario_id: str, week: int | None = Query(None), db: AsyncSession = Depends(get_db)):
    """Años con datos OTB cargados (el XML trae horizonte multi-año en el
    mismo archivo). Con `week`, solo los años presentes EN esa semana."""
    # El OTB es de la PROPIEDAD: el escenario solo dice de dónde se pidió.
    hotel = (await _get_scenario_or_404(scenario_id, db)).hotel_id
    cond = [OnTheBooksEntry.hotel_id == hotel]
    if week is not None:
        cond.append(OnTheBooksEntry.week == week)
    years = (await db.execute(
        select(OnTheBooksEntry.year).where(*cond).distinct()
    )).scalars().all()
    return {"scenario_id": scenario_id, "years": sorted({int(y) for y in years})}


@router.get("/scenarios/{scenario_id}/otb-params/")
async def get_otb_params(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """% de venta en propiedad por semana (parte del historial). Devuelve un mapa
    {week: pct}. Default 0.126 cuando una semana no tiene valor guardado."""
    # El OTB es de la PROPIEDAD: el escenario solo dice de dónde se pidió.
    hotel = (await _get_scenario_or_404(scenario_id, db)).hotel_id
    rows = (await db.execute(select(OtbWeekParam).where(
        OtbWeekParam.hotel_id == hotel))).scalars().all()
    return {"scenario_id": scenario_id, "default": 0.126,
            "by_week": {int(r.week): float(r.on_prop_pct) for r in rows}}


class OtbParamIn(BaseModel):
    on_prop_pct: float = 0.126


@router.put("/scenarios/{scenario_id}/otb-params/")
async def put_otb_param(
    scenario_id: str, body: OtbParamIn, week: int = Query(..., ge=1, le=53),
    db: AsyncSession = Depends(get_db),
):
    """Guarda el % de venta en propiedad para la SEMANA `week` (upsert)."""
    # SIN candado, a propósito — ver la nota en `import_otb_xml`.
    # El OTB es de la PROPIEDAD: el escenario solo dice de dónde se pidió.
    hotel = (await _get_scenario_or_404(scenario_id, db)).hotel_id
    row = (await db.execute(select(OtbWeekParam).where(
        OtbWeekParam.hotel_id == hotel, OtbWeekParam.week == week))).scalar_one_or_none()
    pct = max(0.0, min(1.0, body.on_prop_pct))
    if row:
        row.on_prop_pct = pct
    else:
        db.add(OtbWeekParam(hotel_id=hotel, scenario_id=scenario_id, week=week, on_prop_pct=pct))
    await db.commit()
    return {"scenario_id": scenario_id, "week": week, "on_prop_pct": pct}


@router.get("/scenarios/{scenario_id}/otb-pacing/")
async def get_otb_pacing(scenario_id: str, year: int | None = Query(None), db: AsyncSession = Depends(get_db)):
    """Serie de TODAS las semanas (snapshots) cargadas para el AÑO `year`
    (default: el año del escenario): revenue total y noches ocupadas de ese
    año en cada una — el pace semana a semana. Alimenta Pacing (8.4): cuánto
    se movió el OTB de una carga a la siguiente."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    hotel = scenario.hotel_id  # el OTB es de la propiedad, no del escenario
    anio = year if year is not None else scenario.year
    weeks = sorted({int(w) for w in (await db.execute(
        select(OnTheBooksEntry.week).where(
            OnTheBooksEntry.hotel_id == hotel, OnTheBooksEntry.year == anio).distinct()
    )).scalars().all()})
    unidades = await _otb_units(db)
    snapshots = []
    for wk in weeks:
        rows = (await db.execute(select(OnTheBooksEntry).where(
            OnTheBooksEntry.hotel_id == hotel, OnTheBooksEntry.week == wk,
            OnTheBooksEntry.year == anio
        ))).scalars().all()
        total_revenue = sum(float(r.total_revenue) for r in rows)
        rooms_occupied = sum(float(r.rooms_occupied) for r in rows)
        snapshots.append({"week": wk, "total_revenue": round(total_revenue, 2),
                          "rooms_occupied": rooms_occupied})
    for i, s in enumerate(snapshots):
        prev = snapshots[i - 1]["total_revenue"] if i > 0 else None
        s["delta_vs_prev"] = round(s["total_revenue"] - prev, 2) if prev is not None else None
    return {"scenario_id": scenario_id, "year": anio,
            "rooms_available": unidades, "snapshots": snapshots}


@router.delete("/scenarios/{scenario_id}/otb/")
async def clear_otb(
    scenario_id: str, week: int | None = Query(None, ge=1, le=53),
    db: AsyncSession = Depends(get_db),
):
    """Borra el OTB (mensual + heatmap diario). Sin `week` → borra TODAS las
    semanas (reset para volver a subir desde 0). Con `week` → solo esa semana."""
    # SIN candado, a propósito — ver la nota en `import_otb_xml`.
    # El OTB es de la PROPIEDAD: el escenario solo dice de dónde se pidió.
    hotel = (await _get_scenario_or_404(scenario_id, db)).hotel_id
    ent_cond = [OnTheBooksEntry.hotel_id == hotel]
    day_cond = [OtbDailyOcc.hotel_id == hotel]
    if week is not None:
        ent_cond.append(OnTheBooksEntry.week == week)
        day_cond.append(OtbDailyOcc.week == week)
    r1 = await db.execute(delete(OnTheBooksEntry).where(*ent_cond))
    r2 = await db.execute(delete(OtbDailyOcc).where(*day_cond))
    par_cond = [OtbWeekParam.hotel_id == hotel]
    if week is not None:
        par_cond.append(OtbWeekParam.week == week)
    await db.execute(delete(OtbWeekParam).where(*par_cond))
    await db.commit()
    return {"cleared": True, "scenario_id": scenario_id, "week": week,
            "months_deleted": r1.rowcount or 0, "daily_deleted": r2.rowcount or 0}


@router.get("/scenarios/{scenario_id}/onthebooks-entry/")
async def get_otb_entry(
    scenario_id: str, week: int = Query(20, ge=1, le=53), year: int | None = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """12 filas editables (una por mes) para carga manual/paste del OTB de la
    semana `week` y el año `year` (default: el año del escenario)."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    hotel = scenario.hotel_id  # el OTB es de la propiedad, no del escenario
    anio = year if year is not None else scenario.year
    rows_db = {e.month: e for e in (await db.execute(select(OnTheBooksEntry).where(
        OnTheBooksEntry.hotel_id == hotel, OnTheBooksEntry.week == week,
        OnTheBooksEntry.year == anio))).scalars().all()}
    rows = []
    for m in range(1, 13):
        e = rows_db.get(m)
        rows.append({"month": m, "total_revenue": float(e.total_revenue) if e else 0.0,
                     "rooms_revenue": float(e.rooms_revenue) if e else 0.0,
                     "rooms_occupied": float(e.rooms_occupied) if e else 0.0,
                     "guests": float(e.guests) if e else 0.0})
    return {"scenario_id": scenario_id, "week": week, "year": anio, "rows": rows}


class OtbRowIn(BaseModel):
    month: int
    total_revenue: float = 0
    rooms_revenue: float = 0
    rooms_occupied: float = 0
    guests: float = 0


class OtbEntryIn(BaseModel):
    rows: list[OtbRowIn]


@router.put("/scenarios/{scenario_id}/onthebooks-entry/")
async def put_otb_entry(
    scenario_id: str, body: OtbEntryIn, week: int = Query(20, ge=1, le=53),
    year: int | None = Query(None), db: AsyncSession = Depends(get_db),
):
    """Guarda (upsert) el OTB de la SEMANA `week` y el AÑO `year` (default: el
    año del escenario): reemplaza los 12 meses de esa semana/año con lo
    enviado (preserva las otras semanas y años → histórico de pace)."""
    # SIN candado, a propósito — ver la nota en `import_otb_xml`.
    scenario = await _get_scenario_or_404(scenario_id, db)
    hotel = scenario.hotel_id  # el OTB es de la propiedad, no del escenario
    anio = year if year is not None else scenario.year
    await db.execute(delete(OnTheBooksEntry).where(
        OnTheBooksEntry.hotel_id == hotel, OnTheBooksEntry.week == week,
        OnTheBooksEntry.year == anio))
    saved = 0
    for r in body.rows:
        if not (1 <= r.month <= 12):
            continue
        if not (r.total_revenue or r.rooms_revenue or r.rooms_occupied or r.guests):
            continue
        db.add(OnTheBooksEntry(hotel_id=hotel, scenario_id=scenario_id, week=week, year=anio, month=r.month,
                               total_revenue=r.total_revenue, rooms_revenue=r.rooms_revenue,
                               rooms_occupied=r.rooms_occupied, guests=r.guests))
        saved += 1
    await db.commit()
    return {"saved": True, "week": week, "year": anio, "rows_saved": saved}


@router.get("/scenarios/{scenario_id}/daily-occ/")
async def get_daily_occ(
    scenario_id: str, week: int = Query(20, ge=1, le=53), year: int | None = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Heatmap de ocupación DIARIA on-the-books de la semana `week` y el año
    `year` (default: el año del escenario). Por mes×día: rooms_sold y occ_pct
    (=rooms_sold/inventario)."""
    import calendar
    scenario = await _get_scenario_or_404(scenario_id, db)
    hotel = scenario.hotel_id  # el OTB es de la propiedad, no del escenario
    anio = year if year is not None else scenario.year
    recs = (await db.execute(select(OtbDailyOcc).where(
        OtbDailyOcc.hotel_id == hotel, OtbDailyOcc.week == week,
        OtbDailyOcc.year == anio))).scalars().all()
    by = {(r.month, r.day): float(r.rooms_sold) for r in recs}
    inv = await _otb_units(db)
    months = []
    for m in range(1, 13):
        ndays = calendar.monthrange(anio, m)[1]
        days = []
        tot_occ = 0.0
        for d in range(1, 32):
            if d > ndays:
                days.append(None)
                continue
            sold = by.get((m, d), 0.0)
            occ = sold / inv if inv else 0.0
            tot_occ += occ
            days.append({"day": d, "rooms_sold": sold, "occ_pct": occ})
        months.append({"month": m, "ndays": ndays, "avg_occ": (tot_occ / ndays) if ndays else 0.0, "days": days})
    return {"scenario_id": scenario_id, "year": anio, "week": week,
            "inventory": inv, "has_data": bool(recs), "months": months}


@router.get("/scenarios/{scenario_id}/daily-occ-entry/")
async def get_daily_occ_entry(
    scenario_id: str, week: int = Query(20, ge=1, le=53), year: int | None = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """Grilla 12 meses × 31 días (rooms sold) para carga manual/paste, del año
    `year` (default: el año del escenario)."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    hotel = scenario.hotel_id  # el OTB es de la propiedad, no del escenario
    anio = year if year is not None else scenario.year
    recs = (await db.execute(select(OtbDailyOcc).where(
        OtbDailyOcc.hotel_id == hotel, OtbDailyOcc.week == week,
        OtbDailyOcc.year == anio))).scalars().all()
    by = {(r.month, r.day): float(r.rooms_sold) for r in recs}
    rows = []
    for m in range(1, 13):
        rows.append({"month": m, "days": [by.get((m, d), 0.0) for d in range(1, 32)]})
    return {"scenario_id": scenario_id, "week": week, "year": anio, "rows": rows}


class DailyOccRowIn(BaseModel):
    month: int
    days: list[float]   # 31 valores (rooms sold)


class DailyOccEntryIn(BaseModel):
    rows: list[DailyOccRowIn]


@router.put("/scenarios/{scenario_id}/daily-occ-entry/")
async def put_daily_occ_entry(
    scenario_id: str, body: DailyOccEntryIn, week: int = Query(20, ge=1, le=53),
    year: int | None = Query(None), db: AsyncSession = Depends(get_db),
):
    """Guarda (upsert) la ocupación diaria de la semana/año: reemplaza solo
    ese año dentro de esa semana."""
    # SIN candado, a propósito — ver la nota en `import_otb_xml`.
    scenario = await _get_scenario_or_404(scenario_id, db)
    hotel = scenario.hotel_id  # el OTB es de la propiedad, no del escenario
    anio = year if year is not None else scenario.year
    await db.execute(delete(OtbDailyOcc).where(
        OtbDailyOcc.hotel_id == hotel, OtbDailyOcc.week == week,
        OtbDailyOcc.year == anio))
    saved = 0
    for r in body.rows:
        if not (1 <= r.month <= 12):
            continue
        for i, sold in enumerate(r.days[:31]):
            d = i + 1
            if not sold:
                continue
            db.add(OtbDailyOcc(hotel_id=hotel, scenario_id=scenario_id, week=week, year=anio, month=r.month, day=d,
                               rooms_sold=sold))
            saved += 1
    await db.commit()
    return {"saved": True, "week": week, "year": anio, "cells_saved": saved}


def _otb_agrega_por_dia(rows: list[dict]) -> dict[tuple[int, int, int], dict[str, float]]:
    """`{(year, month, day): {rooms_sold, revenue, pax}}` SIN contar dos veces.

    ⚠️ ANTES SUMABA TODO, y por eso el On the Books salía al doble.

    El XML de Opera trae dos bloques —`G_REC_TYPE` A_STAT (History) y B_FORE
    (Forecast)— y el parser recorría el árbol entero, así que un día presente
    en los dos se sumaba. El comentario de esta misma función ya advertía el
    riesgo («el revenue mensual habría sumado ese día DOBLE en silencio») y era
    lo que estaba pasando: enero con 1.353 noches vendidas en un hotel de 30
    habitaciones —132% de ocupación— y $6.315.043 de OTB contra $4.872.775 de
    presupuesto (owner, 2026-08-18: «ninguno de los escenarios tiene ese saldo»).

    Ahora la regla vive en `elegir_por_dia`: dentro de un bloque se suma —Opera
    abre el día por market o tipo de habitación—; entre bloques gana History,
    que es lo ocurrido.
    """
    from app.importers.opera_history_forecast import elegir_por_dia
    return elegir_por_dia(rows)


@router.post("/scenarios/{scenario_id}/import-otb-xml/", dependencies=[Depends(registro_de_subida)])
async def import_otb_xml(
    scenario_id: str,
    week: int = Query(20, ge=1, le=53),
    full_revenue: UploadFile = File(...),
    only_rooms: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
):
    """Importa el XML 'History Forecast' de Opera (día a día) a la SEMANA
    `week`. El archivo trae horizonte MULTI-AÑO (forecast varios años
    adelante del corte, en el mismo XML) — cada fila se guarda con SU año
    real, tomado de la fecha (no se asume el año del escenario). Alimenta a
    la vez: On the Books mensual (revenue/rooms/pax por mes×año) y el Daily
    Occupancy Heatmap (rooms sold por día×año). `full_revenue` = revenue
    total; `only_rooms` (opcional) = rooms revenue (para separar el rooms
    revenue). Reemplaza SOLO esta semana — no toca las demás, ni otros años
    cargados en otra semana."""
    # ⚠️ SIN candado, a propósito. El On the Books NO es parte del presupuesto.
    #
    # «El escenario es solo una referencia comparativa, pero no tiene nada que
    # ver con las subidas» (owner, 18-ago-2026). Lo que entra por acá son las
    # reservas que YA existen en Opera: un hecho observado, no una cifra que
    # alguien presupuestó. Enllavar un escenario congela SUS números, y el
    # candado se había quedado puesto por inercia sobre las cinco rutas de OTB
    # —esta, `put_otb_entry`, `put_daily_occ_entry`, `put_otb_param` y
    # `clear_otb`—. El resultado: subir el XML teniendo elegido un presupuesto
    # cerrado moría con un 409 «está bloqueado (status=locked)», cuando la
    # subida no tocaba ni una cifra de ese presupuesto.
    from app.importers.opera_history_forecast import (
        parse_history_forecast, dias_duplicados)
    # El OTB es de la PROPIEDAD: el escenario solo dice de dónde se pidió.
    hotel = (await _get_scenario_or_404(scenario_id, db)).hotel_id
    try:
        a = parse_history_forecast(await full_revenue.read())
        b = parse_history_forecast(await only_rooms.read()) if only_rooms is not None else []
    except Exception as e:  # noqa: BLE001
        raise ErrorApi(422, "xml.no_se_pudo_leer", detalle=str(e))
    if not a:
        raise ErrorApi(422, "xml.sin_dias")
    # Auto-detección por monto (sin depender del nombre del archivo): el de MAYOR
    # revenue total = Total Revenue; el otro = Rooms Only. El resto de campos
    # (rooms sold, pax, fechas) son iguales en ambos.
    if b:
        fy_a = sum(r["revenue"] for r in a)
        fy_b = sum(r["revenue"] for r in b)
        full, rooms = (a, b) if fy_a >= fy_b else (b, a)
    else:
        full, rooms = a, []

    # Se agrega por (year, month, day) antes de usar cualquiera de las dos
    # listas — ver el docstring de `_otb_agrega_por_dia`.
    full_by_day = _otb_agrega_por_dia(full)
    rooms_rev_by = {k: v["revenue"] for k, v in _otb_agrega_por_dia(rooms).items()}
    anos = sorted({y for (y, _, _) in full_by_day})

    # 1) Daily heatmap (rooms sold por día). Se borra TODO lo de esta semana
    #    (todos los años) antes de reinsertar: es un reemplazo completo de la
    #    foto de esa semana, no un merge parcial — las DEMÁS semanas (el
    #    historial de pace) no se tocan.
    await db.execute(delete(OtbDailyOcc).where(
        OtbDailyOcc.hotel_id == hotel, OtbDailyOcc.week == week))
    daily_cells = 0
    for (year, month, day), v in full_by_day.items():
        if v["rooms_sold"]:
            db.add(OtbDailyOcc(hotel_id=hotel, scenario_id=scenario_id, week=week, year=year, month=month,
                               day=day, rooms_sold=v["rooms_sold"]))
            daily_cells += 1

    # 2) On the Books mensual (agregado por año×mes)
    bym: dict[tuple[int, int], dict[str, float]] = {}
    for (year, month, day), v in full_by_day.items():
        acc = bym.setdefault((year, month), {"tr": 0.0, "rr": 0.0, "ro": 0.0, "gu": 0.0})
        acc["tr"] += v["revenue"]
        acc["ro"] += v["rooms_sold"]
        acc["gu"] += v["pax"]
        acc["rr"] += rooms_rev_by.get((year, month, day), 0.0)
    await db.execute(delete(OnTheBooksEntry).where(
        OnTheBooksEntry.hotel_id == hotel, OnTheBooksEntry.week == week))
    months_saved = 0
    for (year, mon), v in bym.items():
        if v["tr"] or v["ro"]:
            db.add(OnTheBooksEntry(hotel_id=hotel, scenario_id=scenario_id, week=week, year=year, month=mon,
                                   total_revenue=round(v["tr"], 2), rooms_revenue=round(v["rr"], 2),
                                   rooms_occupied=v["ro"], guests=v["gu"]))
            months_saved += 1
    # ⚠️ CANDADO: una ocupación imposible no se guarda.
    #
    # Un mes no puede vender más noches que las que tiene. Cuando el OTB salió
    # al doble nadie se enteró por meses: el número era grande pero plausible a
    # simple vista, y solo se cayó cuando el owner lo comparó contra los
    # escenarios. Esto lo vuelve imposible de repetir en silencio.
    from app.models.otb_week_param import OtbWeekParam as _OWP
    _uni = (await db.execute(select(_OWP).where(_OWP.scenario_id == scenario_id))).scalars().first()
    unidades = int(getattr(_uni, "units", 0) or 0) or 33
    imposibles = []
    for (year, mon), v in bym.items():
        disponibles = calendar.monthrange(year, mon)[1] * unidades
        if v["ro"] > disponibles:
            imposibles.append(f"{year}-{mon:02d}: {v['ro']:,.0f} noches vendidas contra "
                              f"{disponibles:,} disponibles ({v['ro'] / disponibles:.0%})")
    if imposibles:
        raise ErrorApi(422, "otb.ocupacion_imposible",
                       meses=" · ".join(imposibles[:6]))

    await db.commit()
    duplicados = dias_duplicados(full)

    # El desglose POR AÑO, no un total que los mezcle.
    #
    # Antes esto devolvía `full_year_revenue` = la suma de TODOS los días del
    # archivo. El horizonte del owner llega a 5 años en el mismo XML, así que
    # ese "FY revenue" era 2026+2027+2028 sumados: $6.315.043 cuando el 2026
    # solo eran $4.513.865. El owner lo cazó porque «ninguno de los escenarios
    # tiene ese saldo» — y no lo tenía ninguno, era de tres años a la vez.
    # Un archivo multi-año no tiene UN total; tiene uno por año.
    por_anio = []
    for a in sorted(anos):
        filas = [v for (y, m), v in bym.items() if y == a]
        por_anio.append({"year": a,
                         "revenue": round(sum(f["tr"] for f in filas), 2),
                         "noches": round(sum(f["ro"] for f in filas)),
                         "meses": len(filas)})
    return {"imported": True, "week": week, "years": anos, "days": len(full_by_day),
            "daily_cells": daily_cells, "months": months_saved,
            # Cuántos días venían en los DOS bloques. Si es alto, el archivo
            # solapa History y Forecast — y ahora se sabe, en vez de doblarse.
            "dias_en_ambos_bloques": len(duplicados),
            "por_anio": por_anio}


# ──────────────────────── Channel Mix (Market Set) ────────────────────────
def _norm_metric(metric: str) -> str:
    m = (metric or "rooms").lower()
    return m if m in CHANNEL_METRICS else "rooms"


async def _canales_del_mix(db: AsyncSession, scenario_id: str, metric: str) -> list[str]:
    """Los canales de la grilla: la semilla de ESTA propiedad + lo que ya hay.

    Antes esto era la constante `CWL_CHANNELS` escrita en el modelo, y tenia los
    dos defectos de siempre:

    1. **Se la servia a cualquier propiedad.** Amarena abria su Channel Mix con
       los cuatro canales de Corcovado y el PUT se los estampaba en su base.
    2. **Lo que la lista no nombraba, no se veia.** El GET sumaba TODAS las
       filas al total pero solo mostraba los canales de la constante: un canal
       guardado fuera de la lista entraba en el total, no aparecia en el detalle
       y los porcentajes no cerraban en 100%. Es la misma forma de fallar que le
       hizo mostrar 22 departamentos con 38 en la base.

    Por eso ahora se UNEN: primero la semilla, en su orden —que es el orden en
    que el PUT escribe—, y despues cualquier canal que el escenario ya tenga y
    la semilla no nombre. Lo guardado nunca desaparece de la pantalla.
    """
    from app.seed_data import semilla_cruda
    d = semilla_cruda("canales_mix") or {}
    canales = [str(c) for c in d.get("canales", [])]
    guardados = (await db.execute(select(ChannelMixEntry.channel).where(
        ChannelMixEntry.scenario_id == scenario_id,
        ChannelMixEntry.metric == metric).distinct())).scalars().all()
    return canales + sorted(c for c in set(guardados) if c not in canales)


@router.get("/scenarios/{scenario_id}/channel-mix/")
async def get_channel_mix(
    scenario_id: str, ytd: int = Query(12, ge=1, le=12),
    metric: str = Query("rooms"), db: AsyncSession = Depends(get_db)
):
    """Mix por canal acumulado YTD (meses 1..`ytd`) para una métrica
    (rooms|pax): value por canal + % del total. Los canales salen de
    `_canales_del_mix`: la semilla de la propiedad mas lo ya guardado."""
    await _get_scenario_or_404(scenario_id, db)
    metric = _norm_metric(metric)
    canales = await _canales_del_mix(db, scenario_id, metric)
    recs = (await db.execute(select(ChannelMixEntry).where(
        ChannelMixEntry.scenario_id == scenario_id,
        ChannelMixEntry.metric == metric,
        ChannelMixEntry.month <= ytd))).scalars().all()
    by = {ch: 0.0 for ch in canales}
    for r in recs:
        by[r.channel] = by.get(r.channel, 0.0) + float(r.value)
    total = sum(by.values())
    channels = [{"channel": ch, "value": by.get(ch, 0.0),
                 "pct": (by.get(ch, 0.0) / total if total else 0.0)} for ch in by]
    return {"scenario_id": scenario_id, "ytd": ytd, "metric": metric, "has_data": total > 0,
            "total": total, "channels": channels}


@router.get("/scenarios/{scenario_id}/channel-mix-entry/")
async def get_channel_mix_entry(
    scenario_id: str, metric: str = Query("rooms"), db: AsyncSession = Depends(get_db)
):
    """Grilla editable 12 meses × canales (value) para una métrica, carga manual/paste."""
    await _get_scenario_or_404(scenario_id, db)
    metric = _norm_metric(metric)
    recs = (await db.execute(select(ChannelMixEntry).where(
        ChannelMixEntry.scenario_id == scenario_id,
        ChannelMixEntry.metric == metric))).scalars().all()
    canales = await _canales_del_mix(db, scenario_id, metric)
    by = {(r.month, r.channel): float(r.value) for r in recs}
    rows = [{"month": m, "values": [by.get((m, ch), 0.0) for ch in canales]} for m in range(1, 13)]
    return {"scenario_id": scenario_id, "metric": metric, "channels": canales, "rows": rows}


class ChannelMixRowIn(BaseModel):
    month: int
    values: list[float]   # uno por canal, en el orden que devolvio el GET


class ChannelMixEntryIn(BaseModel):
    rows: list[ChannelMixRowIn]


@router.put("/scenarios/{scenario_id}/channel-mix-entry/")
async def put_channel_mix_entry(
    scenario_id: str, body: ChannelMixEntryIn,
    metric: str = Query("rooms"), db: AsyncSession = Depends(get_db)
):
    """Guarda el mix por canal de una métrica (reemplaza esa métrica del
    escenario: borra-luego-inserta por scenario+metric; valores 0 no se
    guardan). NO toca la otra métrica."""
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    await _get_scenario_or_404(scenario_id, db)
    metric = _norm_metric(metric)
    # Los canales se resuelven ANTES del borrado: despues la tabla esta vacia y
    # los que solo existian en la base —los que la semilla no nombra— se
    # perderian justo en el guardado que pretendia conservarlos.
    canales = await _canales_del_mix(db, scenario_id, metric)
    await db.execute(delete(ChannelMixEntry).where(
        ChannelMixEntry.scenario_id == scenario_id,
        ChannelMixEntry.metric == metric))
    saved = 0
    for r in body.rows:
        if not (1 <= r.month <= 12):
            continue
        for i, ch in enumerate(canales):
            v = r.values[i] if i < len(r.values) else 0.0
            if not v:
                continue
            db.add(ChannelMixEntry(scenario_id=scenario_id, month=r.month,
                                   channel=ch, metric=metric, value=v))
            saved += 1
    await db.commit()
    return {"saved": True, "metric": metric, "rows_saved": saved}


# ──────────────────────── Country Mix (país / mercado) ────────────────────────
def _norm_country_metric(metric: str) -> str:
    m = (metric or "rooms").lower()
    return m if m in COUNTRY_METRICS else "rooms"


@router.get("/scenarios/{scenario_id}/country-mix/")
async def get_country_mix(
    scenario_id: str, ytd: int = Query(12, ge=1, le=12),
    metric: str = Query("rooms"), db: AsyncSession = Depends(get_db)
):
    """Mix por país acumulado YTD (meses 1..`ytd`) para una métrica (rooms|pax):
    value por país + % del total, ordenado desc. Países dinámicos."""
    await _get_scenario_or_404(scenario_id, db)
    metric = _norm_country_metric(metric)
    recs = (await db.execute(select(CountryMixEntry).where(
        CountryMixEntry.scenario_id == scenario_id,
        CountryMixEntry.metric == metric,
        CountryMixEntry.month <= ytd))).scalars().all()
    by: dict[str, float] = {}
    for r in recs:
        by[r.country] = by.get(r.country, 0.0) + float(r.value)
    total = sum(by.values())
    countries = [{"country": c, "value": v, "pct": (v / total if total else 0.0)}
                 for c, v in sorted(by.items(), key=lambda kv: kv[1], reverse=True)]
    return {"scenario_id": scenario_id, "ytd": ytd, "metric": metric,
            "has_data": total > 0, "total": total, "countries": countries}


@router.get("/scenarios/{scenario_id}/country-mix-entry/")
async def get_country_mix_entry(
    scenario_id: str, metric: str = Query("rooms"), db: AsyncSession = Depends(get_db)
):
    """Grilla editable: una fila por país (12 meses) para una métrica."""
    await _get_scenario_or_404(scenario_id, db)
    metric = _norm_country_metric(metric)
    recs = (await db.execute(select(CountryMixEntry).where(
        CountryMixEntry.scenario_id == scenario_id,
        CountryMixEntry.metric == metric))).scalars().all()
    by: dict[str, dict[int, float]] = {}
    for r in recs:
        by.setdefault(r.country, {})[r.month] = float(r.value)
    # ordenar países por total desc
    order = sorted(by.keys(), key=lambda c: sum(by[c].values()), reverse=True)
    rows = [{"country": c, "values": [by[c].get(m, 0.0) for m in range(1, 13)]} for c in order]
    return {"scenario_id": scenario_id, "metric": metric, "rows": rows}


class CountryMixRowIn(BaseModel):
    country: str
    values: list[float]   # 12 meses (ene..dic)


class CountryMixEntryIn(BaseModel):
    rows: list[CountryMixRowIn]


@router.put("/scenarios/{scenario_id}/country-mix-entry/")
async def put_country_mix_entry(
    scenario_id: str, body: CountryMixEntryIn,
    metric: str = Query("rooms"), db: AsyncSession = Depends(get_db)
):
    """Guarda el mix por país de una métrica (reemplaza esa métrica del escenario:
    borra-luego-inserta por scenario+metric; valores 0 y países en blanco se
    omiten). NO toca la otra métrica."""
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    await _get_scenario_or_404(scenario_id, db)
    metric = _norm_country_metric(metric)
    await db.execute(delete(CountryMixEntry).where(
        CountryMixEntry.scenario_id == scenario_id,
        CountryMixEntry.metric == metric))
    saved = 0
    for r in body.rows:
        country = (r.country or "").strip()
        if not country:
            continue
        for m in range(1, 13):
            v = r.values[m - 1] if m - 1 < len(r.values) else 0.0
            if not v:
                continue
            db.add(CountryMixEntry(scenario_id=scenario_id, month=m,
                                   country=country, metric=metric, value=v,
                                   origen="manual",           # editado a mano
                                   actualizado_en=datetime.now(timezone.utc)))
            saved += 1
    await db.commit()
    return {"saved": True, "metric": metric, "rows_saved": saved}


@router.post("/scenarios/{scenario_id}/import-country-xml/", dependencies=[Depends(registro_de_subida)])
async def import_country_xml(
    scenario_id: str,
    file: UploadFile = File(...),
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
    sobrescribir: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Carga el `res_statistics1` de Opera: país de origen DE UN MES, noches y pax.

    «Yo tengo este XML de Opera donde están los países de dónde viene la gente.
    Los países acá listados son los más importantes; cualquiera que no se
    encuentre va a Others. Ocupo me los subas por mes y agregar los pax»
    (owner, 18-ago-2026).

    Tres cosas que hace y conviene tener presentes:

    1. **Escribe las DOS métricas.** El pax estaba vacío; el archivo lo trae
       (`IN_GUEST`) y no cuesta nada más leerlo.
    2. **La lista de países importantes es la que YA está cargada** en el
       escenario. Es literalmente «los países acá listados»: la pantalla es la
       lista. Si el escenario está vacío, se toman los diez de más noches del
       propio archivo para arrancar con algo, y se avisa.
    3. **Devuelve qué cayó en «Others»**, país por país. Con el archivo del
       owner, Alemania (64 noches), Francia (53) y España (45) quedan fuera de
       la lista y son MÁS GRANDES que Suecia (33) o Dinamarca (20), que sí
       están. Sin ese detalle, promover un país se decide a ciegas.

    ⚠️ **Un mes por subida.** El archivo trae el rango entero —el del owner,
    siete meses de una— pero se carga de a uno: sin `month`, y si el archivo
    trae más de uno, devuelve 409 con la lista para que se elija. Es la regla
    del owner y encaja con la otra: el mes se sube UNA vez y después se
    corrige. Cargando siete de un saque, subir el mes nuevo obligaría a pasar
    por encima de los seis anteriores, ya corregidos.
    """
    # SIN candado, a propósito — igual que el On the Books: esto son países de
    # huéspedes que ya se hospedaron, un hecho del PMS, no una cifra del
    # presupuesto. Ver la nota en `import_otb_xml`.
    scenario = await _get_scenario_or_404(scenario_id, db)

    from app.importers.opera_country_stats import (
        OTROS, parse_country_stats, plegar_a_lista)

    crudo = parse_country_stats(await file.read())
    if not crudo:
        raise ErrorApi(422, "xml.sin_dias_con_pais")

    anios = sorted({k[0] for k in crudo})
    anio = year if year is not None else (
        scenario.year if scenario.year in anios else anios[0])
    del_anio = {k: v for k, v in crudo.items() if k[0] == anio}
    if not del_anio:
        raise ErrorApi(422, "xml.anio_no_esta", anio=anio,
                       anios=', '.join(map(str, anios)))

    # ⚠️ UN MES POR SUBIDA. «No se puede subir 2 meses a la vez, es mes por mes»
    # (owner, 18-ago-2026).
    #
    # El archivo de Opera trae el rango entero —el del owner, siete meses de una—
    # y hasta acá se cargaban todos juntos. Eso choca de frente con la otra regla
    # suya: el mes se sube UNA vez y después se corrige a mano. Cargando siete de
    # un saque, subir el mes nuevo obligaba a pasar por encima de los seis
    # anteriores, ya corregidos.
    #
    # Así que el mes se elige. Si el archivo trae uno solo, es ese y no hay nada
    # que preguntar.
    disponibles = sorted({k[1] for k in del_anio})
    if month is None:
        if len(disponibles) > 1:
            raise ErrorApi(409, "xml.elegir_mes",
                           extra={"motivo": "elegir_mes",
                                  "meses_disponibles": disponibles,
                                  "year": anio},
                           n=len(disponibles), anio=anio,
                           meses=', '.join(_MES_CORTO[m - 1] for m in disponibles))
        month = disponibles[0]
    if month not in disponibles:
        raise ErrorApi(422, "xml.mes_no_esta", mes=_MES_CORTO[month - 1], anio=anio,
                       meses=', '.join(_MES_CORTO[m - 1] for m in disponibles))
    del_anio = {k: v for k, v in del_anio.items() if k[1] == month}

    # La lista importante = la que ya está en pantalla.
    existentes = (await db.execute(
        select(CountryMixEntry.country).where(
            CountryMixEntry.scenario_id == scenario_id).distinct())).scalars().all()
    importantes = sorted({c for c in existentes if c and c != OTROS})
    lista_inferida = False
    if not importantes:
        # Escenario vacío: arrancamos con los diez de más noches del archivo.
        por_pais: dict[str, float] = {}
        for (_a, _m, pais), v in del_anio.items():
            por_pais[pais] = por_pais.get(pais, 0.0) + v["rooms"]
        importantes = [p for p, _ in sorted(por_pais.items(), key=lambda x: -x[1])[:10]]
        lista_inferida = True

    plegado, al_cajon = plegar_a_lista(del_anio, importantes)
    meses = sorted({k[1] for k in plegado})

    # ⚠️ EL FRENO. «Este archivo se sube una única vez para el mes, y después se
    # baja y se edita. Entonces un mismo mes no debería subirse más de 2 veces»
    # (owner, 18-ago-2026).
    #
    # El XML escribe el mes UNA vez; la plantilla corregida lo escribe una
    # segunda. Un tercer paso del importador sobre ese mes BORRA la corrección
    # —esta función hace delete + insert— y hasta acá lo hacía sin decir nada.
    # Un mes ya corregido a mano no se pisa sin que alguien lo pida explícito.
    ya = (await db.execute(select(
        CountryMixEntry.month, CountryMixEntry.origen).where(
            CountryMixEntry.scenario_id == scenario_id,
            CountryMixEntry.month.in_(meses)).distinct())).all()
    corregidos = sorted({m for m, o in ya if o == "manual"})
    cargados = sorted({m for m, _o in ya})
    if corregidos and not sobrescribir:
        raise ErrorApi(409, "country_mix.meses_corregidos_a_mano",
                       extra={"motivo": "meses_corregidos_a_mano",
                              "meses": corregidos},
                       meses=', '.join(_MES_CORTO[m - 1] for m in corregidos))

    ahora = datetime.now(timezone.utc)
    # Reemplaza SOLO los meses que trae el archivo, en las dos métricas.
    for metric in COUNTRY_METRICS:
        await db.execute(delete(CountryMixEntry).where(
            CountryMixEntry.scenario_id == scenario_id,
            CountryMixEntry.metric == metric,
            CountryMixEntry.month.in_(meses)))
    guardadas = 0
    for (_a, mes, pais), v in plegado.items():
        for metric in COUNTRY_METRICS:
            valor = v["rooms"] if metric == "rooms" else v["pax"]
            if not valor:
                continue
            db.add(CountryMixEntry(scenario_id=scenario_id, month=mes,
                                   country=pais, metric=metric, value=valor,
                                   origen="xml", actualizado_en=ahora))
            guardadas += 1
    await db.commit()

    return {
        "imported": True,
        "year": anio,
        # Qué meses YA tenían dato antes de esta subida. El owner sube el XML
        # una vez por mes: si esto no viene vacío, es una re-subida.
        "meses_ya_cargados": cargados,
        "meses_sobrescritos_a_mano": corregidos if sobrescribir else [],
        "anios_en_el_archivo": anios,
        "meses": meses,
        "paises": len(importantes) + (1 if al_cajon else 0),
        "lista_inferida": lista_inferida,
        "filas": guardadas,
        "total_noches": round(sum(v["rooms"] for v in plegado.values()), 2),
        "total_pax": round(sum(v["pax"] for v in plegado.values()), 2),
        # Qué se fue al cajón de sastre, para poder promover con criterio.
        "en_others": [{"pais": x["pais"], "noches": round(x["rooms"], 2),
                       "pax": round(x["pax"], 2)} for x in al_cajon[:20]],
    }


@router.get("/scenarios/{scenario_id}/country-mix/plantilla.xlsx")
async def country_mix_plantilla(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Baja la plantilla de ida y vuelta del mix por país (las DOS métricas).

    «Debe haber la opción de editar por si acaso un ajuste; se podría quizás
    bajar a Excel controlado y después subir con el cambio» (owner,
    18-ago-2026). El «⬇ Excel» que ya existía es un REPORTE —trae variance en
    puntos porcentuales contra el budget— y no se puede volver a subir. Esta es
    la grilla cruda, editable y re-subible.
    """
    import io as _io

    from fastapi.responses import StreamingResponse

    from app.export.country_mix_xlsx import construir_libro

    scenario = await _get_scenario_or_404(scenario_id, db)
    recs = (await db.execute(select(CountryMixEntry).where(
        CountryMixEntry.scenario_id == scenario_id))).scalars().all()

    por: dict[tuple[str, str], list[float]] = {}
    for r in recs:
        vals = por.setdefault((r.country, r.metric), [0.0] * 12)
        if 1 <= r.month <= 12:
            vals[r.month - 1] += float(r.value)

    # Orden: por noches del país (de mayor a menor) y, dentro, rooms antes que
    # pax. Así el archivo se lee igual que la pantalla.
    noches = {p: sum(v) for (p, m), v in por.items() if m == "rooms"}
    paises = sorted({p for p, _ in por}, key=lambda p: (-noches.get(p, 0.0), p))
    filas = [{"pais": p, "metric": m, "values": por[(p, m)]}
             for p in paises for m in COUNTRY_METRICS if (p, m) in por]

    wb = construir_libro(
        f"Country Mix — {scenario.type} {scenario.version or ''} {scenario.year}".strip(),
        filas)
    buf = _io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nombre = f"CountryMix_{scenario.type}_{scenario.year}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.post("/scenarios/{scenario_id}/country-mix/plantilla/", dependencies=[Depends(registro_de_subida)])
async def country_mix_subir_plantilla(
    scenario_id: str,
    file: UploadFile = File(...),
    confirmar: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Sube la plantilla corregida. Sin `confirmar`, solo REVISA y no guarda.

    El paso de revisión existe porque esto reemplaza el mix entero del
    escenario: conviene ver qué cambia antes de que cambie. Con
    `confirmar=true` se guarda.
    """
    from app.export.country_mix_xlsx import leer_libro

    await _get_scenario_or_404(scenario_id, db)
    filas, problemas = leer_libro(await file.read())
    if problemas:
        raise HTTPException(status_code=422, detail=" · ".join(problemas[:8]))

    nuevo = {(f["pais"], f["metric"]): f["values"] for f in filas}
    recs = (await db.execute(select(CountryMixEntry).where(
        CountryMixEntry.scenario_id == scenario_id))).scalars().all()
    viejo: dict[tuple[str, str], list[float]] = {}
    for r in recs:
        v = viejo.setdefault((r.country, r.metric), [0.0] * 12)
        if 1 <= r.month <= 12:
            v[r.month - 1] += float(r.value)

    # Qué cambia, para poder mirarlo antes de guardar.
    cambios = []
    for k in sorted(set(nuevo) | set(viejo)):
        a, b = viejo.get(k), nuevo.get(k)
        if a == b:
            continue
        cambios.append({
            "pais": k[0], "metric": k[1],
            "antes": round(sum(a), 2) if a else None,
            "ahora": round(sum(b), 2) if b else None,
        })

    if not confirmar:
        return {"guardado": False, "filas": len(filas), "cambios": cambios[:60],
                "total_cambios": len(cambios)}

    await db.execute(delete(CountryMixEntry).where(
        CountryMixEntry.scenario_id == scenario_id))
    guardadas = 0
    for (pais, metric), vals in nuevo.items():
        for m in range(1, 13):
            v = vals[m - 1]
            if not v:
                continue
            db.add(CountryMixEntry(scenario_id=scenario_id, month=m,
                                   country=pais, metric=metric, value=v,
                                   # ⚠️ `manual`: esto es lo que el freno del
                                   # importador protege. Sin marcarlo, volver a
                                   # subir el XML pisaría la corrección sin avisar.
                                   origen="manual",
                                   actualizado_en=datetime.now(timezone.utc)))
            guardadas += 1
    await db.commit()
    return {"guardado": True, "filas": len(filas), "celdas": guardadas,
            "cambios": cambios[:60], "total_cambios": len(cambios)}


@router.post("/scenarios/{scenario_id}/import-channel-xml/", dependencies=[Depends(registro_de_subida)])
async def import_channel_xml(
    scenario_id: str,
    file: UploadFile = File(...),
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
    sobrescribir: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Carga el `res_statistics1` de Opera abierto por MARKET CODE → canal.

    «Necesito hacer lo mismo con este tab, subir el XML. Seguro hay que ampliar
    los market codes» (owner, 18-ago-2026).

    Es el MISMO reporte que el de países: lo único que cambia es qué trae
    `MASTER_VALUE` —el market code en vez del país—. Por eso comparte parser, y
    las mismas dos reglas: **un mes por subida** y **no pisar lo corregido a
    mano**.

    El código no se interpreta acá: se traduce con la tabla `market_codes`, que
    es la que el owner mantiene en Master Data. Su mapeo —el mismo que tiene en
    su Excel— ya está cargado:

        Travel Agent   TA + TAFIT + TAGP
        Direct Client  BAR + COM + DIR + FNF + SOC
        Website        WEB
        OTA            OTA
        INHOUSE        INHOUSE

    ⚠️ **Un market code sin canal no se adivina.** `CORP` y `GRP` están así a
    propósito, y el XML puede traer códigos que no estén en la tabla. Mandarlos
    «al que parezca» pondría noches en el canal equivocado y el total seguiría
    cuadrando igual — la forma de fallar que no avisa. Se reportan en
    `sin_canal` y **no se cargan**: el total del mix lo dice.
    """
    from app.importers.opera_country_stats import parse_stats_por_codigo
    from app.models.market_code import MarketCode

    scenario = await _get_scenario_or_404(scenario_id, db)
    crudo = parse_stats_por_codigo(await file.read())
    if not crudo:
        raise ErrorApi(422, "xml.sin_dias_con_datos")

    # ⚠️ Que el archivo sea el que se cree que es. El de países y el de market
    # codes son el MISMO reporte con distinto desglose y se ven idénticos por
    # fuera: el owner ya mandó una vez el de países creyendo que era este. Si
    # ningún código del archivo está en la tabla de market codes, no es este.
    conocidos = {c.code.strip().upper() for c in
                 (await db.execute(select(MarketCode))).scalars().all()}
    codigos = {k[2].strip().upper() for k in crudo}
    if conocidos and not (codigos & conocidos):
        raise ErrorApi(422, "channel_mix.xml_no_es_de_market_code",
                       n=len(codigos), codigos=', '.join(sorted(codigos)[:8]))

    anios = sorted({k[0] for k in crudo})
    anio = year if year is not None else (
        scenario.year if scenario.year in anios else anios[0])
    del_anio = {k: v for k, v in crudo.items() if k[0] == anio}
    if not del_anio:
        raise ErrorApi(422, "xml.anio_no_esta", anio=anio,
                       anios=', '.join(map(str, anios)))

    # ⚠️ UN MES POR SUBIDA — la misma regla que en Country Mix.
    disponibles = sorted({k[1] for k in del_anio})
    if month is None:
        if len(disponibles) > 1:
            raise ErrorApi(409, "xml.elegir_mes",
                           extra={"motivo": "elegir_mes",
                                  "meses_disponibles": disponibles,
                                  "year": anio},
                           n=len(disponibles), anio=anio,
                           meses=', '.join(_MES_CORTO[m - 1] for m in disponibles))
        month = disponibles[0]
    if month not in disponibles:
        raise ErrorApi(422, "xml.mes_no_esta", mes=_MES_CORTO[month - 1], anio=anio,
                       meses=', '.join(_MES_CORTO[m - 1] for m in disponibles))
    del_mes = {k: v for k, v in del_anio.items() if k[1] == month}

    # market code → canal, con la tabla del owner.
    canal_de = {c.code.strip().upper(): (c.canal or "").strip()
                for c in (await db.execute(select(MarketCode))).scalars().all()}
    por_canal: dict[str, dict] = {}
    sin_canal: dict[str, dict] = {}
    for (_a, _m, code), v in del_mes.items():
        canal = canal_de.get(code.strip().upper(), "")
        destino = por_canal if canal else sin_canal
        clave = canal or code
        acc = destino.setdefault(clave, {"rooms": 0.0, "pax": 0.0})
        acc["rooms"] += v["rooms"]
        acc["pax"] += v["pax"]

    if not por_canal:
        raise ErrorApi(422, "channel_mix.market_codes_sin_canal")

    # ⚠️ EL FRENO: no pisar lo corregido a mano. Igual que en Country Mix.
    ya = (await db.execute(select(
        ChannelMixEntry.origen).where(
            ChannelMixEntry.scenario_id == scenario_id,
            ChannelMixEntry.month == month).distinct())).scalars().all()
    if "manual" in ya and not sobrescribir:
        raise ErrorApi(409, "channel_mix.mes_corregido_a_mano",
                       extra={"motivo": "meses_corregidos_a_mano",
                              "meses": [month]},
                       mes=_MES_CORTO[month - 1])

    ahora = datetime.now(timezone.utc)

    # ── Las DOS capas, de una sola lectura ───────────────────────────────────
    # El DETALLE es el átomo (por market code) y el RESUMEN es su rollup. Se
    # escriben en la misma transacción y desde los mismos números, así que no
    # pueden discrepar. Guardar solo el detalle habría obligado a cambiar cómo
    # LEE la pantalla de resumen, que hoy funciona; guardar solo el resumen
    # perdería el detalle que el owner pidió ver.
    for metric in CHANNEL_METRICS:
        await db.execute(delete(ChannelMixDetail).where(
            ChannelMixDetail.scenario_id == scenario_id,
            ChannelMixDetail.metric == metric,
            ChannelMixDetail.month == month))
        await db.execute(delete(ChannelMixEntry).where(
            ChannelMixEntry.scenario_id == scenario_id,
            ChannelMixEntry.metric == metric,
            ChannelMixEntry.month == month))

    detalladas = 0
    for (_a, _m, code), v in del_mes.items():
        for metric in CHANNEL_METRICS:
            valor = v["rooms"] if metric == "rooms" else v["pax"]
            if not valor:
                continue
            db.add(ChannelMixDetail(scenario_id=scenario_id, month=month,
                                    market_code=code.strip().upper(), metric=metric,
                                    value=valor, origen="xml", actualizado_en=ahora))
            detalladas += 1

    guardadas = 0
    for canal, v in por_canal.items():
        for metric in CHANNEL_METRICS:
            valor = v["rooms"] if metric == "rooms" else v["pax"]
            if not valor:
                continue
            db.add(ChannelMixEntry(scenario_id=scenario_id, month=month,
                                   channel=canal, metric=metric, value=valor,
                                   origen="xml", actualizado_en=ahora))
            guardadas += 1
    await db.commit()

    return {
        "imported": True,
        "year": anio,
        "month": month,
        "meses_disponibles": disponibles,
        "canales": sorted(por_canal),
        "filas": guardadas,
        "filas_detalle": detalladas,
        "total_noches": round(sum(v["rooms"] for v in por_canal.values()), 2),
        "total_pax": round(sum(v["pax"] for v in por_canal.values()), 2),
        # Los códigos que NO se cargaron por no tener canal. Van con su volumen:
        # sin eso no hay forma de saber si es ruido o si falta media operación.
        "sin_canal": sorted(
            ({"code": c, "noches": round(v["rooms"], 2), "pax": round(v["pax"], 2)}
             for c, v in sin_canal.items() if v["rooms"] or v["pax"]),
            key=lambda x: -x["noches"]),
    }


async def _channel_mix_grillas(db: AsyncSession, scenario_id: str):
    """`(por_canal, por_code, canal_de)` — las dos capas y el mapeo, ya en 12 meses."""
    from app.models.market_code import MarketCode

    canal_de = {c.code.strip().upper(): (c.canal or "").strip()
                for c in (await db.execute(select(MarketCode))).scalars().all()}

    por_code: dict[tuple[str, str], list[float]] = {}
    for r in (await db.execute(select(ChannelMixDetail).where(
            ChannelMixDetail.scenario_id == scenario_id))).scalars().all():
        v = por_code.setdefault((r.market_code, r.metric), [0.0] * 12)
        if 1 <= r.month <= 12:
            v[r.month - 1] += float(r.value)

    por_canal: dict[tuple[str, str], list[float]] = {}
    for r in (await db.execute(select(ChannelMixEntry).where(
            ChannelMixEntry.scenario_id == scenario_id))).scalars().all():
        v = por_canal.setdefault((r.channel, r.metric), [0.0] * 12)
        if 1 <= r.month <= 12:
            v[r.month - 1] += float(r.value)

    return por_canal, por_code, canal_de


@router.get("/scenarios/{scenario_id}/channel-mix/excel.xlsx")
async def channel_mix_excel(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """El reporte: CUATRO pestañas, mes por mes, canal y market code.

    «Quiero tener las estadísticas mes por mes por market codes y channel, total
    rooms y total pax. Quisiera bajar el Excel y ver todos los números de ambas
    cosas por mes y en diferente tab» (owner, 18-ago-2026).
    """
    import io as _io

    from fastapi.responses import StreamingResponse

    from app.export.channel_mix_xlsx import construir_reporte

    scn = await _get_scenario_or_404(scenario_id, db)
    por_canal, por_code, canal_de = await _channel_mix_grillas(db, scenario_id)
    wb = construir_reporte(
        f"Channel Mix — {scn.type} {scn.version or ''} {scn.year}".strip(),
        por_canal, por_code, canal_de)
    buf = _io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="ChannelMix_{scn.type}_{scn.year}.xlsx"'})


@router.get("/scenarios/{scenario_id}/channel-mix/plantilla.xlsx")
async def channel_mix_plantilla(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """La plantilla EDITABLE: dos pestañas, filas = market code.

    ⚠️ Solo por market code, a propósito. El canal se deriva del código: si
    también se pudiera editar el canal, el resumen podría contradecir a su
    propio detalle y ninguno de los dos sería la verdad.
    """
    import io as _io

    from fastapi.responses import StreamingResponse

    from app.export.channel_mix_xlsx import construir_plantilla

    scn = await _get_scenario_or_404(scenario_id, db)
    _pc, por_code, canal_de = await _channel_mix_grillas(db, scenario_id)
    # Orden: por volumen de noches, como se lee en pantalla.
    noches = {c: sum(v) for (c, m), v in por_code.items() if m == "rooms"}
    codes = sorted({c for c, _m in por_code}, key=lambda c: (-noches.get(c, 0.0), c))
    filas = [{"code": c, "metric": m, "values": por_code[(c, m)]}
             for c in codes for m in CHANNEL_METRICS if (c, m) in por_code]

    wb = construir_plantilla(
        f"Channel Mix — {scn.type} {scn.version or ''} {scn.year}".strip(),
        filas, canal_de)
    buf = _io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="ChannelMix_plantilla_{scn.type}_{scn.year}.xlsx"'})


@router.post("/scenarios/{scenario_id}/channel-mix/plantilla/", dependencies=[Depends(registro_de_subida)])
async def channel_mix_subir_plantilla(
    scenario_id: str,
    file: UploadFile = File(...),
    confirmar: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """Sube la plantilla corregida. Sin `confirmar`, solo REVISA y no guarda.

    Reemplaza el detalle entero del escenario y **recalcula el resumen por
    canal** desde él: el canal nunca se toma del archivo. Los códigos sin canal
    quedan en el detalle pero no suman a ningún canal — igual que en el import.
    """
    from app.export.channel_mix_xlsx import leer_plantilla
    from app.models.market_code import MarketCode

    await _get_scenario_or_404(scenario_id, db)
    filas, problemas = leer_plantilla(await file.read())
    if problemas:
        raise HTTPException(status_code=422, detail=" · ".join(problemas[:8]))

    nuevo = {(f["code"], f["metric"]): f["values"] for f in filas}
    _pc, viejo, canal_de = await _channel_mix_grillas(db, scenario_id)

    cambios = []
    for k in sorted(set(nuevo) | set(viejo)):
        a, b = viejo.get(k), nuevo.get(k)
        if a == b:
            continue
        cambios.append({"code": k[0], "metric": k[1],
                        "antes": round(sum(a), 2) if a else None,
                        "ahora": round(sum(b), 2) if b else None})

    sin_canal = sorted({c for c, _m in nuevo if not canal_de.get(c)})
    if not confirmar:
        return {"guardado": False, "filas": len(filas), "cambios": cambios[:60],
                "total_cambios": len(cambios), "sin_canal": sin_canal}

    ahora = datetime.now(timezone.utc)
    await db.execute(delete(ChannelMixDetail).where(
        ChannelMixDetail.scenario_id == scenario_id))
    await db.execute(delete(ChannelMixEntry).where(
        ChannelMixEntry.scenario_id == scenario_id))

    # El detalle, tal como vino.
    celdas = 0
    for (code, metric), vals in nuevo.items():
        for m in range(1, 13):
            if not vals[m - 1]:
                continue
            db.add(ChannelMixDetail(scenario_id=scenario_id, month=m, market_code=code,
                                    metric=metric, value=vals[m - 1],
                                    origen="manual", actualizado_en=ahora))
            celdas += 1

    # Y el resumen, RECALCULADO del detalle. Nunca del archivo.
    roll: dict[tuple[int, str, str], float] = {}
    for (code, metric), vals in nuevo.items():
        canal = canal_de.get(code, "")
        if not canal:
            continue
        for m in range(1, 13):
            if vals[m - 1]:
                roll[(m, canal, metric)] = roll.get((m, canal, metric), 0.0) + vals[m - 1]
    for (m, canal, metric), v in roll.items():
        db.add(ChannelMixEntry(scenario_id=scenario_id, month=m, channel=canal,
                               metric=metric, value=v,
                               origen="manual", actualizado_en=ahora))
    await db.commit()
    return {"guardado": True, "filas": len(filas), "celdas": celdas,
            "cambios": cambios[:60], "total_cambios": len(cambios),
            "sin_canal": sin_canal}


# ──────────────────────── Ops KPI (tabla manual) ─────────────────────────────
@router.get("/scenarios/{scenario_id}/ops-kpi/")
async def get_ops_kpi(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Filas de la tabla manual de Ops KPI del escenario (ordenadas)."""
    await _get_scenario_or_404(scenario_id, db)
    recs = (await db.execute(select(OpsKpiEntry).where(
        OpsKpiEntry.scenario_id == scenario_id).order_by(OpsKpiEntry.order_idx))).scalars().all()
    rows = [{"kpi": r.kpi, "target": r.target, "actual": r.actual,
             "owner": r.owner, "action": r.action} for r in recs]
    return {"scenario_id": scenario_id, "rows": rows}


class OpsKpiRowIn(BaseModel):
    kpi: str = ""
    target: str = ""
    actual: str = ""
    owner: str = ""
    action: str = ""


class OpsKpiEntryIn(BaseModel):
    rows: list[OpsKpiRowIn]


@router.put("/scenarios/{scenario_id}/ops-kpi/")
async def put_ops_kpi(
    scenario_id: str, body: OpsKpiEntryIn, db: AsyncSession = Depends(get_db)
):
    """Reemplaza todas las filas de Ops KPI del escenario (borra-luego-inserta).
    Omite las filas totalmente vacías; conserva el orden recibido."""
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    await _get_scenario_or_404(scenario_id, db)
    await db.execute(delete(OpsKpiEntry).where(OpsKpiEntry.scenario_id == scenario_id))
    saved = 0
    for r in body.rows:
        if not any((r.kpi.strip(), r.target.strip(), r.actual.strip(),
                    r.owner.strip(), r.action.strip())):
            continue
        db.add(OpsKpiEntry(
            scenario_id=scenario_id, order_idx=saved,
            kpi=r.kpi.strip()[:200], target=r.target.strip()[:120],
            actual=r.actual.strip()[:120], owner=r.owner.strip()[:120],
            action=r.action.strip()[:400]))
        saved += 1
    await db.commit()
    return {"saved": True, "rows_saved": saved}


@router.get("/scenarios/{scenario_id}/revenue/{month:int}/")
async def get_monthly_revenue_single(
    scenario_id: str, month: int, db: AsyncSession = Depends(get_db)
):
    """Return revenue result for a single month.

    NOTE: {month:int} restricts this route to integer segments so it does NOT
    swallow the literal sibling routes (/revenue/channels/, /revenue/packages/,
    /revenue/rate-cards/, /revenue/occupancy/).
    """
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")

    scenario = await _get_scenario_or_404(scenario_id, db)
    data = await _load_revenue_data(scenario_id, db)
    room_type_units = {rt.id: rt.units for rt in data["room_types"]}

    from app.engine.revenue_calculator import calculate_revenue
    result = calculate_revenue(
        month=month,
        year=scenario.year,
        rate_cards=[rc for rc in data["rate_cards"] if rc.month == month],
        occ_budgets=[ob for ob in data["occupancies"] if ob.month == month],
        channels=[c for c in data["channels"] if getattr(c, "month", month) == month] or data["channels"],
        pkg_configs=data["pkg_configs"],
        other_revenues=[ot for ot in data["other_revenues"] if ot.month == month],
        room_type_units=room_type_units,
    )
    return _revenue_result_to_dict(result)


# ─── Ocupación (% por tipo de habitación × mes) ───────────────────────────────
# El % es la fuente. rooms_occupied = pct × noches disponibles (unidades × días,
# 0 si el mes está cerrado). Default sugerido 10%.

import calendar as _calendar

_DEFAULT_OCC = Decimal("0.10")


def _days_in_month(year: int, month: int) -> int:
    return _calendar.monthrange(year, month)[1]


@router.get("/scenarios/{scenario_id}/revenue/occupancy-pct/")
async def get_occupancy_pct(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Grilla de % de ocupación: una fila por tipo de habitación × 12 meses.

    Sin filas → sugiere 10% (seeded). Con filas pero pct=0 (p.ej. importadas con
    noches absolutas), deriva el % desde rooms_occupied / noches disponibles.
    """
    scenario = await _get_scenario_or_404(scenario_id, db)
    rts = (await db.execute(
        select(RoomTypeConfig)
        .where(RoomTypeConfig.hotel_id == scenario.hotel_id)
        .order_by(RoomTypeConfig.sort_order)
    )).scalars().all()
    occ = (await db.execute(
        select(OccupancyBudget).where(OccupancyBudget.scenario_id == scenario_id)
    )).scalars().all()
    occ_by_key = {(o.room_type_id, o.month): o for o in occ}
    seeded = not occ

    hotel = await db.get(Hotel, scenario.hotel_id)
    closed = set(hotel.closed_months_list) if hotel else set()
    units_by_rt = {rt.id: rt.units for rt in rts}

    rooms = []
    for rt in rts:
        row = {"room_type_id": rt.id, "name": rt.name}
        for m in range(1, 13):
            o = occ_by_key.get((rt.id, m))
            if o is not None and o.occupancy_pct and o.occupancy_pct > 0:
                pct = o.occupancy_pct                 # % cargado
            elif o is not None:
                # % real del budget importado = rooms_occupied / noches disponibles
                avail = 0 if m in closed else units_by_rt.get(rt.id, 0) * _days_in_month(scenario.year, m)
                pct = (o.rooms_occupied / Decimal(avail)).quantize(Decimal("0.0001")) if avail else Decimal("0")
            else:
                pct = Decimal("0")                    # sin dato / mes cerrado
            row[_RR_MONTHS[m - 1]] = str(pct)
        rooms.append(row)
    return {"scenario_id": scenario_id, "year": scenario.year, "seeded": seeded, "rooms": rooms}


class OccPctRow(BaseModel):
    room_type_id: str
    jan: Decimal = _DEFAULT_OCC; feb: Decimal = _DEFAULT_OCC
    mar: Decimal = _DEFAULT_OCC; apr: Decimal = _DEFAULT_OCC
    may: Decimal = _DEFAULT_OCC; jun: Decimal = _DEFAULT_OCC
    jul: Decimal = _DEFAULT_OCC; aug: Decimal = _DEFAULT_OCC
    sep: Decimal = _DEFAULT_OCC; oct: Decimal = _DEFAULT_OCC
    nov: Decimal = _DEFAULT_OCC; dec: Decimal = _DEFAULT_OCC


@router.put("/scenarios/{scenario_id}/revenue/occupancy-pct/bulk/")
async def bulk_occupancy_pct(
    scenario_id: str, rows: list[OccPctRow], db: AsyncSession = Depends(get_db),
):
    """Guarda el % de ocupación y deriva rooms_occupied por fórmula.

    rooms_occupied = pct × unidades × días del mes (0 si el mes está cerrado).
    """
    import uuid as _uuid
    from sqlalchemy import delete as _delete
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    hotel = await db.get(Hotel, scenario.hotel_id)
    closed = set(hotel.closed_months_list) if hotel else set()
    units_by_rt = {
        rt.id: rt.units for rt in (await db.execute(
            select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == scenario.hotel_id)
        )).scalars().all()
    }

    await db.execute(_delete(OccupancyBudget).where(OccupancyBudget.scenario_id == scenario_id))
    await db.flush()
    for r in rows:
        units = units_by_rt.get(r.room_type_id, 0)
        for i, mk in enumerate(_RR_MONTHS, start=1):
            pct = getattr(r, mk)
            avail = 0 if i in closed else units * _days_in_month(scenario.year, i)
            rooms_occ = (pct * Decimal(avail)).quantize(Decimal("0.0001"))
            db.add(OccupancyBudget(
                id=str(_uuid.uuid4()), scenario_id=scenario_id, hotel_id=scenario.hotel_id,
                room_type_id=r.room_type_id, month=i,
                occupancy_pct=pct, rooms_occupied=rooms_occ,
            ))
    await db.commit()
    return {"saved": len(rows), "scenario_id": scenario_id}


# ─── Rack Rates (rooms only) — grilla tipo habitación × mes ───────────────────
# Las tarifas RACK se cargan tal cual las dan. El net (descuentos por canal) se
# maneja aparte; al guardar rack se preserva el net existente (si lo hay).

_RR_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"]


@router.get("/scenarios/{scenario_id}/revenue/rack-rates/")
async def get_rack_rates(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Grilla de tarifas rack: una fila por tipo de habitación × 12 meses."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    rts = (await db.execute(
        select(RoomTypeConfig)
        .where(RoomTypeConfig.hotel_id == scenario.hotel_id,
               RoomTypeConfig.active == True)  # noqa: E712
        .order_by(RoomTypeConfig.sort_order)
    )).scalars().all()
    cards = (await db.execute(
        select(RateCard).where(RateCard.scenario_id == scenario_id)
    )).scalars().all()
    rack_by_key = {(c.room_type_id, c.month): c.rack_rate for c in cards}

    rooms = []
    for rt in rts:
        row = {"room_type_id": rt.id, "code": rt.code, "name": rt.name}
        for i, mk in enumerate(_RR_MONTHS, start=1):
            row[mk] = str(rack_by_key.get((rt.id, i), Decimal("0")))
        rooms.append(row)
    return {"scenario_id": scenario_id, "year": scenario.year, "rooms": rooms}


class RackRateRow(BaseModel):
    room_type_id: str
    jan: Decimal = Decimal("0"); feb: Decimal = Decimal("0")
    mar: Decimal = Decimal("0"); apr: Decimal = Decimal("0")
    may: Decimal = Decimal("0"); jun: Decimal = Decimal("0")
    jul: Decimal = Decimal("0"); aug: Decimal = Decimal("0")
    sep: Decimal = Decimal("0"); oct: Decimal = Decimal("0")
    nov: Decimal = Decimal("0"); dec: Decimal = Decimal("0")


def _exigir_mix(nf_mes: dict, scenario_id: str) -> None:
    """Se niega a escribir tarifas si el escenario no tiene mix de canales.

    ⚠️ **El agujero que esto tapa, medido.** Cuando un escenario no tiene canales
    guardados, `compute_net_factor` devuelve 0, y las dos puertas que escriben la
    tarifa neta hacían `nf if nf else Decimal("1")`. Ese `1` significa **«no pago
    comisión»**: la tarifa neta quedaba igual a la rack. Después el motor lee
    `net/rack = 1,0`, decide que «mandan las tarifas», y **el mixer ya nunca lo
    corrige**.

    Sobre el volumen del `BUDGET Working 2027` eso infla el ingreso
    **+$1.494.916,87 (+23,45%)** y la utilidad neta +$973.190,88, con los gastos
    moviéndose $0,00 — porque la comisión vive netada en la tarifa, no gastada.
    Nada falla: factura de más.

    Hoy ningún escenario está en ese estado. Es el camino que abre el **clonado**
    de una propiedad, que nace sin canales — por eso la guarda va ANTES de que
    exista el clonado, no después.

    Mejor un 409 que explica, que una tarifa escrita a bruto en silencio.
    """
    sin_mix = [m for m, nf in nf_mes.items() if not nf]
    if sin_mix:
        raise ErrorApi(409, "tarifas.sin_mix_de_canales", n=len(sin_mix),
                       meses=(', '.join(str(m) for m in sin_mix[:6])
                              + ('…' if len(sin_mix) > 6 else '')))


@router.put("/scenarios/{scenario_id}/revenue/rack-rates/bulk/")
async def bulk_rack_rates(
    scenario_id: str,
    rows: list[RackRateRow],
    db: AsyncSession = Depends(get_db),
):
    """Guarda las tarifas rack por tipo de habitación × mes.

    Upsert por (room_type, mes). El **net_rate se recalcula** como
    `rack × factor neto de canales` del mes: el motor del P&L calcula el ingreso
    de habitaciones con net_rate, así que si solo se guardaba el rack (como antes)
    cambiar la tarifa NO movía el ingreso — la pantalla se actualizaba pero el
    P&L seguía con la tarifa vieja.
    """
    import uuid as _uuid
    from app.models.sales_channel_config import compute_net_factor
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    existing = {
        (c.room_type_id, c.month): c
        for c in (await db.execute(
            select(RateCard).where(RateCard.scenario_id == scenario_id)
        )).scalars().all()
    }
    canales = (await db.execute(
        select(SalesChannelConfig).where(SalesChannelConfig.scenario_id == scenario_id)
    )).scalars().all()
    nf_mes: dict[int, Decimal] = {
        m: compute_net_factor([c for c in canales if c.month == m])
        for m in range(1, 13)}
    _exigir_mix(nf_mes, scenario_id)

    for r in rows:
        for i, mk in enumerate(_RR_MONTHS, start=1):
            rack = getattr(r, mk)
            neto = (Decimal(str(rack)) * nf_mes[i]).quantize(Decimal("0.01"))
            card = existing.get((r.room_type_id, i))
            if card:
                card.rack_rate = rack
                card.net_rate = neto
            else:
                db.add(RateCard(
                    id=str(_uuid.uuid4()), scenario_id=scenario_id,
                    hotel_id=scenario.hotel_id, room_type_id=r.room_type_id,
                    month=i, rack_rate=rack, net_rate=neto,
                    pax_per_room=Decimal("1.8"),
                ))
    await db.commit()
    return {"saved": len(rows), "scenario_id": scenario_id,
            "net_rate_recalculado": True}


@router.get("/scenarios/{scenario_id}/revenue/rate-cards/")
async def get_rate_cards(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Return raw rack/net rates per room type × month."""
    await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(select(RateCard).where(RateCard.scenario_id == scenario_id))
    rcs = q.scalars().all()
    return [
        {
            "id": rc.id,
            "room_type_id": rc.room_type_id,
            "month": rc.month,
            "rack_rate": str(rc.rack_rate),
            "net_rate": str(rc.net_rate),
            "pax_per_room": str(rc.pax_per_room),
        }
        for rc in sorted(rcs, key=lambda r: (r.month, r.room_type_id))
    ]


@router.get("/scenarios/{scenario_id}/revenue/occupancy/")
async def get_occupancy(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Return raw rooms-occupied per room type × month."""
    await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(select(OccupancyBudget).where(OccupancyBudget.scenario_id == scenario_id))
    obs = q.scalars().all()
    return [
        {
            "id": ob.id,
            "room_type_id": ob.room_type_id,
            "month": ob.month,
            "rooms_occupied": str(ob.rooms_occupied),
        }
        for ob in sorted(obs, key=lambda o: (o.month, o.room_type_id))
    ]


# ─── Canales de Venta (mix % + comisión % → net factor) ───────────────────────

_CHANNEL_LABELS = {"TA": "Travel Agency", "OTA": "OTAs", "DIRECT": "Direct"}


def _channel_net_factor(channels) -> Decimal:
    """Net Factor = Σ(mix × (1 − comisión))."""
    return sum(
        (c["mix_pct"] if isinstance(c, dict) else c.mix_pct)
        * (Decimal("1") - (c["commission_pct"] if isinstance(c, dict) else c.commission_pct))
        for c in channels
    ) if channels else Decimal("0")


async def _semilla_de_canales(esc, db) -> list[dict]:
    """Lo que se SUGIERE cuando el escenario no tiene canales guardados.

    ⚠️ Esto no es cosmético. Todos los Forecast estan hoy en ese estado —sin
    nada guardado, corriendo con una sugerencia que nadie fijó— y la sugerencia
    era la constante vieja: TA 60/28, OTA 5/20 y **DIRECT 35 al 0%**. O sea que
    cada escenario nuevo nacía creyendo que la venta directa no cuesta nada.

    Owner (2026-08-14): «a partir de enero 2027, el forecast, el budget, todo lo
    que se construye ahí, como auxiliar, tiene que dar con esos parámetros». Por
    eso la sugerencia sale del mixer para los escenarios que el mixer gobierna, y
    solo cae al archivo cuando no hay canales comerciales cargados — que es el
    caso de una propiedad nueva.
    """
    from app.engine import mixer_canales as mixer
    from app.models.canal_comercial import CanalComercial
    from app.models.canal_mix_escenario import CanalMixEscenario
    from app.seed_data import semilla

    aplica, _clave, _params = mixer.gobierna(esc)
    if not aplica:
        return semilla("canales") or []

    base = list((await db.execute(
        select(CanalComercial).where(CanalComercial.activo.is_(True))
        .order_by(CanalComercial.orden))).scalars())
    if not base or not mixer.mix_cierra(base):
        # Sin mix cargado —o con uno que no cierra— derivar daría un net factor
        # sobre una base que no es el total. Mejor la semilla de siempre.
        return semilla("canales") or []

    overs = list((await db.execute(select(CanalMixEscenario).where(
        CanalMixEscenario.scenario_id == esc.id))).scalars())
    return [{"channel": d.channel, "mix_pct": d.mix_pct,
             "commission_pct": d.commission_pct}
            for d in mixer.derivar(mixer.resolver(base, overs))]


@router.get("/scenarios/{scenario_id}/revenue/channels/config/")
async def get_channels_config(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Canales del escenario por mes (mix/comisión × 12) + net factor por mes.

    Formato pensado para la grilla: una entrada por canal con mix[12] y comm[12].
    Si un mes no tiene valor guardado, cae al primer mes disponible del canal;
    si el canal no existe, usa los defaults CWL. seeded=True si no hay nada en DB.
    """
    from app.seed_data import semilla
    esc = await _get_scenario_or_404(scenario_id, db)
    canales_semilla = await _semilla_de_canales(esc, db)
    chs = (await db.execute(
        select(SalesChannelConfig).where(SalesChannelConfig.scenario_id == scenario_id)
    )).scalars().all()

    # Orden determinístico: los canales estándar primero (en su orden familiar),
    # luego los demás alfabéticamente. Sin esto el SELECT devuelve por UUID y la
    # grilla "salta" entre recargas.
    default_by_code = {d["channel"]: d for d in canales_semilla}
    _PREFERRED = ["TA", "Travel Agency", "OTA", "OTAs", "DIRECT", "Direct"]

    def _order_key(ch: str):
        return (0, _PREFERRED.index(ch)) if ch in _PREFERRED else (1, ch.lower())

    if chs:
        distinct = list({c.channel for c in chs})
        order = sorted(distinct, key=_order_key)
    else:
        order = [d["channel"] for d in canales_semilla]

    # index (channel, month) -> row ; y un fallback por canal (cualquier mes)
    by_key = {(c.channel, c.month): c for c in chs}
    any_by_channel: dict[str, SalesChannelConfig] = {}
    for c in chs:
        any_by_channel.setdefault(c.channel, c)

    def val(channel: str, month: int, field: str) -> Decimal:
        row = by_key.get((channel, month)) or any_by_channel.get(channel)
        if row is not None:
            return getattr(row, field)
        d = default_by_code.get(channel)
        return d[field] if d else Decimal("0")

    channels_out = []
    for code in order:
        channels_out.append({
            "channel": code,
            "label": _CHANNEL_LABELS.get(code, code),
            "mix": [str(val(code, m, "mix_pct")) for m in range(1, 13)],
            "comm": [str(val(code, m, "commission_pct")) for m in range(1, 13)],
        })

    # net factor por mes = Σ(mix × (1 − comm)) de ese mes
    net_factor = []
    for m in range(1, 13):
        nf = sum(val(code, m, "mix_pct") * (Decimal("1") - val(code, m, "commission_pct")) for code in order)
        net_factor.append(str(nf))

    return {
        "scenario_id": scenario_id,
        "seeded": not chs,
        "channels": channels_out,
        "net_factor": net_factor,
    }


class ChannelMonthRow(BaseModel):
    channel: str
    month: int
    mix_pct: Decimal
    commission_pct: Decimal


@router.put("/scenarios/{scenario_id}/revenue/channels/bulk/")
async def bulk_channels(
    scenario_id: str, rows: list[ChannelMonthRow], db: AsyncSession = Depends(get_db),
):
    """Reemplaza los canales del escenario (una fila por canal × mes)."""
    import uuid as _uuid
    from sqlalchemy import delete as _delete
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    await db.execute(_delete(SalesChannelConfig).where(SalesChannelConfig.scenario_id == scenario_id))
    await db.flush()
    for r in rows:
        if not 1 <= r.month <= 12:
            continue
        db.add(SalesChannelConfig(
            id=str(_uuid.uuid4()), scenario_id=scenario_id, hotel_id=scenario.hotel_id,
            channel=r.channel[:40], month=r.month,
            mix_pct=r.mix_pct, commission_pct=r.commission_pct,
        ))
    await db.commit()
    return {"saved": len(rows), "scenario_id": scenario_id}


@router.get("/scenarios/{scenario_id}/revenue/channels/")
async def get_channels(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Return sales channel config (mix % and commission %) for a scenario."""
    await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(
        select(SalesChannelConfig).where(SalesChannelConfig.scenario_id == scenario_id)
    )
    chs = q.scalars().all()
    return [
        {
            "id": ch.id,
            "channel": ch.channel,
            "mix_pct": str(ch.mix_pct),
            "commission_pct": str(ch.commission_pct),
        }
        for ch in chs
    ]


@router.get("/scenarios/{scenario_id}/revenue/packages/")
async def get_packages(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Return package component rates for a scenario."""
    await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(
        select(PackageConfig).where(PackageConfig.scenario_id == scenario_id)
    )
    pkgs = q.scalars().all()
    return [
        {
            "id": pkg.id,
            "component": pkg.component,
            "rate_per_pax_night": str(pkg.rate_per_pax_night),
            "is_commissionable": pkg.is_commissionable,
            "bev_food_ratio": str(pkg.bev_food_ratio) if pkg.bev_food_ratio is not None else None,
        }
        for pkg in pkgs
    ]


# ─── Paquete CWL (componentes por pax/noche) ──────────────────────────────────
# Orden de los componentes en la pantalla. Beverage se deriva del ratio de Food.
_PKG_ORDER = ["FOOD", "ACTIVITIES", "TRANSPORT", "SUSTAINABILITY"]


async def etiquetas_de_componente(
    db: AsyncSession, hotel_id: str, kind: str = KIND_PACKAGE,
) -> dict[str, str]:
    """Los rótulos de esta propiedad: el por defecto, pisado por lo que editó.

    El CÓDIGO es fijo y liga (el motor calcula por `FOOD`, `ACTIVITIES`…); la
    etiqueta es lo que se lee y se edita. Misma regla que los tipos de
    habitación.
    """
    base = dict(ETIQUETAS_POR_DEFECTO.get(kind, {}))
    filas = (await db.execute(select(ComponentLabel).where(
        ComponentLabel.hotel_id == hotel_id, ComponentLabel.kind == kind,
    ))).scalars().all()
    for f in filas:
        if (f.label or "").strip():
            base[f.code] = f.label
    return base


@router.get("/hotels/{hotel_id}/component-labels/")
async def get_component_labels(
    hotel_id: str, kind: str = KIND_PACKAGE, db: AsyncSession = Depends(get_db),
):
    """Rótulos editables + el texto por defecto, para poder volver atrás."""
    actuales = await etiquetas_de_componente(db, hotel_id, kind)
    porDefecto = ETIQUETAS_POR_DEFECTO.get(kind, {})
    return {
        "hotel_id": hotel_id, "kind": kind,
        "labels": [
            {"code": c, "label": actuales.get(c, c), "por_defecto": porDefecto[c],
             "editado": actuales.get(c) != porDefecto[c]}
            for c in porDefecto
        ],
    }


class ComponentLabelIn(BaseModel):
    label: str


@router.put("/hotels/{hotel_id}/component-labels/{code}/")
async def put_component_label(
    hotel_id: str, code: str, body: ComponentLabelIn,
    kind: str = KIND_PACKAGE, db: AsyncSession = Depends(get_db),
):
    """Cambia el RÓTULO de un componente. El código no se toca.

    Mandar la etiqueta vacía devuelve el texto por defecto — es el «deshacer»,
    y por eso borra la fila en vez de guardar un vacío.
    """
    if code not in ETIQUETAS_POR_DEFECTO.get(kind, {}):
        raise ErrorApi(404, "componente.no_existe", codigo=code,
                       codigos=', '.join(ETIQUETAS_POR_DEFECTO.get(kind, {})))
    fila = (await db.execute(select(ComponentLabel).where(
        ComponentLabel.hotel_id == hotel_id, ComponentLabel.kind == kind,
        ComponentLabel.code == code,
    ))).scalar_one_or_none()
    nuevo = (body.label or "").strip()
    if not nuevo:
        if fila is not None:
            await db.delete(fila)
            await db.commit()
        return {"code": code, "label": ETIQUETAS_POR_DEFECTO[kind][code], "editado": False}
    if fila is None:
        fila = ComponentLabel(hotel_id=hotel_id, kind=kind, code=code)
        db.add(fila)
    fila.label = nuevo
    await db.commit()
    return {"code": code, "label": nuevo, "editado": True}


@router.get("/scenarios/{scenario_id}/revenue/packages/config/")
async def get_packages_config(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Componentes del paquete (por pax/noche).

    Si no hay nada guardado se sugiere la semilla de ESTA propiedad. Una
    propiedad sin semilla nace en cero — antes le llegaba la de Corcovado.
    """
    from app.seed_data import semilla
    paquete = semilla("paquete") or {}
    await _get_scenario_or_404(scenario_id, db)
    pkgs = {p.component: p for p in (await db.execute(
        select(PackageConfig).where(PackageConfig.scenario_id == scenario_id)
    )).scalars().all()}
    seeded = not pkgs

    def val(comp, field, default):
        p = pkgs.get(comp)
        return getattr(p, field) if p is not None else default

    etiquetas = await etiquetas_de_componente(db, HOTEL_ID)
    rows = []
    for comp in _PKG_ORDER:
        d = paquete.get(comp, {})
        rows.append({
            "component": comp,
            "label": etiquetas.get(comp, comp),
            "rate_per_pax_night": str(val(comp, "rate_per_pax_night", d.get("rate_per_pax_night", Decimal("0")))),
            "is_commissionable": bool(val(comp, "is_commissionable", d.get("is_commissionable", True))),
        })
    # Beverage = ratio del Food
    food = pkgs.get("FOOD")
    bev_ratio = food.bev_food_ratio if (food and food.bev_food_ratio is not None) else \
        paquete.get("FOOD", {}).get("bev_food_ratio", Decimal("0.34"))
    return {
        "scenario_id": scenario_id,
        "seeded": seeded,
        "sin_semilla": not paquete,   # la propiedad todavia no cargo lo suyo
        "components": rows,
        "bev_food_ratio": str(bev_ratio),
    }


class PackageComponentRow(BaseModel):
    component: str
    rate_per_pax_night: Decimal
    is_commissionable: bool = True


class PackagesBulk(BaseModel):
    components: list[PackageComponentRow]
    bev_food_ratio: Decimal = Decimal("0.34")


@router.put("/scenarios/{scenario_id}/revenue/packages/bulk/")
async def bulk_packages(
    scenario_id: str, payload: PackagesBulk, db: AsyncSession = Depends(get_db),
):
    """Reemplaza los componentes del paquete. Beverage va como ratio del Food."""
    import uuid as _uuid
    from sqlalchemy import delete as _delete
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    await db.execute(_delete(PackageConfig).where(PackageConfig.scenario_id == scenario_id))
    await db.flush()
    for r in payload.components:
        comp = r.component.upper()
        db.add(PackageConfig(
            id=str(_uuid.uuid4()), scenario_id=scenario_id, hotel_id=scenario.hotel_id,
            component=comp, rate_per_pax_night=r.rate_per_pax_night,
            is_commissionable=r.is_commissionable,
            bev_food_ratio=payload.bev_food_ratio if comp == "FOOD" else None,
        ))
    await db.commit()
    return {"saved": len(payload.components), "scenario_id": scenario_id}


# ─── Package Components (menú + experiencias que eligen del menú) ──────────────

def _pkg_item_to_dict(it) -> dict:
    return {
        "inclusion": it.inclusion, "unit": it.unit,
        "unit_price": (str(it.unit_price) if it.unit_price is not None else None),
        "enabled": it.enabled, "notes": it.notes, "category": it.category,
        "qty_mult_single": str(it.qty_mult_single), "qty_mult_double": str(it.qty_mult_double),
        "info": it.info,
    }


@router.get("/scenarios/{scenario_id}/packages/components/config/")
async def get_package_components(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Experiencias (sub-tabs), cada una con su tabla de inclusiones.

    Si está vacío, sugiere Classic 3N/4D (con sus inclusiones del Excel) + VIP 4N/5D vacío.
    """
    from app.models.package_menu import PkgExperience, PkgExperienceItem
    from app.seed_data import semilla
    await _get_scenario_or_404(scenario_id, db)
    exps = (await db.execute(
        select(PkgExperience).where(PkgExperience.scenario_id == scenario_id)
        .order_by(PkgExperience.sort_order)
    )).scalars().all()

    if not exps:
        sugeridas = semilla("experiencias")
        if not sugeridas:
            # Propiedad sin semilla: pantalla en blanco, que es la verdad.
            return {"scenario_id": scenario_id, "seeded": False,
                    "sin_semilla": True, "experiences": []}
        return {
            "scenario_id": scenario_id, "seeded": True,
            "experiences": [
                {
                    "name": e["name"], "nights": e["nights"], "days": e["days"],
                    "es_base": bool(e.get("es_base")),
                    "items": [
                        {**it, "unit_price": (str(it["unit_price"]) if it["unit_price"] is not None else None),
                         "qty_mult_single": str(it["qty_mult_single"]), "qty_mult_double": str(it["qty_mult_double"])}
                        for it in e["items"]
                    ],
                }
                for e in sugeridas
            ],
        }

    items = (await db.execute(
        select(PkgExperienceItem).order_by(PkgExperienceItem.sort_order))).scalars().all()
    items_by_exp: dict[str, list] = {}
    for it in items:
        items_by_exp.setdefault(it.experience_id, []).append(it)
    # Ninguna marcada = dato anterior a la marca. Vale la primera, y se dice en
    # la respuesta para que la pantalla no tenga que adivinarlo.
    hay_base = any(getattr(e, "es_base", False) for e in exps)
    return {
        "scenario_id": scenario_id, "seeded": False,
        "experiences": [
            {"name": e.name, "nights": e.nights, "days": e.days,
             "es_base": bool(getattr(e, "es_base", False)) if hay_base else (i == 0),
             "items": [_pkg_item_to_dict(it) for it in items_by_exp.get(e.id, [])]}
            for i, e in enumerate(exps)
        ],
    }


class PkgItemIn(BaseModel):
    inclusion: str
    unit: str = ""
    unit_price: Decimal | None = None
    enabled: bool = True
    notes: str = ""
    category: str = ""
    qty_mult_single: Decimal = Decimal("1")
    qty_mult_double: Decimal = Decimal("1")
    info: str = ""


class ExperienceIn(BaseModel):
    name: str
    nights: int = 0
    days: int = 0
    # Cuál alimenta el Rack & Net. Opcional: si nadie la manda, vale la primera.
    es_base: bool = False
    items: list[PkgItemIn] = []


class PackageComponentsBulk(BaseModel):
    experiences: list[ExperienceIn]


@router.put("/scenarios/{scenario_id}/packages/components/bulk/")
async def bulk_package_components(
    scenario_id: str, payload: PackageComponentsBulk, db: AsyncSession = Depends(get_db),
):
    """Reemplaza las experiencias y sus inclusiones."""
    import uuid as _uuid
    from sqlalchemy import delete as _delete
    from app.models.package_menu import PkgExperience, PkgExperienceItem
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    exp_ids = [e.id for e in (await db.execute(
        select(PkgExperience).where(PkgExperience.scenario_id == scenario_id))).scalars().all()]
    if exp_ids:
        await db.execute(_delete(PkgExperienceItem).where(PkgExperienceItem.experience_id.in_(exp_ids)))
    await db.execute(_delete(PkgExperience).where(PkgExperience.scenario_id == scenario_id))
    await db.flush()

    # Exactamente UNA base. Si el que guarda no marcó ninguna —o borró la que lo
    # era— vale la primera: el tab de Rack & Net no puede quedarse sin fuente, y
    # dejarlo en cero sería una pantalla vacía sin explicación.
    marcadas = [i for i, e in enumerate(payload.experiences) if getattr(e, "es_base", False)]
    base_idx = marcadas[0] if marcadas else 0

    total_items = 0
    for i, e in enumerate(payload.experiences):
        eid = str(_uuid.uuid4())
        db.add(PkgExperience(
            id=eid, scenario_id=scenario_id, hotel_id=scenario.hotel_id,
            name=e.name[:120], nights=e.nights, days=e.days, sort_order=i,
            es_base=(i == base_idx)))
        for j, it in enumerate(e.items):
            total_items += 1
            db.add(PkgExperienceItem(
                id=str(_uuid.uuid4()), experience_id=eid, sort_order=j,
                inclusion=it.inclusion[:120], unit=it.unit[:30], unit_price=it.unit_price,
                enabled=it.enabled, notes=it.notes[:200], category=it.category[:20],
                qty_mult_single=it.qty_mult_single, qty_mult_double=it.qty_mult_double,
                info=it.info[:120]))
    await db.commit()
    return {"saved_experiences": len(payload.experiences), "saved_items": total_items,
            "base": base_idx}


class RateCardUpdate(BaseModel):
    rack_rate: Decimal
    net_rate: Decimal
    pax_per_room: Decimal = Decimal("1.8")


@router.put("/scenarios/{scenario_id}/revenue/rate-cards/{room_type_id}/{month}/")
async def update_rate_card(
    scenario_id: str,
    room_type_id: str,
    month: int,
    payload: RateCardUpdate,
    db: AsyncSession = Depends(get_db),
):
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    q = await db.execute(
        select(RateCard).where(
            RateCard.scenario_id == scenario_id,
            RateCard.room_type_id == room_type_id,
            RateCard.month == month,
        )
    )
    rc = q.scalar_one_or_none()
    if not rc:
        import uuid
        rc = RateCard(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            hotel_id=scenario.hotel_id,
            room_type_id=room_type_id,
            month=month,
            rack_rate=payload.rack_rate,
            net_rate=payload.net_rate,
            pax_per_room=payload.pax_per_room,
        )
        db.add(rc)
    else:
        rc.rack_rate = payload.rack_rate
        rc.net_rate = payload.net_rate
        rc.pax_per_room = payload.pax_per_room

    await db.commit()
    return {"updated": True, "room_type_id": room_type_id, "month": month}


class OccupancyUpdate(BaseModel):
    rooms_occupied: Decimal


@router.put("/scenarios/{scenario_id}/revenue/occupancy/{room_type_id}/{month}/")
async def update_occupancy(
    scenario_id: str,
    room_type_id: str,
    month: int,
    payload: OccupancyUpdate,
    db: AsyncSession = Depends(get_db),
):
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    q = await db.execute(
        select(OccupancyBudget).where(
            OccupancyBudget.scenario_id == scenario_id,
            OccupancyBudget.room_type_id == room_type_id,
            OccupancyBudget.month == month,
        )
    )
    ob = q.scalar_one_or_none()
    if not ob:
        import uuid
        ob = OccupancyBudget(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            hotel_id=scenario.hotel_id,
            room_type_id=room_type_id,
            month=month,
            rooms_occupied=payload.rooms_occupied,
        )
        db.add(ob)
    else:
        ob.rooms_occupied = payload.rooms_occupied

    await db.commit()
    return {"updated": True, "room_type_id": room_type_id, "month": month}


# ─── Historical KPIs (2024/2025 actuals, read-only reference) ──────────────────

def _historical_to_dict(h: HistoricalKpi) -> dict:
    return {
        "hotel_id": h.hotel_id,
        "year": h.year,
        "month": h.month,
        "room_type_id": h.room_type_id,
        "rooms_available": h.rooms_available,
        "rooms_occupied": str(h.rooms_occupied),
        "guests": str(h.guests),
        "occupancy_pct": str(h.occupancy_pct),
        "adr_usd": str(h.adr_usd),
        "revpar_usd": str(h.revpar_usd),
        "revenue_usd": str(h.revenue_usd),
        "source": h.source,
    }


@router.post("/hotels/{hotel_id}/historical/import/", dependencies=[Depends(registro_de_subida)])
async def import_historical_data(
    hotel_id: str,
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Import 2024/2025 actual room KPIs from the budget Excel ('Rooms' sheet).
    Accepts an optional file upload; falls back to server-local EXCEL_PATH for dev.
    Re-importable: clears any existing historical rows for this hotel first.
    """
    import tempfile, os
    if file is not None:
        contents = await file.read()
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
        tmp.write(contents)
        tmp.flush()
        tmp.close()
        xlsx = Path(tmp.name)
    elif EXCEL_PATH.exists():
        xlsx = EXCEL_PATH
        tmp = None
    else:
        raise ErrorApi(404, "excel.no_encontrado")

    existing = await db.execute(
        select(HistoricalKpi).where(HistoricalKpi.hotel_id == hotel_id)
    )
    for obj in existing.scalars().all():
        await db.delete(obj)
    await db.flush()

    try:
        records = import_historical_kpi(xlsx, hotel_id)
    finally:
        if file is not None and tmp is not None:
            os.unlink(tmp.name)

    for rec in records:
        db.add(rec)
    await db.commit()

    return {
        "imported": len(records),
        "hotel_id": hotel_id,
        "years": sorted({r.year for r in records}),
    }


@router.get("/scenarios/{scenario_id}/stats/export/excel/")
async def export_stats_excel(scenario_id: str, db: AsyncSession = Depends(get_db)):
    scenario = await _get_scenario_or_404(scenario_id, db)
    stats_rows = (await db.execute(
        select(ScenarioStat)
        .where(ScenarioStat.scenario_id == scenario_id)
        .order_by(ScenarioStat.month)
    )).scalars().all()

    by_month = {
        s.month: {
            "rooms_available": int(s.rooms_available or 0),
            "rooms_occupied": float(s.rooms_occupied or 0),
            "guests": float(s.guests or 0),
            "occupancy_pct": float(s.occupancy_pct or 0),
            "adr": float(s.adr or 0),
        }
        for s in stats_rows
    }

    label = f"{scenario.hotel_id} {scenario.version}"
    xlsx = export_stats_to_excel(by_month, label, scenario.year)
    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="stats_{scenario_id}.xlsx"'},
    )


@router.post("/scenarios/{scenario_id}/stats/import/excel/", dependencies=[Depends(registro_de_subida)])
async def import_stats_excel(
    scenario_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    import uuid as _uuid
    from sqlalchemy import delete as _delete
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(409, str(e))

    rows = import_stats_from_excel(await file.read())
    if not rows:
        raise ErrorApi(422, "stats.sin_datos_validos")

    await db.execute(_delete(ScenarioStat).where(ScenarioStat.scenario_id == scenario_id))
    await db.flush()

    for r in rows:
        month = r.get("month")
        if not month:
            continue
        occ = r.get("occupancy_pct", 0)
        rooms_avail = int(r.get("rooms_available", 0) or 0)
        rooms_occ   = r.get("rooms_occupied", 0) or 0
        if rooms_avail > 0 and rooms_occ > 0 and (not occ or occ == 0):
            from decimal import Decimal as _D
            occ = _D(str(rooms_occ)) / _D(str(rooms_avail))
        db.add(ScenarioStat(
            id=str(_uuid.uuid4()),
            scenario_id=scenario_id,
            month=month,
            rooms_available=rooms_avail,
            rooms_occupied=r.get("rooms_occupied", 0) or 0,
            guests=r.get("guests", 0) or 0,
            occupancy_pct=occ,
            adr=r.get("adr", 0) or 0,
        ))

    await db.commit()
    return {"imported": len(rows), "scenario_id": scenario_id}


# ─── Revenue checkbook (direct USD per line, alternative to drivers) ───────────

_MONTH_KEYS = ["jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"]


@router.get("/scenarios/{scenario_id}/revenue/checkbook/")
async def get_revenue_checkbook(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Return the 11 revenue lines × 12 months (zero-seeded for missing lines).

    Always returns every canonical line so the grid renders a full table even
    before anything is saved. `source` echoes scenario.revenue_source.
    """
    scenario = await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(
        select(RevenueEntry).where(RevenueEntry.scenario_id == scenario_id)
    )
    by_line = {e.line.upper(): e for e in q.scalars().all()}

    rows = []
    for line in REVENUE_LINES:
        e = by_line.get(line)
        dept_cta = REVENUE_LINE_ACCOUNT.get(line)
        rows.append({
            "line": line,
            "label": REVENUE_LINE_LABELS.get(line, line.title()),
            # La cuenta contable, donde la línea ES una cuenta. `ROOMS` o `FOOD`
            # agregan varias, así que van sin código: poner uno sería mentir.
            "dept": dept_cta[0] if dept_cta else None,
            "account": dept_cta[1] if dept_cta else None,
            **{
                mk: (str(e.get_month(i + 1)) if e else "0")
                for i, mk in enumerate(_MONTH_KEYS)
            },
        })
    return {
        "scenario_id": scenario_id,
        "year": scenario.year,
        "source": getattr(scenario, "revenue_source", "drivers"),
        "lines": rows,
    }


class RevenueCheckbookRow(BaseModel):
    line: str
    jan: Decimal = Decimal("0"); feb: Decimal = Decimal("0")
    mar: Decimal = Decimal("0"); apr: Decimal = Decimal("0")
    may: Decimal = Decimal("0"); jun: Decimal = Decimal("0")
    jul: Decimal = Decimal("0"); aug: Decimal = Decimal("0")
    sep: Decimal = Decimal("0"); oct: Decimal = Decimal("0")
    nov: Decimal = Decimal("0"); dec: Decimal = Decimal("0")


@router.put("/scenarios/{scenario_id}/revenue/checkbook/bulk/")
async def bulk_replace_revenue_checkbook(
    scenario_id: str,
    rows: list[RevenueCheckbookRow],
    db: AsyncSession = Depends(get_db),
):
    """Replace all RevenueEntry rows for a scenario with the posted lines.

    Unknown line codes are rejected (keeps the table aligned to the P&L lines).
    """
    from sqlalchemy import delete as _delete
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    valid = set(REVENUE_LINES)
    bad = [r.line for r in rows if r.line.upper() not in valid]
    if bad:
        raise ErrorApi(422, "revenue.lineas_invalidas", lineas=sorted(set(bad)))

    await db.execute(_delete(RevenueEntry).where(RevenueEntry.scenario_id == scenario_id))
    await db.flush()
    for r in rows:
        db.add(RevenueEntry(
            scenario_id=scenario_id,
            hotel_id=scenario.hotel_id,
            line=r.line.upper(),
            **{mk: getattr(r, mk) for mk in _MONTH_KEYS},
        ))
    await db.commit()
    return {"saved": len(rows), "scenario_id": scenario_id}


@router.post("/scenarios/{scenario_id}/revenue/push-to-checkbook/")
async def push_revenue_to_checkbook(
    scenario_id: str, dry_run: bool = Query(False), db: AsyncSession = Depends(get_db),
):
    """Pasa el ingreso calculado (tarifas × ocupación × canales) al **checkbook de
    ingresos**, que es de donde el P&L toma el ingreso.

    Existe porque el ingreso del presupuesto sale ÚNICAMENTE del checkbook: las
    pantallas de tarifas/ocupación son la calculadora, y este botón traslada el
    resultado. dry_run=true muestra el antes/después sin escribir.
    """
    from app.engine.recalculate import load_revenue_results, revenue_line_dict
    import copy as _copy
    import uuid as _uuid

    scenario = await _get_scenario_or_404(scenario_id, db)
    if not dry_run:
        try:
            scenario.assert_editable()
        except Exception as e:
            raise HTTPException(status_code=409, detail=str(e))

    # Resincronizar net_rate = rack × factor neto ANTES de calcular. Las tarifas
    # guardadas antes del arreglo conservan un net_rate viejo, y el motor calcula el
    # ingreso de habitaciones con net_rate: sin esto el botón pasaría al checkbook una
    # cifra distinta a la que muestra la pantalla (se vio: $3,081,887 vs $3,560,262).
    from app.models.sales_channel_config import compute_net_factor
    canales = (await db.execute(
        select(SalesChannelConfig).where(SalesChannelConfig.scenario_id == scenario_id)
    )).scalars().all()
    tarjetas = (await db.execute(
        select(RateCard).where(RateCard.scenario_id == scenario_id)
    )).scalars().all()
    nf_mes = {m: compute_net_factor([c for c in canales if c.month == m])
              for m in range(1, 13)}
    _exigir_mix(nf_mes, scenario_id)
    resync = 0
    for t in tarjetas:
        esperado = (Decimal(str(t.rack_rate or 0)) * nf_mes.get(t.month, Decimal("1"))
                    ).quantize(Decimal("0.01"))
        if (t.net_rate or Decimal("0")) != esperado:
            t.net_rate = esperado
            resync += 1
    await db.flush()

    # Se fuerza el cálculo por drivers aunque el escenario ya lea del checkbook.
    calc = _copy.copy(scenario)
    calc.revenue_source = "drivers"
    resultados = await load_revenue_results(db, calc)

    actuales = {e.line.upper(): e for e in (await db.execute(
        select(RevenueEntry).where(RevenueEntry.scenario_id == scenario_id)
    )).scalars().all()}

    # Las NOCHES viajan con la plata. El botón pasaba solo el ingreso y dejaba
    # scenario_stats donde estaba: el revenue calzaba al centavo mientras la
    # ocupación se quedaba atrás. En Budget 2027 eso eran 618 noches de
    # diferencia (4,363 contra 4,982) y un ADR de abril de $1,171 que no existe
    # — revenue correcto dividido entre una ocupación vieja. Nada avisaba,
    # porque el total de ingreso cuadraba perfecto.
    stats = {s.month: s for s in (await db.execute(
        select(ScenarioStat).where(ScenarioStat.scenario_id == scenario_id)
    )).scalars().all()}
    noches_antes = float(sum(float(s.rooms_occupied or 0) for s in stats.values()))
    noches_despues = float(sum(float(getattr(r, "rooms_occupied", 0) or 0)
                               for r in resultados.values()))
    if not dry_run:
        for mes, r in resultados.items():
            st = stats.get(mes)
            if st is None:
                st = ScenarioStat(id=str(_uuid.uuid4()), scenario_id=scenario_id, month=mes)
                db.add(st)
            st.rooms_available = int(getattr(r, "rooms_available", 0) or 0)
            st.rooms_occupied = Decimal(str(getattr(r, "rooms_occupied", 0) or 0))
            st.guests = Decimal(str(getattr(r, "guests", 0) or 0))
            # occupancy_pct y adr se derivan de lo de arriba: si se dejaran como
            # estaban, la pantalla mostraría un ADR que ya no corresponde.
            disp = Decimal(str(st.rooms_available or 0))
            ocup = Decimal(str(st.rooms_occupied or 0))
            st.occupancy_pct = (ocup / disp) if disp else Decimal("0")
            st.adr = (Decimal(str(getattr(r, "rooms", 0) or 0)) / ocup) if ocup else Decimal("0")

    lineas: dict[str, dict[int, Decimal]] = {}
    for mes, r in resultados.items():
        for linea, monto in revenue_line_dict(r).items():
            lineas.setdefault(linea.upper(), {})[mes] = Decimal(str(monto or 0))

    detalle = []
    for linea, meses in sorted(lineas.items()):
        nuevo = sum(meses.values())
        fila = actuales.get(linea)
        anterior = sum((getattr(fila, mk) or Decimal("0")) for mk in _RR_MONTHS) if fila else Decimal("0")
        detalle.append({"linea": linea, "antes": round(float(anterior), 2),
                        "despues": round(float(nuevo), 2),
                        "dif": round(float(nuevo - anterior), 2)})
        if dry_run:
            continue
        if fila is None:
            fila = RevenueEntry(id=str(_uuid.uuid4()), scenario_id=scenario_id,
                                hotel_id=scenario.hotel_id, line=linea)
            db.add(fila)
        for i, mk in enumerate(_RR_MONTHS, start=1):
            setattr(fila, mk, meses.get(i, Decimal("0")))

    if dry_run:
        await db.rollback()      # deshace el resync en memoria: no escribe nada
    else:
        await db.commit()
    return {
        "dry_run": dry_run, "scenario_id": scenario_id,
        "tarifas_resincronizadas": resync,
        "total_antes": round(sum(d["antes"] for d in detalle), 2),
        "total_despues": round(sum(d["despues"] for d in detalle), 2),
        "noches_antes": round(noches_antes, 2),
        "noches_despues": round(noches_despues, 2),
        "lineas": detalle,
    }


class RevenueSourceUpdate(BaseModel):
    revenue_source: str   # 'drivers' | 'checkbook'


@router.patch("/scenarios/{scenario_id}/revenue/source/")
async def set_revenue_source(
    scenario_id: str,
    payload: RevenueSourceUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Toggle which revenue source feeds the P&L for this scenario."""
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    src = payload.revenue_source.lower().strip()
    if src not in ("drivers", "checkbook"):
        raise ErrorApi(422, "revenue.fuente_invalida")
    scenario.revenue_source = src
    await db.commit()
    return {"updated": True, "scenario_id": scenario_id, "revenue_source": src}


# ─── Spa budget (capture-rate model) ──────────────────────────────────────────

@router.get("/scenarios/{scenario_id}/revenue/spa/")
async def get_spa_budget(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Return the Spa capture-rate config (12 months) for a scenario.

    Pax per month is computed on the client from the drivers (same as the
    revenue checkbook KPIs). Here we only persist capture_pct per month and a
    single avg treatment price.
    """
    scenario = await _get_scenario_or_404(scenario_id, db)
    q = await db.execute(select(SpaBudget).where(SpaBudget.scenario_id == scenario_id))
    by_month = {s.month: s for s in q.scalars().all()}
    price = next((str(s.avg_price) for s in by_month.values() if s.avg_price), "0")
    months = [
        {
            "month": m,
            "capture_pct": str(by_month[m].capture_pct) if m in by_month else "0",
        }
        for m in range(1, 13)
    ]
    return {
        "scenario_id": scenario_id,
        "year": scenario.year,
        "seeded": len(by_month) == 0,
        "avg_price": price,
        "months": months,
        # El ingreso del Spa aterriza en las dos fuentes de ingreso, así que
        # llega al P&L en cualquiera de los dos modos. Ver `_llega_al_pl.py`.
        "llega_al_pl": llega_al_pl(scenario),
        "modo_ingresos": modo_ingresos(scenario),
    }


class SpaMonthIn(BaseModel):
    month: int
    capture_pct: Decimal = Decimal("0")
    revenue: Decimal = Decimal("0")   # ingreso calculado en el cliente (pax × capture × precio)


class SpaBulkIn(BaseModel):
    avg_price: Decimal = Decimal("0")
    months: list[SpaMonthIn]


@router.put("/scenarios/{scenario_id}/revenue/spa/bulk/")
async def bulk_spa_budget(
    scenario_id: str,
    payload: SpaBulkIn,
    db: AsyncSession = Depends(get_db),
):
    """Guarda el capture rate del Spa y **deposita el ingreso calculado en la
    línea SPA**, sin tocar las demás líneas.

    El Spa tenía el mismo agujero que el Club: el ingreso solo aterrizaba en el
    checkbook (`RevenueEntry`), que es la fuente del modo `checkbook`. En un
    escenario en modo `drivers` el número se guardaba y el P&L no lo veía. Va por
    el mismo camino compartido — ver `app/api/_ingreso_de_driver.py`.
    """
    from sqlalchemy import delete as _delete
    import uuid as _uuid
    scenario = await _get_scenario_or_404(scenario_id, db)
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    await db.execute(_delete(SpaBudget).where(SpaBudget.scenario_id == scenario_id))
    await db.flush()
    for m in payload.months:
        db.add(SpaBudget(
            id=str(_uuid.uuid4()), scenario_id=scenario_id, hotel_id=scenario.hotel_id,
            month=m.month, capture_pct=m.capture_pct, avg_price=payload.avg_price,
        ))

    rev_by_month = {m.month: m.revenue for m in payload.months}
    await persistir_ingreso_de_driver(db, scenario, {
        "SPA": [rev_by_month.get(i, Decimal("0")) for i in range(1, 13)]})

    await db.commit()
    total = sum(rev_by_month.values())
    return {"saved": True, "scenario_id": scenario_id, "spa_total": str(total),
            # Que la respuesta del guardado lo diga, no solo la de la carga
            # inicial: si algún día vuelve a haber una fuente que no se lea, la
            # pantalla se entera en el mismo momento en que se guarda.
            "llega_al_pl": llega_al_pl(scenario),
            "modo_ingresos": modo_ingresos(scenario)}


@router.get("/hotels/{hotel_id}/historical/")
async def get_historical_data(
    hotel_id: str,
    year: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Return historical KPIs (2024/2025 actuals) for a hotel, optionally filtered by year."""
    q = select(HistoricalKpi).where(HistoricalKpi.hotel_id == hotel_id)
    if year is not None:
        q = q.where(HistoricalKpi.year == year)
    q = q.order_by(HistoricalKpi.year, HistoricalKpi.month)
    rows = (await db.execute(q)).scalars().all()
    return [_historical_to_dict(h) for h in rows]
