# -*- coding: utf-8 -*-
"""Arma el libro del Cierre Contable Mensual de CWL: Config + hojas que llena Power Query.

Owner, 2026-11-11: *«crear un nuevo archivo de excel en CWL para revisar el
Cierre Contable Mensual. Que tenga todos los detalles que tiene el archivo de
GL pero que solo tenga la version de Actual para 2024-2025-2026. Que tenga la
version Precierre que es donde preliminarmente subo los resultados para
revisar. que tenga Budget 2026 y el Forecast. Que sea mensual, que yo pueda
escoger el mes que quiero revisar y extraer»*.

Orden para armarlo (ver LEEME.md):
    python -I build_cierre.py <base.xlsx>
    add_queries.ps1 -In <base.xlsx> -Out <libro.xlsx>      (GL + Escenarios)
    add_pestanas.ps1 -Libro <libro.xlsx> -Refrescar         (resto de pestañas)
    python -I pl_spec.py / pl_mes_spec.py + pl_build.ps1 / pl_mes_build.ps1
    controles.ps1 -Libro <libro.xlsx>

⚠️ Python no abre rutas de más de 260 caracteres: construir en %TEMP% y copiar.
"""
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

TINTA = "0B0F0D"
BANDA = "DCEBE3"
GRIS = "657169"

# Las seis versiones del cierre, FIJAS: las columnas del P&L del mes y de los
# controles apuntan a estas etiquetas, así que no se cambian solas.
#
# ⚠️ Versión VACÍA = la que el sistema elija, con el criterio del consolidado
# (`consolidado_api._escoger_escenario`): el ACTUAL real —nunca el espejo del
# Pre-Cierre— y el Forecast marcado ★ Current. Así, cuando se marque el
# forecast del mes siguiente, el libro lo sigue sin tocarlo.
#
# El Pre-Cierre se pide por su NOMBRE (`precierre_api.VERSION_ESPEJO`): es un
# ACTUAL más, con un solo mes cargado por vuelta.
VERSIONES = [
    ("SI", "Actual 2024",     2024, "ACTUAL",   ""),
    ("SI", "Actual 2025",     2025, "ACTUAL",   ""),
    ("SI", "Actual 2026",     2026, "ACTUAL",   ""),
    ("SI", "Pre-Cierre 2026", 2026, "ACTUAL",   "Pre-Cierre"),
    ("SI", "Budget 2026",     2026, "BUDGET",   "Final"),
    ("SI", "Forecast 2026",   2026, "FORECAST", ""),
]

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def _titulo(ws, fila, texto, ancho=6):
    c = ws.cell(fila, 1, texto)
    c.font = Font(bold=True, size=13, color=TINTA)
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=ancho)


def _nota(ws, fila, texto, ancho=6, alto=28):
    c = ws.cell(fila, 1, texto)
    c.font = Font(size=9, color=GRIS)
    c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=ancho)
    ws.row_dimensions[fila].height = alto


