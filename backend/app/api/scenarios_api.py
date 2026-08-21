"""
API de escenarios y hotel master data.

Endpoints:
  GET  /api/hotel/                    datos del hotel CWL
  GET  /api/hotel/room-types/         tipos de habitación
  GET  /api/scenarios/                lista de escenarios
  POST /api/scenarios/                crear escenario (incluye 12 TCs)
  GET  /api/scenarios/{id}/           detalle
  PATCH /api/scenarios/{id}/status/   cambiar status (lock/unlock)
  DELETE /api/scenarios/{id}/         eliminar (solo draft)
"""
import uuid
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from app.importers.registro_dep import registro_de_subida
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api._candado import candado
from app.db import get_db
from app.auth import get_current_user
from app.errores import ErrorApi
from app.textos import Idioma, t
from app.models.hotel import Hotel
from app.models.scenario import Scenario, ScenarioLockedError, SCENARIO_TYPES, SCENARIO_STATUSES
from app.models.exchange_rate import ExchangeRate
from app.models.room_type_config import RoomTypeConfig
from app.models.scenario_master import ScenarioMaster
from app.models.payroll_position import PayrollPosition
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.payroll_params import PayrollParams
from app.models.opex_entry import OpexEntry
from app.models.cost_entry import CostEntry
from app.models.rate_card import RateCard
from app.models.occupancy_budget import OccupancyBudget
from app.models.sales_channel_config import SalesChannelConfig
from app.models.package_config import PackageConfig
from app.models.revenue_other import RevenueOther
from app.models.revenue_entry import RevenueEntry
from app.models.spa_budget import SpaBudget
from app.models.scenario_stat import ScenarioStat
from app.models.statistical_entry import StatisticalEntry
from app.models.club_membership_stat import ClubMembershipStat
from app.models.club_fee_budget import ClubFeeBudget
from app.models.pl_manual_input import PLManualInput
from app.models.actual_entry import ActualEntry
from app.models.actual_pl_line import ActualPLLine
from app.models.revenue_account_entry import RevenueAccountEntry
from app.models.belowgop_account_entry import BelowGopAccountEntry
from app.models.nonop_entry import NonOpEntry
from app.models.capital_project import CapitalProject
# ── modelos que faltaban en el copy (auxiliares, allocations, fórmulas, cash flow) ──
from app.models.cafeteria_allocation_config import CafeteriaAllocationConfig
from app.models.laundry_allocation_config import LaundryAllocationConfig
from app.models.salary_allocation_config import SalaryAllocationConfig
from app.models.rooms_allocation_config import RoomsAllocationConfig
from app.models.laundry_params import LaundryParams
from app.models.allocation_entry import AllocationEntry
from app.models.benefit_allocation_config import BenefitAllocationConfig
from app.models.cashflow_directo_config import CashFlowDirectoConfig
from app.models.cashflow_params import CashFlowParams
from app.models.cashflow_wc_params import CashFlowWCParams
from app.models.cashflow_budget_driver import CashFlowBudgetDriver
from app.models.cashflow_budget_input import CashFlowBudgetInput
from app.models.tax_params import TaxParams
from app.models.package_menu import PkgExperience
from app.models.canal_mix_escenario import CanalMixEscenario
from app.models.channel_mix import ChannelMixEntry, ChannelMixDetail
from app.models.country_mix import CountryMixEntry
from app.models.ops_kpi import OpsKpiEntry
from sqlalchemy import delete as sa_delete
import sqlalchemy as sa
from sqlalchemy.orm import class_mapper
from app.hotel_actual import HOTEL_ID, hotel_slug

router = APIRouter()

# dataset name → ORM model(s) to copy when cloning scenario data
#: La MISMA regla que `es_contrapartida_de_allocation()` del importador, dicha en
#: SQL para poder excluirla de un DELETE masivo. Las dos tienen que decir lo
#: mismo: si se separan, el reemplazo vuelve a borrar los allocations. Lo vigila
#: `test_contrapartidas_sobreviven_al_reemplazo`.
ES_CONTRAPARTIDA_DE_ALLOCATION = sa.and_(
    ActualEntry.account_code.like("4%"),
    sa.func.lower(ActualEntry.account_name).like("%distribu%"),
)


async def _filas_que_sobreviven(db, target, merge: bool,
                                meses_del_archivo: list[int]) -> dict[int, list[dict]]:
    """Las filas de `ActualEntry` que van a SEGUIR ahí después de esta carga.

    Consolidar «solo lo que trae el archivo» da un número que el reporte nunca
    va a dar, porque hay plata que **la escribe el motor y el archivo no puede
    traer**: las contrapartidas de reparto (`4900`, `4901`, `4999`,
    «Distribución») sobreviven al reemplazo justamente por eso. Son −196.326,17
    entre Lavandería y Cafetería, y −92.176,74 en Rooms del Budget Working 2027.

    Medir sobre lo que se digita, en vez de sobre lo que escribe el motor, ya
    costó $92.176 una vez y $6.604 otra. Acá se replica EXACTAMENTE lo que hace
    el escritor de más abajo:

      · reemplazo (`merge=False`) → sobreviven solo las contrapartidas, enteras.
      · merge → sobreviven todas las filas, con los meses del archivo en cero
        (esos los pisa el archivo) — SALVO las contrapartidas, que sobreviven
        enteras también acá: el archivo no puede traerlas, así que pisarlas era
        borrarlas. Ver el escritor en `import_gl_detail`.

    ⚠️ Esto tiene que decir EXACTAMENTE lo que hace el escritor. Si se separan,
    la puerta compara contra un consolidado que el reporte nunca va a dar y
    bloquea una carga correcta (o deja pasar una mala).
    """
    from app.importers.gl_detail_importer import es_contrapartida_de_allocation
    filas = (await db.execute(select(ActualEntry).where(
        ActualEntry.scenario_id == target.id))).scalars().all()
    tocados = set(meses_del_archivo or [])
    fuera: dict[int, list[dict]] = {}
    for e in filas:
        contrapartida = es_contrapartida_de_allocation(e.account_code, e.account_name)
        if not merge and not contrapartida:
            continue
        for m in range(1, 13):
            if merge and m in tocados and not contrapartida:
                continue
            v = e.get_month(m)
            if v:
                fuera.setdefault(m, []).append({
                    "account_code": e.account_code, "dept_code": e.dept_code,
                    "amount": v})
    return fuera


COPY_DATASETS: dict[str, list] = {
    # PayrollConceptEntry va AL FINAL a propósito: se copia después de las
    # posiciones para poder reapuntar su position_id a las nuevas. Sin él, al
    # copiar se perdían los 14 conceptos manuales (horas extra, comisiones,
    # cafetería, cesantía, vacaciones, bonos…) que «Recalcular» NO repone —
    # solo repone SW, CCSS y aguinaldo.
    "payroll":  [PayrollPosition, PayrollParams, PayrollConceptEntry],
    "opex":     [OpexEntry],
    "costs":    [CostEntry],
    "revenue":  [RateCard, OccupancyBudget, SalesChannelConfig, PackageConfig, RevenueOther,
                 RevenueEntry, SpaBudget, ScenarioMaster, PkgExperience,
                 # El precio de la cuota del Club es modelo de ingresos, igual
                 # que el capture rate y el precio del Spa.
                 ClubFeeBudget],
    # El conteo de socios del Club viaja con los estadísticos: al copiar un
    # Budget, la proyección de socios (121 → 129) es parte del plan, igual
    # que la ocupación proyectada.
    # `StatisticalEntry` viaja con ellos por el mismo motivo: las noches por
    # tipo de habitación, los kilos y el headcount proyectados son parte del
    # plan. Si no viajaran, una copia de Budget nacería con el P&L completo y
    # sin una sola estadística detrás, y la ocupación saldría en cero sin que
    # nada explique por qué.
    "stats":    [ScenarioStat, ClubMembershipStat, StatisticalEntry],
    "pl_snapshot": [ActualPLLine],  # snapshot P&L por línea (forecast/budget importados)
    "manual":   [PLManualInput],
    "nonop":    [NonOpEntry],
    # El detalle de capital viaja con el escenario: sin esto, clonar un budget
    # dejaba la línea de inversión sin la lista que la explica.
    "capital":  [CapitalProject],
    "actuals":  [ActualEntry],
    # Configuración que define CÓMO calcula el escenario. Sin esto, la copia se
    # llevaba los números pero no el modelo: las allocations, el cash flow y los
    # parámetros de impuesto quedaban vacíos y el draft no reproducía al original.
    # BenefitAllocationConfig incluido: sin el, el reparto del INS (y el de
    # cualquier cuenta de beneficio) no viaja y la copia deja esas cuentas en cero.
    # RoomsAllocationConfig incluido: es el % por mes que reparte el costo de
    # Rooms a Villas y Residencias. Sin él, una copia deja el costo entero en
    # Rooms y la apertura por set aparece vacía sin decir por qué.
    "allocations": [CafeteriaAllocationConfig, LaundryAllocationConfig,
                    SalaryAllocationConfig, RoomsAllocationConfig, LaundryParams,
                    AllocationEntry, BenefitAllocationConfig],
    # CashFlowDirectoConfig incluido: es modelo de planning. Sin el, una copia
    # perderia la configuracion del metodo directo y el cash flow saldria distinto.
    "cashflow": [CashFlowParams, CashFlowWCParams, CashFlowBudgetDriver,
                 CashFlowBudgetInput, CashFlowDirectoConfig],
    "tax":      [TaxParams],
    "gl_accounts": [RevenueAccountEntry, BelowGopAccountEntry],
    # CanalMixEscenario incluido: es la EXCEPCION del mix de sub-canales de ese
    # escenario. Si no viajara, una copia de un Budget que negocio comisiones
    # distintas volveria al mix base sin avisar — y el Net Factor, que multiplica
    # todo el ingreso de habitaciones, saldria distinto al del original.
    # `ChannelMixDetail` viaja CON `ChannelMixEntry`: son la misma información a
    # dos niveles —el market code y su canal— y copiar una sin la otra dejaría
    # el escenario nuevo con un resumen que su propio detalle no explica.
    "mix":      [ChannelMixEntry, ChannelMixDetail, CountryMixEntry, OpsKpiEntry, CanalMixEscenario],
    "rates":    [ExchangeRate],   # TC por mes (al copiar a otro año se reetiqueta)
}

# Lo que se copia por defecto = EL ESCENARIO ENTERO, exactamente los mismos
# datasets que clona la foto mensual (`_clone_scenario_data`). Que fueran dos
# listas distintas era el defecto: «crear copiando» dejaba fuera el mayor
# (`actuals`), el snapshot del P&L (`pl_snapshot`) y el detalle de capital
# (`capital`) — pero SÍ heredaba `source_mode`. Un origen `imported` producía
# una copia marcada «leo el P&L del mayor» y sin mayor: el reporte se iba por
# otro camino y daba otros números, sin un solo error en pantalla.
#
# `rates` (el TC) va incluido a propósito: el tipo de cambio queda ligado a la
# versión. Sin él, una copia calcularía la planilla en colones con OTRO dólar y
# daría cifras distintas al original sin que se note por qué.
#
# Quien quiera copiar solo una parte sigue pudiendo pedir la lista que quiera;
# lo que ya no se puede es heredar el modo del origen sin heredar su mayor
# (ver `LLAVES_DEL_MAYOR` y `copy_scenario_data`).
DEFAULT_COPY_DATASETS = list(COPY_DATASETS)

#: Los dos datasets de los que se alimenta un escenario en modo `imported`: el
#: mayor por cuenta (`ActualEntry`) y el snapshot del P&L por línea
#: (`ActualPLLine`). `source_mode='imported'` sin ninguno de los dos NO es un
#: escenario histórico: es un escenario que dice serlo y no lo es.
LLAVES_DEL_MAYOR = ("actuals", "pl_snapshot")


# ─── Schemas ──────────────────────────────────────────────────────────────

class ScenarioCreate(BaseModel):
    hotel_id: str = HOTEL_ID
    year: int = 2026
    type: str = Field(..., description="ACTUAL | BUDGET | FORECAST")
    version: str = Field(..., description="v1, FINAL, MAY_REFORECAST...")
    tc_default: Decimal = Field(Decimal("530.0000"), description="TC aplicado a todos los meses")
    tc_by_month: Optional[dict[str, Decimal]] = Field(
        None, description="Override por mes {'1': 530, '7': 545, ...}"
    )
    created_by: str = ""


class StatusUpdate(BaseModel):
    status: str = Field(..., description="draft | approved | locked")


class ActualsThroughUpdate(BaseModel):
    actuals_through: int = Field(..., ge=0, le=12,
                                 description="Mes hasta el cual mandan los actuals (0=ninguno)")


# ─── Hotel ────────────────────────────────────────────────────────────────

@router.get("/hotel/")
async def get_hotel(db: AsyncSession = Depends(get_db)):
    hotel = await db.get(Hotel, HOTEL_ID)
    if not hotel:
        raise ErrorApi(404, "hotel.no_encontrado_corre_seed", hotel=HOTEL_ID)
    return {
        "id": hotel.id,
        "name": hotel.name,
        "short_name": hotel.short_name,
        "rooms": hotel.rooms,
        "tc_usd_default": str(hotel.tc_usd_default),
        "active": hotel.active,
    }


@router.get("/hotel/room-types/")
async def get_room_types(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RoomTypeConfig)
        .where(RoomTypeConfig.hotel_id == HOTEL_ID)
        .order_by(RoomTypeConfig.sort_order)
    )
    types = result.scalars().all()
    total_units = sum(t.units for t in types)
    return {
        "hotel_id": HOTEL_ID,
        "total_units": total_units,
        "room_types": [
            {
                "id": t.id,
                "sort_order": t.sort_order,
                "name": t.name,
                "short_name": t.short_name,
                "units": t.units,
                "pax_min": t.pax_min,
                "pax_max": t.pax_max,
            }
            for t in types
        ],
    }


# ─── Escenarios ───────────────────────────────────────────────────────────

@router.get("/scenarios/")
async def list_scenarios(
    hotel_id: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Scenario).order_by(Scenario.year.desc(), Scenario.created_at.desc())
    if hotel_id:
        stmt = stmt.where(Scenario.hotel_id == hotel_id)
    if year:
        stmt = stmt.where(Scenario.year == year)
    if type:
        stmt = stmt.where(Scenario.type == type)
    result = await db.execute(stmt)
    scenarios = result.scalars().all()
    return [_scenario_summary(s) for s in scenarios]


@router.post("/scenarios/", status_code=201)
async def create_scenario(payload: ScenarioCreate, db: AsyncSession = Depends(get_db)):
    if payload.type not in SCENARIO_TYPES:
        raise ErrorApi(422, "escenario.tipo_invalido", tipos=SCENARIO_TYPES)

    hotel = await db.get(Hotel, payload.hotel_id)
    if not hotel:
        raise ErrorApi(404, "hotel.no_encontrado", hotel=payload.hotel_id)

    scenario = Scenario(
        id=str(uuid.uuid4()),
        hotel_id=payload.hotel_id,
        year=payload.year,
        type=payload.type,
        version=payload.version,
        status="draft",
        created_by=payload.created_by,
    )
    db.add(scenario)

    # Crear las 12 filas de TC
    tc_by_month = payload.tc_by_month or {}
    for month in range(1, 13):
        tc = tc_by_month.get(str(month), payload.tc_default)
        db.add(ExchangeRate(
            id=str(uuid.uuid4()),
            scenario_id=scenario.id,
            hotel_id=payload.hotel_id,
            month=month,
            year=payload.year,
            tc_crc_usd=tc,
        ))

    await db.commit()
    await db.refresh(scenario)
    return _scenario_summary(scenario)


class BulkVersionsRequest(BaseModel):
    year: int = 2027
    hotel_id: str = HOTEL_ID
    tc_default: Decimal = Decimal("530.0000")


@router.post("/scenarios/bulk-create-standard/", status_code=201)
async def bulk_create_standard(payload: BulkVersionsRequest, db: AsyncSession = Depends(get_db)):
    """Crea de una vez el set estándar de versiones de un año (idempotente — omite las
    que ya existen): Forecast Current + 12 forecast mensuales (Enero…Diciembre) +
    Budget Draft 1/2/3, Working y Final. Nacen en blanco (escenario + 12 TC)."""
    if not await db.get(Hotel, payload.hotel_id):
        raise ErrorApi(404, "hotel.no_encontrado", hotel=payload.hotel_id)
    existing = {(s.type, s.version) for s in (await db.execute(select(Scenario).where(
        Scenario.hotel_id == payload.hotel_id, Scenario.year == payload.year))).scalars().all()}
    MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
             "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
    specs = ([("FORECAST", "Current", True)]
             + [("FORECAST", m, False) for m in MESES]
             + [("BUDGET", v, False) for v in ["Draft 1", "Draft 2", "Draft 3", "Working", "Final"]])
    created = []
    for typ, ver, is_curr in specs:
        if (typ, ver) in existing:
            continue
        sc = Scenario(id=str(uuid.uuid4()), hotel_id=payload.hotel_id, year=payload.year,
                      type=typ, version=ver, status="draft", created_by="bulk")
        if is_curr and hasattr(sc, "is_current_forecast"):
            sc.is_current_forecast = True
        db.add(sc)
        for month in range(1, 13):
            db.add(ExchangeRate(id=str(uuid.uuid4()), scenario_id=sc.id, hotel_id=payload.hotel_id,
                                month=month, year=payload.year, tc_crc_usd=payload.tc_default))
        created.append(f"{typ} · {ver} · {payload.year}")
    await db.commit()
    return {"created": created, "created_count": len(created),
            "skipped_count": len(specs) - len(created), "year": payload.year}


