# -*- coding: utf-8 -*-
"""La columna «Commentary» del P&L Statement, escribible y guardada.

Owner, 2026-09-03: *«hay una celda al final del P&L que dice Commentary pero no
tiene forma para que sea editable»*.

Estaba dibujada y vacía: un `<td>` sin nada. Una columna que se ve pero no se
puede usar es peor que no tenerla — se lee como que el reporte perdió el
comentario, no como que nunca se pudo escribir.

## Se guarda, y por eso no es un campo suelto

Un comentario que se pierde al recargar es peor que ninguno: el que lo escribió
cree que quedó. Va a `annotations`, la tabla que este proyecto ya tiene para
esto («explicación de variación, se agrega en la narrativa a dueños»), con
`kind="comment"`.

## Con qué se identifica cada comentario

`(escenario, "pl", renglón, mes)`.

* **El escenario es el de la RANURA 1**, el que se está explicando. La columna
  es una sola para toda la fila y la fila compara tres versiones; el comentario
  responde «por qué MI actual dio esto», así que se ancla al actual y no al
  presupuesto contra el que se compara.
* **El mes es el del cierre.** El mismo comentario de julio no aplica a agosto,
  y guardarlo sin mes lo arrastraría a todos los cierres siguientes.

## Guardar es un UPSERT, y borrar es borrar

`POST /annotations/` siempre CREA. Para una celda que se edita en el lugar eso
dejaría una fila por cada vez que alguien corrige una coma, y la última en ganar
sería la que la consulta devuelva primero — o sea, al azar.

⚠️ Y vaciar la celda **borra**. Guardar una cadena vacía dejaría una fila
fantasma que el día de mañana alguien cuenta como «hay comentario».
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.errores import ErrorApi
from app.models.annotation import Annotation
from app.models.scenario import Scenario
from app.models.user import User

router = APIRouter(tags=["comentario-pl"])

#: La «sección» con la que se guardan estos comentarios.
#:
#: ⚠️ **No se agrega a `SECTIONS`**, que es el vocabulario de las ASIGNACIONES
#: —quién es responsable de qué—. Sumarle «pl» le inventaría a la pantalla de
#: colaboración una sección más, con su responsable y su estado, que nadie pidió.
SECCION = "pl"

LARGO_MAXIMO = 2000   # el de la columna


@router.get("/pl/{scenario_id}/comentarios/")
async def listar(
    scenario_id: str,
    mes: int = Query(..., ge=1, le=12),
    _u: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Los comentarios de ese escenario y ese mes: `{renglón: texto}`."""
    filas = (await db.execute(select(Annotation).where(
        Annotation.scenario_id == scenario_id,
        Annotation.section == SECCION,
        Annotation.month == mes,
    ).order_by(Annotation.created_at))).scalars().all()
    # El último gana. No debería haber dos —guardar es upsert— pero si un
    # guardado viejo dejó duplicados, mostrar el primero sería mostrar el
    # comentario que se corrigió.
    return {"scenario_id": scenario_id, "mes": mes,
            "comentarios": {a.ref: a.body for a in filas}}


class Cuerpo(BaseModel):
    ref: str
    mes: int
    texto: str


@router.put("/pl/{scenario_id}/comentarios/")
async def guardar(
    scenario_id: str, cuerpo: Cuerpo,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Guarda —o borra— el comentario de un renglón."""
    if await db.get(Scenario, scenario_id) is None:
        raise ErrorApi(404, "escenario.no_encontrado")
    if not 1 <= cuerpo.mes <= 12:
        raise ErrorApi(422, "mes.rango_invalido")
    ref = (cuerpo.ref or "").strip()
    if not ref:
        raise ErrorApi(422, "comentario.sin_renglon")
    texto = (cuerpo.texto or "").strip()[:LARGO_MAXIMO]

    existentes = (await db.execute(select(Annotation).where(
        Annotation.scenario_id == scenario_id,
        Annotation.section == SECCION,
        Annotation.ref == ref,
        Annotation.month == cuerpo.mes,
    ))).scalars().all()

    if not texto:
        # Vaciar la celda BORRA. Una fila con texto vacío es una fila fantasma
        # que alguien va a contar como «hay comentario».
        for a in existentes:
            await db.delete(a)
        await db.commit()
        return {"guardado": True, "texto": "", "borrado": len(existentes)}

    if existentes:
        # El primero se actualiza y los demás se van: si quedaron duplicados de
        # un guardado viejo, dejarlos haría que la próxima lectura devolviera
        # uno al azar.
        principal, sobrantes = existentes[0], existentes[1:]
        principal.body = texto
        principal.author_id = user.id
        for a in sobrantes:
            await db.delete(a)
    else:
        db.add(Annotation(
            scenario_id=scenario_id, section=SECCION, ref=ref,
            month=cuerpo.mes, kind="comment", body=texto, author_id=user.id))
    await db.commit()
    return {"guardado": True, "texto": texto}
