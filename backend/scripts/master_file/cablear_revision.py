# -*- coding: utf-8 -*-
"""Mete en el Master File las pestañas de revisión del owner y las deja vivas.

Owner, 2026-11-28: *«yo había agregado tabs para revisar individualmente y que
todas las fórmulas estén ahí mismo para validar cada revenue»*. Armó «0 Paso a
paso» y R1..R8 (una por línea, con su ✓ contra el modelo y contra FinPlan) sobre
el libro de reconstrucción. Esas pestañas leen SOLO de tres hojas del mismo
libro: «Supuestos», «1 Rooms» y «2 Lineas de ingreso».

Lo que hace, sin tocar una fórmula de las pestañas del owner:
  1) Copia TODAS las hojas de su libro EN GRUPO antes de «RV3 Inputs» (las
     referencias entre ellas quedan internas; un vínculo residual al libro de
     origen se cambia por este mismo libro).
  2) En «Supuestos», cada número pegado pasa a ser fórmula: calendario,
     perillas, unidades, ocupación, rack, neta a mano y pax leen la columna
     USED de «RV3 Inputs» (o sea FinPlan, o el «Mine» del owner si escribió uno);
     los canales leen de «RV Data». El factor neto también es el USED.
  3) En «2 Lineas de ingreso», las filas verdes del Checkbook FinPlan leen de
     «RV Data» (CB|LÍNEA|mes).
  4) Agrega sus pestañas al «00 Index».

Requiere que el libro ya tenga «RV3 Inputs» y «RV Data» (agregar_revenue.ps1
-Copiar 'RV3 Inputs','RV Data') y el mapa de filas que deja build_revenue.py.

Uso: python cablear_revision.py <master.xlsx> <libro_del_owner.xlsx> <rv_sheets_mapa.json>
"""
import json
import os
import sys

import win32com.client as w

MASTER, REVISION, MAPA = (os.path.normpath(a) for a in sys.argv[1:4])
mp = json.load(open(MAPA, encoding="utf-8"))

MC = [chr(ord("E") + i) for i in range(12)]          # E..P
RV3 = "'RV3 Inputs'"
DS = "'RV Data'"
MES = lambda c: f"{RV3}!{c}${mp['MROW']}"           # número de mes de esa columna


def dato(clave_expr: str, faltante: str = "0") -> str:
    return f"IFERROR(INDEX({DS}!$B:$B,MATCH({clave_expr},{DS}!$A:$A,0)),{faltante})"


def usado_por_codigo(col: str, filas: list, fila_owner: int, faltante: str = "0") -> str:
    """La celda USED de RV3 de la categoría cuyo código está en Supuestos!B<fila>."""
    a, z = filas[0], filas[-1]
    codigo = f'LEFT($B{fila_owner},FIND(" ",$B{fila_owner}&" ")-1)'
    return (f"=IFERROR(INDEX({RV3}!{col}${a}:{col}${z},"
            f"MATCH({codigo},{RV3}!$B${a}:$B${z},0)),{faltante})")


