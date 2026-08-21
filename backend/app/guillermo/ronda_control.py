# -*- coding: utf-8 -*-
"""La ronda de control — recorre, encuentra y **acumula** en la cola.

Pedido del owner (2026-08-20): «pongo a recorrer y que vaya acumulando esas
notas para después ir resolviendo uno a uno».

⚠️ **Esta ronda no necesita archivos.** La otra (`runner.correr_ronda`) espera
que una fuente le traiga XML, y hoy no hay ninguna conectada. Ésta recorre lo
que YA se puede verificar contra la base —qué falta subir y si los auxiliares
amarran con el GL— y deja cada hallazgo escrito. Eso la vuelve útil hoy, no el
día que se resuelvan D-2 y D-4.

⚠️ **No duplica.** Corriendo todos los días, un hallazgo que sigue abierto
crearía una nota nueva cada mañana y en una semana la cola tendría treinta y
cinco copias del mismo problema. Se reconoce por (tipo + valor) entre las
pendientes y se deja la que ya está.

⚠️ **Y cierra sola lo que se resolvió.** Si el owner sube junio, la nota que
decía «falta junio» no puede quedar esperando que alguien la marque a mano —
eso enseña a ignorar la cola. Se marca `approved` con quién la resolvió:
«se resolvió solo».
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.guillermo.core import transicionar
from app.models.guillermo import GuillermoHeartbeat, ImportException
from app.models.import_registro import ImportBatch

# Los tipos que produce esta ronda. Sirven para saber qué notas son suyas y
# cuáles vinieron de un import — no puede cerrar las ajenas.
TIPOS = ("falta_subir", "no_cuadra", "opera_no_cuadra")


async def _pendientes_mias(db: AsyncSession, hotel_id: str) -> dict[str, ImportException]:
    filas = (await db.execute(
        select(ImportException).where(
            ImportException.hotel_id == hotel_id,
            ImportException.estado == "pending",
            ImportException.tipo.in_(TIPOS))
    )).scalars().all()
    return {f"{f.tipo}|{f.valor_crudo}": f for f in filas}


async def ronda_de_control(db: AsyncSession, hotel_id: str,
                           disparado_por: str = "guillermo") -> dict:
    """Recorre, escribe lo nuevo, cierra lo resuelto y late."""
    from app.guillermo.cuadre import cuadre_de_todos, que_hacer
    from app.guillermo.faltantes import que_falta

    lote = ImportBatch(
        hotel_id=hotel_id, origen="guillermo", endpoint="ronda-de-control",
        estado="queued", modo="control", disparado_por=disparado_por)
    db.add(lote)
    await db.flush()
    lote.estado = transicionar(lote.estado, "running")

    abiertas = await _pendientes_mias(db, hotel_id)
    vistas: set[str] = set()
    nuevas = 0
    resultado, detalle = "ok", ""

    try:
        # ── Qué falta subir ──────────────────────────────────────────────────
        for f in await que_falta(db, hotel_id):
            if f.al_dia:
                continue
            clave = f"falta_subir|{f.etiqueta}"
            vistas.add(clave)
            if clave in abiertas:
                # Ya estaba anotada. Se actualiza el texto por si cambió el
                # detalle (de «falta junio» a «falta junio, julio»).
                abiertas[clave].rationale = f.mensaje
                continue
            db.add(ImportException(
                batch_id=lote.id, hotel_id=hotel_id, tipo="falta_subir",
                valor_crudo=f.etiqueta[:400],
                valor_normalizado=f.report_id[:400],
                # ⚠️ El «por qué» es obligatorio por el principio rector.
                rationale=f"{f.mensaje} · medido por {f.como_se_mide}",
            ))
            nuevas += 1

        # ── Los auxiliares contra el GL ──────────────────────────────────────
        todos = await cuadre_de_todos(db)
        sin_verificar = [c for c in todos if c.estado == "sin_verificar"]

        for c in todos:
            if c.estado != "no_cuadra":
                continue
            # ⚠️ Un descuadre YA documentado no vuelve a la cola cada día: ya
            # se decidió qué hacer con él. Sigue visible en la pantalla del
            # cuadre, que es donde corresponde.
            if c.conocida:
                continue
            clave = f"no_cuadra|{c.escenario}"
            vistas.add(clave)
            if clave in abiertas:
                continue
            peor = max(c.diferencias, key=lambda d: abs(d["diferencia"]))
            db.add(ImportException(
                batch_id=lote.id, hotel_id=hotel_id, tipo="no_cuadra",
                valor_crudo=c.escenario[:400], valor_normalizado=c.estado[:400],
                # ⚠️ La nota lleva LA ACCIÓN, no sólo el número. «Descuadra
                # $199.667,97» manda a investigar; «subí el resumen de junio»
                # se resuelve en un minuto.
                rationale=(f"descuadra en {len(c.diferencias)} totales de "
                           f"control; el peor es {peor['total']} por "
                           f"${abs(peor['diferencia']):,.2f}. {que_hacer(c)}"),
            ))
            nuevas += 1

        # ⚠️ **Los «no se puede verificar» van en UNA nota, no en catorce.**
        # Son todos el mismo hecho —los presupuestos no tienen detalle del
        # mayor— y una sola decisión los resuelve a todos. Catorce notas
        # idénticas no se atienden una por una: se aprenden a saltear, y con
        # ellas se saltea la que sí era distinta.
        if sin_verificar:
            clave = "no_cuadra|sin detalle del mayor"
            vistas.add(clave)
            cuales = ", ".join(c.escenario for c in sin_verificar[:4])
            resto = (f" y {len(sin_verificar) - 4} más"
                     if len(sin_verificar) > 4 else "")
            texto = (f"{len(sin_verificar)} escenarios no se pueden verificar "
                     f"contra el GL: no tienen detalle del mayor contra el cual "
                     f"comparar ({cuales}{resto}). No es que cuadren — es que "
                     f"nadie comparó nada.")
            if clave in abiertas:
                abiertas[clave].rationale = texto
            else:
                db.add(ImportException(
                    batch_id=lote.id, hotel_id=hotel_id, tipo="no_cuadra",
                    valor_crudo="sin detalle del mayor",
                    valor_normalizado="sin_verificar", rationale=texto,
                ))
                nuevas += 1

        # ── Nivel 3 · los reportes de Opera entre sí (pendiente 22) ─────────
        #
        # ⚠️ Es lo que el spec llama «lo que distingue *los archivos están* de
        # *los datos sirven*». Country Mix, Channel Mix y On the Books salen
        # del MISMO XML: si un mes no dice lo mismo en los tres, uno está mal.
        from app.guillermo.cuadre_opera import resumen_opera
        from app.models.scenario import Scenario as _Sc

        escenarios = (await db.execute(
            select(_Sc).where(_Sc.hotel_id == hotel_id))).scalars().all()
        for sc in escenarios:
            r = await resumen_opera(db, sc, hotel_id)
            for par in r.descuadres:
                # ⚠️ La nota se identifica por escenario + par + mes. Sin el
                # mes, dos meses distintos del mismo par se pisarían y sólo
                # quedaría uno en la cola.
                etiqueta = (f"{r.escenario} · mes {par.mes} · "
                            f"{par.izquierda} vs {par.derecha}")
                clave = f"opera_no_cuadra|{etiqueta}"
                vistas.add(clave)
                if clave in abiertas:
                    abiertas[clave].rationale = par.motivo
                    continue
                db.add(ImportException(
                    batch_id=lote.id, hotel_id=hotel_id,
                    tipo="opera_no_cuadra", valor_crudo=etiqueta[:400],
                    valor_normalizado="nivel_3",
                    rationale=(f"{par.motivo}. Los dos salen del mismo XML de "
                               f"Opera, así que uno de los dos está mal."),
                ))
                nuevas += 1

        # ── Lo que ya no aparece, se cierra solo ─────────────────────────────
        cerradas = 0
        for clave, x in abiertas.items():
            if clave in vistas:
                continue
            x.estado = "approved"
            x.resuelto_por = "se resolvió solo"
            x.resuelto_en = datetime.now(timezone.utc)
            cerradas += 1

        lote.lineas_total = len(vistas)
        lote.lineas_pendientes = len(vistas)
        lote.estado = transicionar(lote.estado, "validated")
        # ⚠️ Esta ronda no escribe en el modelo financiero: sólo anota. Su
        # terminal es `shadowed` aunque el nivel sea alto.
        lote.estado = transicionar(lote.estado, "shadowed")
        detalle = (f"{len(vistas)} hallazgos abiertos · {nuevas} nuevos · "
                   f"{cerradas} se resolvieron")
        if vistas:
            resultado = "con_excepciones"

    except Exception as e:                          # noqa: BLE001
        try:
            lote.estado = transicionar(lote.estado, "failed")
        except Exception:
            lote.estado = "failed"
        resultado, detalle = "fallo", str(e)[:2000]
        cerradas = 0

    lote.terminado_en = datetime.now(timezone.utc)
    lote.detalle = detalle[:4000]
    # ⚠️ El latido va SIEMPRE, también cuando la ronda falló: dice «corrió», no
    # «salió bien». Si sólo latiera al terminar bien, un fallo repetido se
    # vería igual que un worker muerto.
    db.add(GuillermoHeartbeat(hotel_id=hotel_id, resultado=resultado,
                              detalle=detalle[:2000]))
    await db.commit()

    return {"batch_id": lote.id, "estado": lote.estado, "resultado": resultado,
            "detalle": detalle, "nuevas": nuevas, "cerradas": cerradas,
            "abiertas": len(vistas)}