class EnsureWorkingBody(BaseModel):
    hotel_id: str = HOTEL_ID
    from_year: int = 2027
    to_year: int = 2035
    tc_default: Decimal = Decimal("530.0000")


@router.post("/scenarios/ensure-working/")
async def ensure_working_budgets(payload: EnsureWorkingBody, db: AsyncSession = Depends(get_db)):
    """Asegura que exista una versión 'Budget Working {año}' para cada año del rango
    (2027 en adelante). Idempotente: solo crea las que faltan. Se llama solo al abrir
    Escenarios para que el budget de cualquier año siempre tenga su Working."""
    if not await db.get(Hotel, payload.hotel_id):
        raise ErrorApi(404, "hotel.no_encontrado", hotel=payload.hotel_id)
    budgets = (await db.execute(select(Scenario).where(
        Scenario.hotel_id == payload.hotel_id, Scenario.type == "BUDGET"))).scalars().all()
    have_working = {s.year for s in budgets if "working" in (s.version or "").lower()}
    created = []
    for year in range(payload.from_year, payload.to_year + 1):
        if year in have_working:
            continue
        sc = Scenario(id=str(uuid.uuid4()), hotel_id=payload.hotel_id, year=year,
                      type="BUDGET", version="Working", status="draft", created_by="auto-working")
        db.add(sc)
        for month in range(1, 13):
            db.add(ExchangeRate(id=str(uuid.uuid4()), scenario_id=sc.id, hotel_id=payload.hotel_id,
                                month=month, year=year, tc_crc_usd=payload.tc_default))
        created.append(f"BUDGET · Working · {year}")
    if created:
        await db.commit()
    return {"created": created, "created_count": len(created)}


@router.get("/scenarios/{scenario_id}/")
async def get_scenario(scenario_id: str, db: AsyncSession = Depends(get_db)):
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    return _scenario_summary(scenario)


