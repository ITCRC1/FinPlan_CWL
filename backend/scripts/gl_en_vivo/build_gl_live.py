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
    # `Usar` prende y apaga la fila sin borrarla: el owner quiere poder ELEGIR
    # (2026-11-10: «que tenga para escoger varias versiones»). `*` = todas las
    # que FinPlan tenga de ese año y tipo.
    #
    # ⚠️ La Etiqueta de una fila con `*` es el PREFIJO del resultado, no la
    # descripcion del pedido: al expandirse se le pega el nombre real de cada
    # version detras. Escribir «Budget 2027 — todas» produce columnas que dicen
    # «Budget 2027 — todas · Draft1», y se lee como si «todas» fuera parte del
    # nombre de la version (owner, 2026-11-10: «me confunde la palabra todas»).
    #
    # ⚠️ No prender `*` y una versión suelta del MISMO año y tipo a la vez: esa
    # versión baja dos veces y cualquier pivot la suma doble.
    # Owner, 2026-11-10: *«yo quiero que sea sencillo, lo mas que voy a comparar
    # son 5 o 6 versiones»*. Por eso filas FIJAS con el nombre exacto y nada de
    # comodines: las columnas del resultado no cambian solas, asi que una
    # formula de varianza escrita al lado sigue apuntando a lo mismo manana.
    #
    # ⚠️ Los nombres son los REALES del sistema (se ven en la hoja Escenarios).
    # Los del Budget 2027 son Draft1, Draft4-BIG, Draft5, Final y Working --
    # NO Draft1/2/3. Si una fila baja con «no existe», copiar el nombre de ahi.
    # Las versiones del libro que el owner ya usaba (2026-11-10), con los nombres
    # REALES de la base de CWL, mas el Budget 2026 Final que pide el cierre.
    ("SI", "Actual 2024",           2024, "ACTUAL",   ""),
    ("SI", "Actual 2025",           2025, "ACTUAL",   ""),
    ("SI", "Actual 2026",           2026, "ACTUAL",   ""),
    ("SI", "Forecast 2026",         2026, "FORECAST", ""),
    ("SI", "Budget 2026 Final",     2026, "BUDGET",   "Final"),
    ("SI", "Budget 2027 Working",   2027, "BUDGET",   "Working"),
    ("SI", "Budget 2027 Final",     2027, "BUDGET",   "Final"),
    ("NO", "Budget 2027 Draft1",    2027, "BUDGET",   "Draft1"),
    ("NO", "Budget 2027 Draft4",    2027, "BUDGET",   "Draft4-BIG"),
    ("NO", "Budget 2027 Draft5",    2027, "BUDGET",   "Draft5"),
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
    for col, ancho in zip("ABCDEF", (8, 30, 10, 14, 20, 16)):
        cfg.column_dimensions[col].width = ancho

    _titulo(cfg, 1, "CWL · Cuentas del mayor por mes y checkbooks — en vivo")
    _nota(cfg, 2,
          "Datos → Actualizar todo. Cada versión se baja de FinPlan con la llave de "
          "solo lectura. El ingreso viene NEGATIVO (es crédito): la suma de todas las "
          "filas es la utilidad cambiada de signo.   Ojo: cada versión es un P&L "
          "completo de doce meses, así que el refresh tarda en proporción a cuántas "
          "pida esta tabla.")

    cfg["A4"] = "Direccion del sistema (BACKEND)"
    cfg["A4"].font = Font(bold=True)
    # ⚠️ El BACKEND, no el frontend. el frontend (`finplan-cwl.up.railway.app/api/...` en CWL)
    # responde 308 y redirige a la misma ruta SIN la barra final, que da 404 --
    # y Power Query no sigue redirecciones: muestra «(308): Permanent Redirect»
    # y no se conecta. Medido el 2026-11-10.
    #
    # Tampoco se puede explicar en la consulta: Power Query RECHAZA los 3xx en
    # `ManualStatusHandling` («'307' is not supported»). O sea que la unica
    # defensa contra esto es que la direccion de aca este bien.
    cfg["C4"] = "https://finplancwl-backend.up.railway.app"
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
          "comparte. Es la LLAVE de CWL, no una dirección: si acá va un https://, FinPlan la rechaza. Con 'cuentas sin movimiento' en true bajan todas las cuentas "
          "del mapeo -- el universo completo -- y las que el escenario no uso vienen "
          "en cero, en su categoria. En false bajan solo las que tienen cifra.")

    for nombre, celda in (("pURL", "C4"), ("pLlave", "C5"), ("pCatalogo", "C6")):
        wb.defined_names.add(DefinedName(nombre, attr_text=f"Config!${celda[0]}${celda[1:]}"))

    cfg["A9"] = "Versiones a bajar"
    cfg["A9"].font = Font(bold=True, size=11)
    _nota(cfg, 10,
          "Usar = SI / NO prende y apaga la fila sin borrarla.   Version vacía  ->  la "
          "que el sistema elija (el ★ Current del forecast, el ACTUAL real); un nombre "
          "exacto  ->  solo esa.   Los nombres reales están en la hoja Escenarios: si "
          "una fila baja con «no existe», copiá el nombre de ahí.   (Avanzado: un * "
          "trae todas las de ese año y tipo, pero entonces las columnas cambian solas.)")

    enc = ["Usar", "Etiqueta", "Anio", "Tipo", "Version"]
    fila0 = 12
    for j, h in enumerate(enc, start=1):
        c = cfg.cell(fila0, j, h)
        c.font = Font(bold=True, color=TINTA)
        c.fill = PatternFill("solid", fgColor=BANDA)
        c.border = Border(bottom=Side(style="medium", color=TINTA))
    for i, (usar, etq, anio, tipo, ver) in enumerate(VERSIONES, start=1):
        c = cfg.cell(fila0 + i, 1, usar)
        c.alignment = Alignment(horizontal="center")
        c.font = Font(bold=True, color=("1B6B3A" if usar == "SI" else "A33A3A"))
        cfg.cell(fila0 + i, 2, etq)
        cfg.cell(fila0 + i, 3, anio)
        cfg.cell(fila0 + i, 4, tipo)
        cfg.cell(fila0 + i, 5, ver)

    ref = f"A{fila0}:E{fila0 + len(VERSIONES)}"
    t = Table(displayName="tVersiones", ref=ref)
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    cfg.add_table(t)

    esc = wb.create_sheet("Escenarios")
    esc.sheet_view.showGridLines = False
    esc["A1"] = ("Lo que FinPlan tiene hoy. La llena Power Query — sirve para ver "
                 "cómo se llaman de verdad las versiones.")
    esc["A1"].font = Font(size=10, color=GRIS)
    esc.column_dimensions["A"].width = 70

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
