# -*- coding: utf-8 -*-
"""Subir el detalle del mayor y recibir las discrepancias.

Owner, 2026-10-05: *«que herramienta puedes hacerme para yo solo subir el
archivo en este detalle y me salgan automaticamente la auditoria con las
discrepancias»*.

**No guarda nada.** Se sube, se revisa y se devuelve: no hay escenario, no hay
tabla, no se toca el P&L. Es a proposito — esto es una lupa sobre un archivo,
no una carga. Guardarlo obligaria a decidir que pasa cuando el mismo mes se
sube dos veces, y la respuesta correcta («nada, mostrame otra vez») no necesita
base de datos.

Por eso tampoco pasa por `registro_de_subida`: ese registro existe para saber
que archivo dejo que numero adentro, y aca no entra ningun numero.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response

from app.auth import get_current_user
from app.engine import auditoria_gl
from app.errores import ErrorApi
from app.export.auditoria_gl_xlsx import QUE_MIRA, construir
from app.importers.balance_comprobacion import leer

router = APIRouter(tags=["auditoria-gl"])

#: 25 MB. El de setiembre pesa 1,5 MB con 8.852 lineas; con margen de sobra para
#: un ano entero. Un archivo mas grande que esto no es el reporte que se espera.
MAXIMO = 25 * 1024 * 1024


async def _revisar(archivo: UploadFile, desde_clase: int):
    contenido = await archivo.read()
    if not contenido:
        raise ErrorApi(422, "auditoria.archivo_vacio")
    if len(contenido) > MAXIMO:
        raise ErrorApi(422, "auditoria.archivo_muy_grande")
    try:
        leido = leer(contenido)
    except Exception as e:                       # noqa: BLE001
        raise ErrorApi(422, "auditoria.no_se_pudo_leer", detalle=str(e)[:200]) from e
    if not leido.lineas:
        raise ErrorApi(422, "auditoria.sin_lineas")
    return leido, auditoria_gl.revisar(leido.lineas, desde_clase, leido.periodo)


@router.post("/auditoria-gl/revisar/")
async def revisar(
    file: UploadFile = File(...),
    #: El owner revisa «las cuentas que empiezan con 4 en adelante». Se deja
    #: mover por si alguna vez quiere mirar el balance tambien.
    desde_clase: int = Query(4, ge=1, le=9),
    user=Depends(get_current_user),
):
    leido, r = await _revisar(file, desde_clase)
    return {
        "archivo": file.filename,
        "titulo": leido.titulo,
        "periodo": r.periodo,
        "moneda": leido.moneda,
        "hojas": leido.hojas,
        "lineas_del_archivo": r.lineas_del_archivo,
        "lineas_revisadas": r.lineas_revisadas,
        "lineas_senaladas": r.lineas_senaladas,
        "monto_en_revision_crc": r.monto_en_revision_crc,
        "por_regla": r.por_regla,
        "por_severidad": r.por_severidad,
        # ⚠️ El corte por tipo de cuenta. Se quedo fuera de la respuesta y la
        # pantalla lo lee sin preguntar (`Object.entries(data.por_grupo)`), asi
        # que TODA subida exitosa terminaba en «Esta pantalla no se pudo
        # dibujar · Cannot convert undefined or null to object» — owner,
        # 2026-10-06. El motor siempre lo calculo; faltaba mandarlo.
        "por_grupo": r.por_grupo,
        # Solo lo que esta regla encontro: explicar reglas que no dispararon
        # llena la pantalla de texto que no corresponde a nada en la tabla.
        "que_mira": {k: v for k, v in QUE_MIRA.items() if k in r.por_regla},
        "hallazgos": [h.dict() for h in r.hallazgos],
    }


@router.post("/auditoria-gl/excel/")
async def excel(
    file: UploadFile = File(...),
    desde_clase: int = Query(4, ge=1, le=9),
    user=Depends(get_current_user),
):
    """El mismo analisis, como hoja de trabajo para revisar fuera de la pantalla."""
    _leido, r = await _revisar(file, desde_clase)
    nombre = "Auditoria_Detalle_{}.xlsx".format(
        (r.periodo or "mayor").replace(" ", "").replace("-", "_"))
    return Response(
        construir(r, archivo=file.filename or ""),
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": 'attachment; filename="{}"'.format(nombre)})
