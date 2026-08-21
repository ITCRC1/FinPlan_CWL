"""
Allocation API — Cafetería (0220) and Lavandería (0161) cost redistribution.

Both allocations net to $0:
  - Each participating dept receives a positive charge
  - The source dept receives an equal negative credit

Source dept total cost is:
  OPEX (opex_entries WHERE dept_code = source) +
  Payroll (payroll_concept_entries WHERE dept_code = source, sum all 17 concepts) +
  CoS (cost_entries WHERE dept_code = source, sum all months)
"""
from decimal import Decimal
from datetime import datetime
from fastapi import APIRouter
from sqlalchemy import select, delete, func
from pydantic import BaseModel
from typing import Optional

from app.errores import ErrorApi
from app.api._candado import candado
from app.db import get_session
from app.models.allocation_entry import AllocationEntry
from app.models.scenario import Scenario
from app.models.cafeteria_allocation_config import CafeteriaAllocationConfig, REMOTE_DEPTS
from app.models.laundry_allocation_config import LaundryAllocationConfig, DEFAULT_KILOS
from app.models.laundry_params import LaundryParams
from app.models.opex_entry import OpexEntry
from app.models.cost_entry import CostEntry
from app.models.payroll_position import PayrollPosition
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.salary_allocation_config import SalaryAllocationConfig
from app.models.rooms_allocation_config import RoomsAllocationConfig
from app.models.exchange_rate import ExchangeRate, get_tc_for_month
from app.models.department_catalog import DepartmentCatalog
from app.models.mapping import AccountMapping
from app.engine.allocation_calculator import (
    calculate_cafeteria_distribution,
    calculate_laundry_distribution,
    calculate_salary_distribution,
    verify_allocation_nets_zero,
)
from app.engine.payroll_calculator import calc_sw

router = APIRouter(tags=["allocations"])


def consolidar_a_la_madre(
    por_dept: dict[str, list[float]],
    padres: dict[str, str],
) -> dict[str, list[float]]:
    """Sube cada sub-departamento a su madre y suma mes a mes.

    El reparto se calcula fino —Front Desk, Reservation, Housekeeping,
    Concierge— porque ahí es donde viven los FTE. Pero el asiento contable y
    el P&L se leen por departamento madre, así que presentarlo desglosado
    obliga a sumar catorce renglones a mano para poder cuadrar contra el P&L.

    Corta ante un ciclo en el catálogo: un padre mal capturado no puede colgar
    la pantalla.
    """
    def madre(dept: str) -> str:
        visto = {dept}
        actual = dept
        while True:
            p = padres.get(actual, "")
            if not p or p in visto:
                return actual
            visto.add(p)
            actual = p

    out: dict[str, list[float]] = {}
    for dept, meses in por_dept.items():
        fila = out.setdefault(madre(dept), [0.0] * 12)
        for i, v in enumerate(meses):
            fila[i] += v
    return {d: [round(v, 4) for v in meses] for d, meses in out.items()}

MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"]

PAYROLL_ALL_COLS = [
    "c6000_sw", "c6001_overtime", "c6002_day_off", "c6003_working_holiday",
    "c6004_disabilities", "c6010_commissions", "c6020_ccss", "c6021_aguinaldo",
    "c6022_occ_hazard", "c6023_vacation_prov", "c6024_vacations_taken",
    "c6025_cafeteria", "c6026_severance", "c6027_incentive_bonus",
    "c6028_housing", "c6029_transport", "c6030_other",
]


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class CafeteriaConfigRow(BaseModel):
    dept_code: str
    dept_name: str
    participates: bool
    notes: str = ""


class LaundryConfigRow(BaseModel):
    dept_code: str
    dept_name: str
    kilos_historicos: float = 0          # legacy / promedio
    kilos_monthly: Optional[list[float]] = None   # 12 valores Ene..Dic
    participates: bool
    notes: str = ""


class LaundryParamsBody(BaseModel):
    kilos_uniformes: float = 0           # legacy / promedio
    kilos_huespedes: float = 0
    uniformes_monthly: Optional[list[float]] = None   # 12 valores
    huespedes_monthly: Optional[list[float]] = None
    account_linen: str = "7310"
    account_uniform: str = "7685"
    account_servicios: str = "5301"


def _norm12(arr: Optional[list[float]]) -> Optional[list[float]]:
    """Normaliza una lista a exactamente 12 floats (rellena/recorta)."""
    if arr is None:
        return None
    out = [float(x or 0) for x in arr[:12]]
    out += [0.0] * (12 - len(out))
    return out


def _avg12(arr: Optional[list[float]], fallback: float) -> float:
    if not arr:
        return fallback
    return sum(arr) / 12.0


class AllocationRow(BaseModel):
    target_dept: str
    amount_usd: float
    basis_value: float
    basis_type: str


class MonthAllocation(BaseModel):
    month: int
    allocation_type: str
    source_dept: str
    total_cost: float
    rows: list[AllocationRow]
    nets_to_zero: bool


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _get_dept_total_cost(session, scenario_id: str, dept_code: str, month: int) -> Decimal:
    """Sum OPEX + Payroll + CoS for a dept in a given month."""
    month_attr = MONTH_ATTRS[month - 1]
    total = Decimal("0")

    # OPEX
    res = await session.execute(
        select(OpexEntry).where(
            OpexEntry.scenario_id == scenario_id,
            OpexEntry.dept_code == dept_code,
        )
    )
    for entry in res.scalars():
        total += getattr(entry, month_attr) or Decimal("0")

    # Payroll (all 17 concepts, for this dept, in this month)
    res = await session.execute(
        select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id,
            PayrollConceptEntry.dept_code == dept_code,
            PayrollConceptEntry.month == month,
        )
    )
    for entry in res.scalars():
        for col in PAYROLL_ALL_COLS:
            total += getattr(entry, col) or Decimal("0")

    # Cost of Sales (class 5 — rarely applies but included for completeness)
    res = await session.execute(
        select(CostEntry).where(
            CostEntry.scenario_id == scenario_id,
            CostEntry.dept_code == dept_code,
        )
    )
    for entry in res.scalars():
        total += entry.get_month(month) or Decimal("0")

    return total