@router.get("/scenarios/{scenario_id}/meses-cerrados/")
async def meses_cerrados_del_escenario(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Qué meses de este escenario ya están cerrados, y si hay foto que los cubra.

    Es lo que necesita la pantalla de carga para separar los dos caminos: una
    carga histórica sobre un escenario que YA tiene meses avisa fuerte, y el
    cierre mensual muestra el mes que va a escribir antes de escribirlo.
    """
    from app.engine import meses_cerrados as mc
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    cerrados = sorted(await mc.meses_cerrados(db, scenario))
    foto = await mc.ultima_foto(db, scenario)
    mes_foto = mc.mes_de_la_foto(foto)
    return {
        "scenario_id": scenario_id,
        "escenario": f"{scenario.type} {scenario.version} {scenario.year}",
        "type": scenario.type,
        "meses_cerrados": cerrados,
        "tiene_datos": bool(cerrados),
        "actuals_through": scenario.actuals_through,
        "ultima_foto": None if foto is None else {
            "id": foto.id, "version": foto.version, "mes": mes_foto,
            "etiqueta": f"Forecast {foto.version} {foto.year}"},
        "meses_cerrados_sin_foto": [m for m in cerrados if m > mes_foto],
    }


@router.get("/scenarios/{scenario_id}/divergencia/")
async def divergencia_del_escenario(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """¿Se movió algún mes CERRADO desde la última foto? Qué mes, qué línea, cuánto.

    No impide nada: muestra. Es el aviso barato que reemplaza al candado por
    grilla que se descartó —ese cubría lo chico y dejaba abierto el recálculo,
    que es el agujero grande—.
    """
    from app.engine import meses_cerrados as mc
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    return await mc.divergencia(db, scenario)


class VersionUpdate(BaseModel):
    version: str = Field(..., description="Nuevo nombre de versión (ej. Working, Final, Draft 1)")


@router.patch("/scenarios/{scenario_id}/version/")
async def update_scenario_version(scenario_id: str, payload: VersionUpdate, db: AsyncSession = Depends(get_db)):
    """Renombra la versión de un escenario. Bloquea si ya existe otra versión con ese
    nombre para el mismo tipo+año (evita duplicados, ej. dos 'Working' del mismo año)."""
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    new = (payload.version or "").strip()
    if not new:
        raise ErrorApi(422, "version.nombre_vacio")
    dup = (await db.execute(select(Scenario).where(
        Scenario.hotel_id == scenario.hotel_id, Scenario.type == scenario.type,
        Scenario.year == scenario.year, Scenario.version == new,
        Scenario.id != scenario.id))).scalars().first()
    if dup is not None:
        raise ErrorApi(409, "version.duplicada", version=new,
                       tipo=scenario.type, anio=scenario.year)
    scenario.version = new
    await db.commit()
    await db.refresh(scenario)
    return _scenario_summary(scenario)


@router.patch("/scenarios/{scenario_id}/status/")
async def update_scenario_status(
    scenario_id: str,
    payload: StatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    if payload.status not in SCENARIO_STATUSES:
        raise ErrorApi(422, "escenario.status_invalido", estados=SCENARIO_STATUSES)
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    scenario.status = payload.status
    await db.commit()
    return {"id": scenario_id, "status": scenario.status}


@router.patch("/scenarios/{scenario_id}/actuals-through/")
async def update_actuals_through(
    scenario_id: str,
    payload: ActualsThroughUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Set the rolling-forecast cut. Only meaningful for FORECAST scenarios."""
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    scenario.actuals_through = payload.actuals_through
    await db.commit()
    return {"id": scenario_id, "actuals_through": scenario.actuals_through}


@router.patch("/scenarios/{scenario_id}/mark-current/")
async def mark_current_forecast(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Marca este FORECAST como 'Current' (el vivo: target de uploads + auto-avance del
    cut). Desmarca cualquier otro Forecast del mismo hotel+año. Solo aplica a FORECAST."""
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    if scenario.type != "FORECAST":
        raise ErrorApi(422, "escenario.solo_forecast_current")
    others = (await db.execute(select(Scenario).where(
        Scenario.hotel_id == scenario.hotel_id, Scenario.year == scenario.year,
        Scenario.type == "FORECAST"))).scalars().all()
    for s in others:
        s.is_current_forecast = (s.id == scenario_id)
    await db.commit()
    return {"id": scenario_id, "is_current_forecast": True}


async def _clone_scenario_data(db, source_id: str, new: Scenario) -> None:
    """Copia al escenario `new` (ya flushed) el TC + todos los datasets de planning
    y el snapshot P&L del origen. Usado por snapshot mensual y rollover Budget→Forecast."""
    rates = (await db.execute(
        select(ExchangeRate).where(ExchangeRate.scenario_id == source_id))).scalars().all()
    for r in rates:
        db.add(ExchangeRate(id=str(uuid.uuid4()), scenario_id=new.id, hotel_id=new.hotel_id,
                            month=r.month, year=r.year, tc_crc_usd=r.tc_crc_usd))
    for models in COPY_DATASETS.values():
        for Model in models:
            rows = (await db.execute(
                select(Model).where(Model.scenario_id == source_id))).scalars().all()
            cols = [c.key for c in class_mapper(Model).columns]
            for row in rows:
                data = {c: getattr(row, c) for c in cols}
                data["scenario_id"] = new.id
                if "id" in cols:
                    data["id"] = str(uuid.uuid4())
                db.add(Model(**data))


@router.post("/scenarios/{scenario_id}/clear-months/")
async def clear_months_from(
    scenario_id: str,
    from_month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
):
    """Limpia los meses >= from_month del escenario: P&L snapshot (ActualPLLine), stats
    (ScenarioStat), planilla (PayrollConceptEntry) por fila; y pone en CERO las columnas
    de esos meses en el detalle GL (Revenue/Opex/Cost/BelowGop). Sirve para recortar un
    Actual en curso a solo los meses cerrados. No toca otros escenarios."""
    s = await db.get(Scenario, scenario_id)
    if not s:
        raise ErrorApi(404, "escenario.no_encontrado")
    # Una versión enllavada no se puede vaciar.
    s.assert_editable()
    months = list(range(from_month, 13))
    await db.execute(sa_delete(ActualPLLine).where(
        ActualPLLine.scenario_id == scenario_id, ActualPLLine.month.in_(months)))
    await db.execute(sa_delete(ScenarioStat).where(
        ScenarioStat.scenario_id == scenario_id, ScenarioStat.month.in_(months)))
    # Los socios del Club son un estadístico más: si se recorta el año a los
    # meses cerrados, quedarse con el conteo proyectado de los meses abiertos
    # dejaría un dato que ya no corresponde a nada.
    await db.execute(sa_delete(ClubMembershipStat).where(
        ClubMembershipStat.scenario_id == scenario_id, ClubMembershipStat.month.in_(months)))
    await db.execute(sa_delete(PayrollConceptEntry).where(
        PayrollConceptEntry.scenario_id == scenario_id, PayrollConceptEntry.month.in_(months)))
    gl_rows = 0
    for Model in (RevenueAccountEntry, OpexEntry, CostEntry, BelowGopAccountEntry):
        rows = (await db.execute(
            select(Model).where(Model.scenario_id == scenario_id))).scalars().all()
        for r in rows:
            for m in months:
                setattr(r, _GL_MONTHS[m - 1], Decimal("0"))
            gl_rows += 1
    await db.commit()
    return {"scenario_id": scenario_id, "cleared_from_month": from_month,
            "months_cleared": months, "gl_rows_zeroed": gl_rows}


@router.post("/scenarios/{scenario_id}/belowgop-adjustment/")
async def belowgop_adjustment(
    scenario_id: str,
    account_name: str = Query(...),
    amount: Decimal = Query(...),
    month: int = Query(12, ge=1, le=12),
    account_code: str = Query("8090"),
    dept_code: str = Query("0240"),
    db: AsyncSession = Depends(get_db),
):
    """Asiento de ajuste/reconciliación en una cuenta Below-GOP (8xxx). Upsert por
    (scenario, dept, account_code): pone `amount` en el mes dado. Sirve para parkear
    diferencias de reconciliación (ej. Financial Losses) sin re-importar. NO toca el
    snapshot del P&L; ajusta el detalle GL para que reconcilie con el net oficial."""
    # Una version enllavada no se puede editar.
    await candado(db, scenario_id)
    s = await db.get(Scenario, scenario_id)
    if not s:
        raise ErrorApi(404, "escenario.no_encontrado")
    col = _GL_MONTHS[month - 1]
    row = (await db.execute(select(BelowGopAccountEntry).where(
        BelowGopAccountEntry.scenario_id == scenario_id,
        BelowGopAccountEntry.dept_code == dept_code,
        BelowGopAccountEntry.account_code == account_code))).scalars().first()
    if row is None:
        row = BelowGopAccountEntry(scenario_id=scenario_id, hotel_id=s.hotel_id,
                                   dept_code=dept_code, account_code=account_code,
                                   account_name=account_name,
                                   **{m: Decimal("0") for m in _GL_MONTHS})
        db.add(row)
    row.account_name = account_name
    setattr(row, col, Decimal(str(amount)))
    await db.commit()
    return {"scenario_id": scenario_id, "account_code": account_code,
            "account_name": account_name, "month": month, "amount": float(amount)}


@router.get("/scenarios/{scenario_id}/flow-through/")
async def flow_through(
    scenario_id: str,
    month: int = Query(0, ge=0, le=12),   # 0 = Full Year
    ytd: bool = Query(False),
    compare: list[str] = Query(default=[]),  # escenarios de comparación (base = principal)
    db: AsyncSession = Depends(get_db),
):
    """Flow Through Analysis: variación por categoría (GL) de la **vista principal**
    ({scenario_id}) contra cada escenario de comparación (`compare`), para el período
    (Full Year / YTD / mes). Categorías: Revenue(4xxx), Payroll(6xxx), OpEx(7xxx),
    Cost(5xxx), Property(8xxx) — con la regla de allocation — + EBITDA y Net del P&L.
    La variación es Principal − comparación con signo de impacto en utilidad (favorable +).
    Si no se pasa `compare`, cae al Budget del año (compatibilidad)."""
    from app.engine.payroll_calculator import total_entry
    from app.engine.recalculate import compute_pl_month
    from app.engine.pl_engine import get_line
    from app.importers.gl_detail_importer import ALLOC_EXCL_PAYROLL, ALLOC_EXCL_OPEX, ALLOC_EXCL_COST

    scen = await db.get(Scenario, scenario_id)
    if not scen:
        raise ErrorApi(404, "escenario.no_encontrado")
    budget = (await db.execute(select(Scenario).where(
        Scenario.hotel_id == scen.hotel_id, Scenario.year == scen.year, Scenario.type == "BUDGET")
        .order_by(Scenario.created_at.desc()))).scalars().first()

    months = list(range(1, 13)) if month == 0 else (list(range(1, month + 1)) if ytd else [month])
    cols = [_GL_MONTHS[m - 1] for m in months]

    async def cats(sid: str, sobj: Scenario):
        def summ(rows, excl):
            return float(sum(getattr(e, c) for e in rows if e.dept_code not in excl for c in cols))
        # ⚠️ El ingreso sale del MOTOR del P&L, no de la tabla del checkbook.
        #
        # Antes leía `RevenueAccountEntry` directo, y eso es correcto solo para
        # un escenario en modo `checkbook`. Los seis Budget 2027 están en modo
        # `drivers` —el ingreso se deriva de tarifas × ocupación— y esa tabla
        # está VACÍA: medido el 2026-08-19, los seis dan 0,00.
        #
        # Con la vista principal en Budget 2027 Working, el Flow Through hacía
        # `0 − 5.216.806,03` y mostraba **($5.216.806,03)** de variación de
        # ingreso contra el Forecast 2026, cuando el P&L de la misma pantalla
        # decía +$1.169.115,30. No fallaba: comparaba contra una tabla vacía.
        #
        # Y aun donde la tabla TIENE dato, no coincide: el Forecast 2026 Working
        # daba 5.216.806,03 en el checkbook contra 5.204.910,88 en el P&L —
        # $11.895,15 de desfase, porque el ingreso se calcula por drivers y la
        # tabla no siempre se vuelve a escribir.
        #
        # EBITDA y Net ya le preguntaban al motor. Ahora el ingreso también, así
        # que las tres filas hablan de la misma fuente que el P&L de arriba.
        opx = summ((await db.execute(select(OpexEntry).where(OpexEntry.scenario_id == sid))).scalars().all(), ALLOC_EXCL_OPEX)
        cost = summ((await db.execute(select(CostEntry).where(CostEntry.scenario_id == sid))).scalars().all(), ALLOC_EXCL_COST)
        prop = summ((await db.execute(select(BelowGopAccountEntry).where(BelowGopAccountEntry.scenario_id == sid))).scalars().all(), set())
        pay_entries = (await db.execute(select(PayrollConceptEntry).where(PayrollConceptEntry.scenario_id == sid))).scalars().all()
        pay = float(sum(total_entry(e) for e in pay_entries if e.month in months and e.dept_code not in ALLOC_EXCL_PAYROLL))
        rev = ebitda = net = 0.0
        for m in months:
            lines = await compute_pl_month(db, sobj, m)
            rev += float(get_line(lines, "TOTAL_REVENUES"))
            ebitda += float(get_line(lines, "EBITDA_BEFORE_CAPITAL"))
            net += float(get_line(lines, "NET_PROFIT"))
        return {"revenue": round(rev, 2), "payroll": pay, "opex": opx, "cost": cost,
                "property": prop, "ebitda": round(ebitda, 2), "net": round(net, 2)}

    v = await cats(scenario_id, scen)

    # escenarios de comparación: los pasados en `compare`; si no, cae al Budget del año
    comp_objs: list[tuple[str, Scenario]] = []
    if compare:
        for cid in compare:
            if cid and cid != scenario_id:
                cobj = await db.get(Scenario, cid)
                if cobj:
                    comp_objs.append((cid, cobj))
    elif budget:
        comp_objs.append((budget.id, budget))

    comp_cats = [(cid, await cats(cid, cobj)) for cid, cobj in comp_objs]

    # (label, clave en cats, es_ingreso) — orden/etiquetas de la vista del usuario
    CATS = [
        ("Revenue", "revenue", True),
        ("Payroll (Overtime + FX + Commissions)", "payroll", False),
        ("Operating Expenses", "opex", False),
        ("Cost of Sales (F&B + Tours)", "cost", False),
        ("Property / Capital", "property", False),
        ("Net Profit", "net", True),
        ("EBITDA Before Capital", "ebitda", True),
    ]
    rows = []
    for label, key, is_income in CATS:
        # impacto en utilidad: ingreso = principal-comp; gasto = comp-principal
        variances = [round((v[key] - c[key]) if is_income else (c[key] - v[key]), 2)
                     for _, c in comp_cats]
        rows.append({"concept": label, "variances": variances})

    return {"scenario_id": scenario_id, "months": months,
            "comparison_ids": [cid for cid, _ in comp_cats],
            "has_data": bool(comp_cats), "rows": rows}


@router.get("/scenarios/{scenario_id}/pl-by-dept/")
async def pl_by_dept(
    scenario_id: str,
    month: int = Query(0, ge=0, le=12),   # 0 = Full Year
    ytd: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """P&L por DEPARTAMENTO (grupos USALI) para el período (Full Year / YTD / mes).
    Por grupo: Revenue · Payroll · Gastos Operativos (OpEx 7xxx + Cost 5xxx) ·
    Total de gastos · GOP del depto. Regla de allocation: Cafetería (0220) se
    excluye completa; Laundry interno (0161) excluye payroll/opex (su Laundry
    Services 4/5 queda). La suma de los GOP por depto = GOP total. Debajo del GOP
    (company-level, del P&L oficial): Rent+Fees+Insurance+Other = Total Non-Op →
    EBITDA Before Capital → −Capital −Financial −Depreciation → EBT → Income Taxes
    → Net Profit."""
    from app.engine.payroll_calculator import total_entry
    from app.engine.recalculate import compute_pl_month
    from app.engine.pl_engine import (
        group_for_dept, GROUP_NAMES, OPERATING_GROUP_ORDER, OVERHEAD_GROUP_ORDER,
        get_line,
    )
    from app.importers.gl_detail_importer import (
        ALLOC_EXCL_PAYROLL, ALLOC_EXCL_OPEX, ALLOC_EXCL_COST,
    )

    scen = await db.get(Scenario, scenario_id)
    if not scen:
        raise ErrorApi(404, "escenario.no_encontrado")

    months = list(range(1, 13)) if month == 0 else (list(range(1, month + 1)) if ytd else [month])
    cols = [_GL_MONTHS[m - 1] for m in months]

    groups: dict[str, dict[str, float]] = {}

    def acc(g: str) -> dict[str, float]:
        return groups.setdefault(g, {"revenue": 0.0, "payroll": 0.0, "opex": 0.0, "cost": 0.0,
                                     "alloc": 0.0, "alloc_payroll": 0.0, "alloc_opex": 0.0,
                                     "alloc_cost": 0.0, "alloc_other": 0.0})

    def msum(e) -> float:
        return float(sum(getattr(e, c) for c in cols))

    rev_rows = (await db.execute(select(RevenueAccountEntry).where(RevenueAccountEntry.scenario_id == scenario_id))).scalars().all()
    for e in rev_rows:
        acc(group_for_dept(e.dept_code))["revenue"] += msum(e)

    opex_rows = (await db.execute(select(OpexEntry).where(OpexEntry.scenario_id == scenario_id))).scalars().all()
    for e in opex_rows:
        if e.dept_code in ALLOC_EXCL_OPEX:
            continue
        acc(group_for_dept(e.dept_code))["opex"] += msum(e)

    cost_rows = (await db.execute(select(CostEntry).where(CostEntry.scenario_id == scenario_id))).scalars().all()
    for e in cost_rows:
        if e.dept_code in ALLOC_EXCL_COST:
            continue
        acc(group_for_dept(e.dept_code))["cost"] += msum(e)

    pay_rows = (await db.execute(select(PayrollConceptEntry).where(PayrollConceptEntry.scenario_id == scenario_id))).scalars().all()
    for e in pay_rows:
        if e.month not in months or e.dept_code in ALLOC_EXCL_PAYROLL:
            continue
        acc(group_for_dept(e.dept_code))["payroll"] += float(total_entry(e))

    # Repartos (cafetería 0220 y lavandería 0161). Los deptos origen se excluyen
    # arriba de payroll/opex/cost justamente porque su gasto se reparte acá: sin
    # esta vuelta el gasto del depto destino queda corto contra el P&L oficial
    # (Rooms 2027 se quedaba $64,416 abajo de OPEX_ROOMS). El neto de todos los
    # repartos es cero, así que el GOP total no se mueve — solo se acomoda entre
    # departamentos, que es el punto del reparto.
    alloc_rows = (await db.execute(
        select(AllocationEntry).where(AllocationEntry.scenario_id == scenario_id))).scalars().all()
    # El reparto NO es una categoría de gasto aparte: es planilla, gasto operativo
    # o costo que se movió de departamento, y la cuenta destino dice cuál. El
    # reparto de salarios cae en 6000 (Tours entrega salario a otros deptos), la
    # cafetería en 6025, la lavandería en 7310/7685, y 5301 es costo. La 4999 es
    # el crédito que vuelve al departamento ORIGEN (cafetería/lavandería) y no
    # pertenece a ninguna de las tres.
    for e in alloc_rows:
        if e.month not in months:
            continue
        d = acc(group_for_dept(e.target_dept))
        monto = float(e.amount_usd or 0)
        d["alloc"] += monto
        clase = str(e.account or "")[:1]
        d[{"6": "alloc_payroll", "7": "alloc_opex", "5": "alloc_cost"}.get(clase, "alloc_other")] += monto

    order = OPERATING_GROUP_ORDER + OVERHEAD_GROUP_ORDER + [g for g in groups if g not in OPERATING_GROUP_ORDER and g not in OVERHEAD_GROUP_ORDER]
    op_set = set(OPERATING_GROUP_ORDER)
    seen: set[str] = set()
    departments = []
    total_gop = 0.0
    total_operating_profit = 0.0   # suma de utilidad de deptos generadores de ingresos
    total_overhead = 0.0           # suma de gastos de deptos overhead (sin ingresos)
    for g in order:
        if g in seen or g not in groups:
            continue
        seen.add(g)
        d = groups[g]
        # 'operating' se deja SIN repartos a propósito: es lo que muestra la
        # pantalla de P&L por departamento desde siempre. Los repartos van
        # aparte, en su propio campo, para quien quiera cuadrar contra OPEX_x
        # del P&L oficial (que sí los trae dentro).
        operating = d["opex"] + d["cost"]
        total_exp = d["payroll"] + operating
        gop = d["revenue"] - total_exp
        if abs(d["revenue"]) + abs(total_exp) < 0.005:
            continue
        # Generador de ingresos (operating) si está en la lista operativa o tiene
        # ingresos; si no (Admin/Ventas/Mant/IT/Utilities, sin ingresos) = overhead.
        kind = "operating" if (g in op_set or d["revenue"] > 0.005) else "overhead"
        total_gop += gop
        if kind == "operating":
            total_operating_profit += gop
        else:
            total_overhead += total_exp
        departments.append({
            "group": g, "name": GROUP_NAMES.get(g, g), "kind": kind,
            "revenue": round(d["revenue"], 2), "payroll": round(d["payroll"], 2),
            # 'operating' = opex+cost (lo consume el P&L por depto de siempre); se
            # expone además desglosado para la Junta, donde el dueño quiere ver el
            # costo de venta y los repartos como líneas propias.
            "operating": round(operating, 2),
            "opex": round(d["opex"], 2), "cost": round(d["cost"], 2),
            "alloc": round(d["alloc"], 2),
            "alloc_payroll": round(d["alloc_payroll"], 2),
            "alloc_opex": round(d["alloc_opex"], 2),
            "alloc_cost": round(d["alloc_cost"], 2),
            "alloc_other": round(d["alloc_other"], 2),
            "total_expenses": round(total_exp, 2),
            "gop": round(gop, 2),
        })

    # Below GOP (company-level) desde el P&L oficial (compute_pl_month).
    # Se toma EBITDA_BEFORE_CAPITAL oficial directo (reconcilia con el P&L); el
    # Total Non-Op se deriva = GOP − EBITDA, y 'Other' es el residual (así el
    # desglose Rent/Fees/Insurance/Other siempre cuadra con el Total Non-Op).
    rent = fees = insurance = ebitda_before = capital = financial = deprec = income_taxes = 0.0
    for m in months:
        L = await compute_pl_month(db, scen, m)
        ebitda_before += float(get_line(L, "EBITDA_BEFORE_CAPITAL"))
        rent += float(get_line(L, "RENT"))
        fees += float(get_line(L, "MGMT_FEE_3")) + float(get_line(L, "MGMT_FEE_5_ROYALTIES"))
        insurance += float(get_line(L, "PROPERTY_INSURANCE"))
        capital += float(get_line(L, "CAPITAL_EXPENSE"))
        financial += float(get_line(L, "FINANCIAL_EXPENSES"))
        deprec += float(get_line(L, "TOTAL_DEPRECIATIONS"))
        income_taxes += float(get_line(L, "INCOME_TAXES"))

    total_non_op = total_gop - ebitda_before
    other = total_non_op - rent - fees - insurance
    ebt = ebitda_before - capital - financial - deprec
    # Corrección de impuesto (igual que _apply_tax_correction): anula el impuesto
    # POSITIVO sobre una pérdida (EBT≤0); respeta créditos negativos.
    if ebt <= 0 and income_taxes > 0:
        income_taxes = 0.0
    net_profit = ebt - income_taxes

    return {
        "scenario_id": scenario_id, "months": months,
        "has_data": bool(departments),
        "departments": departments,
        "total_operating_profit": round(total_operating_profit, 2),
        "total_overhead": round(total_overhead, 2),
        "total_gop": round(total_gop, 2),
        "below_gop": {
            "rent": round(rent, 2), "fees": round(fees, 2),
            "insurance": round(insurance, 2), "other": round(other, 2),
            "total_non_op": round(total_non_op, 2),
            "ebitda_before_capital": round(ebitda_before, 2),
            "capital": round(capital, 2), "financial": round(financial, 2),
            "depreciation": round(deprec, 2),
            "ebt": round(ebt, 2),
            "income_taxes": round(income_taxes, 2),
            "net_profit": round(net_profit, 2),
        },
    }


_SNAP_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


@router.post("/scenarios/{source_id}/snapshot-month/", status_code=201)
async def snapshot_forecast_month(
    source_id: str,
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
):
    """Crea 'Forecast {Mes} {año}' como copia del Forecast Current — el snapshot del
    forecast al cerrar ese mes. Copia TODOS los datasets + el TC. No queda como Current."""
    source = await db.get(Scenario, source_id)
    if not source:
        raise ErrorApi(404, "escenario.origen_no_encontrado")
    if source.type != "FORECAST":
        raise ErrorApi(422, "escenario.origen_debe_ser_forecast")
    version = _SNAP_MONTHS[month - 1]
    dup = (await db.execute(select(Scenario).where(
        Scenario.hotel_id == source.hotel_id, Scenario.year == source.year,
        Scenario.type == "FORECAST", Scenario.version == version))).scalars().first()
    if dup:
        raise ErrorApi(409, "snapshot.ya_existe",
                       version=version, anio=source.year)

    new = Scenario(
        id=str(uuid.uuid4()), hotel_id=source.hotel_id, year=source.year, type="FORECAST",
        version=version, status="draft", actuals_through=source.actuals_through,
        source_mode=getattr(source, "source_mode", "imported"),
        revenue_source=getattr(source, "revenue_source", "drivers"),
        is_current_forecast=False, created_by="snapshot",
    )
    db.add(new)
    await db.flush()
    await _clone_scenario_data(db, source_id, new)
    await db.commit()
    return {**_scenario_summary(new), "label": f"Forecast {version} {source.year}"}


@router.post("/scenarios/{budget_id}/to-forecast-current/", status_code=201)
async def budget_to_forecast_current(budget_id: str, db: AsyncSession = Depends(get_db)):
    """Rollover de arranque de año (1 sola vez): crea 'Forecast Current {año}' como copia
    del Budget y lo marca como el Forecast Current. Copia todos los datasets + TC.
    Si ya existe un Forecast Current para ese hotel+año, devuelve 409."""
    budget = await db.get(Scenario, budget_id)
    if not budget:
        raise ErrorApi(404, "escenario.budget_origen_no_encontrado")
    if budget.type != "BUDGET":
        raise ErrorApi(422, "escenario.origen_debe_ser_budget")
    existing = (await db.execute(select(Scenario).where(
        Scenario.hotel_id == budget.hotel_id, Scenario.year == budget.year,
        Scenario.type == "FORECAST", Scenario.is_current_forecast == True))).scalars().first()  # noqa: E712
    if existing:
        raise ErrorApi(409, "forecast.current_ya_existe",
                       anio=budget.year, version=existing.version)
    new = Scenario(
        id=str(uuid.uuid4()), hotel_id=budget.hotel_id, year=budget.year, type="FORECAST",
        version="Current", status="draft", actuals_through=0,
        source_mode=getattr(budget, "source_mode", "imported"),
        revenue_source=getattr(budget, "revenue_source", "drivers"),
        is_current_forecast=True, created_by="rollover",
    )
    db.add(new)
    await db.flush()
    await _clone_scenario_data(db, budget_id, new)
    await db.commit()
    return {**_scenario_summary(new), "label": f"Forecast Current {budget.year}"}


def is_protected_version(version: str) -> bool:
    """Versiones protegidas: NO se pueden borrar (Working y Final son entregables
    importantes que deben quedar). Los Draft y demás sí se pueden borrar."""
    v = (version or "").strip().lower()
    return "working" in v or "final" in v


@router.delete("/scenarios/{scenario_id}/", status_code=204)
async def delete_scenario(scenario_id: str, db: AsyncSession = Depends(get_db)):
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    if is_protected_version(scenario.version):
        raise ErrorApi(409, "version.protegida", version=scenario.version)
    if scenario.status != "draft":
        raise ErrorApi(409, "escenario.solo_borra_draft", status=scenario.status)
    await db.delete(scenario)
    await db.commit()


#: Tablas que un escenario VACÍO igual tiene, porque se crean solas.
#:
#: Medido en producción sobre los ocho `BUDGET Working 2028..2035`: los tres
#: juntos dan 50 filas —36 de mix de canales, 2 de config de Villas y los 12
#: TC que crea `ensure-working`— y esos ocho escenarios tienen las 110 líneas
#: del P&L EN CERO. O sea: contar filas a secas los daba por «con datos» y la
#: pantalla los seguía preseleccionando. Un escenario que solo tiene esto no
#: sirve como origen de una copia.
TABLAS_DE_ANDAMIAJE = {SalesChannelConfig, RoomsAllocationConfig, ExchangeRate}


async def _filas_por_escenario(
    db, datasets: list[str], solo: str | None = None,
) -> dict[str, dict[str, int]]:
    """Cuántas filas tiene CADA escenario en cada dataset pedido.

    Devuelve `{scenario_id: {dataset: filas}}` y, aparte, la cuenta sin el
    andamiaje bajo la llave `_utiles` — que es la que decide si un escenario
    sirve como origen.

    Va en UNA sola consulta (un `UNION ALL` de un `group by` por tabla). Con
    ~45 tablas, una consulta por tabla contra la base remota tardaba 15 s al
    abrir la pantalla de Escenarios.
    """
    from sqlalchemy import func, literal, union_all

    partes = []
    for ds in datasets:
        for Model in COPY_DATASETS.get(ds, []):
            q = select(
                literal(ds).label("ds"),
                literal(Model in TABLAS_DE_ANDAMIAJE).label("andamio"),
                Model.scenario_id.label("sid"),
                func.count().label("n"),
            ).group_by(Model.scenario_id)
            if solo is not None:
                q = q.where(Model.scenario_id == solo)
            partes.append(q)
    filas: dict[str, dict[str, int]] = {}
    if not partes:
        return filas
    for ds, andamio, sid, n in (await db.execute(union_all(*partes))).all():
        if not sid:
            continue
        d = filas.setdefault(sid, {})
        d[ds] = d.get(ds, 0) + int(n)
        if not andamio:
            d["_utiles"] = d.get("_utiles", 0) + int(n)
    return filas


def _utiles(d: dict[str, int]) -> int:
    """Filas que de verdad son datos del escenario (sin el andamiaje)."""
    return d.get("_utiles", 0)


@router.get("/scenarios/copia/inventario/")
async def inventario_para_copiar(
    hotel_id: str = Query(HOTEL_ID),
    db: AsyncSession = Depends(get_db),
):
    """Qué tiene adentro cada escenario, para poder elegir origen con criterio.

    Existe porque el aviso llegaba tarde: se elegía un origen, se creaba el
    escenario, se copiaba, y recién ahí aparecía un «copiadas 0 filas» fácil de
    pasar por alto — con la copia ya creada y vacía. Con esto la pantalla puede
    ordenar los orígenes con datos primero, marcar los vacíos y preguntar ANTES.
    """
    escs = (await db.execute(select(Scenario).where(
        Scenario.hotel_id == hotel_id))).scalars().all()
    filas = await _filas_por_escenario(db, list(COPY_DATASETS))
    salida = []
    for s in escs:
        d = {k: v for k, v in filas.get(s.id, {}).items() if k != "_utiles"}
        utiles = _utiles(filas.get(s.id, {}))
        salida.append({
            "id": s.id,
            "etiqueta": f"{s.type} {s.version} {s.year}",
            "year": s.year, "type": s.type, "version": s.version,
            "source_mode": getattr(s, "source_mode", "imported"),
            "usar_detalle": bool(getattr(s, "usar_detalle", False)),
            "filas": sum(d.values()),
            # Lo que decide si sirve como origen: filas SIN el andamiaje que se
            # crea solo. Un escenario recién nacido tiene 50 filas y el P&L en
            # cero — contarlas lo hacía pasar por «con datos».
            "filas_utiles": utiles,
            "vacio": utiles == 0,
            # Un `imported` sin mayor lee el P&L por otro camino que el que su
            # propio modo anuncia: sirve saberlo antes de copiarlo.
            "tiene_mayor": sum(d.get(k, 0) for k in LLAVES_DEL_MAYOR) > 0,
            "por_dataset": d,
        })
    salida.sort(key=lambda x: (-x["year"], x["type"], x["version"]))
    return {"hotel_id": hotel_id, "escenarios": salida}


class CopyRequest(BaseModel):
    datasets: list[str] = Field(
        default_factory=lambda: list(DEFAULT_COPY_DATASETS),
        description="Cuáles datos copiar. Opciones: " + ", ".join(COPY_DATASETS),
    )
    replace: bool = Field(True, description="Borra los datos del destino antes de copiar")
    permitir_origen_vacio: bool = Field(
        False,
        description="Dejar copiar de un origen sin una sola fila. Por defecto NO: "
                    "copiar de un escenario vacío produce una copia vacía y eso "
                    "hasta ahora se avisaba después, con la copia ya creada.",
    )


@router.post("/scenarios/{target_id}/copy-from/{source_id}/")
async def copy_scenario_data(
    target_id: str,
    source_id: str,
    payload: CopyRequest,
    db: AsyncSession = Depends(get_db),
    idioma: str = Idioma,
):
    """
    Copia un escenario entero a otro (ej. Forecast→Budget, Budget→Budget).
    Por defecto viaja TODO el escenario: los mismos datasets que clona la foto
    mensual, el mayor y el snapshot del P&L incluidos.
    """
    target = await db.get(Scenario, target_id)
    source = await db.get(Scenario, source_id)
    if not target:
        raise ErrorApi(404, "escenario.destino_no_encontrado")
    if not source:
        raise ErrorApi(404, "escenario.origen_no_encontrado")
    if target.is_locked:
        raise ErrorApi(409, "escenario.destino_bloqueado")

    etiqueta_origen = f"{source.type} {source.version} {source.year}"

    # ── El origen vacío se avisa ANTES, no después ────────────────────────────
    # Copiar de un escenario sin datos deja una copia sin datos. Eso hasta ahora
    # se sabía por un «copiadas 0 filas» al final, con la copia ya creada — y el
    # origen que la pantalla preseleccionaba era justamente uno vacío.
    if not payload.permitir_origen_vacio:
        d = (await _filas_por_escenario(db, payload.datasets, solo=source_id)).get(source_id, {})
        if _utiles(d) == 0:
            raise ErrorApi(409, "copia.origen_vacio", origen=etiqueta_origen)

    # ── El modo viaja con el mayor, o no viaja ────────────────────────────────
    # Al final de esta función el destino hereda `source_mode`. Si el origen lee
    # el P&L del MAYOR (`imported`) y el mayor no está en la lista de datasets,
    # heredarlo deja una copia marcada como histórico y sin histórico: el
    # reporte se va por otro camino (los checkbooks) y da otros números, sin un
    # solo error. O viajan los dos, o no viaja ninguno.
    modo_origen = getattr(source, "source_mode", "imported")
    mayor_viaja = all(k in payload.datasets for k in LLAVES_DEL_MAYOR)
    hereda_modo = modo_origen == "checkbook" or mayor_viaja
    avisos: list[str] = []

    copied: dict[str, int] = {}
    pos_map: dict[str, str] = {}     # posición vieja → posición nueva (para los conceptos)
    huerfanos = 0
    for ds in payload.datasets:
        models = COPY_DATASETS.get(ds)
        if not models:
            raise ErrorApi(422, "copia.dataset_desconocido",
                           dataset=ds, validos=list(COPY_DATASETS))
        n = 0
        for Model in models:
            if payload.replace:
                await db.execute(sa_delete(Model).where(Model.scenario_id == target_id))
                await db.flush()
            rows = (await db.execute(
                select(Model).where(Model.scenario_id == source_id)
            )).scalars().all()
            cols = [c.key for c in class_mapper(Model).columns]
            for row in rows:
                data = {c: getattr(row, c) for c in cols}
                data["scenario_id"] = target_id
                # Al copiar a otro año (2027 → 2028) las filas que llevan el año
                # deben reetiquetarse, si no el destino queda con datos del origen.
                if "year" in cols and getattr(target, "year", None):
                    data["year"] = target.year
                if "hotel_id" in cols and getattr(target, "hotel_id", None):
                    data["hotel_id"] = target.hotel_id
                new_id = str(uuid.uuid4())
                if "id" in cols:
                    data["id"] = new_id
                if Model is PayrollPosition:
                    pos_map[row.id] = new_id
                elif Model is PayrollConceptEntry:
                    # Reapuntar a la posición nueva; si no existe, se omite en vez
                    # de dejar una fila colgando de una posición de otro escenario.
                    nuevo = pos_map.get(row.position_id)
                    if nuevo is None:
                        huerfanos += 1
                        continue
                    data["position_id"] = nuevo
                db.add(Model(**data))
                n += 1
        copied[ds] = n
    if huerfanos:
        copied["conceptos_sin_posicion_omitidos"] = huerfanos

    # El copy debe comportarse como el original: estos dos campos deciden de dónde
    # sale el P&L (auxiliares vs snapshot) y de dónde el ingreso (drivers vs
    # checkbook). Sin alinearlos, la copia mostraba cifras distintas al original.
    target.revenue_source = getattr(source, "revenue_source", "drivers")
    if hereda_modo:
        target.source_mode = modo_origen
    else:
        # El mayor no viajó (lista de datasets recortada a mano): heredar
        # 'imported' dejaría al destino leyendo de un mayor que no tiene. Se
        # queda con el modo que ya traía y se dice, en vez de callarlo.
        avisos.append(t(idioma, "escenario.copia_sin_el_mayor",
                        modo_origen=modo_origen,
                        datasets=", ".join(LLAVES_DEL_MAYOR),
                        modo_destino=target.source_mode))

    # El corte del rolling forecast es parte de la versión: sin él, una copia de
    # un forecast con actuales hasta junio nace pisando cero meses y muestra
    # doce de plan donde el original mostraba seis reales.
    target.actuals_through = getattr(source, "actuals_through", 0) or 0

    await db.commit()
    return {
        "target": target_id, "source": source_id,
        "replace": payload.replace, "copied": copied,
        "revenue_source": target.revenue_source, "source_mode": target.source_mode,
        "actuals_through": target.actuals_through,
        "avisos": avisos,
    }


class SourceModeUpdate(BaseModel):
    source_mode: str = Field(..., description="imported | checkbook")


@router.patch("/scenarios/{scenario_id}/source-mode/")
async def update_source_mode(
    scenario_id: str,
    payload: SourceModeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Switch how the P&L is computed: 'imported' (loaded snapshot) or
    'checkbook' (roll up the in-app checkbooks → edits flow to the P&L)."""
    if payload.source_mode not in ("imported", "checkbook"):
        raise ErrorApi(422, "escenario.source_mode_invalido")
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    scenario.source_mode = payload.source_mode
    await db.commit()
    return {"id": scenario_id, "source_mode": scenario.source_mode}


class UsarDetalleUpdate(BaseModel):
    usar_detalle: bool


@router.patch("/scenarios/{scenario_id}/usar-detalle/")
async def update_usar_detalle(
    scenario_id: str,
    payload: UsarDetalleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Fuerza que el P&L de este ACTUAL lea el DETALLE del mayor, no el resumen.

    Normalmente el motor decide solo: usa el resumen salvo que el detalle dé
    los mismos siete totales. Eso protege al Actual 2024, cuyo detalle traía
    $40.613 de más. Pero cuando el INCOMPLETO es el resumen, el guardián
    descarta el número bueno por no coincidir con el malo — que es lo que
    pasaba en el Actual 2026 con la depreciación y el EBITDA.

    Es por escenario y se apaga igual de fácil. La respuesta devuelve el
    veredicto del cuadre para que quede a la vista qué se eligió y por qué.
    """
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    scenario.usar_detalle = payload.usar_detalle
    await db.commit()

    from app.engine.recalculate import veredicto_del_detalle
    return {"id": scenario_id, "usar_detalle": scenario.usar_detalle,
            "veredicto": await veredicto_del_detalle(db, scenario)}


def _scenario_summary(s: Scenario) -> dict:
    return {
        "id": s.id,
        "hotel_id": s.hotel_id,
        "year": s.year,
        "type": s.type,
        "version": s.version,
        "status": s.status,
        "is_locked": s.is_locked,
        "actuals_through": s.actuals_through,
        "is_current_forecast": getattr(s, "is_current_forecast", False),
        "source_mode": getattr(s, "source_mode", "imported"),
        "created_by": s.created_by,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }


def _match_block_target(scenarios, typ, year):
    """Escenario destino de un bloque del upload. Para FORECAST prefiere el marcado
    como 'Current' (is_current_forecast) — sin ambigüedad cuando hay varias versiones;
    si no hay marcado, cae al más reciente. Para ACTUAL/BUDGET: el más reciente."""
    matches = [s for s in scenarios if s.type == typ and s.year == year]
    if not matches:
        return None
    if typ == "FORECAST":
        current = [s for s in matches if getattr(s, "is_current_forecast", False)]
        if current:
            return current[0]
    return sorted(matches, key=lambda s: s.created_at.isoformat() if s.created_at else "",
                  reverse=True)[0]


# ─── Importar P&L mensual (archivo "upload" multi-escenario) ───────────────────
def _pl_block_checks(blk: dict) -> list[dict]:
    """Valida el cuadre del P&L Summary de un bloque, mes a mes."""
    out = []
    for m, L in sorted((blk.get("lines") or {}).items()):
        g = lambda k: float(L.get(k, 0) or 0)
        s = lambda pre: float(sum(v for k, v in L.items() if k.startswith(pre)))
        pruebas = [
            ("Σ Revenue = Total Revenues", s("REV_"), g("TOTAL_REVENUES")),
            ("Σ OpEx = Total Operating Exp.", s("OPEXP_"), g("TOTAL_OPEXP")),
            ("Σ Overhead = Total Overhead", s("OVH_"), g("TOTAL_OVERHEAD")),
            ("GOP = Rev − OpEx − Overhead",
             g("TOTAL_REVENUES") - g("TOTAL_OPEXP") - g("TOTAL_OVERHEAD"), g("GOP")),
            ("Net = EBT − Impuesto", g("EBT") - g("INCOME_TAXES"), g("NET_PROFIT")),
        ]
        for nombre, calc, arch in pruebas:
            if abs(calc) < 0.01 and abs(arch) < 0.01:
                continue        # ambos en cero: no hay nada que validar
            if abs(calc - arch) >= 1.0:
                out.append({"month": m, "check": nombre, "calculado": round(calc, 2),
                            "archivo": round(arch, 2), "dif": round(calc - arch, 2)})
    return out


def _ultimo_mes_con_dato(blk: dict) -> int:
    """Último mes del bloque que trae ALGÚN número distinto de cero.

    No es lo mismo que el último mes presente en el archivo, y la diferencia
    decide si el forecast conserva su proyección o la pierde.

    Una recarga anual sube los doce meses aunque solo los primeros tengan
    cifras: las columnas de los meses que faltan vienen en cero, no vacías. Si
    el corte avanzara al último mes PRESENTE, un archivo con datos hasta julio
    lo empujaría hasta diciembre — y de agosto en adelante el forecast mostraría
    los ceros del Actual como si fueran el cierre real, en vez de su propia
    proyección. El GOP seguiría cuadrando; simplemente el año se acabaría en
    julio sin que nada lo dijera.

    Mirar el valor y no la presencia también es más conservador con los meses
    cerrados de verdad: en Corcovado octubre cierra en cero, así que si el
    archivo termina ahí el corte se queda en septiembre. Quedarse corto no hace
    daño —el forecast proyecta un mes cerrado, que da casi cero igual— y se
    corrige con la siguiente subida o a mano. Pasarse sí hace daño.
    """
    meses = set(blk.get("stats", {})) | set(blk.get("lines", {}))
    con_dato = []
    for m in meses:
        valores = list((blk.get("stats", {}).get(m) or {}).values())
        valores += list((blk.get("lines", {}).get(m) or {}).values())
        if any(v for v in valores if v):        # 0, 0.0 y None no cuentan
            con_dato.append(m)
    return max(con_dato) if con_dato else 0


@router.post("/scenarios/import-pl-snapshot/", dependencies=[Depends(registro_de_subida)])
async def import_pl_snapshot(
    file: UploadFile = File(...),
    # El default es el ALCANCE DEL MES, igual que `import-gl-detail`.
    #
    # Los dos importadores se recorren en el mismo ciclo —el owner sube los
    # actuales de cuatro propiedades TODOS los meses— y hasta acá tenían
    # defaults opuestos: uno month-scoped y el otro borrando el escenario
    # entero. Que dos puertas al mismo dato se comporten distinto es el tipo de
    # diferencia que nadie recuerda a la hora de escribir un curl.
    #
    # Verificado: ningún llamador del repo pide `merge=False`. La pantalla de
    # carga no llama a este endpoint (llama a `import-gl-detail`), y el único
    # llamador interno es `import-all`, que ahora también arranca en el mes.
    # El reemplazo total sigue disponible, pero ahora hay que pedirlo.
    merge: bool = Query(True),
    dry_run: bool = Query(False),
    # Mismo camino de CIERRE MENSUAL que `import-gl-detail`: escribe SOLO ese
    # mes y descarta el resto del archivo. Vive en el backend y no en la
    # pantalla porque una llamada directa tiene que toparse con el mismo tope.
    mes_de_cierre: int | None = Query(
        None, ge=1, le=12,
        description="Cierre mensual: escribe SOLO este mes y descarta el resto del archivo"),
    # ── Apagar el corte de meses cerrados: EXPLÍCITO, nunca de arrastre ──────
    #
    # Un snapshot de Forecast ya viene mezclado (un Forecast Apr trae actuals
    # ene-abr + proyección may-dic), así que hay un caso legítimo en el que el
    # `actuals_through` del destino estorba: el motor lo usaría para pisar esos
    # meses con el ACTUAL enlazado de HOY, y el snapshot dejaría de decir lo que
    # decía el día que se tomó.
    #
    # Pero eso pasaba SOLO, pegado al modo de reemplazo, y sin decir nada. El
    # corte es lo que hace que el FORECAST Working tome sus meses cerrados del
    # ACTUAL: ponerlo en cero deshace el cierre del mes. Hoy en Corcovado eso
    # son `FORECAST Working 2026` (corte 6) y `FORECAST April 2026` (corte 4).
    #
    # Ahora se pide a mano. Si no se pide y el destino tenía corte, la respuesta
    # lo AVISA en vez de tocarlo.
    apagar_corte: bool = Query(
        False,
        description="Pone actuals_through=0 en los escenarios cargados (deshace el "
                    "corte de meses cerrados). Solo para recargar un snapshot que ya "
                    "trae su propio blend."),
    db: AsyncSession = Depends(get_db),
    idioma: str = Idioma,
):
    """Sube el archivo 'upload' con N bloques (Actual/Forecast/Budget × meses) y
    escribe cada bloque como ScenarioStat + ActualPLLine en el escenario que
    coincida por (tipo, año). Pone source_mode='imported' para que el P&L lea el
    snapshot. Devuelve qué se importó y qué bloques no encontraron escenario.

    merge=true (default): reemplaza SOLO los meses presentes en el archivo (ej.
    subir solo el mes que cerrás) y preserva los demás meses ya cargados.
    merge=false: reemplaza TODO el escenario (borra los 12 meses y carga los del
    archivo). mes_de_cierre=N: escribe SOLO ese mes y descarta el resto.

    En ningún modo se toca `actuals_through` salvo que se pida `apagar_corte=true`:
    el corte es lo que hace que el Forecast Working tome del Actual sus meses
    cerrados, y apagarlo deshace el cierre."""
    from app.importers.pl_snapshot_importer import parse_pl_snapshot
    data = await file.read()
    try:
        blocks = parse_pl_snapshot(data)
    except Exception as e:
        raise ErrorApi(400, "archivo.no_se_pudo_leer", detalle=str(e))

    # ── Cierre mensual: se recorta el archivo al mes elegido ─────────────────
    #
    # Acá arriba, antes de la vista previa y de cualquier escritura, para que
    # todo lo de abajo —el preview, los meses tocados, el avance del corte— vea
    # exactamente lo que se va a escribir. Recortar más tarde dejaría la vista
    # previa mostrando un archivo y la base recibiendo otro.
    meses_descartados: list[int] = []
    if mes_de_cierre is not None:
        for blk in blocks:
            for key in ("stats", "lines"):
                porMes = blk.get(key) or {}
                meses_descartados.extend(m for m in porMes if m != mes_de_cierre)
                blk[key] = {m: v for m, v in porMes.items() if m == mes_de_cierre}
    meses_descartados = sorted(set(meses_descartados))

    scenarios = (await db.execute(select(Scenario))).scalars().all()

    if dry_run:
        # Vista previa: NO escribe nada. Reporta a qué escenario iría cada bloque,
        # qué líneas del summary NO amarraron y si el P&L cuadra.
        prev = []
        for blk in blocks:
            target = _match_block_target(scenarios, blk["type"], blk["year"])
            checks = _pl_block_checks(blk)
            prev.append({
                "label": blk["label"],
                "matched": f"{target.type} {target.version} {target.year}" if target else None,
                "months": sorted(set(blk["stats"]) | set(blk["lines"])),
                "lines_per_month": (len(next(iter(blk["lines"].values()))) if blk["lines"] else 0),
                "unmapped": blk.get("unmapped", []),
                "checks_failed": checks,
                "ok": target is not None and not checks and not blk.get("unmapped"),
            })
        return {"dry_run": True, "merge": merge, "blocks": prev,
                "mes_de_cierre": mes_de_cierre,
                "meses_descartados": meses_descartados,
                "total_unmapped": sum(len(b["unmapped"]) for b in prev),
                "total_checks_failed": sum(len(b["checks_failed"]) for b in prev)}

    results = []
    actual_uploads = []   # (hotel_id, year, último mes subido) para auto-avanzar el cut
    for blk in blocks:
        typ, year = blk["type"], blk["year"]
        target = _match_block_target(scenarios, typ, year)
        if target is None:
            results.append({"label": blk["label"], "matched": None,
                            "stats_months": 0, "line_months": 0})
            continue
        # Una versión enllavada no recibe carga: se salta y se avisa.
        if target.is_locked:
            results.append({
                "label": blk["label"], "matched": None,
                "stats_months": 0, "line_months": 0,
                "aviso": t(idioma, "escenario.enllavado_no_se_cargo",
                           escenario=f"{target.type} {target.version} {target.year}"),
            })
            continue

        # Meses presentes en el bloque (stats o líneas). En merge solo tocamos esos.
        upload_months = sorted(set(blk["stats"].keys()) | set(blk["lines"].keys()))
        if typ == "ACTUAL":
            # El corte avanza también en reemplazo total, no solo en merge: la
            # recarga completa de un año es justo cuando uno NO se quiere
            # acordar de moverlo a mano.
            ultimo = _ultimo_mes_con_dato(blk)
            if ultimo:
                actual_uploads.append((target.hotel_id, year, ultimo))
        if merge:
            if upload_months:
                await db.execute(sa_delete(ScenarioStat).where(
                    ScenarioStat.scenario_id == target.id, ScenarioStat.month.in_(upload_months)))
                await db.execute(sa_delete(ActualPLLine).where(
                    ActualPLLine.scenario_id == target.id, ActualPLLine.month.in_(upload_months)))
        else:
            await db.execute(sa_delete(ScenarioStat).where(ScenarioStat.scenario_id == target.id))
            await db.execute(sa_delete(ActualPLLine).where(ActualPLLine.scenario_id == target.id))
        for m, st in blk["stats"].items():
            db.add(ScenarioStat(
                scenario_id=target.id, month=m,
                rooms_available=int(st.get("rooms_available", 0) or 0),
                rooms_occupied=st.get("rooms_occupied", Decimal("0")),
                guests=st.get("guests", Decimal("0")),
                occupancy_pct=st.get("occupancy_pct", Decimal("0")),
                adr=st.get("adr", Decimal("0")),
            ))
        n_lines = 0
        for m, codes in blk["lines"].items():
            for code, amt in codes.items():
                db.add(ActualPLLine(scenario_id=target.id, month=m,
                                    line_code=code, amount_usd=amt))
                n_lines += 1
        target.source_mode = "imported"
        # ── El corte de meses cerrados NO se apaga de arrastre ───────────────
        #
        # Antes esto era `if not merge: target.actuals_through = 0`, en silencio.
        # El motivo era real —un snapshot de Forecast ya viene mezclado y el
        # corte lo haría pisar con el ACTUAL de hoy— pero el efecto colateral es
        # el ciclo mensual: `actuals_through` es lo que hace que el Forecast
        # Working tome sus meses cerrados del Actual enlazado. Ponerlo en cero
        # deshace el cierre, el P&L sigue cuadrando consigo mismo, y nadie se
        # entera.
        #
        # Ahora se pide a mano (`apagar_corte=true`). Si no se pide, no se toca
        # — y si el destino tenía corte y el modo era reemplazo total, la
        # respuesta lo dice, para que la decisión se tome viéndola.
        corte_previo = target.actuals_through or 0
        aviso_corte = None
        if apagar_corte:
            target.actuals_through = 0
        elif corte_previo and not merge:
            aviso_corte = t(idioma, "escenario.conserva_el_corte",
                            escenario=f"{target.type} {target.version} {target.year}",
                            corte=corte_previo)
        res_blk = {
            "label": blk["label"],
            "matched": f"{target.type} {target.version} {target.year}",
            "scenario_id": target.id,
            "merge": merge,
            "months_touched": upload_months,
            "stats_months": len(blk["stats"]),
            "line_months": len(blk["lines"]),
            "lines_written": n_lines,
            "actuals_through": target.actuals_through or 0,
        }
        if apagar_corte and corte_previo:
            res_blk["corte_apagado"] = corte_previo
        if aviso_corte:
            res_blk["aviso_corte"] = aviso_corte
        results.append(res_blk)

    # Auto-avance del cut: al subir el Actual, el Forecast "Current"
    # (is_current_forecast) avanza su corte al último mes CON DATO — solo hacia
    # adelante. Así los meses cerrados se jalan del Actual sin tocar nada a
    # mano. Reforecasts y snapshots NO se tocan: son fotos de una decisión.
    cut_advanced = []
    for hotel_id, yr, last_m in actual_uploads:
        for s in scenarios:
            if (s.type == "FORECAST" and s.hotel_id == hotel_id and s.year == yr
                    and getattr(s, "is_current_forecast", False)
                    and (s.actuals_through or 0) < last_m):
                s.actuals_through = last_m
                cut_advanced.append({"scenario_id": s.id, "version": s.version,
                                     "actuals_through": last_m})

    await db.commit()
    return {"blocks": results, "cut_advanced": cut_advanced,
            # Qué camino se recorrió, dicho por el servidor y no supuesto por
            # quien llama: un cierre mensual y una carga histórica se veían igual.
            "merge": merge,
            "mes_de_cierre": mes_de_cierre,
            "meses_descartados": meses_descartados}


# ─── Importar detalle GL por cuenta × depto (OPEX 7xxx + Costos 5xxx) ──────────
_GL_MONTHS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]


def exigir_filas_con_cuenta(blocks: list[dict]) -> None:
    """Se niega si el GL trae filas con monto y SIN numero de cuenta.

    Vive aparte porque hay DOS caminos de carga y los dos tienen que validar
    antes de escribir: el importador de GL suelto y el combinado, que sube el
    archivo entero (hoja Resumen + hoja Detalle).

    ⚠️ En el combinado esto tiene que correr **antes** del snapshot. El snapshot
    escribe y hace commit; si el GL fallara despues, quedaria el resumen cargado
    y el detalle no — y el mensaje diria «no se cargo nada», que seria mentira.
    """
    from app.importers.gl_detail_importer import filas_sin_cuenta
    huerfanas = filas_sin_cuenta(blocks)
    if huerfanas:
        MESES_ES = ["ene", "feb", "mar", "abr", "may", "jun",
                    "jul", "ago", "set", "oct", "nov", "dic"]

        def _describe(f):
            meses = " · ".join(
                f"{MESES_ES[m - 1]} {v:,.2f}" for m, v in sorted(f["meses"].items()))
            quien = f["departamento"] or "(sin departamento)"
            desc = f' "{f["descripcion"]}"' if f["descripcion"] else ""
            return f"fila {f['fila']} · {quien}{desc} · {meses} · total {f['total']:,.2f}"

        total = sum(f["total"] for f in huerfanas)
        muestra = [_describe(f) for f in sorted(huerfanas, key=lambda x: -abs(x["total"]))[:8]]
        resto = len(huerfanas) - len(muestra)
        # TRES claves y no una. El singular, el plural, y el plural que
        # ademas tiene que decir «y N mas»: ese pedazo es TEXTO, y el idioma
        # se elige recien al contestar, asi que no se puede pegar aca — tiene
        # que venir ya armado del catalogo. La lista de filas (`muestra`) si
        # viaja como dato: son numeros de fila, departamentos y montos.
        clave = ("gl.fila_sin_cuenta" if len(huerfanas) == 1
                 else "gl.filas_sin_cuenta_y_mas" if resto > 0
                 else "gl.filas_sin_cuenta")
        raise ErrorApi(
            422, clave,
            n=len(huerfanas), total=f"{total:,.2f}",
            muestra="\n".join(muestra), resto=resto,
        )


@router.post("/scenarios/import-gl-detail/", dependencies=[Depends(registro_de_subida)])
async def import_gl_detail(
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    # El default es el ALCANCE DEL MES, no el del año.
    #
    # El ciclo real (owner, 2026-08-16) es mensual: «yo subo julio, se actualiza el
    # ACTUAL 2026». Con `merge=False` una carga de un mes borraba y refabricaba el
    # escenario ENTERO; el default destructivo solo estaba a salvo porque la pantalla
    # manda `merge=true` a mano. Cualquier llamada por fuera (curl, script) se llevaba
    # los meses ya cerrados por delante, y el P&L seguía cuadrando consigo mismo.
    #
    # Verificado: ningún llamador del repo pide `merge=False`. El reemplazo total
    # sigue disponible, pero ahora hay que pedirlo.
    merge: bool = Query(True),
    scenario_id: str | None = Query(None),
    confirmar_diferencias: bool = Query(
        False, description="Seguir aunque la verificación de arriba no cuadre con el detalle"),
    # ── El camino del CIERRE MENSUAL ─────────────────────────────────────────
    #
    # Owner (2026-08-16): «¿Por qué no hacemos 2 botones, uno para los históricos
    # 12 meses y el otro mes a mes? Así queda todo bien configurado y protegido.»
    #
    # Con `mes_de_cierre=7` la carga escribe SOLO julio. No es un aviso ni un
    # default: los demás meses del archivo **no se escriben**, así que un mes ya
    # cerrado no se puede tocar por accidente. Es el camino que se recorre todos
    # los meses con cada hotel, o sea donde un error se repite doce veces al año;
    # ahí no alcanza con avisar.
    #
    # Vive en el BACKEND y no solo en la pantalla porque una llamada directa
    # (curl, script, otra pantalla) tiene que toparse con el mismo límite.
    mes_de_cierre: int | None = Query(
        None, ge=1, le=12,
        description="Cierre mensual: escribe SOLO este mes y descarta el resto del archivo"),
    db: AsyncSession = Depends(get_db),
    usuario=Depends(get_current_user),
    idioma: str = Idioma,
):
    """Sube el archivo de MÁXIMO DETALLE (GL por cuenta×depto) y carga OPEX (7xxx)
    → OpexEntry y Costos (5xxx) → CostEntry en el escenario que coincide por
    tipo+año. Alimenta los reportes de gastos detallados de los históricos.
    dry_run=true → solo reporta qué se importaría, sin escribir.
    merge=false (default): reemplaza TODO el escenario. merge=true: reemplaza SOLO
    los meses presentes en el archivo (los detecta de los valores) y preserva los
    demás meses ya cargados — para subir solo el mes que cerrás."""
    from app.importers.gl_detail_importer import (
        parse_gl_detail, filas_sin_cuenta, es_contrapartida_de_allocation)
    from app.importers import verificacion as verificacion_mod
    data = await file.read()

    # El registro del archivo (checksum, traza, anti-reimport) lo hace
    # `registro_de_subida`, enganchado en el decorador de esta ruta. Vive allá y
    # no acá para que sea UN mecanismo y no veintiuno — ver
    # `app/importers/registro_dep.py`.
    try:
        blocks = parse_gl_detail(data)
    except Exception as e:
        raise ErrorApi(400, "archivo.no_se_pudo_leer", detalle=str(e))

    # ── Una fila con monto y sin numero de cuenta NO pasa ────────────────────
    #
    # El importador necesita el codigo para saber a que cuenta y a que linea del
    # P&L va. Sin el, antes la fila se descartaba EN SILENCIO — asi se perdieron
    # los $40,613.30 del gasto de Habitaciones en el Actual 2024, en dos
    # renglones de noviembre y diciembre. El P&L siguio cuadrando consigo mismo y
    # el descuadre aparecio meses despues, al compararlo contra el auxiliar.
    #
    # Ahora se niega, y el error ES el reporte: dice fila, departamento, mes y
    # monto, que es lo que hace falta para ir al Excel y ponerle la cuenta.
    # Aplica tambien a la vista previa: previsualizar un archivo que va a perder
    # plata no sirve de nada.
    exigir_filas_con_cuenta(blocks)

    # ── Cierre mensual: se recorta el archivo al mes elegido ─────────────────
    #
    # Se recorta ACÁ, antes de la verificación y de cualquier escritura, para que
    # todo lo de abajo —la comparación bucket por bucket, los meses tocados, el
    # avance del corte— vea exactamente lo que se va a escribir. Recortar más
    # tarde dejaría la verificación midiendo un archivo y la base recibiendo otro.
    meses_descartados: list[int] = []
    if mes_de_cierre is not None:
        for blk in blocks:
            for key in ("revenue", "opex", "costs", "belowgop", "payroll"):
                for r in blk.get(key, []):
                    sobra = [m for m in r["months"] if m != mes_de_cierre]
                    meses_descartados.extend(sobra)
                    for m in sobra:
                        del r["months"][m]
            for campo, porMes in list(blk.get("stats", {}).items()):
                blk["stats"][campo] = {m: v for m, v in porMes.items() if m == mes_de_cierre}
            for ctrl, porMes in list(blk.get("verificacion", {}).items()):
                blk["verificacion"][ctrl] = {m: v for m, v in porMes.items()
                                             if m == mes_de_cierre}
    meses_descartados = sorted(set(meses_descartados))

    scenarios = (await db.execute(select(Scenario))).scalars().all()
    # Mapeo de cuentas + config de líneas del reporte: el motor consolida el detalle
    # al P&L (below-GOP/fees/impuesto salen de las cuentas 8xxx reales). Validado al
    # dólar contra el Dashboard (Actual 2026 / Budget 2026).
    from app.engine.recalculate import load_active_account_mappings, load_report_line_config
    from app.engine import pl_engine
    from app.importers.gl_detail_importer import consolidate_block
    mappings = await load_active_account_mappings(db)
    report_lines = await load_report_line_config(db)
    # Versión explícita: si el owner eligió el escenario destino en la UI, TODOS los
    # bloques del archivo van ahí (necesario cuando hay varios del mismo tipo+año,
    # ej. 2 forecast 2026). Si no, se empareja por tipo+año como siempre.
    forced = None
    if scenario_id:
        forced = next((s for s in scenarios if s.id == scenario_id), None)
        if forced is None:
            raise ErrorApi(404, "escenario.no_encontrado")
    # ── La VERIFICACIÓN corre ANTES de escribir una sola fila ────────────────
    #
    # Owner (2026-08-16): «que el upload tenga la verificación arriba versus el
    # detalle abajo […] así el sistema consolida el detalle y valida que estos
    # resultados hagan match». Es el requisito que destraba clonar propiedades:
    # en Corcovado hay tres años cargados y un dato malo se nota comparando; en
    # una propiedad nueva NO HAY CONTRA QUÉ COMPARAR — el archivo entra, el P&L
    # sale, cuadra consigo mismo y nadie se entera hasta meses después.
    #
    # Va en la puerta y no en un reporte posterior, y va antes de cualquier
    # escritura: si bloquea, no se escribió nada que haya que deshacer.
    verificaciones: dict[int, dict] = {}
    consolidados: dict[int, dict] = {}
    choques: list[tuple[str, dict]] = []
    for i, blk in enumerate(blocks):
        if not blk.get("verificacion"):
            continue
        target = forced or _match_block_target(scenarios, blk["type"], blk["year"])
        if target is None or target.is_locked or not (mappings and report_lines):
            continue
        upload_months = sorted({mi for key in ("revenue", "opex", "costs", "belowgop", "payroll")
                                for r in blk.get(key, []) for mi in r["months"].keys()})
        extra = await _filas_que_sobreviven(db, target, merge, upload_months)
        con = consolidate_block(blk, mappings, report_lines, filas_extra=extra)
        consolidados[i] = con
        comparables, cerrados = verificacion_mod.meses_comparables(
            target.type, getattr(target, "actuals_through", 0))
        rep = verificacion_mod.comparar(blk["verificacion"], con["lines"],
                                        comparables, cerrados)
        verificaciones[i] = rep
        if rep["bloquea"]:
            choques.append((blk["label"], rep))

    if choques and not confirmar_diferencias:
        # Nunca en silencio, y nunca un rechazo pelado: el error ES el informe.
        # El owner puede tener una razón legítima para seguir —una provisión que
        # los libros todavía no tienen, por ejemplo— pero tiene que VERLA y
        # aceptarla, no descubrirla después.
        #
        # ⚠️ `error` y `que_hacer` siguen saliendo en español a propósito: son
        # los dos campos que LEE la pantalla (`VerificacionBloqueada`, en
        # `lib/api.ts`), y el manejador solo traduce `mensaje`. Sacarlos
        # dejaría el informe sin encabezado y sin qué-hacer. `mensaje` trae lo
        # mismo ya traducido, para cuando el frontend pase a leerlo.
        raise ErrorApi(409, "gl.verificacion_no_cuadra", extra={
            "error": "La verificación de arriba no cuadra con el detalle de abajo.",
            "que_hacer": ("Revisá la comparación bucket por bucket. Si el detalle está bien "
                          "y la diferencia es esperada, volvé a subir con "
                          "confirmar_diferencias=true."),
            "bloques": [{"label": lab, "verificacion": rep} for lab, rep in choques],
            "texto": "\n".join(verificacion_mod.resumen_texto(rep, lab)
                               for lab, rep in choques),
        })

    actual_uploads: list[tuple[str, int, int]] = []
    results = []
    for idx_blk, blk in enumerate(blocks):
        target = forced or _match_block_target(scenarios, blk["type"], blk["year"])
        # Una versión enllavada no recibe carga: se salta el bloque y se avisa,
        # en vez de sobreescribir en silencio un presupuesto ya aprobado.
        if target is not None and target.is_locked:
            results.append({
                "label": blk["label"], "matched": None,
                "aviso": t(idioma, "escenario.enllavado_no_se_cargo",
                           escenario=f"{target.type} {target.version} {target.year}"),
            })
            continue
        rev_tot = round(sum(sum(r["months"].values()) for r in blk.get("revenue", [])), 2)
        bgop_tot = round(sum(sum(r["months"].values()) for r in blk.get("belowgop", [])), 2)
        opex_tot = round(sum(sum(r["months"].values()) for r in blk["opex"]), 2)
        cost_tot = round(sum(sum(r["months"].values()) for r in blk["costs"]), 2)
        pay_tot = round(sum(sum(r["months"].values()) for r in blk.get("payroll", [])), 2)
        # La planilla GL se carga en cualquier escenario que traiga bloque de planilla
        # (Actual/Budget/Forecast). Crea posiciones sintéticas 'GL' por depto (aportan
        # costo, no headcount) que CONVIVEN con las posiciones reales sin pisarlas: el
        # DELETE de abajo solo borra las 'GL'. Confirmado con el usuario 2026-06-27: el
        # presupuesto 2026 toma su payroll del GL (ya está cuadrado ahí), no a mano.
        pay_applies = bool(target)
        res = {"label": blk["label"],
               "matched": (f"{target.type} {target.version} {target.year}" if target else None),
               "revenue_total": rev_tot, "belowgop_total": bgop_tot,
               "opex_accounts": len(blk["opex"]), "opex_total": opex_tot,
               "cost_accounts": len(blk["costs"]), "cost_total": cost_tot,
               "payroll_total": pay_tot if pay_applies else 0,
               "payroll_note": "",
               "locked": bool(target and target.is_locked),
               "unmapped_depts": blk["unmapped"]}
        # Meses presentes en el bloque (en merge solo tocamos esos; preservamos el resto).
        upload_months = sorted({mi for key in ("revenue", "opex", "costs", "belowgop", "payroll")
                                for r in blk.get(key, []) for mi in r["months"].keys()})
        res["merge"] = merge
        res["months_touched"] = upload_months
        # El resultado de la verificación viaja SIEMPRE en la respuesta, cuadre
        # o no: si solo apareciera cuando falla, el owner no tendría cómo saber
        # que el archivo trae control y que se miró.
        if idx_blk in verificaciones:
            res["verificacion"] = verificaciones[idx_blk]
        elif blk.get("verificacion"):
            res["verificacion"] = {"hay_verificacion": False,
                                   "motivo": t(idioma, "gl.verificacion_no_corrio")}
        # El consolidado del bloque, ya con las filas que escribe el MOTOR y el
        # archivo no puede traer (contrapartidas de reparto). Se computa una vez.
        if target is not None and mappings and report_lines and idx_blk not in consolidados:
            consolidados[idx_blk] = consolidate_block(
                blk, mappings, report_lines,
                filas_extra=await _filas_que_sobreviven(db, target, merge, upload_months))
        # ── Chequeo de amarre GL ↔ P&L Summary (solo en vista previa) ──────────
        # El detalle GL (costos 5xxx + planilla 6xxx + opex 7xxx, TODOS los deptos)
        # debe sumar el gasto operativo total del summary = TOTAL_OPEXP (deptos
        # operativos) + TOTAL_OVERHEAD (overhead). Total anual; tolerancia 2%
        # (allocation 0220/0161 puede diferir algo).
        if dry_run and target is not None:
            snap = (await db.execute(select(ActualPLLine.line_code, ActualPLLine.amount_usd).where(
                ActualPLLine.scenario_id == target.id,
                ActualPLLine.line_code.in_(["TOTAL_OPEXP", "TOTAL_OVERHEAD"])))).all()
            pl_cost = float(sum(v for _, v in snap)) if snap else 0.0
            gl_cost = opex_tot + cost_tot + pay_tot   # opex 7xxx + costos 5xxx + planilla 6xxx
            res["check_opex"] = {
                "pl_total_opex": round(pl_cost, 2),
                "gl_opex_plus_payroll": round(gl_cost, 2),
                "dif": round(gl_cost - pl_cost, 2),
                "ok": (pl_cost == 0) or abs(gl_cost - pl_cost) <= max(1.0, abs(pl_cost) * 0.02),
                "sin_snapshot": not snap,
            }
            # P&L consolidado que producirá el motor desde ESTE detalle (preview).
            if mappings and report_lines:
                con = consolidados[idx_blk]
                agg: dict[str, float] = {}
                for ls in con["lines"].values():
                    for lc, v in ls.items():
                        agg[lc] = agg.get(lc, 0.0) + float(v)
                res["pl_preview"] = {
                    "revenue": round(agg.get("TOTAL_REVENUES", 0.0), 2),
                    "gop": round(agg.get("TOTAL_GOP", 0.0), 2),
                    "ebitda": round(agg.get("EBITDA_BEFORE_CAPITAL", 0.0), 2),
                    "net": round(agg.get("NET_PROFIT", 0.0), 2),
                    "stat_months": sorted(con["stats"].keys()),
                }
        results.append(res)
        if target is None or dry_run:
            continue
        # Versión enllavada: no se sobrescribe. Hay que desbloquearla para editar.
        if target.is_locked:
            res["skipped_locked"] = True
            continue

        # Agregar por (dept, cuenta) sumando meses — el GL puede traer la misma
        # cuenta varias veces (distintos orígenes); el unique es (scenario,dept,account,detail).
        def _agg(rows):
            acc: dict[tuple, dict] = {}
            for r in rows:
                k = (r["dept_code"], r["account_code"])
                a = acc.setdefault(k, {"account_name": r["account_name"], "_best": -1e18, "months": {}})
                rsum = sum(r["months"].values())
                if rsum > a["_best"]:  # nombre de la línea que más aporta (varias comparten cuenta)
                    a["_best"] = rsum; a["account_name"] = r["account_name"]
                for mi, v in r["months"].items():
                    a["months"][mi] = a["months"].get(mi, 0.0) + v
            return acc

        async def _write_accounts(Model, rows, extra_new):
            agg = _agg(rows)
            if not merge:
                await db.execute(sa_delete(Model).where(Model.scenario_id == target.id))
                for (dept, code), a in agg.items():
                    kw = {m: Decimal(str(a["months"].get(i + 1, 0))) for i, m in enumerate(_GL_MONTHS)}
                    db.add(Model(scenario_id=target.id, hotel_id=target.hotel_id, dept_code=dept,
                                 account_code=code, account_name=a["account_name"], **extra_new(a), **kw))
                return
            # merge: limpiar los meses subidos en TODAS las filas existentes, luego upsert
            existing = (await db.execute(
                select(Model).where(Model.scenario_id == target.id))).scalars().all()
            by_key = {(e.dept_code, e.account_code): e for e in existing}
            for e in existing:
                for mi in upload_months:
                    setattr(e, _GL_MONTHS[mi - 1], Decimal("0"))
            for (dept, code), a in agg.items():
                row = by_key.get((dept, code))
                if row is None:
                    row = Model(scenario_id=target.id, hotel_id=target.hotel_id, dept_code=dept,
                                account_code=code, account_name=a["account_name"], **extra_new(a),
                                **{m: Decimal("0") for m in _GL_MONTHS})
                    db.add(row); by_key[(dept, code)] = row
                else:
                    row.account_name = a["account_name"]
                for mi, v in a["months"].items():
                    setattr(row, _GL_MONTHS[mi - 1], Decimal(str(v)))

        await _write_accounts(RevenueAccountEntry, blk["revenue"], lambda a: {})
        await _write_accounts(BelowGopAccountEntry, blk.get("belowgop", []), lambda a: {})
        await _write_accounts(OpexEntry, blk["opex"],
                              lambda a: {"detail_code": "", "detail_desc": a["account_name"]})
        await _write_accounts(CostEntry, blk["costs"], lambda a: {})

        # ── Planilla (6xxx) → conceptos. Posición sintética "(Actual GL)" por depto
        #    (position_code='GL') + PayrollConceptEntry por (dept, mes). ──
        if pay_applies and blk.get("payroll"):
            agg: dict[tuple, dict] = {}
            dept_names: dict[str, str] = {}
            for r in blk["payroll"]:
                dept_names.setdefault(r["dept_code"], r.get("dept_name", ""))
                for mi, v in r["months"].items():
                    a = agg.setdefault((r["dept_code"], mi), {})
                    a[r["concept"]] = a.get(r["concept"], 0.0) + v
            depts = {d for (d, _m) in agg}

            if merge:
                # preservar posiciones GL; borrar solo los conceptos GL de los meses subidos
                gl_pos = (await db.execute(select(PayrollPosition).where(
                    PayrollPosition.scenario_id == target.id,
                    PayrollPosition.position_code == "GL"))).scalars().all()
                pos_by_dept = {p.dept_code: p for p in gl_pos}
                gl_ids = [p.id for p in gl_pos]
                if gl_ids and upload_months:
                    await db.execute(sa_delete(PayrollConceptEntry).where(
                        PayrollConceptEntry.scenario_id == target.id,
                        PayrollConceptEntry.position_id.in_(gl_ids),
                        PayrollConceptEntry.month.in_(upload_months)))
            else:
                await db.execute(sa_delete(PayrollConceptEntry).where(
                    PayrollConceptEntry.scenario_id == target.id))
                await db.execute(sa_delete(PayrollPosition).where(
                    PayrollPosition.scenario_id == target.id,
                    PayrollPosition.position_code == "GL"))
                pos_by_dept = {}

            # Nombre canónico del depto: adoptar el de una posición real (no-GL)
            # existente del escenario, para no generar duplicados de dept_name en
            # el selector de planilla (causa raíz de departamentos repetidos).
            real_rows = (await db.execute(select(
                PayrollPosition.dept_code, PayrollPosition.dept_name).where(
                PayrollPosition.scenario_id == target.id,
                PayrollPosition.position_code != "GL"))).all()
            real_names: dict[str, str] = {}
            for _rc, _rn in real_rows:
                if _rn and _rc not in real_names:
                    real_names[_rc] = _rn

            for d in depts:                       # crear posiciones GL faltantes
                if d not in pos_by_dept:
                    pos = PayrollPosition(scenario_id=target.id, hotel_id=target.hotel_id,
                                          dept_code=d, dept_name=(real_names.get(d) or dept_names.get(d, "")), position_code="GL",
                                          position_name="(Actual GL)", employee_name="(Actual GL)",
                                          salary_amount=Decimal("0"), salary_currency="USD",
                                          **{f: Decimal("0") for f in [
                                              "fte_jan","fte_feb","fte_mar","fte_apr","fte_may","fte_jun",
                                              "fte_jul","fte_aug","fte_sep","fte_oct","fte_nov","fte_dec"]})
                    db.add(pos); pos_by_dept[d] = pos
            await db.flush()
            for (d, mi), concepts in agg.items():
                db.add(PayrollConceptEntry(
                    scenario_id=target.id, position_id=pos_by_dept[d].id,
                    dept_code=d, month=mi, year=target.year,
                    **{c: Decimal(str(v)) for c, v in concepts.items()}))

        # ── Consolidar el summary desde el detalle ────────────────────────────
        # Escribe ActualEntry (cuentas 4-8 crudas, planilla expandida) para que el
        # motor arme el P&L al vuelo (below-GOP/fees/impuesto vienen de las 8xxx), y
        # limpia el snapshot de línea (ActualPLLine) para que gane el camino a nivel
        # cuenta. Estadísticas → ScenarioStat. Así "solo el detalle" produce el P&L.
        if mappings and report_lines:
            con = consolidados[idx_blk]
        else:
            con = {"lines": {}, "stats": {}}
        touched = sorted({mi for key in ("revenue", "opex", "costs", "belowgop", "payroll")
                          for r in blk.get(key, []) for mi in r["months"].keys()})
        # La llave lleva el OUTLET: el GL de A&B trae la misma cuenta una vez por
        # punto de venta. Sin él, los cuatro outlets se agregan en una sola fila
        # y la apertura se pierde en la carga. Vacío en todo lo que no sea A&B.
        ae_agg: dict[tuple, dict] = {}
        def _ae_add(dept_c, code_c, name_c, months_c, outlet_c="", fila_c=None):
            a = ae_agg.setdefault((dept_c, code_c, outlet_c or ""),
                                  {"name": name_c or "", "months": {}, "fila": None})
            if name_c:
                a["name"] = name_c
            # Se guarda la PRIMERA fila del archivo donde aparecio. Una cuenta
            # puede venir repartida en varias filas; para devolver la plantilla
            # en el orden del owner manda donde la puso por primera vez.
            if fila_c is not None and (a["fila"] is None or fila_c < a["fila"]):
                a["fila"] = fila_c
            for mi_, v_ in months_c.items():
                a["months"][mi_] = a["months"].get(mi_, 0.0) + v_
        for key in ("revenue", "costs", "opex", "belowgop"):
            for r in blk.get(key, []):
                _ae_add(r["dept_code"], r["account_code"], r.get("account_name", ""),
                        r["months"], r.get("outlet", ""), r.get("fila"))
        for r in blk.get("payroll", []):
            acct = pl_engine.payroll_account_for_column(r["concept"])
            if acct:
                _ae_add(r["dept_code"], acct, "", r["months"], "", r.get("fila"))

        if merge:
            if touched:
                existing_ae = (await db.execute(select(ActualEntry).where(
                    ActualEntry.scenario_id == target.id))).scalars().all()
                ae_by = {(e.dept_code, e.account_code, e.outlet or ""): e
                         for e in existing_ae}
                # ⚠️ Las contrapartidas de reparto TAMPOCO se pisan al subir un mes.
                #
                # El reemplazo total ya las protegía (`~ES_CONTRAPARTIDA_DE_ALLOCATION`,
                # abajo), pero el merge no: ponía en cero TODAS las filas de los meses
                # subidos, contrapartidas incluidas. Y el archivo no puede reponerlas
                # —el parser las excluye a propósito (`es_contrapartida_de_allocation`)
                # porque son el crédito del asiento, no ingreso—, así que quedaban en
                # cero para siempre. Nada las regenera: un ACTUAL no recalcula repartos.
                #
                # Medido sobre el Actual 2025: subir SOLO julio se llevaba −5.007,57 de
                # Lavandería (0161/4900) y −12.537,17 de Cafetería (0220/4901) = −17.544,74
                # de crédito, que el overhead pasaba a mostrar de más. En el año son
                # −196.326,17. Y el P&L seguía cuadrando consigo mismo.
                #
                # Es el camino que usa la pantalla de carga (manda merge=true), o sea el
                # que se recorre TODOS los meses con CADA hotel. Owner (2026-08-16): sí.
                for e in existing_ae:
                    if es_contrapartida_de_allocation(e.account_code, e.account_name):
                        continue
                    for mi_ in touched:
                        e.set_month(mi_, Decimal("0"))
                await db.execute(sa_delete(ActualPLLine).where(
                    ActualPLLine.scenario_id == target.id, ActualPLLine.month.in_(touched)))
                await db.execute(sa_delete(ScenarioStat).where(
                    ScenarioStat.scenario_id == target.id, ScenarioStat.month.in_(touched)))
                for (dept_c, code_c, outlet_c), a in ae_agg.items():
                    e = ae_by.get((dept_c, code_c, outlet_c))
                    if e is None:
                        e = ActualEntry(scenario_id=target.id, hotel_id=target.hotel_id,
                                        dept_code=dept_c, account_code=code_c,
                                        account_name=a["name"], outlet=outlet_c,
                                        orden_archivo=a.get("fila"))
                        db.add(e); ae_by[(dept_c, code_c, outlet_c)] = e
                    elif a["name"]:
                        e.account_name = a["name"]
                    for mi_, v_ in a["months"].items():
                        e.set_month(mi_, Decimal(str(v_)))
        else:
            # ⚠️ Las contrapartidas de los allocations SOBREVIVEN al reemplazo.
            #
            # Owner (2026-08-14): bajo la plantilla del Detalle y le faltaban dos
            # filas —4900 Distribucion (Lavanderia 0161) y 4901 (Cafeteria
            # 0220), −$196.326,17—. No es que se pierdan al bajar: el parser
            # EXCLUYE a proposito las clase 4 llamadas «Distribucion», porque son
            # el credito del asiento con que esos departamentos reparten su costo
            # y contarlas como ingreso duplicaria el reparto.
            #
            # El problema era el viaje de vuelta: como el archivo nunca las trae,
            # este reemplazo completo las borraba. Bajar, corregir una celda y
            # volver a subir se llevaba $196 mil por delante — y el P&L seguia
            # cuadrando consigo mismo, asi que la diferencia solo aparecia
            # despues, comparando contra el auxiliar. Es el mismo patron que los
            # $40.613 del Actual 2024.
            #
            # Las genera el sistema, no se digitan. Por eso no se borran: el
            # archivo no puede quitar lo que el archivo no puede traer.
            await db.execute(sa_delete(ActualEntry).where(
                ActualEntry.scenario_id == target.id,
                ~ES_CONTRAPARTIDA_DE_ALLOCATION))
            await db.execute(sa_delete(ActualPLLine).where(ActualPLLine.scenario_id == target.id))
            await db.execute(sa_delete(ScenarioStat).where(ScenarioStat.scenario_id == target.id))
            for (dept_c, code_c, outlet_c), a in ae_agg.items():
                e = ActualEntry(scenario_id=target.id, hotel_id=target.hotel_id,
                                dept_code=dept_c, account_code=code_c,
                                account_name=a["name"], outlet=outlet_c,
                                orden_archivo=a.get("fila"))
                for mi_, v_ in a["months"].items():
                    e.set_month(mi_, Decimal(str(v_)))
                db.add(e)
        for mi_, s in con["stats"].items():
            db.add(ScenarioStat(
                scenario_id=target.id, month=mi_,
                rooms_available=int(s.get("rooms_available", 0) or 0),
                rooms_occupied=s.get("rooms_occupied", Decimal("0")),
                guests=s.get("guests", Decimal("0")),
                occupancy_pct=s.get("occupancy_pct", Decimal("0")),
                adr=s.get("adr", Decimal("0")),
            ))
        target.source_mode = "imported"
        # Los meses de ACTUAL que trae este archivo, para mover el corte del
        # forecast al final. Solo cuentan los que tienen alguna cifra.
        if target.type == "ACTUAL":
            con_dato = sorted(
                mi for mi in upload_months
                if any(v for a in ae_agg.values() for k, v in a["months"].items() if k == mi)
                or (con["stats"].get(mi) and any(con["stats"][mi].values()))
            )
            if con_dato:
                actual_uploads.append((target.hotel_id, target.year, max(con_dato)))

    # El Forecast «Current» toma del Actual los meses cerrados y proyecta el
    # resto. Ese corte tiene que moverse solo al subir el cierre de un mes: si
    # hay que acordarse de correrlo a mano, el forecast se queda proyectando un
    # mes que ya cerró y nadie lo nota — los totales cuadran igual.
    #
    # Este endpoint es el que usa la pantalla de carga, y no lo movía. El de
    # `import-pl-snapshot` sí, pero ya no lo llama nadie desde la app.
    #
    # Solo hacia adelante, y solo el forecast vivo: los reforecasts archivados
    # y los snapshots son fotos de una decisión, y moverles el corte los haría
    # decir algo distinto de lo que decían el día que se tomaron.
    cut_advanced = []
    if not dry_run:
        for hotel_id, yr, last_m in actual_uploads:
            fcs = (await db.execute(select(Scenario).where(
                Scenario.hotel_id == hotel_id, Scenario.year == yr,
                Scenario.type == "FORECAST",
                Scenario.is_current_forecast == True,  # noqa: E712
            ))).scalars().all()
            for f in fcs:
                if (f.actuals_through or 0) < last_m:
                    f.actuals_through = last_m
                    cut_advanced.append({"scenario_id": f.id, "version": f.version,
                                         "actuals_through": last_m})

    if not dry_run:
        await db.commit()
    return {"dry_run": dry_run, "blocks": results, "cut_advanced": cut_advanced,
            # Qué camino se recorrió, dicho por el servidor y no supuesto por la
            # pantalla. Sin esto, un cierre mensual y una carga histórica se ven
            # iguales en la respuesta.
            "mes_de_cierre": mes_de_cierre,
            "meses_descartados": meses_descartados}


# ─── Importar TODO de un solo archivo (P&L resumen + detalle GL) ───────────────
class _BytesFile:
    """Shim mínimo: los importadores solo llaman `await file.read()`. Evita
    depender de la firma de Starlette UploadFile (cambia entre versiones)."""
    def __init__(self, data: bytes, filename: str = "upload.xlsx"):
        self._d = data
        self.filename = filename

    async def read(self) -> bytes:
        return self._d


@router.post("/scenarios/import-all/", dependencies=[Depends(registro_de_subida)])
async def import_all(
    file: UploadFile = File(...),
    # Alcance del MES por defecto, igual que los dos importadores que envuelve.
    # Este endpoint pasaba su `merge` a AMBOS, así que su default arrastraba a
    # `import-gl-detail` de vuelta al reemplazo total aunque ese ya estuviera
    # arreglado: la puerta combinada deshacía el arreglo de la puerta simple.
    merge: bool = Query(True),
    dry_run: bool = Query(False),
    confirmar_diferencias: bool = Query(False),
    # El cierre mensual vale para el archivo entero: resumen y detalle recortan
    # al mismo mes. Si solo recortara uno, el control de arriba y el detalle de
    # abajo estarían hablando de meses distintos.
    mes_de_cierre: int | None = Query(
        None, ge=1, le=12,
        description="Cierre mensual: escribe SOLO este mes y descarta el resto del archivo"),
    apagar_corte: bool = Query(
        False,
        description="Pone actuals_through=0 en los escenarios cargados (deshace el "
                    "corte de meses cerrados)."),
    db: AsyncSession = Depends(get_db),
    usuario=Depends(get_current_user),
    idioma: str = Idioma,
):
    """Un solo archivo → corre AMBOS importadores: P&L por línea (hoja Resumen) +
    detalle GL por cuenta×depto (hoja Detalle). Cada importador auto-elige su hoja.
    En reemplazo real corre P&L primero (deja el snapshot) y luego GL. dry_run no
    escribe nada y devuelve el cuadre de ambos para validar antes de importar."""
    data = await file.read()
    name = file.filename or "upload.xlsx"

    # El GL se valida ANTES de tocar nada. El snapshot escribe y hace commit, asi
    # que si el GL reventara despues quedaria el resumen cargado y el detalle no:
    # media importacion, y un mensaje de error diciendo que no se cargo nada.
    from app.importers.gl_detail_importer import parse_gl_detail
    try:
        exigir_filas_con_cuenta(parse_gl_detail(data))
    except HTTPException:
        raise
    except Exception:
        # Que el archivo no tenga hoja de Detalle no es asunto de esta validacion:
        # el importador de GL lo reporta a su manera mas abajo.
        pass

    # Y la VERIFICACION tambien va antes del snapshot, por el mismo motivo: si
    # el bloque de control no cuadra, el GL contesta 409 — y si eso pasara
    # DESPUES de que el snapshot ya hizo commit, quedaria el resumen cargado, el
    # detalle no, y un mensaje de error diciendo que no se cargo nada. La corrida
    # en seco no escribe: solo compara y, si bloquea, corta aca.
    # ⚠️ Acá se llama a los importadores COMO FUNCIONES, no por HTTP: FastAPI no
    # resuelve los defaults, así que cada parámetro omitido llega como el objeto
    # `Query(...)` — y `bool(Query(None))` es **True**. Por eso van todos
    # explícitos. `scenario_id` era el que faltaba: `if scenario_id:` daba
    # verdadero con el objeto, no encontraba ningún escenario con ese id y la
    # carga combinada moría con un 404 «Escenario (versión) no encontrado».
    if not dry_run:
        await import_gl_detail(file=_BytesFile(data, name), dry_run=True, merge=merge,
                               scenario_id=None, confirmar_diferencias=confirmar_diferencias,
                               mes_de_cierre=mes_de_cierre,
                               db=db, usuario=usuario, idioma=idioma)

    pl = await import_pl_snapshot(file=_BytesFile(data, name), merge=merge, dry_run=dry_run,
                                  mes_de_cierre=mes_de_cierre, apagar_corte=apagar_corte, db=db,
                                  idioma=idioma)
    gl = await import_gl_detail(file=_BytesFile(data, name), dry_run=dry_run, merge=merge,
                                scenario_id=None, confirmar_diferencias=confirmar_diferencias,
                                mes_de_cierre=mes_de_cierre,
                                db=db, usuario=usuario, idioma=idioma)
    return {"dry_run": dry_run, "merge": merge, "mes_de_cierre": mes_de_cierre,
            "pl": pl, "gl": gl}


# ─── Aplicar el Big Picture (top-down) a un escenario Budget ──────────────────
class ApplyBigPictureBody(BaseModel):
    base_scenario_id: str
    groups: dict = {}          # {grupo: {"revenue":x,"payroll":y,"opex":z,"cost":w}} anual proyectado
    belowgop_total: float = 0.0  # below-GOP anual proyectado (= GOP − Net del Big Picture)
    stats: dict = {}           # {"rooms_available":n,"rooms_occupied":m,"guests":p} anual


@router.post("/scenarios/{target_id}/apply-big-picture/")
async def apply_big_picture(target_id: str, body: ApplyBigPictureBody,
                            dry_run: bool = Query(False), db: AsyncSession = Depends(get_db)):
    """Escribe el Budget top-down del Big Picture en el escenario destino: escala cada
    cuenta del escenario base (Forecast) por el factor grupo×clase proyectado y consolida
    el P&L con el motor. dry_run=true → solo devuelve el P&L que quedaría (no escribe).
    Respeta el lock del destino."""
    from app.engine.recalculate import load_active_account_mappings, load_report_line_config
    from app.engine import pl_engine
    target = await db.get(Scenario, target_id)
    if not target:
        raise ErrorApi(404, "escenario.destino_no_encontrado")
    if target.is_locked:
        raise ErrorApi(409, "escenario.enllavado_big_picture", version=target.version)
    base_rows = (await db.execute(select(ActualEntry).where(
        ActualEntry.scenario_id == body.base_scenario_id))).scalars().all()
    if not base_rows:
        raise ErrorApi(400, "bigpicture.base_sin_detalle")

    CLSN = {"4": "revenue", "5": "cost", "6": "payroll", "7": "opex"}
    _M = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    base_gc: dict[tuple, float] = {}
    base_bg = 0.0
    for e in base_rows:
        d = str(e.account_code or "0")[0]
        g = pl_engine.group_for_dept(e.dept_code or "")
        yr = float(sum(getattr(e, m) or 0 for m in _M))
        if d in CLSN:
            base_gc[(g, CLSN[d])] = base_gc.get((g, CLSN[d]), 0.0) + yr
        elif d == "8":
            base_bg += yr

    def factor(e) -> float:
        d = str(e.account_code or "0")[0]
        g = pl_engine.group_for_dept(e.dept_code or "")
        if d in CLSN:
            base = base_gc.get((g, CLSN[d]), 0.0)
            proj = (body.groups.get(g) or {}).get(CLSN[d])
            return (proj / base) if (proj is not None and base) else 1.0
        if d == "8":
            return (body.belowgop_total / base_bg) if base_bg else 1.0
        return 1.0  # clase 9 u otras → sin cambio (stats se manejan aparte)

    # cuentas escaladas → filas por mes para consolidar + ActualEntry a escribir
    per_month: dict[int, list[dict]] = {m: [] for m in range(1, 13)}
    ae_out: list[tuple] = []
    for e in base_rows:
        if str(e.account_code or "0")[0] == "9":
            continue
        fac = factor(e)
        months = {}
        for i, m in enumerate(_M, start=1):
            v = float(getattr(e, m) or 0) * fac
            months[i] = v
            if v:
                per_month[i].append({"account_code": e.account_code, "dept_code": e.dept_code, "amount": Decimal(str(v))})
        ae_out.append((e.dept_code, e.account_code, e.account_name, months))

    mappings = await load_active_account_mappings(db)
    report_lines = await load_report_line_config(db)
    pl_by_month: dict[int, dict] = {}
    agg: dict[str, float] = {}
    for m in range(1, 13):
        res = pl_engine.calculate_pl_from_mapping(per_month[m], mappings, report_lines)
        pl_by_month[m] = {L.line_code: L.amount_usd for L in res}
        for L in res:
            agg[L.line_code] = agg.get(L.line_code, 0.0) + float(L.amount_usd)
    preview = {"revenue": round(agg.get("TOTAL_REVENUES", 0.0), 2), "gop": round(agg.get("TOTAL_GOP", 0.0), 2),
               "ebitda": round(agg.get("EBITDA_BEFORE_CAPITAL", 0.0), 2), "net": round(agg.get("NET_PROFIT", 0.0), 2)}
    target_label = f"{target.type} {target.version} {target.year}"
    if dry_run:
        return {"dry_run": True, "target": target_label, "preview": preview}

    # ── escribir: ActualEntry (reemplaza) + ActualPLLine + ScenarioStat ──
    await db.execute(sa_delete(ActualEntry).where(ActualEntry.scenario_id == target.id))
    await db.execute(sa_delete(ActualPLLine).where(ActualPLLine.scenario_id == target.id))
    await db.execute(sa_delete(ScenarioStat).where(ScenarioStat.scenario_id == target.id))
    for dept, code, name, months in ae_out:
        e = ActualEntry(scenario_id=target.id, hotel_id=target.hotel_id, dept_code=dept,
                        account_code=code, account_name=name or "")
        for i in range(1, 13):
            e.set_month(i, Decimal(str(months.get(i, 0))))
        db.add(e)
    for m in range(1, 13):
        for code, amt in pl_by_month[m].items():
            db.add(ActualPLLine(scenario_id=target.id, month=m, line_code=code, amount_usd=Decimal(str(amt))))
    # estadísticas: repartir el anual por la forma mensual de ocupación del base
    base_stats = (await db.execute(select(ScenarioStat).where(
        ScenarioStat.scenario_id == body.base_scenario_id))).scalars().all()
    occ_by = {s.month: float(s.rooms_occupied or 0) for s in base_stats}
    avail_by = {s.month: float(s.rooms_available or 0) for s in base_stats}
    tot_occ = sum(occ_by.values()) or 0.0
    ann = body.stats or {}
    ann_occ = float(ann.get("rooms_occupied", 0) or 0)
    rooms_rev = float((body.groups.get("ROOMS") or {}).get("revenue", 0) or 0)
    adr = (rooms_rev / ann_occ) if ann_occ else 0.0
    for m in range(1, 13):
        share = (occ_by.get(m, 0) / tot_occ) if tot_occ else (1 / 12)
        occ = ann_occ * share
        avail = avail_by.get(m) or (float(ann.get("rooms_available", 0) or 0) / 12)
        guests = float(ann.get("guests", 0) or 0) * share
        db.add(ScenarioStat(
            scenario_id=target.id, month=m,
            rooms_available=int(round(avail)),
            rooms_occupied=Decimal(str(round(occ, 2))),
            guests=Decimal(str(round(guests, 2))),
            occupancy_pct=Decimal(str(round(occ / avail, 4))) if avail else Decimal("0"),
            adr=Decimal(str(round(adr, 2))),
        ))
    target.source_mode = "imported"
    await db.commit()
    return {"dry_run": False, "target": target_label, "preview": preview}


# ─── Descargar la plantilla de Detalle (round-trip: bajar → editar → subir) ────
_PAYROLL_NAMES = {
    "6000": "Salary and Wages", "6001": "Overtime", "6002": "Day Off",
    "6003": "Working Holiday", "6004": "Disabilities", "6010": "Commissions",
    "6020": "Social Security", "6021": "Christmas bonus", "6022": "Work Risk Policy",
    "6023": "Vacation Provision", "6024": "Vacations Taken", "6025": "Cafeteria",
    "6026": "Notice and Severance Pay", "6027": "Incentive Bonus", "6028": "Housing",
    "6029": "Transport", "6030": "Employee Benefit Others",
}


def filas_de_la_clase(derivadas: list, gl_rows: list, clase: str) -> list:
    """De dónde saca la plantilla del Detalle una clase de cuentas.

    **El defecto que cierra.** Las cuatro tablas de detalle por cuenta
    —`revenue_account_entries`, `cost_entries`, `opex_entries`,
    `belowgop_account_entries`— y la planilla sintética del GL las escribe UN
    solo camino: `POST /scenarios/import-gl-detail/`. Nada las deriva de
    `actual_entries`, y ningún reporte avisa cuando faltan.

    Así que un escenario cuyo detalle llegó por otra puerta —la carga original
    del libro de trabajo, `apply-big-picture`, o un `copy-from` de antes del
    2026-08-08, que no copiaba `gl_accounts` ni `costs`— queda con el mayor
    completo y estas vacías. Su P&L sale bien (para un escenario `imported` el
    motor lee `actual_entries`), pero **la plantilla sale SIN esa clase**.

    Le pasaba al `FORECAST Working 2026`: 279 filas de mayor, y la plantilla
    salía con $1,55M de opex y nada más — $9,1M de ingreso, costo, planilla y
    below-GOP escondidos. El owner la baja, corrige una celda y la vuelve a
    subir; el reemplazo se lleva por delante lo que la plantilla nunca mostró, y
    el P&L sigue cuadrando consigo mismo. Es el agujero de los $196 mil de las
    contrapartidas, por otra puerta.

    **El respaldo es POR CLASE, nunca por fila.** Si la tabla derivada trae
    aunque sea una fila, manda ella entera. Mezclar las dos fuentes duplicaría:
    el Spa vive en el `0130` en el mayor y en el `0140` en `opex_entries`, así
    que la misma plata entraría dos veces con dos departamentos distintos.

    Las contrapartidas de allocation quedan fuera del respaldo, igual que las
    excluye el parser: las genera el sistema y no se digitan.
    """
    if derivadas:
        return list(derivadas)
    from app.importers.gl_detail_importer import es_contrapartida_de_allocation
    return [e for e in gl_rows
            if str(e.account_code or "").startswith(clase)
            and not es_contrapartida_de_allocation(e.account_code, e.account_name)]


@router.get("/scenarios/{scenario_id}/export-detail/")
async def export_scenario_detail(
    scenario_id: str,
    month: int = Query(0, description="0 = año completo (12 meses); 1..12 = solo ese mes"),
    db: AsyncSession = Depends(get_db),
):
    """Genera la plantilla de Detalle de una versión (escenario), con los meses
    elegidos (todo el año o solo el mes cerrado), desde los datos del sistema. El
    owner la baja, edita solo las filas que necesita y la vuelve a subir a esa versión."""
    from starlette.responses import Response
    from app.export.detail_excel import build_detail_workbook, CLASE_BY_PREFIX
    from app.models.mapping import AccountMapping
    from app.importers.gl_detail_importer import es_contrapartida_de_allocation
    from app.models.department_catalog import DepartmentCatalog
    from app.engine.pl_engine import (
        consolidate_dept, group_for_dept, payroll_account_for_column)
    from app.engine.recalculate import PAYROLL_ALL_COLS

    scen = (await db.execute(select(Scenario).where(Scenario.id == scenario_id))).scalar_one_or_none()
    if scen is None:
        raise ErrorApi(404, "escenario.no_encontrado")
    months = list(range(1, 13)) if not month else [month]
    label = f"{scen.type.title()} {scen.version} {scen.year}"
    dept_names = {d.dept_code: d.dept_name for d in
                  (await db.execute(select(DepartmentCatalog))).scalars().all()}
    # El orden en que el owner subio cada fila (mig 111). La plantilla se
    # devuelve EN ESE ORDEN; lo que no lo tenga cae al orden por grupo del P&L.
    # Se lee de `ActualEntry` porque es la unica tabla que lo guarda — las cuatro
    # que se recorren abajo son derivadas de ella.
    orden_por_cuenta: dict[tuple, int] = {}
    gl_rows = (await db.execute(select(ActualEntry).where(
        ActualEntry.scenario_id == scenario_id))).scalars().all()
    for e in gl_rows:
        if e.orden_archivo is None:
            continue
        k = (e.dept_code, e.account_code)
        previo = orden_por_cuenta.get(k)
        if previo is None or e.orden_archivo < previo:
            orden_por_cuenta[k] = e.orden_archivo

    # A que linea del P&L va cada cuenta, con el MISMO resolvedor que el motor.
    # Se muestra en la plantilla en vez del «grupo», que para un departamento sin
    # grupo caia por descarte a OTHER_OVERHEAD y rotulaba de overhead a un
    # departamento de ingreso (Miscelaneos).
    from app.engine.pl_engine import construir_resolvedor
    from app.engine.recalculate import load_active_account_mappings
    _resolver = construir_resolvedor(await load_active_account_mappings(db))

    def _linea_pl(dept, code) -> str:
        m, como = _resolver(dept or "", str(code))
        if not m:
            return "(sin regla)"
        linea = m.get("report_line_code", "")
        # FALLBACK = la regla se encontro por descarte, no por departamento. Se
        # marca porque es inestable: depende del orden fisico de las filas.
        return f"{linea} ⚠" if como == "FALLBACK" else linea

    # QUE CUENTAS declaro el owner para cada departamento, segun su archivo.
    #
    # ⚠️ Un departamento LISTADO recibe SUS cuentas, no todas las del mapeo.
    #
    # Owner (2026-08-18): «Departamento 0210 Utilities solo tiene sus cuentas
    # especificas. Hay basura, cuentas que no aplican para el departamento».
    # Tenia razon: Utilities salia con 19 cuentas de opex cuando su lista tiene
    # 8 — se le colaban Training, Travel, Entertainment, Equipment Rental…
    #
    # Antes el filtro era por CLASE («todas las de opex»), interpretando un
    # pedido anterior de que «vinieran todas las cuentas». Ese pedido era sobre
    # la PLANILLA, que salia al 16%; la lista del owner ya trae los 16 conceptos
    # completos, asi que filtrar por cuenta no lo desatiende y si saca la basura.
    #
    # Un departamento que NO esta en su archivo no tiene lista que respetar y
    # entra todo, como antes.
    from app.export.detail_excel import orden_canonico
    cuentas_listadas = {(d, str(c)) for d, c in orden_canonico()}
    deptos_listados = {d for d, _c in cuentas_listadas}
    accts: dict[tuple, dict] = {}

    def _add(dept, code, name, val_by_month):
        cls = CLASE_BY_PREFIX.get(str(code)[:1])
        if not cls:
            return
        # ⚠️ UN DEPARTAMENTO HIJO NO ES UN LUGAR DONDE DIGITAR.
        #
        # Owner (2026-08-18): «En Administración 0180 es el único que existe
        # como departamento madre, todos los hijos se consolidan acá; veo 0184
        # y este no debe estar. Tampoco spa, debe estar con la madre y no solo
        # como está ahorita 0130».
        #
        # Tenía razón y la plantilla se contradecía sola: el catálogo ya declara
        # 0184→0180, 0130→0140 y 0181→0180, y el motor consolida por ahí. La
        # plantilla igual ofrecía una fila por hijo, así que se digitaba en un
        # lugar y el P&L lo sumaba en otro.
        #
        # Se PLIEGA, no se descarta: lo que el hijo traiga se acumula en la fila
        # de la madre. Descartarlo perdería el dato al volver a subir el mes.
        dept = consolidate_dept(dept)
        # El credito del asiento con que Cafeteria y Lavanderia reparten su
        # costo. Es clase 4 y no es ingreso; en el archivo del owner va en su
        # propio bloque, al final del departamento.
        if es_contrapartida_de_allocation(code, name):
            cls = "Distribucion"
        key = (dept, code)
        a = accts.get(key)
        if a is None:
            a = {"clase": cls, "grupo": group_for_dept(dept), "dept_code": dept,
                 "cuenta": code, "nombre": name or "", "vals": {},
                 "orden": orden_por_cuenta.get(key),
                 "linea_pl": _linea_pl(dept, code)}
            accts[key] = a
        elif name and not a["nombre"]:
            a["nombre"] = name
        for m in months:
            v = float(val_by_month(m) or 0)
            if v:
                a["vals"][(label, m)] = a["vals"].get((label, m), 0.0) + v

    # TODAS las cuentas del mapeo, aunque no tengan movimiento.
    #
    # Owner (2026-08-14): «no muestra el 100% de las cuentas de salario […]
    # ademas que vengan todas las cuentas». La plantilla solo traia las cuentas
    # CON dato: de las 426 combinaciones de planilla salian 68, o sea el 16%. Y
    # una cuenta que no aparece es una cuenta donde no se puede escribir — la
    # plantilla existe justamente para digitar lo que todavia no esta.
    #
    # Se siembran en cero primero; el dato real las pisa mas abajo.
    for m in (await db.execute(select(AccountMapping).where(
            AccountMapping.active_status == "YES"))).scalars().all():
        if not m.dept_code:
            continue
        # ⚠️ Las cuentas de DISTRIBUCION no van en una plantilla para digitar.
        #
        # Owner (2026-08-14), viendo el 4999 en Transportation, Utilities y
        # varios mas: «por que esto aparece en este departamento».
        #
        # Aparecian porque el mapeo SI las tiene en 23 departamentos — y esa
        # regla es correcta y load-bearing: es donde el motor de allocations
        # deposita el credito de reparto de cada departamento (en Budget Working
        # 2027, −92.176,74 en Rooms). Desactivarlas mandaba esa plata a la linea
        # equivocada; se probo y se revirtio.
        #
        # SI VAN cuando el owner las listo — y es seguro.
        #
        # Owner (2026-08-18): «no quedo la cuenta de allocation en lavanderia
        # […] recuerda que laundry 0161 y cafeteria 0220 deben quedar en 0 al
        # final de mes». Necesita VERLAS para comprobar que el departamento
        # netea; sin ellas la seccion no cierra y no hay como saberlo.
        #
        # No hay riesgo de contar el reparto dos veces: al SUBIR, el parser las
        # salta (`es_contrapartida_de_allocation` en `gl_detail_importer`) y el
        # reemplazo las protege de quedar en cero. Lo que se escriba ahi se
        # ignora; lo que ya estaba, sobrevive. Son informativas.
        #
        # En un departamento que el owner NO listo se siguen sin ofrecer.
        if (es_contrapartida_de_allocation(m.account_code, m.account_name_example)
                and m.dept_code not in deptos_listados):
            continue
        # ⚠️ NO se le inventan CLASES a un departamento.
        #
        # Owner (2026-08-14): «Utilities no tiene planilla, solo Opex, de donde
        # sacaste eso». Tenia razon y lo puse yo: al sembrar todas las cuentas
        # del mapeo aparecio una seccion PLANILLA en Utilities, que no tiene
        # personal. El mapeo tiene reglas 6xxx para casi todo departamento
        # «por si acaso»; su estructura no.
        #
        # «Todas las cuentas» significa todas las de las clases que el
        # departamento SI tiene —Utilities recibe todas las de opex, no solo las
        # que el owner listo—, no clases nuevas. Para un departamento que no esta
        # en su archivo no hay estructura que respetar y entra todo.
        if m.dept_code in deptos_listados and                 (m.dept_code, str(m.account_code)) not in cuentas_listadas:
            continue
        _add(m.dept_code, str(m.account_code), m.account_name_example or "",
             lambda _mes: 0)

    # Si una clase NO tiene filas derivadas, se lee del MAYOR — ver
    # `filas_de_la_clase`, que es donde está escrito por qué.
    for Model, clase in ((RevenueAccountEntry, "4"), (CostEntry, "5"),
                         (OpexEntry, "7"), (BelowGopAccountEntry, "8")):
        derivadas = (await db.execute(select(Model).where(
            Model.scenario_id == scenario_id))).scalars().all()
        for e in filas_de_la_clase(derivadas, gl_rows, clase):
            _add(e.dept_code, e.account_code, getattr(e, "account_name", ""), e.get_month)
    # planilla: expandir conceptos a cuentas 6xxx
    conceptos = (await db.execute(select(PayrollConceptEntry).where(
        PayrollConceptEntry.scenario_id == scenario_id,
        PayrollConceptEntry.month.in_(months)))).scalars().all()
    if not conceptos:
        # Mismo respaldo: la planilla del GL vive en posiciones sintéticas que
        # también escribe solo `import-gl-detail`. Sin ellas la sección PLANILLA
        # salía en cero teniendo el mayor sus cuentas 6xxx.
        for e in filas_de_la_clase([], gl_rows, "6"):
            _add(e.dept_code, e.account_code,
                 _PAYROLL_NAMES.get(str(e.account_code), e.account_name or ""),
                 e.get_month)
    for e in conceptos:
        for col in PAYROLL_ALL_COLS:
            amt = getattr(e, col, None) or Decimal("0")
            if amt:
                code = payroll_account_for_column(col)
                if code:
                    key = (e.dept_code, code)
                    a = accts.get(key)
                    if a is None:
                        a = {"clase": "Payroll", "grupo": group_for_dept(e.dept_code),
                             "dept_code": e.dept_code, "cuenta": code,
                             "nombre": _PAYROLL_NAMES.get(code, ""), "vals": {},
                             "orden": orden_por_cuenta.get(key),
                             "linea_pl": _linea_pl(e.dept_code, code)}
                        accts[key] = a
                    a["vals"][(label, e.month)] = a["vals"].get((label, e.month), 0.0) + float(amt)
    stats: dict[tuple, dict] = {}
    for s in (await db.execute(select(ScenarioStat).where(ScenarioStat.scenario_id == scenario_id))).scalars().all():
        if s.month in months:
            stats[(label, s.month)] = {"rooms_available": s.rooms_available,
                                       "rooms_occupied": s.rooms_occupied, "guests": s.guests}

    # ── La verificación viaja en la BAJADA también ───────────────────────────
    #
    # Norma del owner: bajo, corrijo, subo. Si el bloque de control solo
    # existiera en la subida, habría que escribirlo de memoria cada vez — y un
    # control que hay que teclear a mano es un control que nadie llena. Bajando
    # con los totales que hoy reporta el sistema, el viaje redondo se valida
    # solo: si al volver a subir cambiaron, el archivo lo dice.
    #
    # ⚠️ Para un FORECAST los meses cerrados salen en BLANCO a propósito: esos
    # meses el reporte los toma del Actual enlazado, no de este archivo, así que
    # controlarlos acá mediría algo que el reporte no usa.
    from app.importers.verificacion import CONTROLES, meses_comparables
    from app.engine.recalculate import compute_pl_month
    comparables, _cerrados = meses_comparables(scen.type, getattr(scen, "actuals_through", 0))
    verif: dict[str, dict] = {}
    for m in months:
        if m not in comparables:
            continue
        try:
            lineas_pl = {L.line_code: L.amount_usd for L in await compute_pl_month(db, scen, m)}
        except Exception:
            # Que el P&L de un mes no se pueda computar no puede tumbar la
            # descarga de la plantilla: el bloque sale en blanco y se digita.
            continue
        for ctrl in CONTROLES:
            v = lineas_pl.get(ctrl.line_code)
            if v is not None:
                verif.setdefault(ctrl.codigo, {})[m] = v

    xls = build_detail_workbook([label], list(accts.values()), stats, dept_names,
                                verificacion={label: verif})
    scope = f"m{month:02d}" if month else "full"
    fn = f"{hotel_slug()}_Detalle_{scen.type}_{scen.version}_{scen.year}_{scope}.xlsx".replace(" ", "-")
    return Response(content=xls,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{fn}"'})
