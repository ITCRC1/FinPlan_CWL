"""
Budget Big Picture — P&L top-down rápido.

- breakdown: separa por departamento y CLASE USALI (4 ingreso / 6 planilla /
  7 opex / 5 costo) leyendo actual_entries (nivel cuenta del snapshot), usando
  el mismo mapeo depto→grupo del P&L. Reconcilia con el OPEX combinado del P&L.
- versions: guarda los % de crecimiento por línea para retomar el ejercicio.
"""
from datetime import datetime
from fastapi import APIRouter
from sqlalchemy import select, delete
from pydantic import BaseModel
from typing import Optional

from app.errores import ErrorApi
from app.db import get_session
from app.models.actual_entry import ActualEntry
from app.models.big_picture_version import BigPictureVersion
from app.engine.pl_engine import (
    group_for_dept, OPERATING_GROUP_ORDER, OVERHEAD_GROUP_ORDER, GROUP_NAMES,
)
from app.hotel_actual import HOTEL_ID

router = APIRouter(tags=["big-picture"])
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


@router.get("/scenarios/{scenario_id}/big-picture-breakdown/")
async def big_picture_breakdown(scenario_id: str):
    """Por grupo operativo: revenue/payroll/opex/cost (full year). Por overhead:
    payroll/opex/cost. Desde actual_entries (nivel cuenta), clase = 1er dígito."""
    async with get_session() as session:
        rows = (await session.execute(
            select(ActualEntry).where(ActualEntry.scenario_id == scenario_id)
        )).scalars().all()

    # group -> class -> total anual
    agg: dict[str, dict[str, float]] = {}
    for e in rows:
        g = group_for_dept(e.dept_code or "")
        cls = str(e.account_code or "0")[0]
        yr = sum(float(getattr(e, m) or 0) for m in MONTHS)
        agg.setdefault(g, {}).setdefault(cls, 0.0)
        agg[g][cls] += yr

    def block(g: str) -> dict:
        d = agg.get(g, {})
        return {
            "group": g, "name": GROUP_NAMES.get(g, g),
            "revenue": d.get("4", 0.0), "payroll": d.get("6", 0.0),
            "opex": d.get("7", 0.0), "cost": d.get("5", 0.0),
        }

    def has(g: str) -> bool:
        d = agg.get(g, {})
        return any(abs(d.get(c, 0.0)) > 0.5 for c in ("4", "5", "6", "7"))

    operating = [block(g) for g in OPERATING_GROUP_ORDER if has(g)]
    overhead = [block(g) for g in OVERHEAD_GROUP_ORDER if has(g)]
    return {"scenario_id": scenario_id, "operating": operating, "overhead": overhead}


# ─── Versiones guardadas ──────────────────────────────────────────────────────

class BigPictureVersionBody(BaseModel):
    id: Optional[str] = None
    name: str
    base_scenario_id: Optional[str] = None
    target_year: int = 2027
    growth: dict = {}


@router.get("/big-picture-versions/")
async def list_versions(hotel_id: str = HOTEL_ID):
    async with get_session() as session:
        rows = (await session.execute(
            select(BigPictureVersion).where(BigPictureVersion.hotel_id == hotel_id)
            .order_by(BigPictureVersion.updated_at.desc())
        )).scalars().all()
        return [{"id": r.id, "name": r.name, "base_scenario_id": r.base_scenario_id,
                 "target_year": r.target_year, "updated_at": r.updated_at.isoformat() if r.updated_at else None}
                for r in rows]


@router.get("/big-picture-versions/{version_id}/")
async def get_version(version_id: str):
    async with get_session() as session:
        r = await session.get(BigPictureVersion, version_id)
        if not r:
            raise ErrorApi(404, "version.no_encontrada")
        return {"id": r.id, "name": r.name, "base_scenario_id": r.base_scenario_id,
                "target_year": r.target_year, "growth": r.growth or {}}


@router.post("/big-picture-versions/")
async def save_version(body: BigPictureVersionBody, hotel_id: str = HOTEL_ID):
    async with get_session() as session:
        r = await session.get(BigPictureVersion, body.id) if body.id else None
        if r:
            r.name = body.name
            r.base_scenario_id = body.base_scenario_id
            r.target_year = body.target_year
            r.growth = body.growth
            r.updated_at = datetime.utcnow()
        else:
            r = BigPictureVersion(
                hotel_id=hotel_id, name=body.name, base_scenario_id=body.base_scenario_id,
                target_year=body.target_year, growth=body.growth,
            )
            session.add(r)
        await session.commit()
        await session.refresh(r)
        return {"id": r.id, "name": r.name}


@router.delete("/big-picture-versions/{version_id}/")
async def delete_version(version_id: str):
    async with get_session() as session:
        await session.execute(delete(BigPictureVersion).where(BigPictureVersion.id == version_id))
        await session.commit()
    return {"ok": True}
