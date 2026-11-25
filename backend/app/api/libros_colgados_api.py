"""Mis libros: subir los Excels propios a la app y bajarlos tal cual.

Owner, 2026-11-24: *«tengo versiones por todos lados… quiero ir a un lugar solo
y bajar mis proyectos, mis creaciones, pero que no se rompa nada»* y *«no quiero
llenarme de versiones»*.

- El archivo NO se abre ni se arma: se guarda byte por byte y se entrega igual.
  Así el Power Query llega intacto y el owner lo actualiza como siempre.
- Un libro por título. Subir con un título que ya existe lo reemplaza y deja la
  versión anterior (una sola) para volver atrás.

    GET    /libros/                         → los libros (sin el archivo)
    GET    /libros/budget-package/          → el del botón (o {existe: false})
    GET    /libros/{id}/descargar/          → el archivo tal cual
    GET    /libros/{id}/descargar/anterior/ → la versión anterior
    POST   /libros/                         → subir o reemplazar — solo admin
    POST   /libros/{id}/volver-a-anterior/  → deshacer la última subida — solo admin
    DELETE /libros/{id}/                    → quitarlo — solo admin
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import undefer

from app.auth import get_current_admin
from app.db import get_session
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID
from app.models.libro_colgado import TITULO_BUDGET_PACKAGE, LibroColgado

router = APIRouter(tags=["libros"])

#: El v13 pesa ~5 MB; con 40 hay aire sin abrir la puerta a cualquier cosa.
MAX_BYTES = 40 * 1024 * 1024
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLSM = "application/vnd.ms-excel.sheet.macroEnabled.12"


def es_excel(nombre: str, contenido: bytes) -> bool:
    """Un .xlsx/.xlsm es un ZIP: empieza con «PK». Sin esto se colaba cualquier
    archivo con la extensión cambiada."""
    return nombre.lower().endswith((".xlsx", ".xlsm")) and contenido[:2] == b"PK"


def limpiar_titulo(titulo: str) -> str:
    return " ".join((titulo or "").split())[:160]


def _fila(l: LibroColgado) -> dict:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"id": l.id, "titulo": l.titulo, "nombre_archivo": l.nombre_archivo,
            "tamano": l.tamano, "nota": l.nota, "subido_por": l.subido_por,
            "subido_el": iso(l.subido_el),
            "anterior": None if not l.anterior_nombre else {
                "nombre_archivo": l.anterior_nombre, "tamano": l.anterior_tamano,
                "subido_por": l.anterior_subido_por, "subido_el": iso(l.anterior_subido_el)}}


def _archivo(nombre: str, contenido: bytes) -> Response:
    nombre = (nombre or "libro.xlsx").replace('"', "")
    return Response(content=contenido,
                    media_type=XLSM if nombre.lower().endswith(".xlsm") else XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


async def _libro(s, libro_id: str, *campos) -> LibroColgado:
    q = select(LibroColgado).where(LibroColgado.id == libro_id,
                                   LibroColgado.hotel_id == HOTEL_ID)
    if campos:
        q = q.options(*[undefer(getattr(LibroColgado, c)) for c in campos])
    l = (await s.execute(q)).scalar_one_or_none()
    if l is None:
        raise ErrorApi(404, "libro.no_existe")
    return l


@router.get("/libros/")
async def listar_libros():
    async with get_session() as s:
        filas = (await s.execute(select(LibroColgado).where(
            LibroColgado.hotel_id == HOTEL_ID))).scalars().all()
    # El Budget Package primero: es el del botón.
    filas = sorted(filas, key=lambda l: (l.titulo != TITULO_BUDGET_PACKAGE, l.titulo.lower()))
    return [_fila(l) for l in filas]


@router.get("/libros/budget-package/")
async def budget_package():
    async with get_session() as s:
        l = (await s.execute(select(LibroColgado).where(
            LibroColgado.hotel_id == HOTEL_ID,
            LibroColgado.titulo == TITULO_BUDGET_PACKAGE))).scalar_one_or_none()
    return {"existe": False, "titulo": TITULO_BUDGET_PACKAGE} if l is None \
        else {"existe": True, **_fila(l)}


@router.get("/libros/{libro_id}/descargar/")
async def descargar_libro(libro_id: str):
    async with get_session() as s:
        l = await _libro(s, libro_id, "contenido")
        return _archivo(l.nombre_archivo, l.contenido)


@router.get("/libros/{libro_id}/descargar/anterior/")
async def descargar_anterior(libro_id: str):
    async with get_session() as s:
        l = await _libro(s, libro_id, "anterior_contenido")
        if not l.anterior_contenido:
            raise ErrorApi(404, "libro.sin_anterior")
        return _archivo(l.anterior_nombre, l.anterior_contenido)


@router.post("/libros/")
async def subir_libro(titulo: str = Form(...), nota: str = Form(""),
                      file: UploadFile = File(...), user=Depends(get_current_admin)):
    titulo = limpiar_titulo(titulo)
    if not titulo:
        raise ErrorApi(422, "libro.sin_titulo")
    contenido = await file.read()
    nombre = (file.filename or "libro.xlsx").replace("\\", "/").split("/")[-1][:200]
    if not es_excel(nombre, contenido):
        raise ErrorApi(422, "libro.no_es_excel")
    if len(contenido) > MAX_BYTES:
        raise ErrorApi(422, "libro.muy_grande")
    async with get_session() as s:
        l = (await s.execute(select(LibroColgado).options(undefer(LibroColgado.contenido))
             .where(LibroColgado.hotel_id == HOTEL_ID,
                    LibroColgado.titulo == titulo))).scalar_one_or_none()
        if l is None:
            l = LibroColgado(hotel_id=HOTEL_ID, titulo=titulo)
            s.add(l)
        else:
            # La que estaba pasa a ser «la anterior»; la de antes de esa se va.
            l.anterior_nombre, l.anterior_contenido = l.nombre_archivo, l.contenido
            l.anterior_tamano, l.anterior_subido_por = l.tamano, l.subido_por
            l.anterior_subido_el = l.subido_el
        l.nombre_archivo, l.contenido, l.tamano = nombre, contenido, len(contenido)
        l.nota = (nota or "").strip()[:500] or None
        l.subido_por = getattr(user, "email", None)
        l.subido_el = datetime.now(timezone.utc)
        await s.commit()
        await s.refresh(l)
        return _fila(l)


@router.post("/libros/{libro_id}/volver-a-anterior/")
async def volver_a_anterior(libro_id: str, _=Depends(get_current_admin)):
    """Deshace la última subida: la anterior vuelve a ser la actual y la actual
    queda como anterior (así deshacer también se puede deshacer)."""
    async with get_session() as s:
        l = await _libro(s, libro_id, "contenido", "anterior_contenido")
        if not l.anterior_contenido:
            raise ErrorApi(404, "libro.sin_anterior")
        (l.nombre_archivo, l.anterior_nombre) = (l.anterior_nombre, l.nombre_archivo)
        (l.contenido, l.anterior_contenido) = (l.anterior_contenido, l.contenido)
        (l.tamano, l.anterior_tamano) = (l.anterior_tamano, l.tamano)
        (l.subido_por, l.anterior_subido_por) = (l.anterior_subido_por, l.subido_por)
        (l.subido_el, l.anterior_subido_el) = (l.anterior_subido_el, l.subido_el)
        await s.commit()
        await s.refresh(l)
        return _fila(l)


@router.delete("/libros/{libro_id}/")
async def quitar_libro(libro_id: str, _=Depends(get_current_admin)):
    async with get_session() as s:
        l = await _libro(s, libro_id)
        await s.delete(l)
        await s.commit()
    return {"quitado": libro_id}