async def _get_fte_by_dept(session, scenario_id: str, month: int,
                            participating_depts: set[str]) -> dict[str, Decimal]:
    """Sum FTE per dept for a given month, filtered to participating depts."""
    fte_attr = f"fte_{MONTH_ATTRS[month - 1]}"
    res = await session.execute(
        select(PayrollPosition).where(PayrollPosition.scenario_id == scenario_id)
    )
    totals: dict[str, Decimal] = {}
    for pos in res.scalars():
        if pos.dept_code not in participating_depts:
            continue
        val = getattr(pos, fte_attr) or Decimal("0")
        totals[pos.dept_code] = totals.get(pos.dept_code, Decimal("0")) + val
    return totals


# ─── Cafetería config ─────────────────────────────────────────────────────────

@router.get("/allocations/cafeteria/{scenario_id}/config/")
async def get_cafeteria_config(scenario_id: str):
    async with get_session() as session:
        res = await session.execute(
            select(CafeteriaAllocationConfig).where(
                CafeteriaAllocationConfig.scenario_id == scenario_id
            ).order_by(CafeteriaAllocationConfig.dept_code)
        )
        rows = res.scalars().all()
        return [
            {
                "dept_code": r.dept_code,
                "dept_name": r.dept_name,
                "participates": r.participates,
                "notes": r.notes,
            }
            for r in rows
        ]


@router.put("/allocations/cafeteria/{scenario_id}/config/")
async def upsert_cafeteria_config(scenario_id: str, rows: list[CafeteriaConfigRow]):
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        for row in rows:
            res = await session.execute(
                select(CafeteriaAllocationConfig).where(
                    CafeteriaAllocationConfig.scenario_id == scenario_id,
                    CafeteriaAllocationConfig.dept_code == row.dept_code,
                )
            )
            existing = res.scalar_one_or_none()
            if existing:
                existing.dept_name = row.dept_name
                existing.participates = row.participates
                existing.notes = row.notes
            else:
                session.add(CafeteriaAllocationConfig(
                    scenario_id=scenario_id,
                    dept_code=row.dept_code,
                    dept_name=row.dept_name,
                    participates=row.participates,
                    notes=row.notes,
                ))
        await session.commit()
    return {"ok": True, "updated": len(rows)}


# ─── Lavandería config ────────────────────────────────────────────────────────

@router.get("/allocations/laundry/{scenario_id}/config/")
async def get_laundry_config(scenario_id: str):
    async with get_session() as session:
        res = await session.execute(
            select(LaundryAllocationConfig).where(
                LaundryAllocationConfig.scenario_id == scenario_id
            ).order_by(LaundryAllocationConfig.dept_code)
        )
        rows = res.scalars().all()
        return [
            {
                "dept_code": r.dept_code,
                "dept_name": r.dept_name,
                "kilos_historicos": float(r.kilos_historicos),
                "kilos_monthly": _norm12(r.kilos_monthly) or [float(r.kilos_historicos)] * 12,
                "participates": r.participates,
                "notes": r.notes,
            }
            for r in rows
        ]


@router.put("/allocations/laundry/{scenario_id}/config/")
async def upsert_laundry_config(scenario_id: str, rows: list[LaundryConfigRow]):
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        for row in rows:
            monthly = _norm12(row.kilos_monthly)
            # promedio mensual (legacy / fallback); si no mandan mensual usa el escalar
            hist = Decimal(str(_avg12(monthly, row.kilos_historicos)))
            res = await session.execute(
                select(LaundryAllocationConfig).where(
                    LaundryAllocationConfig.scenario_id == scenario_id,
                    LaundryAllocationConfig.dept_code == row.dept_code,
                )
            )
            existing = res.scalar_one_or_none()
            if existing:
                existing.dept_name = row.dept_name
                existing.kilos_historicos = hist
                existing.kilos_monthly = monthly
                existing.participates = row.participates
                existing.notes = row.notes
            else:
                session.add(LaundryAllocationConfig(
                    scenario_id=scenario_id,
                    dept_code=row.dept_code,
                    dept_name=row.dept_name,
                    kilos_historicos=hist,
                    kilos_monthly=monthly,
                    participates=row.participates,
                    notes=row.notes,
                ))
        await session.commit()
    return {"ok": True, "updated": len(rows)}


# ─── Lavandería params (kilos uniformes/huéspedes + cuentas) ───────────────────

async def _get_or_make_laundry_params(session, scenario_id: str) -> LaundryParams:
    res = await session.execute(
        select(LaundryParams).where(LaundryParams.scenario_id == scenario_id)
    )
    p = res.scalar_one_or_none()
    if p is None:
        p = LaundryParams(scenario_id=scenario_id)
        session.add(p)
        await session.commit()
        await session.refresh(p)
    return p


@router.get("/allocations/laundry/{scenario_id}/params/")
async def get_laundry_params(scenario_id: str):
    async with get_session() as session:
        p = await _get_or_make_laundry_params(session, scenario_id)
        return {
            "kilos_uniformes": float(p.kilos_uniformes),
            "kilos_huespedes": float(p.kilos_huespedes),
            "uniformes_monthly": _norm12(p.uniformes_monthly) or [float(p.kilos_uniformes)] * 12,
            "huespedes_monthly": _norm12(p.huespedes_monthly) or [float(p.kilos_huespedes)] * 12,
            "account_linen": p.account_linen,
            "account_uniform": p.account_uniform,
            "account_servicios": p.account_servicios,
        }


@router.put("/allocations/laundry/{scenario_id}/params/")
async def upsert_laundry_params(scenario_id: str, body: LaundryParamsBody):
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        p = await _get_or_make_laundry_params(session, scenario_id)
        uni_m = _norm12(body.uniformes_monthly)
        gst_m = _norm12(body.huespedes_monthly)
        p.uniformes_monthly = uni_m
        p.huespedes_monthly = gst_m
        p.kilos_uniformes = Decimal(str(_avg12(uni_m, body.kilos_uniformes)))
        p.kilos_huespedes = Decimal(str(_avg12(gst_m, body.kilos_huespedes)))
        p.account_linen = body.account_linen or "7310"
        p.account_uniform = body.account_uniform or "7685"
        p.account_servicios = body.account_servicios or "5301"
        await session.commit()
    return {"ok": True}


