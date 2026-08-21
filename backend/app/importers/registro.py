# -*- coding: utf-8 -*-
"""Registrar una subida y detectar el reimport (Guillermo, Fase 0).

Una función, dos efectos: deja la traza de qué archivo entró, y frena el mismo
archivo si ya entró antes al mismo escenario.

**Cómo se engancha.** Una línea al principio del endpoint, justo después de
`await file.read()` y ANTES de parsear:

    lote = await registrar_subida(
        db, data, file.filename, scenario_id=sc.id,
        endpoint="import-gl-detail", usuario=..., permitir_reimport=...)

⚠️ **No cambia el comportamiento de ningún import**, salvo el 409 del reimport
— que se pasa con un flag explícito, igual que `confirmar_diferencias`. Si algo
de acá falla, el import **sigue**: un registro roto no puede tumbar una carga
que funcionaba. Se registra el fallo y se avanza.

⚠️ **El `dry_run` NO registra.** Una previsualización no importó nada; anotarla
como archivo entrado haría que el archivo real después chocara contra su propia
sombra.
"""
from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID
from app.models.import_registro import ImportBatch, ImportFile


def checksum_de(data: bytes) -> str:
    """sha256 del CONTENIDO.

    ⚠️ Del contenido y no del nombre: renombrar no convierte un archivo en
    otro, y «actuales_julio (2).xlsx» es la forma más común de reimportar sin
    querer.
    """
    return hashlib.sha256(data).hexdigest()


async def subida_previa(db: AsyncSession, checksum: str,
                        scenario_id: str | None) -> ImportFile | None:
    """El registro anterior de ESTE archivo en ESTE escenario, si existe.

    ⚠️ **Éste es el chequeo de verdad, no el `UNIQUE` de la tabla.** En
    Postgres dos NULL no chocan entre sí, así que
    `UNIQUE (hotel_id, scenario_id, checksum)` **no deduplica** cuando el
    escenario viene vacío — y viene vacío en el camino más usado, donde el
    escenario destino se resuelve bloque por bloque adentro del importador.

    Acá `== None` se traduce a `IS NULL`, que sí compara. El constraint queda
    como red de abajo para el caso con escenario.
    """
    q = select(ImportFile).where(
        ImportFile.hotel_id == HOTEL_ID,
        ImportFile.checksum == checksum,
        ImportFile.scenario_id == scenario_id,
    )
    return (await db.execute(q)).scalars().first()


async def registrar_subida(
    db: AsyncSession,
    data: bytes,
    nombre: str | None,
    *,
    scenario_id: str | None = None,
    endpoint: str = "",
    usuario: str = "",
    origen: str = "manual",
    permitir_reimport: bool = False,
    dry_run: bool = False,
) -> ImportBatch | None:
    """Registra la subida. Devuelve el batch, o `None` si no se registró.

    Lanza `ErrorApi(409, "import.ya_subido")` si el archivo ya entró a este
    escenario y `permitir_reimport` es False.
    """
    if dry_run:
        # Una previsualización no importó nada.
        return None

    try:
        suma = checksum_de(data)
    except Exception:
        return None

    previa = await subida_previa(db, suma, scenario_id)
    if previa is not None and not permitir_reimport:
        # ⚠️ 409 con el MOTIVO adentro —cuándo entró y quién lo subió—, no un
        # «duplicado» pelado. Quien lo reciba tiene que poder decidir si es el
        # mismo archivo por error o el archivo corregido.
        raise ErrorApi(
            409, "import.ya_subido",
            detalle=(f"«{previa.nombre or nombre}» ya se importó "
                     f"el {previa.creado_en:%Y-%m-%d %H:%M} "
                     f"por {previa.subido_por or 'desconocido'}. "
                     f"Es el mismo contenido, no solo el mismo nombre. "
                     f"Para subirlo igual: permitir_reimport=true"))

    try:
        lote = ImportBatch(
            hotel_id=HOTEL_ID, scenario_id=scenario_id, origen=origen,
            endpoint=endpoint, estado="running", modo="assisted",
            disparado_por=usuario,
        )
        db.add(lote)
        await db.flush()
        db.add(ImportFile(
            batch_id=lote.id, hotel_id=HOTEL_ID, scenario_id=scenario_id,
            nombre=(nombre or "")[:255], checksum=suma, tamano=len(data),
            subido_por=usuario,
        ))
        await db.flush()
        return lote
    except ErrorApi:
        raise
    except Exception:
        # ⚠️ Un registro roto NO puede tumbar una carga que funcionaba. El
        # import sigue; lo que se pierde es la traza, no el dato.
        return None


async def cerrar_lote(db: AsyncSession, lote: ImportBatch | None, *,
                      estado: str = "imported", lineas: int = 0,
                      detalle: str = "") -> None:
    """Marca el batch como terminado. Nunca lanza."""
    if lote is None:
        return
    try:
        from datetime import datetime, timezone
        lote.estado = estado
        lote.lineas_total = lineas
        lote.detalle = (detalle or "")[:4000]
        lote.terminado_en = datetime.now(timezone.utc)
        await db.flush()
    except Exception:
        return
