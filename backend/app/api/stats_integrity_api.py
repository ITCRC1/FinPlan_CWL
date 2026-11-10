# -*- coding: utf-8 -*-
"""Master Data → Estadísticas → «Stats»: las estadísticas de Integrity al mes.

Owner, 2026-11-10: *«puedes ponerla en otro sub tab para no mezclar»* · *«la
contabilidad manda»* · *«solo full month»*.

Lee el Balance de Comprobación guardado (`mayor_movimientos`, el que se sube en
la Auditoría del mayor), toma las cuentas clase 9, suma los días de cada una y
las cruza con el catálogo homologado (`seed_data/stats_integrity_<HOTEL>.json`).
No escribe nada y no hay otra puerta de carga: el dato es el de contabilidad.
Ver `app/engine/stats_integrity.py`.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.engine import stats_integrity as si
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID
from app.models.mayor_movimiento import MayorMovimiento

router = APIRouter()


@router.get("/stats-integrity/catalogo/")
async def catalogo(_=Depends(get_current_user)):
    """El catálogo homologado, sin valores."""
    cat = si.leer_catalogo(HOTEL_ID)
    return {"hotel": cat.get("hotel", HOTEL_ID), "version": cat.get("version", ""),
            "grupos": cat.get("grupos", {}), "cuentas": cat.get("cuentas", [])}


@router.get("/stats-integrity/{anio}/")
async def valores(anio: int, db: AsyncSession = Depends(get_db),
                  _=Depends(get_current_user)):
    """El año: cada cuenta del catálogo con sus 12 meses (suma de los días), los
    totales por grupo, los meses que tienen balanza guardada y lo que Integrity
    registró fuera del catálogo."""
    if not 2000 <= anio <= 2100:
        raise ErrorApi(422, "stats_integrity.anio_invalido", anio=anio)
    cat = si.leer_catalogo(HOTEL_ID)
    filas = (await db.execute(
        select(MayorMovimiento.mes, MayorMovimiento.cuenta,
               MayorMovimiento.debito, MayorMovimiento.credito)
        .where(MayorMovimiento.hotel_id == HOTEL_ID, MayorMovimiento.anio == anio,
               MayorMovimiento.seg1.like("9%")))).all()
    meses = (await db.execute(
        select(distinct(MayorMovimiento.mes))
        .where(MayorMovimiento.hotel_id == HOTEL_ID, MayorMovimiento.anio == anio))).scalars().all()
    vista = si.armar_vista(cat, si.agregar(filas), meses)
    vista["anio"] = anio
    vista["hotel"] = HOTEL_ID
    return vista
