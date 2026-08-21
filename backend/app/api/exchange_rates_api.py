"""
API de tipos de cambio por escenario.

Endpoints:
  GET  /api/scenarios/{id}/exchange-rates/            los 12 TCs del escenario
  PUT  /api/scenarios/{id}/exchange-rates/{month}/    actualizar TC de un mes
  PUT  /api/scenarios/{id}/exchange-rates/            actualizar todos de una vez
"""
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.errores import ErrorApi
from app.db import get_db
from app.models.scenario import Scenario
from app.models.exchange_rate import ExchangeRate, get_tc_for_month

router = APIRouter()


class TCUpdate(BaseModel):
    tc_crc_usd: Decimal
    notes: str = ""


class TCBulkUpdate(BaseModel):
    tc_by_month: dict[str, Decimal]   # {"1": 530, "2": 530, ..., "12": 545}
    notes: str = ""


@router.get("/scenarios/{scenario_id}/exchange-rates/")
async def get_exchange_rates(scenario_id: str, db: AsyncSession = Depends(get_db)):
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")

    result = await db.execute(
        select(ExchangeRate)
        .where(ExchangeRate.scenario_id == scenario_id)
        .order_by(ExchangeRate.month)
    )
    rates = result.scalars().all()

    # Mostrar los 12 meses con su TC efectivo (aplicando fallback)
    months = []
    for month in range(1, 13):
        try:
            tc = get_tc_for_month(rates, month)
        except ValueError:
            tc = None
        exact = next((r for r in rates if r.month == month), None)
        months.append({
            "month": month,
            "tc_crc_usd": str(tc) if tc else None,
            "is_explicit": exact is not None,
            "notes": exact.notes if exact else "",
        })

    return {
        "scenario_id": scenario_id,
        "scenario_type": scenario.type,
        "year": scenario.year,
        "months": months,
    }


@router.put("/scenarios/{scenario_id}/exchange-rates/{month}/")
async def update_exchange_rate(
    scenario_id: str,
    month: int,
    payload: TCUpdate,
    db: AsyncSession = Depends(get_db),
):
    if not 1 <= month <= 12:
        raise ErrorApi(422, "mes.fuera_de_rango")

    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    result = await db.execute(
        select(ExchangeRate).where(
            ExchangeRate.scenario_id == scenario_id,
            ExchangeRate.month == month,
        )
    )
    rate = result.scalar_one_or_none()
    if rate:
        rate.tc_crc_usd = payload.tc_crc_usd
        rate.notes = payload.notes
    else:
        import uuid
        db.add(ExchangeRate(
            id=str(uuid.uuid4()),
            scenario_id=scenario_id,
            hotel_id=scenario.hotel_id,
            month=month,
            year=scenario.year,
            tc_crc_usd=payload.tc_crc_usd,
            notes=payload.notes,
        ))

    await db.commit()
    return {"scenario_id": scenario_id, "month": month, "tc_crc_usd": str(payload.tc_crc_usd)}


@router.put("/scenarios/{scenario_id}/exchange-rates/")
async def update_all_exchange_rates(
    scenario_id: str,
    payload: TCBulkUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Actualiza múltiples meses de una vez."""
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise ErrorApi(404, "escenario.no_encontrado")
    try:
        scenario.assert_editable()
    except Exception as e:
        raise HTTPException(status_code=409, detail=str(e))

    result = await db.execute(
        select(ExchangeRate).where(ExchangeRate.scenario_id == scenario_id)
    )
    existing = {r.month: r for r in result.scalars().all()}

    import uuid
    updated = []
    for month_str, tc in payload.tc_by_month.items():
        month = int(month_str)
        if not 1 <= month <= 12:
            continue
        if month in existing:
            existing[month].tc_crc_usd = tc
            existing[month].notes = payload.notes
        else:
            db.add(ExchangeRate(
                id=str(uuid.uuid4()),
                scenario_id=scenario_id,
                hotel_id=scenario.hotel_id,
                month=month,
                year=scenario.year,
                tc_crc_usd=tc,
                notes=payload.notes,
            ))
        updated.append(month)

    await db.commit()
    return {"scenario_id": scenario_id, "updated_months": sorted(updated)}
