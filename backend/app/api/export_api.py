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
from app.export.cierre_word import DOCX, build_cierre_docx
from app.export.cuadro_excel import FORMATOS, build_cuadros_workbook
from app.hotel_actual import HOTEL_NAME, hotel_slug

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


class FilaKpi(BaseModel):
    """Un renglón de la franja de estadísticas: el rótulo y un valor por
    versión."""
    label: str = ""
    valores: list[float | str | None] = Field(default_factory=list)


class Cuadro(BaseModel):
    titulo: str = "Cuadro"
    subtitulo: str | None = None
    hoja: str | None = None
    columnas: list[Columna] = Field(default_factory=list)
    filas: list[Fila] = Field(default_factory=list)
    #: Las notas ya escritas, para que el Word las imprima DENTRO del recuadro
    #: de comentarios.
    #:
    #: ⚠️ **Tiene que estar declarado acá o no llega.** Pydantic descarta en
    #: silencio los campos que el modelo no conoce: la pantalla las mandaba, el
    #: generador sabía imprimirlas, y en el medio se caían sin que nada fallara
    #: — el documento salía con el recuadro vacío (owner, 2026-09-03: «las
    #: notas no salen»).
    comentarios: list[str] = Field(default_factory=list)
    #: La franja de estadísticas, como cabecera del cuadro.
    #:
    #: ⚠️ Igual que `comentarios`: si el modelo no lo declara, Pydantic lo
    #: descarta en silencio y el documento sale sin la franja sin que nada
    #: falle. Ya pasó una vez con las notas.
    kpis: list[FilaKpi] = Field(default_factory=list)
    kpis_columnas: list[str] = Field(default_factory=list)


class ExportBody(BaseModel):
    archivo: str = "Reporte"
    cuadros: list[Cuadro] = Field(default_factory=list)


class WordBody(ExportBody):
    """Lo mismo que el Excel, mas lo que necesita la PORTADA.

    Hereda a proposito: el cuadro es el mismo objeto que ya arma cada pantalla,
    asi que un reporte que se puede bajar a Excel se puede meter en el Word sin
    escribir nada nuevo.
    """
    titulo: str = "Reporte de cierre"
    periodo: str = ""
    versiones: str = ""
    #: Los sub-tabs que la pantalla NO pudo incluir, con el motivo. Se imprimen
    #: en la portada: un índice de diez cuadros se ve completo aunque falten
    #: cuatro, y el que recibe el archivo por correo no tiene otra forma de
    #: saberlo (owner, 2026-09-03: «no todos los tabs salen»).
    omitidos: list[str] = Field(default_factory=list)


def _validar(body: ExportBody) -> None:
    """Lo que NO se puede exportar, en un solo lugar.

    El Excel y el Word tienen que rechazar lo mismo: si uno aceptara un cuadro
    que el otro no, habria formas de bajar un documento con una columna de mas
    que nadie revisa.
    """
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

@router.post("/export/cuadros/")
async def exportar_cuadros(body: ExportBody):
    _validar(body)
    contenido = build_cuadros_workbook([c.model_dump() for c in body.cuadros])
    nombre = f"{body.archivo}_{hotel_slug()}.xlsx".replace(" ", "_")
    return Response(
        content=contenido, media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.post("/export/cuadros/word/")
async def exportar_word(body: WordBody):
    """El reporte de cierre en Word, con espacio para comentar cada cuadro.

    Owner, 2026-09-02: *«un documento Word con todos los tabs activos… dejá
    espacio entre los tabs para poder comentar… y siempre deben salir los tabs
    que estén activos en la vista»*.

    ⚠️ **Lo de «los que estén activos» sale gratis y por eso no hay codigo que
    lo resuelva.** La pantalla manda los cuadros que dibuja, y dibuja
    exactamente los que quedaron activos en el panel de Vistas. Filtrar acá por
    `tab_enablement` seria una segunda lectura de la misma decision: el dia que
    las dos difieran, el documento diria una cosa y la pantalla otra.
    """
    _validar(body)
    contenido = build_cierre_docx(
        [c.model_dump() for c in body.cuadros],
        propiedad=HOTEL_NAME, titulo=body.titulo,
        periodo=body.periodo, versiones=body.versiones,
        omitidos=body.omitidos)
    nombre = f"{body.archivo}_{hotel_slug()}.docx".replace(" ", "_")
    return Response(
        content=contenido, media_type=DOCX,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