# ─── Inicializar la lista de departamentos (el checkpoint) ─────────────────────

@router.post("/allocations/{scenario_id}/init-config/")
async def init_allocation_config(scenario_id: str):
    """Pobla las configs de Cafetería y Lavandería con TODOS los departamentos de
    planilla del escenario que falten (incluye los sub-departamentos de cada área,
    p.ej. cada sub-área de Finanzas con su propio código). Idempotente: no toca los
    ya configurados. Defaults — Cafetería: participa salvo remotos (0191/0192/0200)
    y la fuente 0220; Lavandería: kilos sugeridos (DEFAULT_KILOS) o 0. El usuario
    marca/desmarca el check de cada departamento después."""
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        res = await session.execute(
            select(PayrollPosition.dept_code, PayrollPosition.dept_name)
            .where(PayrollPosition.scenario_id == scenario_id).distinct()
        )
        depts: dict[str, str] = {}
        for dc, dn in res.all():
            if dc and dc not in depts:
                depts[dc] = dn or dc

        caf_existing = {r.dept_code for r in (await session.execute(select(
            CafeteriaAllocationConfig).where(
            CafeteriaAllocationConfig.scenario_id == scenario_id))).scalars()}
        lau_existing = {r.dept_code for r in (await session.execute(select(
            LaundryAllocationConfig).where(
            LaundryAllocationConfig.scenario_id == scenario_id))).scalars()}

        added_caf = added_lau = 0
        for dc, dn in sorted(depts.items()):
            # 0220 (cafetería) no participa de su propia cafetería; 0161 (lavandería)
            # no participa de su propia lavandería — son las fuentes.
            if dc not in caf_existing and dc != "0220":
                session.add(CafeteriaAllocationConfig(
                    scenario_id=scenario_id, dept_code=dc, dept_name=dn,
                    participates=(dc not in REMOTE_DEPTS)))
                added_caf += 1
            if dc not in lau_existing and dc != "0161":
                d = DEFAULT_KILOS.get(dc)
                session.add(LaundryAllocationConfig(
                    scenario_id=scenario_id, dept_code=dc, dept_name=dn,
                    kilos_historicos=(d[1] if d else Decimal("0")),
                    participates=(d[2] if d else (dc not in REMOTE_DEPTS))))
                added_lau += 1
        await session.commit()
    return {"ok": True, "cafeteria_added": added_caf, "laundry_added": added_lau}


# ─── Calculate (regenerate) ───────────────────────────────────────────────────

@router.post("/allocations/{scenario_id}/calculate/")
async def calculate_allocations(scenario_id: str):
    """Regenera TODOS los repartos del escenario: cafetería, lavandería,
    salarios y el reparto de Rooms a sus sets.

    Delega en `_recalc_allocations`, el mismo paso que corre el recálculo
    completo. Antes este endpoint tenía su propia copia que solo sabía de
    cafetería y lavandería — pero borraba la tabla entera primero, así que
    apretar «Recalcular» en la pantalla de repartos BORRABA en silencio las
    reasignaciones de salario hasta el siguiente recálculo completo. Una sola
    implementación no puede quedarse a medias.

    ⚠️ **Respeta los meses cerrados igual que el recálculo completo.** Delegar en
    la misma función no alcanzaba: el corte es un ARGUMENTO, así que llamarla sin
    él dejaba esta pantalla borrando y refabricando los doce meses mientras el
    recálculo completo protegía. Dos caminos a la misma tabla que protegen
    distinto son un camino sin protección.
    """
    from app.engine.recalculate import _recalc_allocations
    from app.engine.meses_cerrados import meses_cerrados

    async with get_session() as session:
        scenario = await session.get(Scenario, scenario_id)
        if scenario is None:
            raise ErrorApi(404, "escenario.no_encontrado")
        scenario.assert_editable()
        avisos: list[str] = []
        cerrados = await meses_cerrados(session, scenario)
        total = await _recalc_allocations(session, scenario, avisos, cerrados)
        await session.commit()
    return {"ok": True, "total_entries": total, "avisos": avisos}


