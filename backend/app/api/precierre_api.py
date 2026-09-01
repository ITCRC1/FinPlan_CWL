# -*- coding: utf-8 -*-
"""Pre-Cierre — subir el Integrity crudo, revisarlo, y recién ahí cerrar.

## Qué resuelve

Hasta hoy el cierre mensual se armaba a mano en un libro de Excel de 104 MB en
Drive: de Integrity baja sólo la hoja `Final` hasta la columna U, y todo lo
demás —signo, tipo de cambio, departamento, división— se pedía con fórmulas
hasta que cuadrara. Recién entonces se llenaba la plantilla y se subía.

El trabajo manual era determinístico. El problema de fondo no: **la revisión de
los actuales pasaba por el ojo de una persona**, y por ahí podía entrar
cualquier cosa —una cuenta que USALI no contempla, un departamento nuevo, un
gasto que nadie presupuestó—. Si nadie lo miraba, entraba igual y el P&L
cuadraba consigo mismo.

## ⚠️ Es una antesala, no una segunda puerta

`pasar-a-final` **no escribe**. Arma la plantilla de upload con
`export/detail_excel` y se la da a `import_gl_detail`, que es el único camino
que escribe actuales en este sistema. Este repo ya se quemó con dos puertas al
mismo dato; no se abre una tercera.

Y un pre-cierre **no es un escenario**: ningún reporte lo lee. Si se filtrara
habría dos versiones del mismo mes conviviendo.
"""
from __future__ import annotations

import hashlib
import io
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.engine import pl_engine
from app.errores import ErrorApi
from app.export import revision_mes_xlsx as revision
from app.hotel_actual import HOTEL_ID
from app.importers import integrity_final
from app.importers.registro_dep import registro_de_subida
from app.models.department_catalog import DepartmentCatalog
from app.models.precierre import Precierre, PrecierreFila
from app.textos import Idioma

router = APIRouter()

MESES = ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"]


# ─── El puente y la clasificación ─────────────────────────────────────────────

async def _puente() -> dict:
    """El mapeo Integrity → FinPlan de esta propiedad."""
    from app.seed_data import semilla_cruda
    # Sin extensión: `semilla_cruda` la agrega. Y es `_cruda` a propósito —
    # `semilla()` convierte a Decimal lo que parece número y «0113» se vuelve
    # 113: el departamento perdería el cero de adelante y dejaría de existir.
    datos = semilla_cruda("mapd_integrity")
    if not datos:
        raise ErrorApi(422, "precierre.sin_puente")
    return {d["codigo"]: d for d in datos["departamentos"]}


async def _clasificador(db: AsyncSession):
    """`destino de FinPlan → grupo del P&L`, según el catálogo.

    Devuelve `None` para los departamentos que el catálogo deja SIN grupo a
    propósito: los que se abren por cuenta (`280` Misceláneos). Ahí no se
    inventa nada — el fallback los rotularía como overhead y son ingreso.
    """
    filas = (await db.execute(select(DepartmentCatalog))).scalars().all()
    pl_engine.set_dept_catalog([{"dept_code": r.dept_code,
                                 "default_pl_group": r.default_pl_group,
                                 "parent_dept_code": r.parent_dept_code}
                                for r in filas])
    sin_grupo = {r.dept_code for r in filas if not (r.default_pl_group or "")}

    def resolver(destino: str):
        if not destino or destino in sin_grupo:
            return None
        return pl_engine.group_for_dept(destino)
    return resolver


async def _traer(db: AsyncSession, precierre_id: str) -> Precierre:
    pc = await db.get(Precierre, precierre_id)
    if pc is None:
        raise ErrorApi(404, "precierre.no_encontrado")
    return pc


async def _filas(db: AsyncSession, precierre_id: str) -> list[dict]:
    filas = (await db.execute(select(PrecierreFila).where(
        PrecierreFila.precierre_id == precierre_id))).scalars().all()
    return [{"fila": f.fila, "cuenta": f.cuenta, "cuenta_base": f.cuenta_base,
             "descripcion": f.descripcion, "depto": f.depto,
             "destino_finplan": f.destino_finplan, "grupo": f.grupo or None,
             "categoria": f.categoria, "mes_usd": f.mes_usd,
             "acumulado_usd": f.acumulado_usd} for f in filas]


# ─── Subir ────────────────────────────────────────────────────────────────────

