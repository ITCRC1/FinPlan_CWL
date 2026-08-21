# -*- coding: utf-8 -*-
"""Mapeo de orígenes y carga de actuales por API.

    GET    /api/origenes/                        qué orígenes hay y su estado
    GET    /api/origenes/{origen}/mapeo/         las equivalencias cargadas
    PUT    /api/origenes/{origen}/mapeo/         reemplaza el mapeo (bulk)
    DELETE /api/origenes/{origen}/mapeo/{id}/    baja una regla

    POST   /api/origenes/{origen}/previsualizar/ qué pasaría. NO escribe
    POST   /api/origenes/{origen}/aplicar/       escribe

**Previsualizar y aplicar están separados a propósito.** Es la norma del owner en
todo el sistema: se mira antes de que escriba. Y acá importa más que en otros
lados, porque del otro lado hay un sistema que nadie de este equipo controla.

⚠️ **Hoy ningún adaptador trae dato todavía.** `previsualizar` y `aplicar`
reciben las filas en el cuerpo, así que la tubería —traducir, ver, escribir— se
puede usar y probar entera desde ya. Cuando exista el adaptador de QuickBooks o
el del backoffice, lo único que cambia es de dónde salen esas filas.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete

from app.api._candado import candado
from app.auth import get_current_admin
from app.db import get_session
from app.errores import ErrorApi
from app.textos import Idioma, t
from app.hotel_actual import HOTEL_ID
from app.models.mapeo_origen import MapeoOrigen, ORIGENES
from app.models.scenario import Scenario
from app.origenes import FilaDeOrigen
from app.origenes import aterrizaje
from app.origenes.traductor import traducir

router = APIRouter()


def _valida_origen(origen: str) -> str:
    o = origen.upper()
    if o not in ORIGENES:
        raise ErrorApi(422, "origen.desconocido", origen=origen,
                       origenes=", ".join(ORIGENES))
    return o


def _regla_dict(r: MapeoOrigen) -> dict:
    return {
        "id": r.id, "origen": r.origen,
        "cuenta_origen": r.cuenta_origen, "nombre_origen": r.nombre_origen,
        "dept_origen": r.dept_origen,
        "account_code": r.account_code, "dept_code": r.dept_code, "outlet": r.outlet,
        "activo": r.activo, "nota": r.nota,
    }


@router.get("/origenes/")
async def listar_origenes(_=Depends(get_current_admin), idioma: str = Idioma):
    """Qué orígenes existen y cuántas equivalencias tiene cargadas cada uno."""
    async with get_session() as s:
        filas = (await s.execute(
            select(MapeoOrigen).where(MapeoOrigen.hotel_id == HOTEL_ID))).scalars().all()
    por_origen: dict[str, int] = {}
    for r in filas:
        if r.activo:
            por_origen[r.origen] = por_origen.get(r.origen, 0) + 1
    return {
        "hotel_id": HOTEL_ID,
        "origenes": [{
            "origen": o,
            "reglas_activas": por_origen.get(o, 0),
            # Sin reglas no entra ningún monto. Se dice acá para que no haya que
            # descubrirlo con una importación que no importó nada.
            "listo_para_importar": por_origen.get(o, 0) > 0,
        } for o in ORIGENES],
        "nota": t(idioma, "origenes.el_mapeo_habilita_el_origen"),
    }


@router.get("/origenes/{origen}/mapeo/")
async def ver_mapeo(origen: str, _=Depends(get_current_admin)):
    o = _valida_origen(origen)
    async with get_session() as s:
        filas = (await s.execute(
            select(MapeoOrigen).where(
                MapeoOrigen.hotel_id == HOTEL_ID, MapeoOrigen.origen == o
            ).order_by(MapeoOrigen.cuenta_origen, MapeoOrigen.dept_origen))).scalars().all()
    return {"hotel_id": HOTEL_ID, "origen": o,
            "reglas": [_regla_dict(r) for r in filas]}


class ReglaIn(BaseModel):
    cuenta_origen: str
    account_code: str
    nombre_origen: str = ""
    dept_origen: str = ""
    dept_code: str = ""
    outlet: str = ""
    activo: bool = True
    nota: str = ""


class MapeoBulk(BaseModel):
    reglas: list[ReglaIn]


@router.put("/origenes/{origen}/mapeo/")
async def guardar_mapeo(origen: str, body: MapeoBulk, _=Depends(get_current_admin)):
    """Reemplaza el mapeo de este origen, entero.

    Es bulk y no fila por fila porque la forma de trabajar del owner es bajar,
    corregir y subir. Se valida ANTES de borrar: si el archivo trae dos veces la
    misma cuenta no se puede saber cuál gana, y quedarse con la última sería
    perder la otra sin decirlo.
    """
    o = _valida_origen(origen)
    vistas: set[tuple[str, str]] = set()
    for r in body.reglas:
        k = (r.cuenta_origen.strip(), r.dept_origen.strip())
        if k in vistas:
            if k[1]:
                raise ErrorApi(409, "origen.cuenta_duplicada_en_depto",
                               cuenta=k[0], departamento=k[1])
            raise ErrorApi(409, "origen.cuenta_duplicada", cuenta=k[0])
        vistas.add(k)
        if not r.cuenta_origen.strip() or not r.account_code.strip():
            raise ErrorApi(422, "origen.regla_incompleta")

    async with get_session() as s:
        await s.execute(delete(MapeoOrigen).where(
            MapeoOrigen.hotel_id == HOTEL_ID, MapeoOrigen.origen == o))
        for r in body.reglas:
            s.add(MapeoOrigen(
                hotel_id=HOTEL_ID, origen=o,
                cuenta_origen=r.cuenta_origen.strip(), nombre_origen=r.nombre_origen.strip(),
                dept_origen=r.dept_origen.strip(), account_code=r.account_code.strip(),
                dept_code=r.dept_code.strip(), outlet=r.outlet.strip(),
                activo=r.activo, nota=r.nota.strip()))
        await s.commit()
    return {"origen": o, "reglas": len(body.reglas)}


@router.delete("/origenes/{origen}/mapeo/{regla_id}/")
async def borrar_regla(origen: str, regla_id: str, _=Depends(get_current_admin)):
    o = _valida_origen(origen)
    async with get_session() as s:
        r = await s.get(MapeoOrigen, regla_id)
        if r is None or r.hotel_id != HOTEL_ID or r.origen != o:
            raise ErrorApi(404, "origen.regla_no_existe")
        await s.delete(r)
        await s.commit()
    return {"borrada": regla_id}


# ── Carga ──────────────────────────────────────────────────────────────────

class FilaIn(BaseModel):
    cuenta: str
    mes: int
    monto: Decimal
    nombre: str = ""
    dept: str = ""
    outlet: str = ""


class CargaIn(BaseModel):
    scenario_id: str
    filas: list[FilaIn]
    permitir_sin_mapeo: bool = False


async def _preparar(origen: str, body: CargaIn):
    o = _valida_origen(origen)
    try:
        filas = [FilaDeOrigen(cuenta=f.cuenta, mes=f.mes, monto=f.monto,
                              nombre=f.nombre, dept=f.dept, outlet=f.outlet)
                 for f in body.filas]
    except ValueError as e:
        raise HTTPException(422, str(e))
    if not filas:
        raise ErrorApi(422, "origen.sin_filas")
    return o, filas


@router.post("/origenes/{origen}/previsualizar/")
async def previsualizar(origen: str, body: CargaIn, _=Depends(get_current_admin)):
    """Qué pasaría. No escribe."""
    o, filas = await _preparar(origen, body)
    async with get_session() as s:
        escenario = await s.get(Scenario, body.scenario_id)
        if escenario is None:
            raise ErrorApi(404, "escenario.no_encontrado")
        reglas = (await s.execute(select(MapeoOrigen).where(
            MapeoOrigen.hotel_id == HOTEL_ID, MapeoOrigen.origen == o))).scalars().all()
        traduccion = traducir(filas, reglas)
        return await aterrizaje.previsualizar(s, escenario, traduccion)


@router.post("/origenes/{origen}/aplicar/")
async def aplicar(origen: str, body: CargaIn, _=Depends(get_current_admin)):
    """Escribe. Se niega si hay cuentas sin equivalencia."""
    o, filas = await _preparar(origen, body)
    async with get_session() as s:
        escenario = await s.get(Scenario, body.scenario_id)
        if escenario is None:
            raise ErrorApi(404, "escenario.no_encontrado")
        await candado(s, body.scenario_id)
        reglas = (await s.execute(select(MapeoOrigen).where(
            MapeoOrigen.hotel_id == HOTEL_ID, MapeoOrigen.origen == o))).scalars().all()
        traduccion = traducir(filas, reglas)
        try:
            return await aterrizaje.aplicar(s, escenario, traduccion,
                                            permitir_sin_mapeo=body.permitir_sin_mapeo)
        except ValueError as e:
            raise HTTPException(409, str(e))