async def _calculate_allocations_legacy(scenario_id: str):
    """Copia vieja (solo cafetería + lavandería). Se conserva sin ruta para no
    perder el detalle mensual que devolvía; no la llama nadie."""
    async with get_session() as session:
        # Clear existing
        await session.execute(
            delete(AllocationEntry).where(AllocationEntry.scenario_id == scenario_id)
        )

        # Load configs
        res = await session.execute(
            select(CafeteriaAllocationConfig).where(
                CafeteriaAllocationConfig.scenario_id == scenario_id
            )
        )
        caf_configs = {r.dept_code: r for r in res.scalars()}

        res = await session.execute(
            select(LaundryAllocationConfig).where(
                LaundryAllocationConfig.scenario_id == scenario_id
            )
        )
        lau_configs = {r.dept_code: r for r in res.scalars()}

        participating_caf = {
            dc for dc, cfg in caf_configs.items() if cfg.participates
        }
        # Depts que participan en lavandería (linen por kilos / uniformes por FTE).
        participating_lau_cfgs = {dc: cfg for dc, cfg in lau_configs.items() if cfg.participates}
        participating_lau_depts = set(participating_lau_cfgs.keys())
        lau_params = await _get_or_make_laundry_params(session, scenario_id)

        new_entries: list[AllocationEntry] = []
        results = {"cafeteria": [], "laundry": []}

        for month in range(1, 13):
            # ── Cafetería ─────────────────────────────────────────────────────
            caf_cost = await _get_dept_total_cost(session, scenario_id, "0220", month)
            fte_by_dept = await _get_fte_by_dept(session, scenario_id, month, participating_caf)
            caf_rows = calculate_cafeteria_distribution(caf_cost, fte_by_dept)

            for row in caf_rows:
                new_entries.append(AllocationEntry(
                    scenario_id=scenario_id,
                    allocation_type="CAFETERIA",
                    month=month,
                    year=2026,
                    source_dept="0220",
                    target_dept=row["target_dept"],
                    amount_usd=row["amount_usd"],
                    basis_value=row["basis_value"],
                    basis_type=row["basis_type"],
                    account=row["account"],
                    calculated_at=datetime.utcnow(),
                ))
            results["cafeteria"].append({
                "month": month,
                "total_cost": float(caf_cost),
                "rows": len(caf_rows),
                "nets_zero": verify_allocation_nets_zero(caf_rows),
            })

            # ── Lavandería (3 vías: linen/uniformes/huéspedes) — kilos por mes ─
            lau_cost = await _get_dept_total_cost(session, scenario_id, "0161", month)
            uni_fte = await _get_fte_by_dept(session, scenario_id, month, participating_lau_depts)
            linen_kilos = {dc: cfg.kilos_for(month) for dc, cfg in participating_lau_cfgs.items()}
            kilos_uni = lau_params.uniformes_for(month)
            kilos_gst = lau_params.huespedes_for(month)
            lau = calculate_laundry_distribution(
                lau_cost, linen_kilos, uni_fte, kilos_uni, kilos_gst,
                acct_linen=lau_params.account_linen,
                acct_uniform=lau_params.account_uniform,
                acct_servicios=lau_params.account_servicios,
            )

            for row in lau["rows"]:
                new_entries.append(AllocationEntry(
                    scenario_id=scenario_id,
                    allocation_type="LAUNDRY",
                    month=month,
                    year=2026,
                    source_dept="0161",
                    target_dept=row["target_dept"],
                    amount_usd=row["amount_usd"],
                    basis_value=row["basis_value"],
                    basis_type=row["basis_type"],
                    account=row["account"],
                    calculated_at=datetime.utcnow(),
                ))
            results["laundry"].append({
                "month": month,
                "total_cost": float(lau_cost),
                "linen_cost": float(lau["linen_cost"]),
                "uniform_cost": float(lau["uniform_cost"]),
                "guest_cost": float(lau["guest_cost"]),
                "rows": len(lau["rows"]),
                "nets_zero": verify_allocation_nets_zero(lau["rows"]),
            })

        session.add_all(new_entries)
        await session.commit()

    return {
        "ok": True,
        "total_entries": len(new_entries),
        "monthly": results,
    }


# ─── Read results ─────────────────────────────────────────────────────────────

@router.get("/allocations/{scenario_id}/month/{month}/")
async def get_allocations_month(scenario_id: str, month: int):
    if not 1 <= month <= 12:
        raise ErrorApi(400, "mes.fuera_de_rango")
    async with get_session() as session:
        res = await session.execute(
            select(AllocationEntry).where(
                AllocationEntry.scenario_id == scenario_id,
                AllocationEntry.month == month,
            ).order_by(AllocationEntry.allocation_type, AllocationEntry.target_dept)
        )
        entries = res.scalars().all()
        return [
            {
                "id": e.id,
                "allocation_type": e.allocation_type,
                "source_dept": e.source_dept,
                "target_dept": e.target_dept,
                "amount_usd": float(e.amount_usd),
                "basis_value": float(e.basis_value),
                "basis_type": e.basis_type,
            }
            for e in entries
        ]


@router.get("/allocations/{scenario_id}/summary/")
async def get_allocations_summary(scenario_id: str):
    """
    Returns per-dept, per-month allocation totals for both types.
    Shape: { cafeteria: {dept: [m1..m12]}, laundry: {dept: [m1..m12]} }
    """
    async with get_session() as session:
        res = await session.execute(
            select(AllocationEntry).where(
                AllocationEntry.scenario_id == scenario_id,
            ).order_by(AllocationEntry.month, AllocationEntry.target_dept)
        )
        entries = res.scalars().all()

    summary: dict[str, dict[str, list[float]]] = {
        "CAFETERIA": {},
        "LAUNDRY": {},
    }
    for e in entries:
        atype = e.allocation_type
        dept = e.target_dept
        if dept not in summary[atype]:
            summary[atype][dept] = [0.0] * 12
        summary[atype][dept][e.month - 1] += float(e.amount_usd)

    return summary


