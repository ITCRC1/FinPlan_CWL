# -*- coding: utf-8 -*-
"""El USALI dentro de la aplicación: subirlo y consultarlo.

Owner, 2026-10-08: *«yo quiero subir el pdf y que el documento viva en la app y
se use para análisis»*.

Esta es la **etapa 1** de tres, y conviene saber qué hace y qué todavía no:

1. **El documento vive acá** (esto). Se sube, se lee, se guarda y se consulta.
   Todavía NO marca nada.
2. **El puente** — cada cuenta de Integrity apareada con su cuenta USALI. Sin
   eso el catálogo no puede tocar un asiento: el libro habla por nombre
   —«Rooms / Operating Supplies»— y la contabilidad por número —`7400-0110`—.
3. **Las reglas** — recién ahí la auditoría compara el detalle contra el
   estándar.

El orden no es capricho. Una regla nueva que marca cien cosas el primer mes no
se revisa: se ignora, y después nadie vuelve a abrir la pantalla. Con las etapas
1 y 2 hechas, cuando la 3 marque algo se va a poder decir por qué.
"""
from __future__ import annotations

import hashlib
import json
import re

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from sqlalchemy import delete as sa_delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_admin, get_current_user
from app.db import get_db
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID
from app.importers.registro_dep import registro_de_subida
from app.models.usali import UsaliDefinicion, UsaliDocumento, UsaliItem

router = APIRouter(tags=["usali"])

#: Un archivo de 391 páginas pesa 2,8 MB. El tope deja lugar a una edición más
#: grande y corta cualquier cosa que claramente no sea el libro.
TOPE_MB = 40


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


