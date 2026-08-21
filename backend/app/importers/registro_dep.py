# -*- coding: utf-8 -*-
"""La puerta única del registro de importaciones (Guillermo, Fase 0).

Se engancha en el **decorador** de la ruta, no en la firma:

    @router.post("/opex/{id}/import/excel/",
                 dependencies=[Depends(registro_de_subida)])

**Por qué así y no de 21 formas distintas.** Los 21 endpoints de subida leen su
archivo de maneras diferentes —`await file.read()` suelto, `await archivo.read()`,
o incrustado adentro de la llamada al parser—. Insertar una línea en cada uno
significa 21 ediciones distintas sobre 8 archivos, cada una con su forma. Acá el
mecanismo es **uno solo**, y las rutas nuevas se cubren agregando el mismo
`dependencies=[...]`.

⚠️ **No se usó middleware, aunque cubriría todo sin tocar nada.** Un middleware
que lee el cuerpo para calcular el checksum tiene que devolverle el stream al
endpoint, y con `BaseHTTPMiddleware` eso es frágil: si sale mal, **se rompen
TODAS las subidas a la vez**. Una dependencia falla de a una ruta y la atrapan
las pruebas.

⚠️ **`seek(0)` no es opcional.** Leer el `UploadFile` acá mueve el puntero; sin
devolverlo al principio, el `await file.read()` del endpoint devuelve **vacío** y
el import entra sin datos, sin fallar. Eso sería mucho peor que no tener
registro.
"""
from __future__ import annotations

from fastapi import Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.auth import get_current_user
from app.db import get_db
from app.errores import ErrorApi
from app.importers.registro import checksum_de, subida_previa
from app.hotel_actual import HOTEL_ID
from app.models.import_registro import ImportBatch, ImportFile


def _verdadero(v: str | None) -> bool:
    return (v or "").lower() in ("1", "true", "yes", "on")


def _escenario_de(request: Request) -> str | None:
    """El escenario destino: primero el de la ruta, después el de la query.

    ⚠️ Se lee del `request` y NO se declara como parámetro: en unos endpoints
    `scenario_id` viene en la ruta y en otros en la query, y declararlo acá
    chocaría con la firma de la mitad de ellos.
    """
    for clave in ("scenario_id", "id"):
        v = request.path_params.get(clave)
        if v:
            return str(v)
    return request.query_params.get("scenario_id") or None


async def registro_de_subida(
    request: Request,
    # ⚠️ Es el ÚNICO parámetro que se declara. El nombre no lo usa ningún
    # endpoint, así que no puede chocar con ninguna firma existente.
    permitir_reimport: bool = Query(
        False,
        description="Subir igual un archivo cuyo contenido ya se importó antes"),
    db: AsyncSession = Depends(get_db),
    usuario=Depends(get_current_user),
) -> None:
    """Registra los archivos de la petición y frena el reimport.

    Lanza `ErrorApi(409, "import.ya_subido")` si el contenido ya entró a este
    escenario. Cualquier otro problema del registro se traga: **un registro
    roto no puede tumbar una carga que funcionaba.**
    """
    # Un `dry_run` no importó nada. Registrarlo haría que el archivo real
    # después chocara contra su propia sombra.
    if _verdadero(request.query_params.get("dry_run")):
        return

    try:
        form = await request.form()
    except Exception:
        return

    archivos = [(k, v) for k, v in form.multi_items()
                if isinstance(v, StarletteUploadFile)]
    if not archivos:
        return

    scenario_id = _escenario_de(request)
    email = getattr(usuario, "email", "") or ""
    ruta = request.url.path[:120]

    leidos: list[tuple[str, str, int]] = []   # (nombre, checksum, tamaño)
    for _campo, up in archivos:
        try:
            data = await up.read()
            # ⚠️ Sin esto el endpoint lee VACÍO y el import entra sin datos.
            await up.seek(0)
        except Exception:
            continue
        if not data:
            continue
        suma = checksum_de(data)
        previa = await subida_previa(db, suma, scenario_id)
        if previa is not None and not permitir_reimport:
            raise ErrorApi(
                409, "import.ya_subido",
                detalle=(f"«{previa.nombre or up.filename}» ya se importó "
                         f"el {previa.creado_en:%Y-%m-%d %H:%M} "
                         f"por {previa.subido_por or 'desconocido'}. "
                         f"Es el mismo contenido, no sólo el mismo nombre. "
                         f"Para subirlo igual: permitir_reimport=true"))
        leidos.append((up.filename or "", suma, len(data)))

    if not leidos:
        return

    try:
        lote = ImportBatch(
            hotel_id=HOTEL_ID, scenario_id=scenario_id, origen="manual",
            endpoint=ruta, estado="running", modo="assisted",
            disparado_por=email,
        )
        db.add(lote)
        await db.flush()
        for nombre, suma, tam in leidos:
            db.add(ImportFile(
                batch_id=lote.id, hotel_id=HOTEL_ID, scenario_id=scenario_id,
                nombre=nombre[:255], checksum=suma, tamano=tam,
                subido_por=email,
            ))
        await db.flush()
    except ErrorApi:
        raise
    except Exception:
        # La traza se pierde, el dato no. Es el orden correcto de prioridades.
        return
