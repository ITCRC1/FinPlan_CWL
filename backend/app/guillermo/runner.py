# -*- coding: utf-8 -*-
"""La ronda de Guillermo (`docs/GUILLERMO.md` §2 y §15).

Un entry point: lo llama el cron de Railway, o una tarea de Windows si alguna
vez hace falta el agente local. El núcleo y las fuentes no cambian.

⚠️ **En modo sombra no escribe NADA en el modelo financiero.** Procesa, valida,
registra lo que habría hecho y late. Ése es el default, y subirlo a `assisted`
es una decisión humana que se toma en la pantalla.

⚠️ **La ronda late SIEMPRE, aunque falle.** El latido no dice «salió bien»,
dice «Guillermo corrió». Si sólo latiera al terminar bien, un fallo repetido se
vería igual que un worker muerto — y el dead-man switch, que existe justamente
para distinguirlos, no distinguiría nada.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.guillermo.core import (ArchivoVisto, Esperado, nivel_1_presencia,
                                nivel_2_periodo, transicionar)
from app.guillermo.sources import Periodo, ReportSource
from app.hotel_actual import HOTEL_ID
from app.importers.registro import checksum_de
from app.models.guillermo import (ExpectedReport, GuillermoConfig,
                                  GuillermoHeartbeat, ImportException)
from app.models.import_registro import ImportBatch, ImportFile


async def _config(db: AsyncSession) -> dict[str, str]:
    filas = (await db.execute(
        select(GuillermoConfig).where(GuillermoConfig.hotel_id == HOTEL_ID)
    )).scalars().all()
    return {f.clave: f.valor for f in filas}


async def _esperados(db: AsyncSession) -> list[Esperado]:
    filas = (await db.execute(
        select(ExpectedReport).where(ExpectedReport.hotel_id == HOTEL_ID,
                                     ExpectedReport.activo.is_(True))
    )).scalars().all()
    return [Esperado(f.report_id, f.patron, f.obligatorio, f.tamano_min)
            for f in filas]


async def correr_ronda(db: AsyncSession, fuente: ReportSource,
                       desde: date, hasta: date) -> dict:
    """Una ronda completa. Devuelve el resumen; el detalle queda en la base."""
    cfg = await _config(db)
    modo = cfg.get("autonomy_level", "shadow")

    lote = ImportBatch(
        hotel_id=HOTEL_ID, origen="guillermo", endpoint="ronda",
        estado="queued", modo=modo, disparado_por="guillermo",
    )
    db.add(lote)
    await db.flush()
    lote.estado = transicionar(lote.estado, "running")

    resultado, detalle = "ok", ""
    hallazgos: list = []
    try:
        traidos = fuente.fetch(Periodo(desde, hasta))

        # La traza de cada archivo, con su checksum, igual que en una subida
        # manual: la ronda no es una puerta distinta.
        vistos: list[ArchivoVisto] = []
        for a in traidos:
            db.add(ImportFile(
                batch_id=lote.id, hotel_id=HOTEL_ID, scenario_id=None,
                nombre=a.nombre[:255], checksum=checksum_de(a.contenido),
                tamano=len(a.contenido), subido_por="guillermo",
            ))
            # ⚠️ La fecha interna sale del PARSER de cada reporte, y hoy no hay
            # ninguno conectado (D-1/D-2). Va `None`, que el nivel 2 trata como
            # «no se pudo leer» — no como «coincide».
            vistos.append(ArchivoVisto(a.nombre, len(a.contenido), None))

        esperados = await _esperados(db)
        hallazgos = nivel_1_presencia(vistos, esperados)
        if all(h.pasa for h in hallazgos):
            hallazgos += nivel_2_periodo(vistos, desde, hasta)

        fallas = [h for h in hallazgos if not h.pasa]
        for h in fallas:
            db.add(ImportException(
                batch_id=lote.id, hotel_id=HOTEL_ID,
                tipo=f"nivel_{h.nivel}", valor_crudo=h.control[:400],
                # El «por qué» es obligatorio: puede decidir, pero no esconder.
                rationale=h.detalle,
            ))

        if fallas:
            lote.estado = transicionar(lote.estado, "pending_review")
            resultado = "con_excepciones"
            detalle = f"{len(fallas)} controles no pasaron"
        else:
            lote.estado = transicionar(lote.estado, "validated")
            # ⚠️ Sombra termina en `shadowed`, no en `imported`: no escribió.
            lote.estado = transicionar(
                lote.estado, "shadowed" if modo == "shadow" else "imported")
            detalle = f"{len(vistos)} archivos, todo en verde"

        lote.lineas_total = len(vistos)
        lote.lineas_pendientes = len(fallas)

    except Exception as e:                      # noqa: BLE001
        # Un fallo NO deja el batch colgado en `running`: quedaría contando como
        # «corriendo» para siempre y el semáforo diría que está trabajando.
        try:
            lote.estado = transicionar(lote.estado, "failed")
        except Exception:
            lote.estado = "failed"
        resultado, detalle = "fallo", str(e)[:2000]

    lote.terminado_en = datetime.now(timezone.utc)
    lote.detalle = detalle[:4000]

    # ⚠️ El latido va SIEMPRE, incluso cuando la ronda falló.
    db.add(GuillermoHeartbeat(hotel_id=HOTEL_ID, resultado=resultado,
                              detalle=detalle[:2000]))
    await db.commit()

    return {
        "batch_id": lote.id, "estado": lote.estado, "modo": modo,
        "resultado": resultado, "detalle": detalle,
        "controles": [{"nivel": h.nivel, "control": h.control,
                       "pasa": h.pasa, "detalle": h.detalle}
                      for h in hallazgos],
    }