def construir(salida: str, mes: int = 10) -> None:
    wb = Workbook()

    cfg = wb.active
    cfg.title = "Config"
    cfg.sheet_view.showGridLines = False
    for col, ancho in zip("ABCDEF", (8, 30, 14, 14, 20, 16)):
        cfg.column_dimensions[col].width = ancho

    _titulo(cfg, 1, "Corcovado Wilderness Lodge · Cierre Contable Mensual — en vivo")
    _nota(cfg, 2,
          "Elegí el MES en C7 y todo el libro muestra ese mes y el acumulado a ese mes, "
          "sin volver a bajar nada. Datos → Actualizar todo trae de FinPlan las seis "
          "versiones con la llave de solo lectura.")

    cfg["A4"] = "Dirección del sistema (BACKEND)"
    cfg["A4"].font = Font(bold=True)
    # ⚠️ El BACKEND, no el frontend: el frontend responde 308 (redirige) y Power
    # Query no sigue redirecciones ni deja atraparlas en ManualStatusHandling.
    cfg["C4"] = "https://finplancwl-backend.up.railway.app"
    cfg["A5"] = "Llave de solo lectura"
    cfg["A5"].font = Font(bold=True)
    cfg["C5"] = ""                      # se guarda VACIA: la llave no viaja en el archivo
    cfg["C5"].fill = PatternFill("solid", fgColor="FFF4CE")
    cfg["A6"] = "Incluir cuentas sin movimiento"
    cfg["A6"].font = Font(bold=True)
    cfg["C6"] = "true"                  # el universo del mapeo, como el libro del GL
    cfg["A7"] = "MES A REVISAR (1–12)"
    cfg["A7"].font = Font(bold=True, color="7F1F1F")
    cfg["C7"] = mes
    cfg["C7"].fill = PatternFill("solid", fgColor="CCFFFF")
    cfg["C7"].font = Font(bold=True, size=12)
    cfg["C7"].alignment = Alignment(horizontal="center")
    cfg["D7"] = '=INDEX({"' + '","'.join(MESES) + '"},C7)'
    cfg["D7"].font = Font(bold=True, size=12, color="7F1F1F")
    dv = DataValidation(type="whole", operator="between", formula1="1", formula2="12",
                        showErrorMessage=True, errorTitle="Mes", error="Un número de 1 a 12")
    cfg.add_data_validation(dv)
    dv.add("C7")
    _nota(cfg, 8,
          "La llave se pega una sola vez y NO se guarda en el archivo que se comparte: "
          "borrala de C5 antes de mandarlo.   Cada tabla trae los doce meses y, al final, "
          "las columnas «Mes» y «Acumulado» del mes de C7: filtrá por Etiqueta y copiá "
          "para extraer.", alto=40)

    for nombre, celda in (("pURL", "C4"), ("pLlave", "C5"), ("pCatalogo", "C6"),
                          ("pMes", "C7"), ("pMesNombre", "D7")):
        wb.defined_names.add(DefinedName(nombre, attr_text=f"Config!${celda[0]}${celda[1:]}"))

    cfg["A10"] = "Versiones del cierre (fijas)"
    cfg["A10"].font = Font(bold=True, size=11)
    _nota(cfg, 11,
          "Versión vacía = la que elige el sistema: el ACTUAL real (nunca el espejo del "
          "Pre-Cierre) y el Forecast ★ Current. El Pre-Cierre trae solo los meses que se "
          "están pre-cerrando. Los nombres reales están en la hoja Escenarios.")

    enc = ["Usar", "Etiqueta", "Anio", "Tipo", "Version"]
    fila0 = 13
    for j, h in enumerate(enc, start=1):
        c = cfg.cell(fila0, j, h)
        c.font = Font(bold=True, color=TINTA)
        c.fill = PatternFill("solid", fgColor=BANDA)
        c.border = Border(bottom=Side(style="medium", color=TINTA))
    for i, (usar, etq, anio, tipo, ver) in enumerate(VERSIONES, start=1):
        c = cfg.cell(fila0 + i, 1, usar)
        c.alignment = Alignment(horizontal="center")
        c.font = Font(bold=True, color="1B6B3A")
        cfg.cell(fila0 + i, 2, etq)
        cfg.cell(fila0 + i, 3, anio)
        cfg.cell(fila0 + i, 4, tipo)
        cfg.cell(fila0 + i, 5, ver)
    t = Table(displayName="tVersiones", ref=f"A{fila0}:E{fila0 + len(VERSIONES)}")
    t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
    cfg.add_table(t)

    _nota(cfg, fila0 + len(VERSIONES) + 2,
          "Hojas: P&L Mes (las seis versiones, mes y acumulado) · P&L USALI (doce meses de "
          "una versión) · GL (todo el detalle del mayor) · Checkbook Ingresos · Checkbook "
          "Costos · Checkbook OPEX · Checkbook Planilla (posición × concepto) · Posiciones "
          "(FTE y costo) · Estadisticas Rooms · P&L Motor · Controles (deben dar 0).", alto=40)

    esc = wb.create_sheet("Escenarios")
    esc.sheet_view.showGridLines = False
    esc["A1"] = "Lo que FinPlan tiene hoy. La llena Power Query."
    esc["A1"].font = Font(size=10, color=GRIS)

    datos = wb.create_sheet("GL")
    datos.sheet_view.showGridLines = False
    datos["A1"] = "Esta hoja la llena Power Query. Datos → Actualizar todo."
    datos["A1"].font = Font(size=10, color=GRIS)

    wb.save(salida)
    print(f"libro escrito: {salida}  ·  {len(VERSIONES)} versiones  ·  mes {mes}")


if __name__ == "__main__":
    construir(sys.argv[1] if len(sys.argv) > 1 else "CWL_Cierre_Mensual.xlsx",
              int(sys.argv[2]) if len(sys.argv) > 2 else 10)