@router.get("/allocations/{scenario_id}/laundry-breakdown/")
async def get_laundry_breakdown(scenario_id: str):
    """
    Detailed laundry validation: per-dept linen (7310) and uniform (7685)
    charges, the 0161 credit (4999), and the guest COGS (5301) that stays
    in 0161. The distributed part (linen + uniform) nets to $0; the guest
    portion is the residual retained by 0161.
    Shape:
      { accounts: {linen, uniform, servicios},
        linen:   {dept: [m1..m12]},   # account 7310, by kilos
        uniform: {dept: [m1..m12]},   # account 7685, by FTE
        credit:  [m1..m12],           # 0161 credit (account 4999, negative)
        guest_cogs: [m1..m12],        # moved to 0162 as COGS (account 5301)
        total_cost: [m1..m12] }       # 0161 source cost
    """
    async with get_session() as session:
        params = await _get_or_make_laundry_params(session, scenario_id)
        acct_linen, acct_uniform = params.account_linen, params.account_uniform
        acct_servicios = params.account_servicios

        res = await session.execute(
            select(AllocationEntry).where(
                AllocationEntry.scenario_id == scenario_id,
                AllocationEntry.allocation_type == "LAUNDRY",
            )
        )
        entries = res.scalars().all()

        linen: dict[str, list[float]] = {}
        uniform: dict[str, list[float]] = {}
        credit = [0.0] * 12
        guest_cogs = [0.0] * 12
        for e in entries:
            mi = e.month - 1
            if e.basis_type == "CREDIT" or e.target_dept == "0161":
                credit[mi] += float(e.amount_usd)
            elif e.account == acct_servicios:
                # guest COGS — moved to 0162 (Laundry Revenue), no longer in 0161
                guest_cogs[mi] += float(e.amount_usd)
            elif e.account == acct_uniform or e.basis_type == "FTE":
                uniform.setdefault(e.target_dept, [0.0] * 12)[mi] += float(e.amount_usd)
            else:  # linen / kilos
                linen.setdefault(e.target_dept, [0.0] * 12)[mi] += float(e.amount_usd)

        total_cost = [0.0] * 12
        for month in range(1, 13):
            total_cost[month - 1] = float(
                await _get_dept_total_cost(session, scenario_id, "0161", month)
            )

    guest_cogs = [round(g, 4) for g in guest_cogs]

    # Nombre de cada cuenta, para que el asiento se lea como asiento y no como
    # una lista de codigos. Primero las lineas del checkbook; si la cuenta no
    # tiene ninguna —la 5301 de huespedes no la tiene, nace del reparto y por
    # eso salia con un guion— se cae al catalogo de mapeo, que es donde el
    # usuario la nombra.
    codigos = [params.account_linen, params.account_uniform,
               params.account_servicios, "4999"]
    nombres: dict[str, str] = {}
    async with get_session() as session:
        for Model in (OpexEntry, CostEntry):
            for cod, nom in (await session.execute(
                select(Model.account_code, Model.account_name)
                .where(Model.account_code.in_(codigos))
                .distinct()
            )).all():
                if nom and cod not in nombres:
                    nombres[cod] = nom

        # Al caer al mapeo hay que decir de QUE departamento. La 5301 la usan
        # el Spa (0130) y la lavanderia (0162), y agarrar la primera que
        # aparezca traia «Costos Spa» a un asiento de lavanderia.
        dept_preferido = {params.account_servicios: "0162"}
        faltan = [c for c in codigos if c not in nombres]
        if faltan:
            filas = (await session.execute(
                select(AccountMapping.account_code, AccountMapping.dept_code,
                       AccountMapping.account_name_example)
                .where(AccountMapping.account_code.in_(faltan),
                       AccountMapping.active_status == "YES")
                .distinct()
            )).all()
            for cod, dept, nom in filas:
                if not nom:
                    continue
                quiero = dept_preferido.get(cod)
                if quiero and (dept or "").strip() != quiero:
                    continue          # de otro departamento: no es este gasto
                nombres.setdefault(cod, nom)
            # Si el departamento preferido no tenia nombre, cualquiera es
            # mejor que un guion.
            for cod, _dept, nom in filas:
                if nom:
                    nombres.setdefault(cod, nom)

        # El asiento se lee al nivel del departamento MADRE. El reparto se
        # calcula por sub-departamento —Front Desk, Reservation, Housekeeping,
        # Concierge— porque ahi es donde estan los FTE, pero un asiento con
        # catorce renglones de 7685 no se revisa: se salta. Consolidado quedan
        # cinco y se comparan de un vistazo contra el P&L, que ahora tambien
        # rutea por la madre.
        padres = {
            d.dept_code: (d.parent_dept_code or "").strip()
            for d in (await session.execute(select(DepartmentCatalog))).scalars().all()
            if (d.parent_dept_code or "").strip()
        }
    nombres.setdefault("4999", "Expense Distribution")

    linen = consolidar_a_la_madre(linen, padres)
    uniform = consolidar_a_la_madre(uniform, padres)

    return {
        "accounts": {
            "linen": params.account_linen,
            "uniform": params.account_uniform,
            "servicios": params.account_servicios,
        },
        "account_names": nombres,
        "linen": linen,
        "uniform": uniform,
        "credit": credit,
        "guest_cogs": guest_cogs,
        "total_cost": total_cost,
    }


# ─── Salary allocation (reasignación de salarios de deptos de apoyo) ───────────

class SalaryRuleRow(BaseModel):
    source_dept: str
    position_code: str
    position_name: str = ""
    portion_pct: float = 1.0
    cafeteria_pct: float = 0.0
    salary_override: Optional[list[float]] = None
    dummy_monthly: Optional[list[float]] = None
    target_depts: list[str] = []
    account: str = "6000"
    active: bool = True


@router.get("/allocations/salary/{scenario_id}/positions/")
async def salary_positions(scenario_id: str):
    """Posiciones de la planilla con el SALARIO (SW) por mes [12] por posición y el
    FTE por mes [12] por depto, + tasas (CCSS, aguinaldo) → el front muestra y
    calcula TODO en vivo (salario, CCSS, aguinaldo, cafetería, total, distribución)
    apenas elegís la posición, sin necesidad de guardar."""
    from app.models.payroll_params import PayrollParams
    from app.engine.payroll_calculator import CCSS_RATE, AGUINALDO_DIVISOR
    async with get_session() as session:
        pos = (await session.execute(select(PayrollPosition).where(
            PayrollPosition.scenario_id == scenario_id))).scalars().all()
        rates = (await session.execute(select(ExchangeRate).where(
            ExchangeRate.scenario_id == scenario_id))).scalars().all()
        pp = (await session.execute(select(PayrollParams).where(
            PayrollParams.scenario_id == scenario_id))).scalar_one_or_none()
        tcs = [get_tc_for_month(rates, m) for m in range(1, 13)]
        depts: dict[str, dict] = {}
        positions: dict[tuple, dict] = {}
        for p in pos:
            d = depts.setdefault(p.dept_code, {"dept_code": p.dept_code, "dept_name": p.dept_name or p.dept_code, "fte": [0.0] * 12})
            key = (p.dept_code, p.position_code)
            pr = positions.setdefault(key, {"dept_code": p.dept_code, "dept_name": p.dept_name or p.dept_code,
                                            "position_code": p.position_code, "position_name": p.position_name, "sw": [0.0] * 12})
            for m in range(1, 13):
                d["fte"][m - 1] += float(getattr(p, f"fte_{MONTH_ATTRS[m - 1]}") or 0)
                pr["sw"][m - 1] += round(float(calc_sw(p, m, tcs[m - 1])), 2)
        return {
            "depts": sorted(depts.values(), key=lambda x: x["dept_code"]),
            "positions": sorted(positions.values(), key=lambda x: (x["dept_code"], x["position_code"])),
            "ccss_rate": float(pp.ccss_rate if pp else CCSS_RATE),
            "aguinaldo_divisor": float(pp.aguinaldo_divisor if pp else AGUINALDO_DIVISOR),
        }


