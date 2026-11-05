# -*- coding: utf-8 -*-
"""API del Deposit Ledger.

    POST   /api/deposits/preview                  qué trae el XML (no guarda)
    POST   /api/deposits/upload                   guarda un corte
    GET    /api/deposits/loads                    los cortes subidos
    DELETE /api/deposits/loads/{id}
    GET    /api/deposits/ledger?load_id=          el reporte tal cual
    GET    /api/deposits/analisis?load_id=        todos los análisis
    GET    /api/deposits/rango?desde=&hasta=      los de un rango de llegadas
    GET    /api/deposits/por-cobrar?week=&iva=    OTB + IVA − depósitos = saldo
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

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.engine import deposits as motor
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID
from app.importers import deposit_xml as dx
from app.importers.registro_dep import registro_de_subida
from app.models.deposit import DepositEntry, DepositLoad
from app.models.on_the_books import OnTheBooksEntry

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


def _fecha_valida(valor: str | None, campo: str) -> str | None:
    """Una fecha ISO, o nada. Cualquier otra cosa se rechaza en la puerta.

    `en_rango` compara las fechas como texto —en ISO eso da el orden correcto—,
    así que dejar entrar `20-12-26` no daría error: devolvería la ventana
    equivocada sin que nada avise.
    """
    v = (valor or "").strip()
    if not v:
        return None
    try:
        date.fromisoformat(v)
    except ValueError:
        raise ErrorApi(422, "deposits.fecha_invalida", campo=campo, valor=v) from None
    return v


@router.get("/deposits/rango")
async def rango(
    desde: str | None = Query(None),
    hasta: str | None = Query(None),
    load_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Los depósitos cuya LLEGADA cae entre dos fechas, con sus análisis.

    Owner, 2026-11-05: *«necesito poder buscar los deposits por rango de fecha
    de arrival… del 20 de diciembre al 31 de diciembre»*. Los dos extremos
    entran.
    """
    d = _fecha_valida(desde, "desde")
    h = _fecha_valida(hasta, "hasta")
    if d and h and d > h:
        raise ErrorApi(422, "deposits.rango_al_reves", desde=d, hasta=h)
    c = await _resolver(db, load_id)
    filas = await _filas_de(db, c.id)
    return {"corte": _carga_publica(c), **motor.rango(filas, d, h, c.as_of)}


@router.get("/deposits/por-cobrar")
async def por_cobrar(
    week: int | None = Query(None, ge=1, le=53),
    iva: float = Query(motor.IVA_RATE, ge=0, le=1),
    load_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Lo que falta por cobrar de lo que ya está vendido, mes a mes.

    Owner, 2026-11-05: *«on the books no tiene impuestos. entonces on the books
    total revenue más el 13% menos los depósitos recibidos es el saldo por
    cobrar del mes»*. Y: *«debe tomar el reporte más reciente»*.

    ⚠️ **«El más reciente» es el `week` mayor, porque es lo único que hay.**
    `on_the_books_entries` guarda la semana ISO del corte y ninguna fecha
    propia, así que un corte tomado en enero de 2027 tendría `week=2` y
    quedaría *detrás* del de la semana 45 de 2026. Mientras los cortes sean
    del mismo año calendario esto es correcto —y es lo mismo que hace la
    pantalla de On the Books—, pero el primer corte del año que viene lo
    rompe. La semana elegida viaja en la respuesta para que se vea cuál se
    usó, y `week` deja elegirla a mano.
    """
    ultima = (await db.execute(
        select(func.max(OnTheBooksEntry.week))
        .where(OnTheBooksEntry.hotel_id == HOTEL_ID))).scalar()
    w = week or ultima
    if not w:
        raise ErrorApi(404, "deposits.sin_otb")

    filas_otb = (await db.execute(
        select(OnTheBooksEntry).where(OnTheBooksEntry.hotel_id == HOTEL_ID,
                                      OnTheBooksEntry.week == w))).scalars().all()
    otb = {(e.year, e.month): {"total": float(e.total_revenue or 0),
                               "rooms": float(e.rooms_revenue or 0),
                               "noches": float(e.rooms_occupied or 0)}
           for e in filas_otb}

    c = await _resolver(db, load_id)
    filas = await _filas_de(db, c.id)
    return {"corte": _carga_publica(c), "otb_week": w,
            "otb_week_es_la_ultima": w == ultima,
            "otb_weeks": sorted({int(x) for x in (await db.execute(
                select(OnTheBooksEntry.week)
                .where(OnTheBooksEntry.hotel_id == HOTEL_ID).distinct())).scalars().all()}),
            **motor.por_cobrar(otb, filas, iva, c.as_of)}


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