@router.post("/precierre/", dependencies=[Depends(registro_de_subida)])
async def crear(
    file: UploadFile = File(...),
    tc: Decimal = Query(..., gt=0, description="Tipo de cambio CRC/USD del mes"),
    mes: int = Query(..., ge=1, le=12),
    anio: int = Query(...),
    db: AsyncSession = Depends(get_db),
    usuario=Depends(get_current_user),
    idioma: str = Idioma,
):
    """Sube el estado de resultados CRUDO de Integrity y lo deja en revisión.

    **Subir de nuevo es el flujo normal, no la excepción.** Durante la revisión
    el mismo mes se sube muchas veces: aparece un error de posteo, se corrige en
    Integrity, se vuelve a bajar y se sube otra vez, hasta llegar al cierre
    acordado. Por eso cada subida **reemplaza** el borrador anterior sin
    preguntar — pedir confirmación en cada vuelta convertiría el camino principal
    en una molestia, y a la quinta nadie lee el aviso.

    No se pierde nada: el borrador anterior queda `descartado`, con su archivo y
    su hora, y la respuesta dice a cuál reemplazó. La cuenta de vueltas es parte
    de la historia del mes.

    El **tipo de cambio es obligatorio** y no tiene default: cambia todos los
    meses y es un dato del cierre, no una constante del sistema. Inventarlo
    pondría todo el P&L a un TC que nadie decidió, y cuadraría igual.
    """
    data = await file.read()
    if not data:
        raise ErrorApi(422, "precierre.archivo_vacio")

    ya = (await db.execute(select(Precierre).where(
        Precierre.hotel_id == HOTEL_ID, Precierre.anio == anio,
        Precierre.mes == mes, Precierre.estado == "borrador"))).scalars().first()
    reemplazado = None
    if ya is not None:
        ya.estado = "descartado"
        reemplazado = {"id": ya.id, "archivo": ya.archivo_nombre,
                       "subido_en": ya.creado_en.isoformat() if ya.creado_en else None}
        await db.flush()
    vueltas = len((await db.execute(select(Precierre.id).where(
        Precierre.hotel_id == HOTEL_ID, Precierre.anio == anio,
        Precierre.mes == mes))).all()) + 1

    puente = await _puente()
    grupo_de = await _clasificador(db)
    try:
        leido = integrity_final.leer(data, tc, puente, grupo_de)
    except integrity_final.FormatoInesperado as e:
        raise ErrorApi(422, "precierre.formato", detalle=str(e))

    pc = Precierre(hotel_id=HOTEL_ID, anio=anio, mes=mes, tc=tc,
                   archivo_nombre=(file.filename or "")[:255],
                   # El checksum se guarda para poder decir DE QUE archivo salió
                   # este mes. El anti-reimport NO vive acá: lo hace
                   # `registro_de_subida`, enganchado en el decorador, que es UN
                   # mecanismo para las veinticuatro puertas y no veinticuatro.
                   checksum=hashlib.sha256(data).hexdigest(),
                   subido_por=getattr(usuario, "email", "") or "")
    db.add(pc)
    await db.flush()
    for f in leido["filas"]:
        db.add(PrecierreFila(
            precierre_id=pc.id, fila=f["fila"], cuenta=f["cuenta"],
            cuenta_base=f["cuenta_base"], descripcion=f["descripcion"][:200],
            depto=f["depto"], destino_finplan=f["destino_finplan"],
            grupo=f["grupo"] or "", categoria=f["categoria"],
            mes_usd=f["mes_usd"], acumulado_usd=f["acumulado_usd"]))
    await db.commit()

    return {"id": pc.id, "anio": anio, "mes": mes, "tc": float(tc),
            "filas": len(leido["filas"]),
            # A cuál reemplazó y cuántas vueltas lleva el mes. Reemplazar sin
            # decirlo sería pisar en silencio; decirlo lo vuelve historia.
            "reemplaza_a": reemplazado, "vuelta": vueltas,
            # Los departamentos que nadie mapeó, CON su monto: sin eso no hay
            # forma de saber si es ruido o si falta media operación.
            "sin_mapeo": [{"depto": x["depto"], "mes_usd": float(x["mes_usd"]),
                           "cuentas": x["cuentas"][:8]}
                          for x in leido["sin_mapeo"]]}


# ─── Ver ──────────────────────────────────────────────────────────────────────

@router.get("/precierre/")
async def listar(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    filas = (await db.execute(select(Precierre).where(
        Precierre.hotel_id == HOTEL_ID).order_by(
        Precierre.anio.desc(), Precierre.mes.desc()))).scalars().all()
    return {"precierres": [
        {"id": p.id, "anio": p.anio, "mes": p.mes, "estado": p.estado,
         "tc": float(p.tc), "archivo": p.archivo_nombre,
         "subido_por": p.subido_por,
         "creado_en": p.creado_en.isoformat() if p.creado_en else None,
         "hallazgos_abiertos": p.hallazgos_abiertos} for p in filas]}


@router.get("/precierre/{precierre_id}/")
async def detalle(precierre_id: str, db: AsyncSession = Depends(get_db),
                  _=Depends(get_current_user)):
    """La hoja de revisión del mes, en la misma forma que el tab del owner."""
    pc = await _traer(db, precierre_id)
    filas = await _filas(db, precierre_id)
    valores = revision.valores_completos(filas)
    return {
        "id": pc.id, "anio": pc.anio, "mes": pc.mes, "estado": pc.estado,
        "tc": float(pc.tc),
        "hoja": [{"fila": f, "etiqueta": e, "clave": c,
                  "actual": float(valores.get(c, 0)) if c else None}
                 for f, e, c in revision.PLAN],
        "filas": len(filas),
    }


@router.get("/precierre/{precierre_id}/hoja.xlsx")
async def hoja(precierre_id: str, db: AsyncSession = Depends(get_db),
               _=Depends(get_current_user)):
    """La hoja de revisión, con el layout exacto del tab que el owner revisa a
    ojo — mismas filas, mismas columnas, mismas etiquetas."""
    pc = await _traer(db, precierre_id)
    valores = revision.valores_desde_precierre(await _filas(db, precierre_id))
    wb = revision.construir(MESES[pc.mes - 1], pc.anio, {}, valores)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nombre = f"Revision_{MESES[pc.mes - 1]}_{pc.anio}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.delete("/precierre/{precierre_id}/")
async def descartar(precierre_id: str, db: AsyncSession = Depends(get_db),
                    _=Depends(get_current_user)):
    """Se marca descartado, no se borra: queda la traza de que se intentó."""
    pc = await _traer(db, precierre_id)
    if pc.estado == "pasado_a_final":
        raise ErrorApi(409, "precierre.ya_paso_a_final")
    pc.estado = "descartado"
    await db.commit()
    return {"id": pc.id, "estado": pc.estado}