@router.get("/allocations/salary/{scenario_id}/config/")
async def get_salary_config(scenario_id: str):
    async with get_session() as session:
        rows = (await session.execute(select(SalaryAllocationConfig).where(
            SalaryAllocationConfig.scenario_id == scenario_id)
            .order_by(SalaryAllocationConfig.source_dept, SalaryAllocationConfig.position_code))).scalars().all()
        return [{
            "source_dept": r.source_dept, "position_code": r.position_code,
            "position_name": r.position_name, "portion_pct": float(r.portion_pct),
            "cafeteria_pct": float(getattr(r, "cafeteria_pct", 0) or 0),
            "dummy_monthly": _dummy_list(r),
            "salary_override": [float(x or 0) for x in ((getattr(r, "salary_override", None) or []) + [0] * 12)[:12]],
            "target_depts": r.target_depts or [], "account": r.account, "active": r.active,
        } for r in rows]


@router.put("/allocations/salary/{scenario_id}/config/")
async def put_salary_config(scenario_id: str, rows: list[SalaryRuleRow]):
    """Reemplaza el set de reglas de Salary Allocation del escenario."""
    async with get_session() as session:
        # Una version enllavada no se puede editar.
        await candado(session, scenario_id)
        await session.execute(delete(SalaryAllocationConfig).where(
            SalaryAllocationConfig.scenario_id == scenario_id))
        for r in rows:
            if not r.source_dept or not r.position_code:
                continue
            session.add(SalaryAllocationConfig(
                scenario_id=scenario_id, source_dept=r.source_dept, position_code=r.position_code,
                position_name=r.position_name, portion_pct=Decimal(str(r.portion_pct)),
                cafeteria_pct=Decimal(str(r.cafeteria_pct)),
                dummy_monthly=_norm12(r.dummy_monthly) or [0.0] * 12,
                salary_override=_norm12(r.salary_override) or [0.0] * 12,
                target_depts=[t for t in r.target_depts if t], account=r.account or "6000",
                active=r.active,
            ))
        await session.commit()
    return {"ok": True, "rules": len(rows)}


@router.get("/allocations/salary/{scenario_id}/preview/")
async def salary_preview(scenario_id: str, month: int = 1):
    """Preview/validación: crédito a la fuente + débitos a los destinos del mes,
    que netean $0. Para confirmar la reasignación antes de mirar el P&L."""
    if not 1 <= month <= 12:
        raise ErrorApi(400, "mes.fuera_de_rango")
    async with get_session() as session:
        cfgs = [c for c in (await session.execute(select(SalaryAllocationConfig).where(
            SalaryAllocationConfig.scenario_id == scenario_id))).scalars() if c.active]
        positions = (await session.execute(select(PayrollPosition).where(
            PayrollPosition.scenario_id == scenario_id))).scalars().all()
        rates = (await session.execute(select(ExchangeRate).where(
            ExchangeRate.scenario_id == scenario_id))).scalars().all()
        from app.models.payroll_params import PayrollParams
        from app.engine.allocation_calculator import loaded_salary_breakdown
        from app.engine.payroll_calculator import CCSS_RATE, AGUINALDO_DIVISOR
        pp = (await session.execute(select(PayrollParams).where(
            PayrollParams.scenario_id == scenario_id))).scalar_one_or_none()
        ccss_rate = pp.ccss_rate if pp else CCSS_RATE
        agu_div = pp.aguinaldo_divisor if pp else AGUINALDO_DIVISOR
        tc = get_tc_for_month(rates, month)
        fte_attr = f"fte_{MONTH_ATTRS[month - 1]}"
        out = []
        for cfg in cfgs:
            sw = sum((calc_sw(p, month, tc) for p in positions
                      if p.dept_code == cfg.source_dept and p.position_code == cfg.position_code), Decimal("0"))
            bd = loaded_salary_breakdown(sw, ccss_rate, agu_div, getattr(cfg, "cafeteria_pct", 0))
            targets = [t for t in (cfg.target_depts or []) if t]
            tgt_fte: dict = {}
            for p in positions:
                if p.dept_code in targets:
                    tgt_fte[p.dept_code] = tgt_fte.get(p.dept_code, Decimal("0")) + (getattr(p, fte_attr) or Decimal("0"))
            rows = calculate_salary_distribution(bd["total"], cfg.portion_pct, tgt_fte, cfg.source_dept, cfg.account or "6000")
            out.append({
                "source_dept": cfg.source_dept, "position_code": cfg.position_code,
                "position_name": cfg.position_name, "portion_pct": float(cfg.portion_pct),
                "cafeteria_pct": float(getattr(cfg, "cafeteria_pct", 0) or 0),
                "breakdown": {k: round(float(v), 2) for k, v in bd.items()},  # sw, ccss, aguinaldo, cafeteria, total
                "movements": [{"dept": r["target_dept"], "amount": round(float(r["amount_usd"]), 2),
                               "type": "Crédito" if r["amount_usd"] < 0 else "Débito"} for r in rows],
                "nets_zero": verify_allocation_nets_zero(rows),
            })
        return {"month": month, "rules": out}


def _dummy_list(cfg) -> list[float]:
    d = getattr(cfg, "dummy_monthly", None) or []
    return [float(d[i]) if i < len(d) and d[i] is not None else 0.0 for i in range(12)]


