# -*- coding: utf-8 -*-
"""El informe operativo de variaciones, desde la aplicacion.

Owner, 2026-10-08: *«el tema es que yo ocupo seguir haciendolo mes a mes, escojo
el mes y genero la informacion»* y, sobre como llega el analisis: *«si solo
quiero que me generes los cuadros y despues lo subo aca y me lo analizas»*.

Asi que esto hace exactamente eso: **saca los cuadros y nada mas**. No llama a
ningun modelo, no inventa un numero y no necesita llave de API. El analisis —que
es juicio: que hallazgo va primero, si una favorabilidad es ahorro o
diferimiento, que se le pregunta a que gerente— se escribe aparte y queda
versionado en `app/informes/narrativa/`.

Si el mes ya tiene su analisis escrito, el documento sale completo. Si no, sale
con los 53 cuadros y marcas «[PENDIENTE]» en el texto, y la respuesta dice que
claves faltan.

⚠️ **El cuadre viaja en la cabecera de la respuesta.** `X-Informe-Cuadra` dice
si el GOP del reporte menos el del motor es exactamente el credito 4999 que el
tab descarta. Si dice `no`, hay otra causa y el informe no se publica hasta
entenderla. La especificacion completa esta en `informes/INFORME_OPERATIVO.md`.
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID

router = APIRouter(tags=["informes"])

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"]


@router.get("/informes/operativo/{anio}/{mes}/estado/")
async def estado(
    anio: int,
    mes: int,
    hotel: str = Query(HOTEL_ID),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Si el mes se puede armar, y con que.

    La pantalla lo consulta antes de ofrecer el boton: «setiembre no esta
    subido» es una respuesta; un documento vacio no.
    """
    from app.informes.armador import armar, cargar_narrativa, cuadre
    from app.informes.datos import Datos
    from app.informes.extraccion import FaltaDato, extraer

    try:
        corte = await extraer(db, anio, mes, hotel)
    except FaltaDato as e:
        return {"anio": anio, "mes": mes, "hay": False, "motivo": str(e)}

    D = Datos(anio, mes, corte)
    nar = cargar_narrativa(anio, mes)
    _doc, faltantes = armar(D, nar)
    return {
        "anio": anio, "mes": mes, "hay": True,
        "escenarios": corte["escenarios"],
        "avisos": corte["avisos"],
        "archivo_mayor": D.archivo_mayor,
        "lineas_mayor": len(corte["mayor"]),
        "con_analisis": not faltantes,
        "faltantes": faltantes,
        "cuadre": cuadre(D),
    }


@router.get("/informes/operativo/{anio}/{mes}/")
async def operativo(
    anio: int,
    mes: int,
    hotel: str = Query(HOTEL_ID),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """El documento. Los cuadros siempre; el analisis si esta escrito."""
    from app.informes.armador import armar, cuadre
    from app.informes.datos import Datos
    from app.informes.extraccion import FaltaDato, extraer

    try:
        corte = await extraer(db, anio, mes, hotel)
    except FaltaDato as e:
        raise ErrorApi(409, "informe.falta_dato", detalle=str(e))

    D = Datos(anio, mes, corte)
    doc, faltantes = armar(D)
    c = cuadre(D)

    buf = io.BytesIO()
    doc.save(buf)
    nombre = f"{hotel}_Informe_Operativo_{MESES[mes-1]}_{anio}.docx"
    return Response(
        buf.getvalue(),
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".wordprocessingml.document"),
        headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
            # El cuadre viaja con el archivo: quien lo baje puede verificarlo
            # sin volver a preguntar.
            "X-Informe-Cuadra": "si" if c["cuadra"] else "no",
            "X-Informe-GOP-Reporte": str(c["gop_reporte"]),
            "X-Informe-GOP-Motor": str(c["gop_motor"]),
            "X-Informe-Con-Analisis": "si" if not faltantes else "no",
            "Access-Control-Expose-Headers":
                ("X-Informe-Cuadra, X-Informe-GOP-Reporte, X-Informe-GOP-Motor, "
                 "X-Informe-Con-Analisis"),
        })
