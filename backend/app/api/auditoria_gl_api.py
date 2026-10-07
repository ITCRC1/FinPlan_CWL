# -*- coding: utf-8 -*-
"""Subir el detalle del mayor y recibir las discrepancias.

Owner, 2026-10-05: *«que herramienta puedes hacerme para yo solo subir el
archivo en este detalle y me salgan automaticamente la auditoria con las
discrepancias»*.

**No toca el P&L.** No hay escenario, no se arma un total, no entra plata por
aca: la del mes sigue entrando por `integrity_final` → borrador → espejo →
ACTUAL. Esto es el LIBRO, para mirarlo.

**Lo que si hace desde el 2026-10-06 es guardarlo.** Owner: *«me gustaria que
quede guardado pero cada vez que se corra se le caiga encima […] es solo para
poder revisar detalladamente a nivel de detalle»*. Un mes por hotel; subir el
mismo mes otra vez lo reemplaza. Ver `app/models/mayor_movimiento.py`.

Por eso sigue sin pasar por `registro_de_subida`: ese registro trae
anti-reimport, y volver a subir el mismo mes es justamente lo que se quiere.
"""
from __future__ import annotations

from decimal import Decimal

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.engine import auditoria_gl
from app.errores import ErrorApi
from app.export.auditoria_gl_xlsx import QUE_MIRA, construir
from app.hotel_actual import HOTEL_ID
from app.importers.balance_comprobacion import leer
from app.models.mayor_movimiento import MayorMovimiento

router = APIRouter(tags=["auditoria-gl"])

#: 25 MB. El de setiembre pesa 1,5 MB con 8.852 lineas; con margen de sobra para
#: un ano entero. Un archivo mas grande que esto no es el reporte que se espera.
MAXIMO = 25 * 1024 * 1024


async def _revisar(archivo: UploadFile, desde_clase: int):
    contenido = await archivo.read()
    if not contenido:
        raise ErrorApi(422, "auditoria.archivo_vacio")
    if len(contenido) > MAXIMO:
        raise ErrorApi(422, "auditoria.archivo_muy_grande")
    try:
        leido = leer(contenido)
    except Exception as e:                       # noqa: BLE001
        raise ErrorApi(422, "auditoria.no_se_pudo_leer", detalle=str(e)[:200]) from e
    if not leido.lineas:
        raise ErrorApi(422, "auditoria.sin_lineas")
    return leido, auditoria_gl.revisar(leido.lineas, desde_clase, leido.periodo)


async def _guardar(db: AsyncSession, leido, contenido: bytes,
                   archivo: str, usuario: str) -> dict:
    """Deja el mes guardado, pisando lo que hubiera de ese mismo mes.

    Un solo `DELETE` + el `INSERT`, en la transaccion de la peticion: o queda el
    mes nuevo entero, o queda el viejo entero. Nunca medio y medio, que con un
    libro contable es la peor forma de fallar.

    ⚠️ Se guardan TODAS las lineas, no solo las clases que se revisan. Ver el
    modelo: recortar ahorraba ~10 MB al año y dejaba un «eso no lo guardamos»
    para el dia que haga falta mirar un banco.

    Si el periodo del archivo no se entiende, NO se guarda y se dice. Adivinar
    el mes guardaria los asientos de setiembre bajo otro mes, y despues no hay
    como darse cuenta.
    """
    am = leido.anio_mes
    if am is None:
        return {"guardado": False, "motivo": "periodo_no_entendido",
                "periodo": leido.periodo}
    anio, mes = am
    await db.execute(sa_delete(MayorMovimiento).where(
        MayorMovimiento.hotel_id == HOTEL_ID,
        MayorMovimiento.anio == anio, MayorMovimiento.mes == mes))
    sello = {
        "hotel_id": HOTEL_ID, "anio": anio, "mes": mes,
        "archivo": (archivo or "")[:255],
        "checksum": hashlib.sha256(contenido).hexdigest(),
        "subido_en": datetime.now(timezone.utc), "subido_por": (usuario or "")[:120],
    }
    for l in leido.lineas:
        db.add(MayorMovimiento(
            cuenta=l.cuenta[:40], seg1=l.seg1[:6], seg2=l.seg2[:6], seg3=l.seg3[:6],
            asiento=l.asiento[:20], linea=l.linea[:10], fecha=l.fecha[:20],
            descripcion=l.descripcion[:250], desc_asiento=l.desc_asiento[:250],
            origen=l.origen[:20], referencia=l.referencia[:120],
            num_doc=l.num_doc[:40],
            debito=_dec(l.debito), credito=_dec(l.credito), tc=_dec(l.tc),
            moneda=(l.moneda or "")[:10], **sello))
    await db.commit()
    return {"guardado": True, "anio": anio, "mes": mes,
            "movimientos": len(leido.lineas)}


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:                                # noqa: BLE001
        return Decimal("0")


