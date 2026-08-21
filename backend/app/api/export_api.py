"""Descarga a Excel de cualquier cuadro de la app, con el formato de la casa.

**Un solo endpoint para ~47 pantallas.** La pantalla manda el cuadro que ya
tiene renderizado y recibe el `.xlsx` armado. No hay que escribir —ni mantener—
un exportador por pantalla, y todas salen con el mismo estilo.

**Por qué la pantalla manda los datos y no los busca el servidor.** Porque lo
que el usuario quiere bajar es *lo que está viendo*: con su escenario, su mes,
su comparación y sus filtros. Recalcularlo acá sería reimplementar cada pantalla
en el backend y arriesgar que el Excel diga algo distinto de lo que estaba en
pantalla. Es el mismo camino que ya usa `owner_excel`.

**Lo que NO hace:** no toca la base, no recalcula, no persiste. Solo formatea.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.errores import ErrorApi
from app.export.cuadro_excel import FORMATOS, build_cuadros_workbook
from app.hotel_actual import hotel_slug

router = APIRouter(tags=["export"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_FILAS = 20_000       # techo de cordura: un cuadro más grande es un error


class Columna(BaseModel):
    label: str = ""
    ancho: float | None = None
    formato: str = "usd"


class Fila(BaseModel):
    label: str = ""
    nivel: int = 0
    es_total: bool = False
    # Pisa el formato de la columna. Para cuadros que mezclan unidades en la
    # misma columna (noches / ocupación % / ADR en dólares, una bajo la otra).
    formato: str | None = None
    # Números, no texto YA FORMATEADO: un Excel con "$1,234.00" como cadena no
    # se puede sumar ni graficar. `None` deja la celda vacía.
    #
    # Se admite `str` para lo que es texto de verdad — nombre de cuenta,
    # departamento, línea del P&L, modo de ruteo. Las pantallas de mapeo y de
    # control son casi todas de texto, y sin esto había que amontonar cuatro
    # datos dentro de la etiqueta de la fila. El orden del `|` importa: con
    # `str` primero, Pydantic convertiría los números a cadena y volveríamos al
    # problema que esto viene a evitar.
    valores: list[float | str | None] = Field(default_factory=list)


class Cuadro(BaseModel):
    titulo: str = "Cuadro"
    subtitulo: str | None = None
    hoja: str | None = None
    columnas: list[Columna] = Field(default_factory=list)
    filas: list[Fila] = Field(default_factory=list)


class ExportBody(BaseModel):
    archivo: str = "Reporte"
    cuadros: list[Cuadro] = Field(default_factory=list)


@router.post("/export/cuadros/")
async def exportar_cuadros(body: ExportBody):
    if not body.cuadros:
        raise ErrorApi(422, "export.sin_cuadros")
    total = sum(len(c.filas) for c in body.cuadros)
    if total > MAX_FILAS:
        raise ErrorApi(413, "export.demasiadas_filas", filas=f"{total:,}")

    malos = ({c.formato for cu in body.cuadros for c in cu.columnas}
             | {f.formato for cu in body.cuadros for f in cu.filas if f.formato}
             ) - set(FORMATOS)
    if malos:
        raise ErrorApi(422, "export.formato_desconocido",
                       malos=sorted(malos), validos=sorted(FORMATOS))

    # La primera columna es la etiqueta de la fila, así que a `valores` le
    # corresponden `len(columnas) - 1` celdas. Una fila con una de más se
    # perdería en silencio al armar el libro — y una columna que falta en el
    # Excel pero está en pantalla es exactamente el defecto que todo esto viene
    # a corregir. Que falle acá, con el nombre de la fila.
    for cu in body.cuadros:
        huecos = max(0, len(cu.columnas) - 1)
        for f in cu.filas:
            if len(f.valores) > huecos:
                raise ErrorApi(422, "export.fila_con_valores_de_mas",
                               cuadro=cu.titulo, fila=f.label,
                               valores=len(f.valores), huecos=huecos,
                               columnas=len(cu.columnas),
                               sobran=len(f.valores) - huecos)

    contenido = build_cuadros_workbook([c.model_dump() for c in body.cuadros])
    nombre = f"{body.archivo}_{hotel_slug()}.xlsx".replace(" ", "_")
    return Response(
        content=contenido, media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
