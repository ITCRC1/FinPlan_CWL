"""Mis libros: subir los Excels propios a la app y bajarlos tal cual.

Owner, 2026-11-24: *«tengo versiones por todos lados… quiero ir a un lugar solo
y bajar mis proyectos, mis creaciones, pero que no se rompa nada»* y *«no quiero
llenarme de versiones»*.

- El archivo NO se abre ni se arma: se guarda byte por byte y se entrega igual.
  Así el Power Query llega intacto y el owner lo actualiza como siempre.
- Un libro por título. Subir con un título que ya existe lo reemplaza y deja la
  versión anterior (una sola) para volver atrás.

    GET    /libros/                         → los libros (sin el archivo)
    GET    /libros/carpetas/                 → los sub-tabs y cuántos hay en cada uno
    GET    /libros/budget-package/          → el del botón (o {existe: false})
    GET    /libros/{id}/descargar/          → el archivo tal cual
    GET    /libros/{id}/descargar/anterior/ → la versión anterior
    POST   /libros/                         → subir o reemplazar — solo admin
    POST   /libros/{id}/volver-a-anterior/  → deshacer la última subida — solo admin
    POST   /libros/{id}/carpeta/            → moverlo de sub-tab — solo admin
    DELETE /libros/{id}/                    → quitarlo — solo admin

La **carpeta** solo ordena la vista: el repositorio sigue siendo uno y la llave
única sigue siendo `hotel_id + titulo`. Mover un libro no toca el archivo.
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
from app.models.libro_colgado import (CARPETA_POR_DEFECTO, CARPETAS,
                                      ORDEN_CARPETA, TITULO_BUDGET_PACKAGE,
                                      LibroColgado)

router = APIRouter(tags=["libros"])

#: El v13 pesa ~5 MB; con 40 hay aire sin abrir la puerta a cualquier cosa.
MAX_BYTES = 40 * 1024 * 1024
# Owner, 2026-11-26: «cambia para que acepte todo tipo de archivos» (quería subir el
# Resumen Ejecutivo en Word). Entra cualquier archivo; lo que lo hace seguro es cómo
# se ENTREGA: siempre como descarga (attachment) y con nosniff, así el navegador
# nunca abre ni ejecuta lo que se subió (un .html, por ejemplo) dentro de la app.
GENERICO = "application/octet-stream"


def tipo_de(nombre: str) -> str:
    """El tipo por la extensión (xlsx, docx, pdf, pptx…); si no se conoce, binario."""
    import mimetypes
    extra = {".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
             ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
             ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}
    ext = "." + nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    return extra.get(ext) or mimetypes.guess_type(nombre)[0] or GENERICO


def limpiar_titulo(titulo: str) -> str:
    return " ".join((titulo or "").split())[:160]


def limpiar_carpeta(carpeta: str | None) -> str:
    """La carpeta que mande el cliente, o la de por defecto si no la conoce.

    Cae en OTROS en vez de rebotar: una carpeta desconocida es un libro mal
    clasificado —se mueve con un clic— y no vale perder la subida por eso.
    """
    # Llamada derecho (las pruebas) y sin pasar el argumento: lo que llega es el
    # `Form(...)` de FastAPI, no un texto. Eso es «no dijo carpeta».
    if not isinstance(carpeta, str):
        return CARPETA_POR_DEFECTO
    c = carpeta.strip().upper()
    return c if c in CARPETAS else CARPETA_POR_DEFECTO


def _fila(l: LibroColgado) -> dict:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"id": l.id, "titulo": l.titulo,
            "carpeta": l.carpeta or CARPETA_POR_DEFECTO,
            "nombre_archivo": l.nombre_archivo,
            "tamano": l.tamano, "nota": l.nota, "subido_por": l.subido_por,
            "subido_el": iso(l.subido_el),
            "anterior": None if not l.anterior_nombre else {
                "nombre_archivo": l.anterior_nombre, "tamano": l.anterior_tamano,
                "subido_por": l.anterior_subido_por, "subido_el": iso(l.anterior_subido_el)}}


def _archivo(nombre: str, contenido: bytes) -> Response:
    nombre = (nombre or "archivo").replace('"', "")
    from urllib.parse import quote
    return Response(content=contenido, media_type=tipo_de(nombre),
                    headers={"Content-Disposition":
                             f"attachment; filename=\"{nombre.encode('ascii', 'replace').decode()}\"; "
                             f"filename*=UTF-8''{quote(nombre)}",
                             "X-Content-Type-Options": "nosniff"})


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
    # Por carpeta en el orden de los tabs y, adentro, el Budget Package primero
    # (es el del botón) y el resto por nombre.
    filas = sorted(filas, key=lambda l: (
        ORDEN_CARPETA.get(l.carpeta or CARPETA_POR_DEFECTO, len(ORDEN_CARPETA)),
        l.titulo != TITULO_BUDGET_PACKAGE, l.titulo.lower()))
    return [_fila(l) for l in filas]


@router.get("/libros/carpetas/")
async def listar_carpetas():
    """Los sub-tabs con su rótulo y cuántos libros tiene cada uno.

    Salen los cuatro siempre, con cero incluido: un tab que aparece y desaparece
    según si hay archivos obliga a adivinar dónde subir el primero.
    """
    async with get_session() as s:
        filas = (await s.execute(select(LibroColgado).where(
            LibroColgado.hotel_id == HOTEL_ID))).scalars().all()
    cuantos: dict[str, int] = {c: 0 for c in CARPETAS}
    for l in filas:
        cuantos[limpiar_carpeta(l.carpeta)] += 1
    return [{"clave": c, "rotulo": r, "libros": cuantos[c]} for c, r in CARPETAS.items()]


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
                      file: UploadFile = File(...),
                      user=Depends(get_current_admin),
                      # Último a propósito: las pruebas llaman por posición
                      # (titulo, nota, archivo, admin) y meterlo antes les
                      # correría los argumentos sin que nada avise.
                      carpeta: str = Form(CARPETA_POR_DEFECTO)):
    titulo = limpiar_titulo(titulo)
    if not titulo:
        raise ErrorApi(422, "libro.sin_titulo")
    contenido = await file.read()
    nombre = (file.filename or "archivo").replace("\\", "/").split("/")[-1][:200]
    if not contenido:
        raise ErrorApi(422, "libro.vacio")
    if len(contenido) > MAX_BYTES:
        raise ErrorApi(422, "libro.muy_grande")
    async with get_session() as s:
        l = (await s.execute(select(LibroColgado).options(undefer(LibroColgado.contenido))
             .where(LibroColgado.hotel_id == HOTEL_ID,
                    LibroColgado.titulo == titulo))).scalar_one_or_none()
        if l is None:
            l = LibroColgado(hotel_id=HOTEL_ID, titulo=titulo,
                             carpeta=limpiar_carpeta(carpeta))
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


@router.post("/libros/{libro_id}/carpeta/")
async def mover_libro(libro_id: str, carpeta: str = Form(...),
                      _=Depends(get_current_admin)):
    """Cambia de sub-tab un libro ya subido. No toca el archivo ni su anterior.

    Una carpeta que no existe sí rebota acá —a diferencia de la subida—: mover
    es un clic sobre una lista cerrada, así que un valor raro es un error de
    programación, no un libro mal clasificado.
    """
    c = (carpeta or "").strip().upper()
    if c not in CARPETAS:
        raise ErrorApi(422, "libro.carpeta_invalida", carpetas=", ".join(CARPETAS))
    async with get_session() as s:
        l = await _libro(s, libro_id)
        l.carpeta = c
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
