# -*- coding: utf-8 -*-
"""Arma el libro CWL_GL_en_vivo.xlsx: hoja Config + hoja de datos.

La consulta de Power Query se inyecta aparte con `add_queries.ps1` (COM de
Excel), igual que el libro del P&L en vivo.

⚠️ Python no abre rutas de mas de 260 caracteres: construir en
`%TEMP%\\finplan_gl` y recien despues copiar al destino.

    python build_gl_live.py <salida.xlsx>
"""
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.table import Table, TableStyleInfo

TINTA = "0B0F0D"
BANDA = "DCEBE3"
GRIS = "657169"

# Las versiones que pidio el owner (2026-11-10). Se editan EN EL LIBRO, no aca:
# la consulta lee esta tabla, asi que agregar un Draft es escribir un renglon.
#
# ⚠️ Los nombres de version tienen que ser los REALES del sistema. En FinPlan el
# forecast 2026 se llama `October`, no «October 2026`; el budget 2027 tiene
# `Working` y `Final`. Dejar la celda VACIA es valido y significa «la que el
# sistema elija»: el ★ Current del forecast, el ACTUAL real.
VERSIONES = [
    ("Budget 2027 · Working", 2027, "BUDGET", "Working"),
    ("Budget 2027 · Final", 2027, "BUDGET", "Final"),
    ("Budget 2027 · Draft1", 2027, "BUDGET", "Draft1"),
    ("Budget 2027 · Draft2", 2027, "BUDGET", "Draft2"),
    ("Budget 2027 · Draft3", 2027, "BUDGET", "Draft3"),
    ("Forecast 2026 · Working", 2026, "FORECAST", "Working"),
    ("Forecast 2026 · October", 2026, "FORECAST", "October"),
    ("Forecast 2026 · November", 2026, "FORECAST", "November"),
    ("Forecast 2026 · vigente (★)", 2026, "FORECAST", ""),
    ("Actual 2026", 2026, "ACTUAL", ""),
]


def _titulo(ws, fila, texto, ancho=6):
    c = ws.cell(fila, 1, texto)
    c.font = Font(bold=True, size=13, color=TINTA)
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=ancho)


def _nota(ws, fila, texto, ancho=6):
    c = ws.cell(fila, 1, texto)
    c.font = Font(size=9, color=GRIS)
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=ancho)
    ws.row_dimensions[fila].height = 28


def construir(salida: str) -> None:
    wb = Workbook()

    # ── Config ───────────────────────────────────────────────────────────
    cfg = wb.active
    cfg.title = "Config"
    cfg.sheet_view.showGridLines = False
    for col, ancho in zip("ABCDEF", (30, 12, 16, 22, 16, 16)):
        cfg.column_dimensions[col].width = ancho

    _titulo(cfg, 1, "CWL · Cuentas del mayor por mes — en vivo")
    _nota(cfg, 2,
          "Datos → Actualizar todo. Cada version se baja de FinPlan con la llave de "
          "solo lectura. El ingreso viene NEGATIVO (es credito): la suma de todas las "
          "filas es la utilidad cambiada de signo.")

    cfg["A4"] = "Direccion del sistema"
    cfg["A4"].font = Font(bold=True)
    cfg["C4"] = "https://finplan-cwl.up.railway.app"
    cfg["A5"] = "Llave de solo lectura"
    cfg["A5"].font = Font(bold=True)
    cfg["C5"] = ""                      # se guarda VACIA: la llave no viaja en el archivo
    cfg["C5"].fill = PatternFill("solid", fgColor="FFF4CE")
    cfg["A6"] = "Incluir cuentas sin movimiento"
    cfg["A6"].font = Font(bold=True)
    # Prendido: el owner quiere el UNIVERSO, no solo lo que el escenario uso
    # (2026-11-10, mostrando su export del mapeo: «tiene todo el universo de los
    # gl mapping»). Son 1.087 pares (depto, cuenta) unicos.
    cfg["C6"] = "true"
    _nota(cfg, 7,
          "La llave se pega una sola vez y NO se guarda en el archivo que se "
          "comparte. Con 'cuentas sin movimiento' en true bajan las 1.087 cuentas "
          "del mapeo -- el universo completo -- y las que el escenario no uso vienen "
          "en cero, en su categoria. En false bajan solo las que tienen cifra.")

    for nombre, celda in (("pURL", "C4"), ("pLlave", "C5"), ("pCatalogo", "C6")):
        wb.defined_names.add(DefinedName(nombre, attr_text=f"Config!${celda[0]}${celda[1:]}"))

    cfg["A9"] = "Versiones a bajar"
    cfg["A9"].font = Font(bold=True, size=11)
    _nota(cfg, 10,
          "Una fila por version. 'Version' vacia = la que el sistema elija (el ★ "
          "Current del forecast, el ACTUAL real). Si una version no existe, ESA fila "
          "baja con el error y las demas siguen bajando igual.")

    enc = ["Etiqueta", "Anio", "Tipo", "Version"]
    fila0 = 12
    for j, h in enumerate(enc, start=1):
        c = cfg.cell(fila0, j, h)
        c.font = Font(bold=True, color=TINTA)
        c.fill = PatternFill("solid", fgColor=BANDA)
        c.border = Border(bottom=Side(style="medium", color=TINTA))
    for i, (etq, anio, tipo, ver) in enumerate(VERSIONES, start=1):
        cfg.cell(fila0 + i, 1, etq)
        cfg.cell(fila0 + i, 2, anio)
        cfg.cell(fila0 + i, 3, tipo)
        cfg.cell(fila0 + i, 4, ver)

    ref = f"A{fila0}:D{fila0 + len(VERSIONES)}"
    t = Table(displayName="tVersiones", ref=ref)
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    cfg.add_table(t)

    # ── Hoja de datos: la llena Power Query ──────────────────────────────
    datos = wb.create_sheet("GL")
    datos.sheet_view.showGridLines = False
    datos["A1"] = "Esta hoja la llena Power Query. Datos → Actualizar todo."
    datos["A1"].font = Font(size=10, color=GRIS)
    datos.column_dimensions["A"].width = 60

    wb.save(salida)
    print(f"libro escrito: {salida}  ·  {len(VERSIONES)} versiones")


if __name__ == "__main__":
    construir(sys.argv[1] if len(sys.argv) > 1 else "CWL_GL_en_vivo.xlsx")
