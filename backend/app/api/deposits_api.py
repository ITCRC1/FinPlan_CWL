# -*- coding: utf-8 -*-
"""API del Deposit Ledger.

    POST   /api/deposits/preview                  qué trae el XML (no guarda)
    POST   /api/deposits/upload                   guarda un corte
    GET    /api/deposits/loads                    los cortes subidos
    DELETE /api/deposits/loads/{id}
    GET    /api/deposits/ledger?load_id=          el reporte tal cual
    GET    /api/deposits/analisis?load_id=        todos los análisis
    GET    /api/deposits/comparar?antes=&despues= qué entró y qué salió

⚠️ **Nada lleva `{scenario_id}`.** El ledger es un hecho de Opera, llave el
HOTEL — igual que el pacing y el On the Books. El candado de escenarios no
tiene nada que frenar acá.

⚠️ **Subir el mismo corte dos veces lo reemplaza, no lo duplica.** La llave es
`(hotel_id, as_of)`: un ledger del 4 de noviembre es *el* ledger del 4 de
noviembre. Si se permitieran dos, la comparación tendría que preguntar cuál de
los dos, y el owner solo quiere elegir entre fechas.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.engine import deposits as motor
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID
from app.importers import deposit_xml as dx
from app.importers.registro_dep import registro_de_subida
from app.models.deposit import DepositEntry, DepositLoad

router = APIRouter(tags=["deposits"])

_CAMPOS = ("resv_name_id", "confirmation_no", "name", "sname", "room", "arrival",
           "departure", "last_date", "resv_status", "guarantee_code",
           "external_reference", "nights")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _carga_publica(c: DepositLoad) -> dict:
    return {"id": c.id, "as_of": c.as_of, "file_name": c.file_name,
            "cuenta": c.cuenta, "total_amt": float(c.total_amt or 0),
            "min_arrival": c.min_arrival, "max_arrival": c.max_arrival,
            "nota": c.nota,
            "uploaded_at": c.uploaded_at.isoformat() if c.uploaded_at else None,
            "uploaded_by": c.uploaded_by}


def _fila(e: DepositEntry) -> dict:
    d = {k: getattr(e, k) for k in _CAMPOS}
    d["total_paid_amt"] = float(e.total_paid_amt or 0)   # negativo, como el XML
    return d


async def _filas_de(db: AsyncSession, load_id: str) -> list[dict]:
    rows = (await db.execute(
        select(DepositEntry)
        .where(DepositEntry.hotel_id == HOTEL_ID, DepositEntry.load_id == load_id)
        .order_by(DepositEntry.arrival, DepositEntry.name))).scalars().all()
    return [_fila(e) for e in rows]


async def _carga(db: AsyncSession, load_id: str) -> DepositLoad:
    c = await db.get(DepositLoad, load_id)
    if c is None or c.hotel_id != HOTEL_ID:
        raise ErrorApi(404, "deposits.corte_no_existe", detalle=load_id)
    return c


async def _ultima(db: AsyncSession) -> DepositLoad | None:
    return (await db.execute(
        select(DepositLoad).where(DepositLoad.hotel_id == HOTEL_ID)
        .order_by(DepositLoad.as_of.desc(), DepositLoad.uploaded_at.desc())
        .limit(1))).scalar_one_or_none()


async def _resolver(db: AsyncSession, load_id: str | None) -> DepositLoad:
    c = await _carga(db, load_id) if load_id else await _ultima(db)
    if c is None:
        raise ErrorApi(404, "deposits.sin_cortes")
    return c


# ───────────────────────────────── subida ───────────────────────────────────
@router.post("/deposits/preview")
async def preview(file: UploadFile = File(...)):
    """Qué trae el archivo, sin guardar nada."""
    crudo = await file.read()
    try:
        filas = dx.leer(crudo)
    except dx.XmlNoEsDepositLedger as e:
        raise ErrorApi(422, "deposits.xml_no_reconocido", detalle=str(e)) from e
    return {"file_name": file.filename, **dx.resumen(filas),
            "muestra": filas[:5]}


@router.post("/deposits/upload", dependencies=[Depends(registro_de_subida)])
async def upload(
    file: UploadFile = File(...),
    as_of: str | None = Form(None),
    nota: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    """Guarda un corte entero. Si ya existe uno con esa fecha, lo reemplaza."""
    crudo = await file.read()
    try:
        filas = dx.leer(crudo)
    except dx.XmlNoEsDepositLedger as e:
        raise ErrorApi(422, "deposits.xml_no_reconocido", detalle=str(e)) from e

    res = dx.resumen(filas)
    corte = (as_of or "").strip() or res["as_of"]
    if not corte:
        raise ErrorApi(422, "deposits.sin_fecha_de_corte",
                       detalle="el archivo no trae LAST_DATE; indique la fecha")

    previo = (await db.execute(
        select(DepositLoad).where(DepositLoad.hotel_id == HOTEL_ID,
                                  DepositLoad.as_of == corte))).scalar_one_or_none()
    reemplazo = previo is not None
    if previo is not None:
        await db.execute(delete(DepositEntry).where(DepositEntry.load_id == previo.id))
        carga = previo
    else:
        carga = DepositLoad(hotel_id=HOTEL_ID, as_of=corte)
        db.add(carga)
        await db.flush()

    carga.file_name = file.filename
    carga.cuenta = res["cuenta"]
    carga.total_amt = res["total_amt"]
    carga.min_arrival = res["min_arrival"]
    carga.max_arrival = res["max_arrival"]
    carga.nota = (nota or "").strip() or None
    carga.uploaded_at = _ahora()
    carga.uploaded_by = getattr(user, "email", None)

    for f in filas:
        db.add(DepositEntry(hotel_id=HOTEL_ID, load_id=carga.id, **f))
    await db.commit()

    # Si hay un corte anterior, decir de una vez qué se movió.
    anterior = (await db.execute(
        select(DepositLoad)
        .where(DepositLoad.hotel_id == HOTEL_ID, DepositLoad.as_of < corte)
        .order_by(DepositLoad.as_of.desc()).limit(1))).scalar_one_or_none()
    cambio = None
    if anterior is not None:
        cmp = motor.comparar(await _filas_de(db, anterior.id), filas)
        cambio = {"contra": anterior.as_of,
                  "entraron": cmp["entraron"]["reservas"],
                  "salieron": cmp["salieron"]["reservas"],
                  "monto": cmp["variacion"]["monto"]}
    return {"load_id": carga.id, "as_of": corte, "reemplazo": reemplazo,
            **res, "cambio": cambio}


# ───────────────────────────────── lectura ──────────────────────────────────
@router.get("/deposits/loads")
async def loads(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(DepositLoad).where(DepositLoad.hotel_id == HOTEL_ID)
        .order_by(DepositLoad.as_of.desc()))).scalars().all()
    return {"cortes": [_carga_publica(c) for c in rows]}


@router.delete("/deposits/loads/{load_id}")
async def borrar(load_id: str, db: AsyncSession = Depends(get_db)):
    c = await _carga(db, load_id)
    await db.execute(delete(DepositEntry).where(DepositEntry.load_id == load_id))
    await db.delete(c)
    await db.commit()
    return {"ok": True, "as_of": c.as_of}


@router.get("/deposits/ledger")
async def ledger(load_id: str | None = Query(None), db: AsyncSession = Depends(get_db)):
    """El reporte tal como está en el XML: mismo signo, mismos campos."""
    c = await _resolver(db, load_id)
    filas = await _filas_de(db, c.id)
    return {"corte": _carga_publica(c), "filas": filas,
            "total_paid_amt": round(sum(f["total_paid_amt"] for f in filas), 2)}


@router.get("/deposits/analisis")
async def analisis(load_id: str | None = Query(None), db: AsyncSession = Depends(get_db)):
    """Por mes de llegada, por estado, antigüedad, vencidos y concentración."""
    c = await _resolver(db, load_id)
    filas = await _filas_de(db, c.id)
    return {"corte": _carga_publica(c), **motor.resumen_completo(filas, c.as_of)}


@router.get("/deposits/comparar")
async def comparar(
    antes: str | None = Query(None),
    despues: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Qué entró y qué salió entre dos cortes.

    Sin parámetros toma los dos más recientes, que es lo que se quiere mirar
    el 99% de las veces.
    """
    if not antes or not despues:
        ultimos = (await db.execute(
            select(DepositLoad).where(DepositLoad.hotel_id == HOTEL_ID)
            .order_by(DepositLoad.as_of.desc()).limit(2))).scalars().all()
        if len(ultimos) < 2:
            raise ErrorApi(409, "deposits.faltan_cortes",
                           detalle="hacen falta dos cortes para comparar")
        despues = despues or ultimos[0].id
        antes = antes or ultimos[1].id

    ca, cb = await _carga(db, antes), await _carga(db, despues)
    fa, fb = await _filas_de(db, ca.id), await _filas_de(db, cb.id)
    cmp = motor.comparar(fa, fb)
    return {"corte_antes": _carga_publica(ca), "corte_despues": _carga_publica(cb),
            **cmp, "cuadre": motor.cuadre(cmp)}