@router.get("/allocations/salary/{scenario_id}/calc/")
async def salary_calc(scenario_id: str):
    """Cálculo de los 12 MESES por regla: salario (SW), CCSS, aguinaldo, cafetería,
    dummy y total cargado por mes (+ total anual), y la distribución a los destinos.
    Es la tabla amigable para revisar todo de una vez."""
    from app.models.payroll_params import PayrollParams
    from app.engine.allocation_calculator import loaded_salary_breakdown
    from app.engine.payroll_calculator import CCSS_RATE, AGUINALDO_DIVISOR
    async with get_session() as session:
        cfgs = (await session.execute(select(SalaryAllocationConfig).where(
            SalaryAllocationConfig.scenario_id == scenario_id)
            .order_by(SalaryAllocationConfig.source_dept, SalaryAllocationConfig.position_code))).scalars().all()
        positions = (await session.execute(select(PayrollPosition).where(
            PayrollPosition.scenario_id == scenario_id))).scalars().all()
        rates = (await session.execute(select(ExchangeRate).where(
            ExchangeRate.scenario_id == scenario_id))).scalars().all()
        pp = (await session.execute(select(PayrollParams).where(
            PayrollParams.scenario_id == scenario_id))).scalar_one_or_none()
        ccss_rate = pp.ccss_rate if pp else CCSS_RATE
        agu_div = pp.aguinaldo_divisor if pp else AGUINALDO_DIVISOR
        out = []
        for cfg in cfgs:
            dummy = _dummy_list(cfg)
            concepts = {k: [0.0] * 12 for k in ("sw", "ccss", "aguinaldo", "cafeteria", "loaded", "reassigned")}
            targets = [t for t in (cfg.target_depts or []) if t]
            dist = {t: [0.0] * 12 for t in targets}
            nets = True
            for m in range(1, 13):
                tc = get_tc_for_month(rates, m)
                fte_attr = f"fte_{MONTH_ATTRS[m - 1]}"
                sw = sum((calc_sw(p, m, tc) for p in positions
                          if p.dept_code == cfg.source_dept and p.position_code == cfg.position_code), Decimal("0"))
                bd = loaded_salary_breakdown(sw, ccss_rate, agu_div, getattr(cfg, "cafeteria_pct", 0))
                loaded = float(bd["total"]) + dummy[m - 1]
                concepts["sw"][m - 1] = round(float(bd["sw"]), 2)
                concepts["ccss"][m - 1] = round(float(bd["ccss"]), 2)
                concepts["aguinaldo"][m - 1] = round(float(bd["aguinaldo"]), 2)
                concepts["cafeteria"][m - 1] = round(float(bd["cafeteria"]), 2)
                concepts["loaded"][m - 1] = round(loaded, 2)
                tgt_fte: dict = {}
                for p in positions:
                    if p.dept_code in targets:
                        tgt_fte[p.dept_code] = tgt_fte.get(p.dept_code, Decimal("0")) + (getattr(p, fte_attr) or Decimal("0"))
                rows = calculate_salary_distribution(Decimal(str(loaded)), cfg.portion_pct, tgt_fte, cfg.source_dept, cfg.account or "6000")
                reassigned = 0.0
                for r in rows:
                    if r["target_dept"] in dist:
                        dist[r["target_dept"]][m - 1] = round(float(r["amount_usd"]), 2)
                        reassigned += float(r["amount_usd"])
                concepts["reassigned"][m - 1] = round(reassigned, 2)
                if rows and not verify_allocation_nets_zero(rows):
                    nets = False
            out.append({
                "source_dept": cfg.source_dept, "position_code": cfg.position_code,
                "position_name": cfg.position_name, "portion_pct": float(cfg.portion_pct),
                "cafeteria_pct": float(getattr(cfg, "cafeteria_pct", 0) or 0),
                "dummy": dummy, "concepts": concepts, "targets": targets, "dist": dist,
                "totals": {k: round(sum(v), 2) for k, v in concepts.items()},
                "nets_zero": nets,
            })
        return {"rules": out}


# ─── Reparto de Rooms a sus sets (Villas / Residencias) ───────────────────────

class RoomsPctRow(BaseModel):
    dept_code: str
    pct_monthly: list[float] = []       # 12 fracciones (0.30 = 30%)
    active: bool = True


async def _rooms_base_mensual(session, scenario_id: str) -> tuple[list[float], list[float]]:
    """(base por mes, FTE por mes) de la familia Rooms — lo que se va a repartir.

    Usa EXACTAMENTE la misma base que el motor: el GL de Rooms y sus hijos de
    función más los repartos que ya cayeron ahí. Si la pantalla calculara el
    pote por su cuenta, mostraría un número y el asiento movería otro.
    """
    from app.engine.recalculate import (
        rooms_family, _rooms_base_por_cuenta,
    )

    familia, _sets = await rooms_family(session, "0110")
    opex = (await session.execute(
        select(OpexEntry).where(OpexEntry.scenario_id == scenario_id))).scalars().all()
    costs = (await session.execute(
        select(CostEntry).where(CostEntry.scenario_id == scenario_id))).scalars().all()
    payroll = (await session.execute(
        select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id))).scalars().all()
    # Los repartos ya calculados (cafetería / lavandería / salarios) cuentan;
    # los del propio reparto de Rooms NO — serían la salida entrando de vuelta.
    repartos = [e for e in (await session.execute(
        select(AllocationEntry).where(
            AllocationEntry.scenario_id == scenario_id))).scalars().all()
        if e.allocation_type != "ROOMS"]
    positions = (await session.execute(
        select(PayrollPosition).where(
            PayrollPosition.scenario_id == scenario_id))).scalars().all()

    base, fte = [], []
    for m in range(1, 13):
        por_cuenta = _rooms_base_por_cuenta(
            opex, costs, payroll, [r for r in repartos if r.month == m], familia, m)
        base.append(float(sum(por_cuenta.values())))
        attr = f"fte_{MONTH_ATTRS[m - 1]}"
        fte.append(float(sum(
            (getattr(p, attr) or Decimal("0"))
            for p in positions if p.dept_code in familia)))
    return base, fte


