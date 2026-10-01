"""
Shared styles and helpers for all FinPlan CWL Excel exporters.
"""
from __future__ import annotations

import io
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

MONTHS_ES = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
             "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"]

# ── Shared color palette ───────────────────────────────────────────────────────

C = {
    "navy":        "1A3A5C",
    "navy_mid":    "2D5A9E",
    "blue_light":  "EBF3FB",
    "blue_header": "F0F4F8",
    # ── La paleta de junta (owner, 2026-09-30) ───────────────────────────
    #
    # *«debe verse profesional para una junta. colores pasteles y bien
    # profesional»*.
    #
    # ⚠️ **Pastel no es claro a secas: es poco saturado.** Un azul clarito pero
    # vivo compite con los números; estos tonos se apoyan en el papel y dejan que
    # la cifra sea lo primero que se lee. Y todos pasan el contraste con texto
    # oscuro, que es lo que hace que sigan leyéndose impresos en blanco y negro.
    "banda_seccion": "E7EDF2",   #: encabezado de sección — azul pizarra pálido
    "banda_total":   "D8E4EE",   #: fila de total — un punto más de color
    "raya":          "C7D2DD",   #: la rejilla fina
    "marco":         "000000",   #: el recuadro de los totales
    "tinta":         "1A1A2E",   #: el texto de los totales
    #: La fila alterna. ⚠️ Tiene que verse IMPRESA: con `F7F9FB` se adivinaba en
    #: pantalla y en papel desaparecía, que es justo donde un checkbook de trece
    #: columnas necesita que el ojo no se salte de renglón. Y tiene que quedar
    #: claramente por debajo de `banda_seccion`, o una fila normal se confunde
    #: con un encabezado de bloque.
    "cebra":         "F2F6FA",
    #: ── Los dos tonos de encabezado de los cuadros que se bajan ──────────
    #:
    #: ⚠️ Son PROPIOS y no `navy` / `navy_mid`: esos dos los usan una docena de
    #: exportadores viejos, y bajarles la saturación acá les cambiaría el
    #: formato a todos de rebote. El azul de `navy_mid` (2D5A9E) es el azul
    #: vivo de una plantilla de oficina; al lado de una banda pastel canta.
    "cab_titulo":  "2E4A62",     #: la banda del título, pizarra profunda
    #: ── La cabecera de columnas ──────────────────────────────────────────
    #:
    #: Owner, 2026-09-30, con una captura de cómo la quiere: *«no sé si ese azul
    #: funciona, podrías quizás bajarle el tono un poco para que se vea más
    #: nítido»*.
    #:
    #: ⚠️ **Se invirtió: fondo claro y letra oscura.** Era un azul medio con la
    #: letra en blanco, y a 10 pt el blanco sobre color pierde definición —es
    #: justo lo que el owner llama «no se ve nítido»—. La referencia que mandó
    #: es cabecera clara con el rótulo en azul y el período en negro.
    "cab_tabla":   "EDF1F6",     #: el relleno de la cabecera, casi papel
    "cab_texto":   "1F3D5C",     #: el rótulo de la versión, azul de tinta
    "cab_sub":     "2B2B2B",     #: el período, debajo, en negro
    #: El relleno de las filas de TOTAL en los cuadros que se bajan.
    #:
    #: Owner, 2026-09-30: *«quiero que todos los que son totales bajen con el
    #: relleno bien claro»*. `blue_header` (F0F4F8) es tan pálido que sobre el
    #: blanco de Excel no se distingue: en pantalla se adivina y al imprimir en
    #: blanco y negro desaparece, y entonces un total se lee como una fila más.
    #:
    #: ⚠️ Claro pero VISIBLE. Un total oscuro obligaría a poner el texto en
    #: blanco y el cuadro pasaría a tener tantas bandas como bloques.
    #:
    #: ⚠️ **Es el mismo valor que `banda_total`, y tiene que seguir siéndolo.**
    #: Son dos nombres del mismo relleno —uno viejo, uno de la paleta de junta—.
    #: Cuando se retocó la paleta sólo se movió `banda_total` y quedaron dos
    #: azules casi iguales conviviendo en la misma hoja. Se define abajo, fuera
    #: del literal, para que no se puedan separar otra vez.
    "total_fill":  "",
    "white":       "FFFFFF",
    "text_dark":   "1A1A2E",
    "text_mid":    "4A5568",
    "gray_light":  "F8F9FA",
    "border":      "CBD5E0",
    "green_dark":  "1A5C3A",
    "amber":       "92400E",
    "amber_light": "FEF3C7",
    "teal_dark":   "0D5E5E",
    "teal_light":  "E0F7F7",
}


#: Un solo relleno para los totales, con sus dos nombres. Ver `total_fill`.
C["total_fill"] = C["banda_total"]


def fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


def font(bold=False, color="1A1A2E", size=10, italic=False,
         underline=None) -> Font:
    return Font(name="Calibri", bold=bold, color=color, size=size,
                italic=italic, underline=underline)


def marco_total(izq: bool, der: bool, color_marco=None,
                color_raya=None) -> Border:
    """El borde de una celda de fila TOTAL.

    Owner, 2026-09-30, mostrando el tab que arregló a mano: recuadro exterior
    NEGRO medio arriba, abajo y en los extremos; las verticales internas finas y
    grises, como el resto.

    ⚠️ Es por celda y no por fila: sólo la primera lleva el negro a la izquierda
    y sólo la última a la derecha. Poniéndolo en todas, el total sale con la
    rejilla negra y parece otra tabla.
    """
    # ⚠️ Los colores salen de la PALETA, no de un literal en la firma. Estaban
    # escritos a mano —«000000», «CBD5E0»— y al retocar la paleta quedaron dos
    # grises casi iguales conviviendo en la misma hoja sin que nada fallara.
    n = Side(style="medium", color=color_marco or C["marco"])
    f = Side(style="thin", color=color_raya or C["raya"])
    return Border(top=n, bottom=n, left=n if izq else f, right=n if der else f)