@router.post("/auditoria-gl/revisar/")
async def revisar(
    file: UploadFile = File(...),
    #: El owner revisa «las cuentas que empiezan con 4 en adelante». Se deja
    #: mover por si alguna vez quiere mirar el balance tambien.
    desde_clase: int = Query(4, ge=1, le=9),
    #: Guardar el mes es el comportamiento normal. Se puede apagar para mirar un
    #: archivo sin tocar lo que ya esta guardado — por ejemplo, para comparar dos
    #: exportes del mismo mes antes de decidir cual es el bueno.
    guardar: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    contenido = await file.read()
    await file.seek(0)
    leido, r = await _revisar(file, desde_clase)
    guardado = (await _guardar(db, leido, contenido, file.filename or "",
                               getattr(user, "email", "") or str(user or ""))
                if guardar else {"guardado": False, "motivo": "no_pedido"})
    return {
        "guardado": guardado,
        "archivo": file.filename,
        "titulo": leido.titulo,
        "periodo": r.periodo,
        "moneda": leido.moneda,
        "hojas": leido.hojas,
        "lineas_del_archivo": r.lineas_del_archivo,
        "lineas_revisadas": r.lineas_revisadas,
        "lineas_senaladas": r.lineas_senaladas,
        "monto_en_revision_crc": r.monto_en_revision_crc,
        "por_regla": r.por_regla,
        "por_severidad": r.por_severidad,
        # ⚠️ El corte por tipo de cuenta. Se quedo fuera de la respuesta y la
        # pantalla lo lee sin preguntar (`Object.entries(data.por_grupo)`), asi
        # que TODA subida exitosa terminaba en «Esta pantalla no se pudo
        # dibujar · Cannot convert undefined or null to object» — owner,
        # 2026-10-06. El motor siempre lo calculo; faltaba mandarlo.
        "por_grupo": r.por_grupo,
        # Solo lo que esta regla encontro: explicar reglas que no dispararon
        # llena la pantalla de texto que no corresponde a nada en la tabla.
        "que_mira": {k: v for k, v in QUE_MIRA.items() if k in r.por_regla},
        "hallazgos": [h.dict() for h in r.hallazgos],
    }


@router.post("/auditoria-gl/excel/")
async def excel(
    file: UploadFile = File(...),
    desde_clase: int = Query(4, ge=1, le=9),
    user=Depends(get_current_user),
):
    """El mismo analisis, como hoja de trabajo para revisar fuera de la pantalla."""
    _leido, r = await _revisar(file, desde_clase)
    nombre = "Auditoria_Detalle_{}.xlsx".format(
        (r.periodo or "mayor").replace(" ", "").replace("-", "_"))
    return Response(
        construir(r, archivo=file.filename or ""),
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": 'attachment; filename="{}"'.format(nombre)})


# ── El mayor guardado: leerlo ────────────────────────────────────────────────

@router.get("/mayor/meses/")
async def meses_guardados(db: AsyncSession = Depends(get_db),
                          _=Depends(get_current_user)):
    """Qué meses tienen el libro guardado, y de qué archivo salió cada uno.

    La pantalla lo necesita para no ofrecer un mes vacío: «setiembre no está
    subido» es una respuesta; una tabla en blanco no.
    """
    from sqlalchemy import func, select

    filas = (await db.execute(
        select(MayorMovimiento.anio, MayorMovimiento.mes,
               func.count().label("movimientos"),
               func.max(MayorMovimiento.archivo).label("archivo"),
               func.max(MayorMovimiento.subido_en).label("subido_en"))
        .where(MayorMovimiento.hotel_id == HOTEL_ID)
        .group_by(MayorMovimiento.anio, MayorMovimiento.mes)
        .order_by(MayorMovimiento.anio.desc(), MayorMovimiento.mes.desc()))).all()
    return {"meses": [
        {"anio": a, "mes": m, "movimientos": n, "archivo": arch,
         "subido_en": sub.isoformat() if sub else None}
        for a, m, n, arch, sub in filas]}


@router.get("/mayor/{anio}/{mes}/movimientos/")
async def movimientos(
    anio: int,
    mes: int,
    cuenta: str = Query("", description="cuenta completa o su raíz: 7310 o 7310-0110"),
    depto: str = Query("", description="código de departamento (seg2)"),
    q: str = Query("", description="texto en la descripción, el asiento o la referencia"),
    limite: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Los asientos que forman una cuenta de un mes.

    Owner, 2026-10-06: *«es solo para poder revisar detalladamente a nivel de
    detalle»* · *«máximo detalle y descripción del asiento»*.

    `cuenta` acepta la raíz: `7310` trae la cuenta en todos los departamentos y
    `7310-0110` sólo la de Habitaciones. Es la forma en que se lee un cuadro —
    se ve un número por cuenta y se quiere abrir ÉSE.

    ⚠️ **El total viaja aparte del listado.** `limite` recorta lo que se dibuja,
    no lo que se suma: si se sumara lo dibujado, una cuenta con 600 asientos
    mostraría un total que no es el de la cuenta, y el cuadro mentiría sin
    avisar. Es el mismo cuidado que `planilla-por-posicion`.
    """
    from sqlalchemy import func, or_, select

    if not 1 <= mes <= 12:
        raise ErrorApi(422, "precierre.mes_invalido")
    cond = [MayorMovimiento.hotel_id == HOTEL_ID,
            MayorMovimiento.anio == anio, MayorMovimiento.mes == mes]
    if cuenta:
        cond.append(MayorMovimiento.cuenta.like(f"{cuenta.strip()}%"))
    if depto:
        cond.append(MayorMovimiento.seg2 == depto.strip())
    if q:
        patron = f"%{q.strip()}%"
        cond.append(or_(MayorMovimiento.descripcion.ilike(patron),
                        MayorMovimiento.desc_asiento.ilike(patron),
                        MayorMovimiento.referencia.ilike(patron),
                        MayorMovimiento.asiento.ilike(patron)))

    tot = (await db.execute(select(
        func.count(), func.coalesce(func.sum(MayorMovimiento.debito), 0),
        func.coalesce(func.sum(MayorMovimiento.credito), 0)).where(*cond))).one()
    filas = (await db.execute(
        select(MayorMovimiento).where(*cond)
        .order_by(MayorMovimiento.cuenta, MayorMovimiento.asiento,
                  MayorMovimiento.linea)
        .limit(limite))).scalars().all()
    return {
        "anio": anio, "mes": mes,
        "hay_mes": bool(tot[0]) or bool((await db.execute(select(func.count()).where(
            MayorMovimiento.hotel_id == HOTEL_ID,
            MayorMovimiento.anio == anio,
            MayorMovimiento.mes == mes))).scalar()),
        "movimientos": int(tot[0]),
        "debito": float(tot[1]), "credito": float(tot[2]),
        "neto": float(tot[1]) - float(tot[2]),
        "recortado": int(tot[0]) > limite,
        "filas": [{
            "cuenta": f.cuenta, "seg2": f.seg2, "seg3": f.seg3,
            "asiento": f.asiento, "linea": f.linea, "fecha": f.fecha,
            "descripcion": f.descripcion, "desc_asiento": f.desc_asiento,
            "origen": f.origen, "referencia": f.referencia, "num_doc": f.num_doc,
            "debito": float(f.debito), "credito": float(f.credito),
            "neto": float(f.debito) - float(f.credito),
            "tc": float(f.tc), "moneda": f.moneda,
        } for f in filas],
    }