xl = w.DispatchEx("Excel.Application")
xl.Visible = False; xl.DisplayAlerts = False; xl.AskToUpdateLinks = False
wb = xl.Workbooks.Open(MASTER, 0)
try:
    xl.Calculation = -4135
    src = xl.Workbooks.Open(REVISION, 0)
    hojas = [s.Name for s in src.Worksheets]
    print("hojas del owner:", hojas)

    # 1) Una corrida anterior se va entera, y el grupo entra antes de RV3 Inputs.
    for s in list(wb.Worksheets):
        if s.Name in hojas:
            s.Visible = -1; s.Delete()
    src.Worksheets(hojas).Copy(wb.Worksheets("RV3 Inputs"))
    ruta = src.FullName
    src.Close(False)
    links = wb.LinkSources(1)
    if links:
        for l in links:
            if l == ruta:
                wb.ChangeLink(l, wb.FullName, 1)

    # 2) Supuestos
    S = wb.Worksheets("Supuestos")
    S.Range("A1").Formula = ('="CWL · "&' + RV3 + '!B8&" · Supuestos del ingreso — EN VIVO desde FinPlan '
                             '(Datos → Actualizar todo; el escenario se elige en RV3 Inputs)"')
    S.Range("A2").Value = ("Ya no hay números pegados: cada celda lee la columna USED de «RV3 Inputs» "
                           "(lo de FinPlan, o tu «Mine» si escribiste uno ahí). Con un «Mine» escrito, los ✓ "
                           "contra el Checkbook de FinPlan pasan a mostrar el efecto de ese supuesto.")
    for i, c in enumerate(MC):
        S.Range(f"{c}5").Formula = f"={RV3}!{c}${mp['DAYS']}"
        S.Range(f"{c}6").Formula = f"={RV3}!{c}${mp['OPEN']}"
        for fila, clave in ((9, "MIX|TA|"), (10, "COM|TA|"), (11, "MIX|OTA|"), (12, "COM|OTA|"),
                            (13, "MIX|DIRECT|"), (14, "COM|DIRECT|")):
            S.Range(f"{c}{fila}").Formula = "=" + dato(f'"{clave}"&{MES(c)}')
        S.Range(f"{c}15").Formula = f"={RV3}!{c}${mp['NF']}"
    perillas = {18: ("food", 1), 19: ("tours", 1), 20: ("transport", 1), 21: ("nights_per_stay", 1),
                22: ("bev_ratio", 100), 23: ("no_consume_pct", 100), 24: ("sust_rate", 1),
                25: ("sust_non_pay", 100), 26: ("retail_pct", 100), 27: ("innoceana_pct", 100)}
    for fila, (k, div) in perillas.items():
        ref = f"{RV3}!$E${mp['knobs'][k]}"
        S.Range(f"E{fila}").Formula = f"={ref}" if div == 1 else f"={ref}/{div}"
    for k in range(7):
        S.Range(f"D{30 + k}").Formula = usado_por_codigo("$F", mp["cat"], 30 + k)
    grillas = (("occ", 30, "0"), ("rack", 39, "0"), ("netman", 48, '""'), ("pax", 57, "0"))
    for g, primera, faltante in grillas:
        for k in range(7):
            for i, c in enumerate(MC):
                S.Range(f"{c}{primera + k}").Formula = usado_por_codigo(
                    mp["used_cols"][i], mp["grids"][g], primera + k, faltante)

    # 3) 2 Lineas de ingreso: el Checkbook FinPlan
    L = wb.Worksheets("2 Lineas de ingreso")
    filas_cb = {8: ["ROOMS"], 15: ["FOOD"], 22: ["BEVERAGE"], 29: ["ACTIVITIES"], 36: ["TRANSPORT"],
                43: ["SUSTAINABILITY"], 50: ["RETAIL"], 57: ["INNOCEANA"], 61: ["SPA"],
                64: ["LAUNDRY"], 67: ["FNB_MISC"], 70: ["CLUB", "CLUB_ACTIVIDAD", "CLUB_VISITANTES"]}
    for fila, lineas in filas_cb.items():
        etiqueta = str(L.Range(f"A{fila}").Value or "")
        assert ("Checkbook" in etiqueta or "hotel" in etiqueta), f"fila {fila} no es la del checkbook: {etiqueta}"
        for c in MC:
            L.Range(f"{c}{fila}").Formula = "=" + "+".join(dato(f'"CB|{ln}|"&{MES(c)}') for ln in lineas)
        L.Range(f"Q{fila}").Formula = f"=SUM(E{fila}:P{fila})"

    # 4) Índice
    ix = wb.Worksheets("00 Index")
    ult = ix.Cells(ix.Rows.Count, 2).End(-4162).Row
    ya = {str(ix.Cells(r, 2).Value) for r in range(5, ult + 1)}
    descr = {
        "Resumen": "Revenue rebuild (ES): every line Standard vs Villas vs the FinPlan checkbook",
        "0 Paso a paso": "Step by step for one month: net factor → Rooms → the other lines, each with ✓",
        "R1 Rooms": "Rooms revenue validation, category by category, with ✓ per month",
        "R2 Food": "Food revenue validation with ✓", "R3 Beverage": "Beverage revenue validation with ✓",
        "R4 Tours": "Tours revenue validation with ✓", "R5 Transporte": "Transport revenue validation with ✓",
        "R6 Sustainability": "Sustainability fee validation with ✓",
        "R7 Retail e Innoceana": "Retail and Innoceana validation with ✓",
        "R8 Spa y otros": "Spa, Laundry, F&B Misc and Club (typed amounts) with ✓",
    }
    r = ult
    n0 = ix.Cells(ult, 1).Value
    for nombre, texto in descr.items():
        if nombre in ya or nombre not in hojas:
            continue
        r += 1
        if isinstance(n0, (int, float)):
            n0 = int(n0) + 1; ix.Cells(r, 1).Formula = str(n0)
        ix.Cells(r, 2).Formula = nombre; ix.Cells(r, 3).Formula = texto

    xl.Calculation = -4105
    xl.CalculateFull()
    wb.Worksheets("Resumen").Activate()
    wb.Save()
    print("listo:", MASTER)
finally:
    wb.Close(False)
    xl.Quit()