def border(color=None, sides="all") -> Border:
    color = color or C["raya"]      # la misma raya de la paleta, no un literal
    s = Side(style="thin", color=color)
    m = Side(style="medium", color=color)
    n = Side(style=None)
    if sides == "all":
        return Border(left=s, right=s, top=s, bottom=s)
    if sides == "bottom":
        return Border(bottom=s)
    if sides == "top":
        return Border(top=m)
    if sides == "top_bottom":
        return Border(top=s, bottom=s)
    # La rejilla completa, con la raya de arriba MARCADA: es como se cierra un
    # bloque en un estado de resultados impreso. Con el relleno solo, dos
    # totales seguidos se leen como una sola banda.
    if sides == "all_top":
        return Border(left=s, right=s, top=m, bottom=s)
    return Border()


def align(h="left", v="center", wrap=False) -> Alignment:
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)


def merged_header(ws, row: int, col_start: int, col_end: int,
                  text: str, bg: str, fg: str = "FFFFFF", sz: int = 12) -> None:
    """Write a merged cell spanning col_start..col_end on given row."""
    ws.merge_cells(
        start_row=row, start_column=col_start,
        end_row=row, end_column=col_end,
    )
    cell = ws.cell(row=row, column=col_start, value=text)
    cell.fill = fill(bg)
    cell.font = font(bold=True, color=fg, size=sz)
    cell.alignment = align("center")


def month_header_row(ws, row: int, first_col: int, total_col: int | None = None,
                     bg: str = "2D5A9E", fg: str = "FFFFFF") -> None:
    """Write ENE..DIC headers starting at first_col; optionally write TOTAL."""
    for i, m in enumerate(MONTHS_ES):
        c = ws.cell(row=row, column=first_col + i, value=m)
        c.fill = fill(bg)
        c.font = font(bold=True, color=fg, size=10)
        c.alignment = align("center")
        c.border = border()
    if total_col:
        t = ws.cell(row=row, column=total_col, value="TOTAL")
        t.fill = fill(bg)
        t.font = font(bold=True, color=fg, size=10)
        t.alignment = align("center")
        t.border = border()


def set_col_widths(ws, widths: dict[int, float]) -> None:
    for col, w in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = w


def workbook_to_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Protection helpers ─────────────────────────────────────────────────────────

SHEET_PASSWORD = "cwl2026"

_UNLOCKED = Protection(locked=False)
_LOCKED   = Protection(locked=True)


def unlock(cell) -> None:
    """Mark a cell as editable when the sheet is protected."""
    cell.protection = _UNLOCKED


def protect_sheet(ws, password: str = SHEET_PASSWORD) -> None:
    """
    Enable sheet protection. All cells are locked by default; call unlock()
    on data-entry cells before calling this.
    Allows: selecting any cell, using AutoFilter, formatting unlocked cells.
    """
    ws.protection.sheet          = True
    ws.protection.password       = password
    ws.protection.selectLockedCells   = False
    ws.protection.selectUnlockedCells = False


def add_dropdown(ws, col_letter: str, first_data_row: int, last_row: int,
                 options: list[str], prompt: str = "") -> None:
    """Add an in-cell dropdown for col_letter from first_data_row to last_row."""
    formula = '"' + ",".join(options) + '"'
    dv = DataValidation(
        type="list",
        formula1=formula,
        allow_blank=True,
        showDropDown=False,   # False = show the arrow
        prompt=prompt,
        promptTitle="Opciones",
    )
    dv.sqref = f"{col_letter}{first_data_row}:{col_letter}{last_row}"
    ws.add_data_validation(dv)


# ── Nombre de pestaña ─────────────────────────────────────────────────────────

# Excel prohíbe estos caracteres en el título de una hoja y el libro entero se
# cae al guardarlo. No es hipotético: los tres exportadores pasaron a rotular las
# pestañas con el `department_catalog` —para que el 260 dejara de salir «260
# 260»— y el catálogo dice «Rooms / Habitaciones». La barra reventó el export
# completo en el primer intento.
_PROHIBIDOS = r':\/?*[]'
LARGO_MAX_HOJA = 31


def nombre_de_hoja(base: str, usados: set[str], *, sufijo: str = "") -> str:
    """Un título de hoja válido y ÚNICO, y lo registra en `usados`.

    Dos cosas que Excel no perdona y que se descubren tarde, al abrir el archivo:

    * los caracteres de arriba;
    * y **el nombre repetido** — dos departamentos con nombre largo colapsan en
      los mismos 31 caracteres y el libro no abre. Por eso hay `sufijo`: algo
      corto y único (el código del departamento) con lo que desempatar.
    """
    limpio = "".join(ch for ch in (base or "") if ch not in _PROHIBIDOS).strip()
    nombre = (limpio or "Hoja")[:LARGO_MAX_HOJA]
    if nombre in usados and sufijo:
        nombre = f"{nombre[:LARGO_MAX_HOJA - len(sufijo) - 1]} {sufijo}"[:LARGO_MAX_HOJA]
    n = 2
    while nombre in usados:                      # último recurso: numerar
        cola = f" ({n})"
        nombre = f"{nombre[:LARGO_MAX_HOJA - len(cola)]}{cola}"
        n += 1
    usados.add(nombre)
    return nombre
