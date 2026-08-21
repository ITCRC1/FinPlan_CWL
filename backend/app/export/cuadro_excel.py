"""Exportador GENÉRICO de cuadros a Excel, con el formato de la casa.

**Por qué existe.** El owner pidió que todos los cuadros de todos los tabs se
puedan bajar a Excel con formato profesional. Son ~47 pantallas sin exportación
y ~11 más que exportan mal. Escribir 47 exportadores a mano no es viable: cada
uno son 200 líneas y todos se desincronizan del estilo con el tiempo.

**Y hay una razón técnica que cierra la discusión.** Las 10 pantallas que hoy
bajan Excel lo hacen desde el navegador con `xlsx` (SheetJS Community), que **no
escribe estilos de celda**: negrita, relleno, bordes y formato de moneda son de
la edición paga. Con esa librería, «formato profesional» es imposible por más
código que se escriba. Por eso esto vive en el servidor, con `openpyxl`.

**El contrato.** La pantalla manda lo que YA tiene renderizado:

    {
      "titulo": "Big Picture — Budget 2027",
      "subtitulo": "Corcovado · USD",          # opcional
      "columnas": [
        {"label": "Concepto", "ancho": 42, "formato": "texto"},
        {"label": "2026",     "ancho": 14, "formato": "usd"},
        {"label": "Var %",    "ancho": 10, "formato": "pct"},
      ],
      "filas": [
        {"label": "Ingresos",       "nivel": 0, "es_total": True,  "valores": [1000, 0.12]},
        {"label": "  Habitaciones", "nivel": 1, "es_total": False, "valores": [800, 0.10]},
      ],
    }

Los valores van como NÚMERO, nunca como texto ya formateado. Es la diferencia
entre un Excel que se puede sumar y uno que no — hoy `/reports/summary` manda
`"$1,234.00"` como cadena y el archivo resultante no sirve para nada.

Un libro puede llevar varios cuadros: cada uno es su hoja. Las pantallas con
tabs (allocations tiene 12 cuadros, cash flow directo 6) bajan todo de una.
"""
from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment

from app.export.excel_base import (
    C, align, border, fill, font, merged_header, nombre_de_hoja,
    set_col_widths, workbook_to_bytes,
)

# Mismos formatos que `pl_full_detail_excel`, que es la referencia del repo:
# negativo en rojo y entre paréntesis, y el cero NO se imprime — una grilla
# llena de ceros esconde las cifras que sí importan.
FORMATOS = {
    "usd":   '#,##0;[Red](#,##0);""',
    "usd2":  '#,##0.00;[Red](#,##0.00);""',
    "pct":   '0.0%;[Red](0.0%);""',
    "num":   '#,##0;[Red](#,##0);""',
    "num1":  '#,##0.0;[Red](#,##0.0);""',
    "texto": None,
}

FILA_TITULO = 1
FILA_SUBTITULO = 2
FILA_CABECERA = 4
PRIMERA_FILA = 5


def _hoja(wb: Workbook, cuadro: dict, usados: set[str]):
    columnas = cuadro.get("columnas") or []
    filas = cuadro.get("filas") or []
    titulo = (cuadro.get("titulo") or "Cuadro").strip()
    n_col = max(1, len(columnas))

    ws = wb.create_sheet(nombre_de_hoja(cuadro.get("hoja") or titulo, usados))

    merged_header(ws, FILA_TITULO, 1, n_col, titulo, C["navy"], sz=13)
    if cuadro.get("subtitulo"):
        merged_header(ws, FILA_SUBTITULO, 1, n_col, cuadro["subtitulo"],
                      C["navy_mid"], sz=10)

    for i, col in enumerate(columnas, start=1):
        c = ws.cell(FILA_CABECERA, i, col.get("label", ""))
        c.fill = fill(C["navy_mid"])
        c.font = font(bold=True, color=C["white"], size=10)
        # La primera columna es la etiqueta de la fila; el resto son números.
        c.alignment = align("left" if i == 1 else "center", wrap=True)
        c.border = border()

    for j, f in enumerate(filas):
        fila = PRIMERA_FILA + j
        es_total = bool(f.get("es_total"))
        nivel = int(f.get("nivel") or 0)

        # La jerarquía va con SANGRÍA de Excel, no con espacios dentro del texto.
        # Con espacios, ordenar la columna o copiarla a otro lado se lleva la
        # sangría puesta y el nivel deja de significar nada. Es lo que hace hoy
        # `/reports/expenses`, que simula la jerarquía con espacios.
        etiqueta = ws.cell(fila, 1, f.get("label", ""))
        etiqueta.font = font(bold=es_total)
        etiqueta.alignment = Alignment(horizontal="left", vertical="center",
                                       indent=min(nivel, 8))
        etiqueta.border = border()
        if es_total:
            etiqueta.fill = fill(C["blue_header"])

        # La fila puede pisar el formato de la columna. Hace falta cuando un mismo
        # cuadro mezcla unidades en la misma columna — el bloque de drivers del
        # Big Picture tiene noches, ocupación % y ADR en dólares, una debajo de
        # otra. Sin esto habría que partirlo en tres cuadros.
        fmt_fila = f.get("formato")

        for i, valor in enumerate(f.get("valores") or [], start=2):
            if i > n_col:
                break
            celda = ws.cell(fila, i, valor)
            fmt = FORMATOS.get(fmt_fila or columnas[i - 1].get("formato") or "usd",
                               FORMATOS["usd"])
            if fmt:
                celda.number_format = fmt
            # El texto se alinea a la izquierda: una columna de nombres de cuenta
            # alineada a la derecha es ilegible. Pasa en las pantallas de mapeo,
            # que son casi todas de texto (cuenta · departamento · línea del P&L).
            celda.alignment = align("left" if isinstance(valor, str) else "right")
            celda.font = font(bold=es_total)
            celda.border = border()
            if es_total:
                celda.fill = fill(C["blue_header"])

    set_col_widths(ws, {i: (col.get("ancho") or (38 if i == 1 else 14))
                        for i, col in enumerate(columnas, start=1)})
    # Congelar la cabecera y la columna de etiquetas: sin esto, un cuadro de 12
    # meses obliga a adivinar qué fila se está mirando al llegar a diciembre.
    ws.freeze_panes = ws.cell(PRIMERA_FILA, 2)
    return ws


def build_cuadros_workbook(cuadros: list[dict]) -> bytes:
    """Un libro con una hoja por cuadro."""
    wb = Workbook()
    wb.remove(wb.active)
    usados: set[str] = set()
    for cuadro in cuadros or []:
        _hoja(wb, cuadro, usados)
    if not wb.sheetnames:            # nunca devolver un libro sin hojas
        wb.create_sheet("Sin datos")
    return workbook_to_bytes(wb)