@router.get("/usali/estado/")
async def estado(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Qué hay cargado. La pantalla lo consulta antes de ofrecer la búsqueda."""
    doc = (await db.execute(select(UsaliDocumento)
                            .where(UsaliDocumento.hotel_id == HOTEL_ID)
                            .order_by(UsaliDocumento.subido_en.desc())
                            .limit(1))).scalars().first()
    if doc is None:
        return {"hay": False}
    schedules = [
        {"schedule": s, "items": n} for s, n in (await db.execute(
            select(UsaliItem.schedule, func.count())
            .where(UsaliItem.hotel_id == HOTEL_ID)
            .group_by(UsaliItem.schedule)
            .order_by(func.count().desc()))).all()]
    return {
        "hay": True,
        "archivo": doc.archivo,
        "paginas": doc.paginas,
        "paginas_con_texto": doc.paginas_con_texto,
        "items": doc.items,
        "items_confirmados": doc.items_confirmados,
        "definiciones": doc.definiciones,
        "cruce": json.loads(doc.cruce or "{}"),
        "subido_en": doc.subido_en.isoformat() if doc.subido_en else None,
        "subido_por": doc.subido_por,
        "schedules": schedules,
    }


# Toda puerta que recibe un archivo y escribe queda registrada: meses
# despues, «¿de que archivo salio este catalogo?» tiene que poder
# contestarse sin preguntarle a nadie.
@router.post("/usali/subir/", dependencies=[Depends(registro_de_subida)])
async def subir(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_admin),
):
    """Sube el PDF, lo lee y reemplaza lo que hubiera.

    ⚠️ **Reemplaza, no acumula.** Igual que el mayor: la llave de negocio es la
    propiedad, y subir otra edición le cae encima a la anterior. Dos ediciones
    conviviendo serían dos estándares para la misma cuenta, y ninguna pantalla
    podría decir cuál manda.
    """
    from app.importers.usali_pdf import leer_pdf

    crudo = await file.read()
    if not crudo:
        raise ErrorApi(422, "usali.archivo_vacio")
    if len(crudo) > TOPE_MB * 1024 * 1024:
        raise ErrorApi(422, "usali.archivo_grande", tope=TOPE_MB)
    if not crudo[:5].startswith(b"%PDF"):
        raise ErrorApi(422, "usali.no_es_pdf")

    try:
        lectura = leer_pdf(crudo)
    except Exception as e:                       # pragma: no cover - defensivo
        raise ErrorApi(422, "usali.no_se_pudo_leer", detalle=str(e)[:200])

    if not lectura.catalogo:
        # Un PDF escaneado da cero entradas. Decirlo es la diferencia entre
        # «su archivo es una imagen» y una pantalla vacía sin explicación.
        raise ErrorApi(
            422, "usali.sin_entradas",
            paginas=lectura.paginas, con_texto=lectura.paginas_con_texto)

    # ── reemplazo, en una sola transacción ────────────────────────────────
    for modelo in (UsaliItem, UsaliDefinicion, UsaliDocumento):
        await db.execute(sa_delete(modelo).where(modelo.hotel_id == HOTEL_ID))

    db.add(UsaliDocumento(
        hotel_id=HOTEL_ID, archivo=file.filename or "usali.pdf",
        checksum=hashlib.sha256(crudo).hexdigest(),
        paginas=lectura.paginas, paginas_con_texto=lectura.paginas_con_texto,
        items=len(lectura.catalogo),
        items_confirmados=sum(1 for c in lectura.catalogo
                              if c.confianza == "confirmado"),
        definiciones=len(lectura.definiciones),
        cruce=json.dumps(lectura.cruce, ensure_ascii=False),
        subido_por=getattr(user, "email", "")))

    vistos: set[tuple] = set()
    for c in lectura.catalogo:
        k = (_norm(c.item), c.schedule, c.cuenta)
        if k in vistos:
            continue
        vistos.add(k)
        db.add(UsaliItem(hotel_id=HOTEL_ID, item=c.item[:400],
                         item_norm=_norm(c.item)[:400], schedule=c.schedule[:80],
                         cuenta=c.cuenta[:200], confianza=c.confianza,
                         paginas=c.paginas[:60]))
    vistas: set[tuple] = set()
    for d in lectura.definiciones:
        k = (_norm(d.cuenta), d.pagina)
        if k in vistas:
            continue
        vistas.add(k)
        db.add(UsaliDefinicion(hotel_id=HOTEL_ID, cuenta=d.cuenta[:200],
                               cuenta_norm=_norm(d.cuenta)[:200],
                               texto=d.texto, pagina=d.pagina))
    await db.commit()

    return {
        "ok": True, "archivo": file.filename,
        "paginas": lectura.paginas, "paginas_con_texto": lectura.paginas_con_texto,
        "items": len(vistos), "definiciones": len(vistas),
        "cruce": lectura.cruce,
    }


@router.get("/usali/buscar/")
async def buscar(
    q: str = Query("", description="texto a buscar en el artículo o la cuenta"),
    schedule: str = Query("", description="filtrar por departamento del USALI"),
    limite: int = Query(80, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Dónde dice el estándar que va algo.

    Busca en el artículo y en el nombre de cuenta, porque las dos preguntas son
    legítimas: «¿dónde va el combustible?» y «¿qué va en Operating Supplies?».
    """
    stmt = select(UsaliItem).where(UsaliItem.hotel_id == HOTEL_ID)
    texto = _norm(q)
    if texto:
        like = f"%{texto}%"
        stmt = stmt.where(or_(UsaliItem.item_norm.like(like),
                              func.lower(UsaliItem.cuenta).like(f"%{q.lower()}%")))
    if schedule:
        stmt = stmt.where(UsaliItem.schedule == schedule)
    filas = (await db.execute(stmt.order_by(UsaliItem.item_norm)
                              .limit(limite))).scalars().all()
    total = (await db.execute(
        select(func.count()).select_from(stmt.subquery()))).scalar() or 0
    return {
        "total": total, "recortado": total > len(filas),
        "filas": [{"item": f.item, "schedule": f.schedule, "cuenta": f.cuenta,
                   "confianza": f.confianza, "paginas": f.paginas}
                  for f in filas],
    }


@router.get("/usali/excel/")
async def excel(
    q: str = Query(""),
    schedule: str = Query(""),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """El catalogo en Excel: el diccionario y las definiciones, dos hojas.

    No es un adorno: con las ~1.950 filas afuera se puede revisar el catalogo de
    corrido y, sobre todo, es la base para armar el PUENTE contra las cuentas de
    Integrity, que es la etapa 2. Esa correspondencia la tiene que mirar una
    persona.

    ⚠️ Baja lo que la pantalla esta mostrando, filtros incluidos. Este proyecto
    ya pago una vez por un Excel que no era lo que se veia.
    """
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    stmt = select(UsaliItem).where(UsaliItem.hotel_id == HOTEL_ID)
    texto = _norm(q)
    if texto:
        like = f"%{texto}%"
        stmt = stmt.where(or_(UsaliItem.item_norm.like(like),
                              func.lower(UsaliItem.cuenta).like(f"%{q.lower()}%")))
    if schedule:
        stmt = stmt.where(UsaliItem.schedule == schedule)
    items = (await db.execute(stmt.order_by(UsaliItem.schedule, UsaliItem.cuenta,
                                            UsaliItem.item_norm))).scalars().all()
    defs = (await db.execute(
        select(UsaliDefinicion).where(UsaliDefinicion.hotel_id == HOTEL_ID)
        .order_by(UsaliDefinicion.pagina))).scalars().all()

    wb = Workbook()
    cab = Font(bold=True, color="FFFFFF")
    fondo = PatternFill("solid", fgColor="1F3B63")

    h = wb.active
    h.title = "Diccionario"
    h.append(["Departamento", "Cuenta", "Articulo", "Origen", "Paginas"])
    for c in h[1]:
        c.font, c.fill = cab, fondo
    for x in items:
        h.append([x.schedule, x.cuenta, x.item,
                  "confirmado" if x.confianza == "confirmado" else "de un solo lado",
                  x.paginas])
    for col, ancho in zip("ABCDE", (22, 34, 60, 16, 12)):
        h.column_dimensions[col].width = ancho
    h.freeze_panes = "A2"

    d = wb.create_sheet("Definiciones")
    d.append(["Cuenta", "Pagina", "Definicion"])
    for c in d[1]:
        c.font, c.fill = cab, fondo
    for x in defs:
        d.append([x.cuenta, x.pagina, x.texto])
    for col, ancho in zip("ABC", (34, 9, 140)):
        d.column_dimensions[col].width = ancho
    for fila in d.iter_rows(min_row=2, min_col=3, max_col=3):
        fila[0].alignment = Alignment(wrap_text=True, vertical="top")
    d.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    return Response(
        buf.getvalue(),
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": 'attachment; filename="USALI_catalogo.xlsx"'})


@router.get("/usali/definicion/")
async def definicion(
    cuenta: str = Query(..., description="nombre de cuenta del USALI"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Qué dice el libro que incluye esa cuenta, y qué artículos le asigna."""
    n = _norm(cuenta)
    defs = (await db.execute(
        select(UsaliDefinicion)
        .where(UsaliDefinicion.hotel_id == HOTEL_ID,
               UsaliDefinicion.cuenta_norm == n))).scalars().all()
    if not defs:
        # El nombre de cuenta del diccionario puede venir abreviado; se busca
        # por prefijo antes de contestar que no hay nada.
        defs = (await db.execute(
            select(UsaliDefinicion)
            .where(UsaliDefinicion.hotel_id == HOTEL_ID,
                   UsaliDefinicion.cuenta_norm.like(f"{n[:24]}%"))
            .limit(3))).scalars().all()
    items = (await db.execute(
        select(UsaliItem).where(UsaliItem.hotel_id == HOTEL_ID,
                                UsaliItem.cuenta == cuenta)
        .order_by(UsaliItem.item_norm).limit(300))).scalars().all()
    return {
        "cuenta": cuenta,
        "definiciones": [{"cuenta": d.cuenta, "texto": d.texto, "pagina": d.pagina}
                         for d in defs],
        "items": [{"item": i.item, "schedule": i.schedule,
                   "confianza": i.confianza} for i in items],
    }