@router.get("/allocations/rooms/{scenario_id}/config/")
async def get_rooms_config(scenario_id: str):
    """Los % por mes y por set, más el pote que se está repartiendo.

    Devuelve una fila por set destino aunque no exista en la base: la pantalla
    abre con la tabla puesta en ceros y no hay que «crear» nada para empezar.
    """
    from app.engine.recalculate import rooms_family

    async with get_session() as session:
        scenario = await session.get(Scenario, scenario_id)
        if scenario is None:
            raise ErrorApi(404, "escenario.no_encontrado")

        _familia, sets = await rooms_family(session, "0110")
        nombres = {d.dept_code: d.dept_name for d in (await session.execute(
            select(DepartmentCatalog))).scalars()}
        cfgs = {c.dept_code: c for c in (await session.execute(
            select(RoomsAllocationConfig).where(
                RoomsAllocationConfig.scenario_id == scenario_id))).scalars()}

        base, fte = await _rooms_base_mensual(session, scenario_id)

        filas = []
        for dept in sorted(sets):
            c = cfgs.get(dept)
            pct = _norm12([float(x or 0) for x in (c.pct_monthly or [])]) if c else None
            filas.append({
                "dept_code": dept,
                "dept_name": nombres.get(dept, dept),
                "pct_monthly": pct or [0.0] * 12,
                "active": bool(c.active) if c else True,
                "monto_mensual": [round(base[m] * (pct or [0.0] * 12)[m], 2)
                                  for m in range(12)],
            })

        # Aviso por mes: repartir más del 100% no arma el asiento, así que hay
        # que decirlo ANTES de recalcular, no después de que no pase nada.
        excesos = [m + 1 for m in range(12)
                   if sum(f["pct_monthly"][m] for f in filas) > 1.0001]

        return {
            "scenario_id": scenario_id,
            "source_dept": "0110",
            "source_name": nombres.get("0110", "Rooms"),
            "rows": filas,
            "base_mensual": [round(b, 2) for b in base],
            "fte_mensual": [round(f, 4) for f in fte],
            "resto_rooms": [
                round(base[m] * (1 - sum(f["pct_monthly"][m] for f in filas)), 2)
                for m in range(12)
            ],
            "meses_pasados_de_100": excesos,
        }


@router.put("/allocations/rooms/{scenario_id}/config/")
async def put_rooms_config(scenario_id: str, rows: list[RoomsPctRow]):
    """Guarda los % por set. No recalcula: el asiento se arma con Recalcular.

    Se rechaza el mes que se pase de 100% en vez de guardarlo y dejar que el
    motor lo descarte en silencio — el owner tiene que enterarse en la pantalla
    donde escribió el número.
    """
    async with get_session() as session:
        await candado(session, scenario_id)
        scenario = await session.get(Scenario, scenario_id)
        if scenario is None:
            raise ErrorApi(404, "escenario.no_encontrado")

        for m in range(12):
            total = sum(float((r.pct_monthly or [0] * 12)[m] if m < len(r.pct_monthly or []) else 0)
                        for r in rows if r.active)
            if total > 1.0001:
                raise ErrorApi(422, "rooms.reparto_supera_100",
                               mes=m + 1, pct=f"{total * 100:.1f}")

        cfgs = {c.dept_code: c for c in (await session.execute(
            select(RoomsAllocationConfig).where(
                RoomsAllocationConfig.scenario_id == scenario_id))).scalars()}
        for r in rows:
            pct = _norm12([float(x or 0) for x in (r.pct_monthly or [])]) or [0.0] * 12
            c = cfgs.get(r.dept_code)
            if c is None:
                c = RoomsAllocationConfig(
                    scenario_id=scenario_id, hotel_id=scenario.hotel_id,
                    dept_code=r.dept_code, source_dept="0110")
                session.add(c)
            c.pct_monthly = pct
            c.active = r.active
            c.updated_at = datetime.utcnow()
        await session.commit()
    return {"ok": True, "rows": len(rows)}


@router.get("/allocations/{scenario_id}/fuente/")
async def costo_a_repartir(scenario_id: str, dept: str = "0220"):
    """El POTE que se va a repartir, abierto por clase de cuenta y por mes.

    Es lo que el reparto toma del departamento origen, con el mismo criterio que
    usa el motor (`_dept_total_cost`): costo de ventas (clase 5) + planilla
    (clase 6) + gastos operativos (clase 7). Sin esto, el owner ve el resultado
    del reparto pero no de dónde salió el monto.
    """
    from app.engine.recalculate import (
        cos_by_dept, opex_by_dept, payroll_by_dept,
    )

    from app.models.cost_entry import CostEntry
    from app.models.opex_entry import OpexEntry
    from app.models.payroll_position import PayrollPosition

    LINEAS = [
        ("5", "Costo de ventas (Food Cost)", cos_by_dept, CostEntry, "Cost of Sales"),
        ("6", "Salarios y cargas", payroll_by_dept, PayrollPosition, "Planilla"),
        ("7", "Gastos operativos (OPEX)", opex_by_dept, OpexEntry, "OPEX por Departamento"),
    ]

    async with get_session() as session:
        scenario = await session.get(Scenario, scenario_id)
        if not scenario:
            raise ErrorApi(404, "escenario.no_encontrado")

        lineas = []
        por_mes = [Decimal("0")] * 12
        for clase, nombre, fn, Model, donde in LINEAS:
            meses = []
            for m in range(1, 13):
                v = (await fn(session, scenario_id, m)).get(dept, Decimal("0"))
                meses.append(v)
                por_mes[m - 1] += v
            # Cuántas líneas existen en ese departamento. Un total en cero puede
            # ser «no hay líneas» o «hay líneas sin monto», y no es lo mismo: la
            # segunda solo necesita que alguien las llene.
            n = (await session.execute(
                select(func.count()).select_from(Model)
                .where(Model.scenario_id == scenario_id, Model.dept_code == dept)
            )).scalar_one()
            lineas.append({
                "clase": clase, "nombre": nombre,
                "meses": [float(x) for x in meses],
                "total": float(sum(meses)),
                "lineas_cargadas": int(n),
                "donde": donde,
            })

        return {
            "scenario_id": scenario_id,
            "dept_code": dept,
            "lineas": lineas,
            "totales_mes": [float(x) for x in por_mes],
            "total": float(sum(por_mes)),
        }
