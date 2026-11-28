# -*- coding: utf-8 -*-
"""Pestañas RV del Master File: el ingreso reconstruido línea por línea.

Owner, 2026-11-28, sobre el libro que reconstruía cada línea del Budget 2027
separando Standard y Villas: *«como puedo mantener este excel para correr cuando
yo quiera pero que la informacion se calcule en forma automatica»* y luego
*«metelo en el master file»*.

Arma un libro con seis hojas y TODO en fórmulas:

    RV1 Revenue Build    resumen Standard vs Villas, estadísticas y controles
    RV2 Per guest-night  de la tarifa rack al dólar que entra, por pax-noche
    RV3 Inputs           escenario a bajar + supuestos: FinPlan | Mine | Used
    RV4 Rooms            noches, pax y Room Revenue por categoría y por set
    RV5 Revenue lines    cada línea × set × mes contra el Revenue Checkbook
    RV Data              la tabla tRevSup (clave · valor · texto) de
                         /api/consolidado/revenue-supuestos/

`agregar_revenue.ps1` copia las seis al Master File como grupo (así las
referencias entre ellas quedan internas) y engancha la consulta en «RV Data».

Reglas del libro, para no romperlo después:
  * Nada lee por número de fila de «RV Data»: todo es INDEX/MATCH por clave.
  * Las categorías son 10 lugares; el código de cada uno lo dice FinPlan
    (`ORDEN|n|0`). Una categoría nueva entra sola; la 11 la avisa un control.
  * «Mine» vacío = vale lo de FinPlan. Con algún «Mine» escrito, la diferencia
    contra el checkbook deja de ser un control y pasa a ser el efecto de esos
    supuestos — RV1 lo dice.

Uso:  python build_revenue.py <salida.xlsx> [supuestos.json]
      (el json es la respuesta del endpoint, para dejar datos de muestra).
"""
import json
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

OUT = sys.argv[1]
MUESTRA = json.load(open(sys.argv[2], encoding="utf-8"))["filas"] if len(sys.argv) > 2 else []

SLOTS = 10
M = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
C0 = 5                                   # columna E = enero
MC = [L(C0 + i) for i in range(12)]      # E..P
YC = "Q"
MINE = [L(C0 + 14 + i) for i in range(12)]   # S..AD
USED = [L(C0 + 28 + i) for i in range(12)]   # AG..AR

DS = "'RV Data'"
BLUE = Font(color="0000FF"); GREEN = Font(color="008000"); B = Font(bold=True)
H1 = Font(bold=True, size=14); GR = Font(color="808080", italic=True); RED = Font(color="C00000", bold=True)
F_H = PatternFill("solid", fgColor="DDE4EE"); F_S = PatternFill("solid", fgColor="F2F2F2")
F_IN = PatternFill("solid", fgColor="FFF2CC"); F_T = PatternFill("solid", fgColor="E8F1E4")
F_FP = PatternFill("solid", fgColor="EAF1FB")
TOP = Border(top=Side(style="thin", color="999999"))
USD = '#,##0.00;(#,##0.00);"-"'; USD0 = '#,##0;(#,##0);"-"'; N1 = '#,##0.0;(#,##0.0);"-"'
PCT = '0.0%;(0.0%);"-"'; PCT4 = "0.0000%"


def V(key: str, blank_if_missing: bool = False) -> str:
    miss = '""' if blank_if_missing else "0"
    return f"IFERROR(INDEX({DS}!$B:$B,MATCH({key},{DS}!$A:$A,0)),{miss})"


def T(key: str) -> str:
    return f'IFERROR(INDEX({DS}!$C:$C,MATCH({key},{DS}!$A:$A,0))&"","")'


wb = Workbook()


def base(ws, title, sub, a=44, b=12, c=14, d=9):
    ws["A1"] = title; ws["A1"].font = H1
    ws["A2"] = sub; ws["A2"].font = GR
    ws.column_dimensions["A"].width = a; ws.column_dimensions["B"].width = b
    ws.column_dimensions["C"].width = c; ws.column_dimensions["D"].width = d
    for i in range(12):
        ws.column_dimensions[MC[i]].width = 12
    ws.column_dimensions[YC].width = 14
    ws.sheet_view.showGridLines = False


def month_header(ws, row, first, cols=MC, extra=("Code", "Set", "Units"), year=True):
    ws.cell(row, 1, first).font = B
    for j, t in enumerate(extra):
        ws.cell(row, 2 + j, t).font = B
    for i, col in enumerate(cols):
        ws[f"{col}{row}"] = M[i]; ws[f"{col}{row}"].font = B
    if year:
        ws[f"{YC}{row}"] = "Year"; ws[f"{YC}{row}"].font = B
    last = 17 if cols is MC else 4 + 12 + (cols is MINE) * 14 + (cols is USED) * 28
    for c in range(1, 18):
        ws.cell(row, c).fill = F_H


# ════════════════════════════ RV3 Inputs ════════════════════════════
I = wb.active; I.title = "RV3 Inputs"
base(I, "RV3 · Revenue inputs — FinPlan | Mine | Used",
     "Blue = what FinPlan has (refreshed). Yellow = Mine: type here to test a different assumption; blank = FinPlan. "
     "Used = what every RV sheet calculates with. Data → Refresh All brings the scenario chosen below.")
for col in ("R", "AE"):
    I.column_dimensions[col].width = 3
for cols in (MINE, USED):
    for c in cols:
        I.column_dimensions[c].width = 11
I.column_dimensions["D"].width = 11

# Selector de escenario (nombres pRV_* los crea agregar_revenue.ps1)
sel = [("Year", 2027), ("Type (BUDGET / FORECAST)", "BUDGET"), ("Version (blank = FinPlan default)", "Working")]
I["A4"] = "Scenario to read from FinPlan"; I["A4"].font = B
for k, (lab, v) in enumerate(sel):
    r = 5 + k
    I.cell(r, 1, lab); c = I.cell(r, 2, v); c.font = BLUE; c.fill = F_IN
    if k == 2:
        c.number_format = "@"
I["A8"] = "Loaded"; I["B8"] = "=" + T('"INFO|escenario|0"'); I["B8"].font = B
I["A9"] = "Revenue source of its P&L"; I["B9"] = "=" + T('"INFO|fuente|0"')
I["A10"] = "Read from FinPlan at"; I["B10"] = "=" + T('"INFO|leido|0"')
I["A11"] = "Message from the refresh"; I["B11"] = "=" + T('"INFO|error|0"'); I["B11"].font = RED
I["D9"] = ('=IF(B9="checkbook","The P&L reads the Revenue Checkbook: RV5 «FinPlan» rows are what it books.",'
           'IF(B9="","","The P&L calculates from drivers: no «no-consume», Retail from its typed amounts."))')
I["D9"].font = GR

# Calendario
r = 12
month_header(I, r, "Calendar", extra=("", "", ""))
I.cell(r + 1, 1, "Month number (helper)").font = GR
for i, col in enumerate(MC):
    I[f"{col}{r+1}"] = i + 1; I[f"{col}{r+1}"].font = GR
MROW = r + 1
DAYS = r + 2; OPEN = r + 3
I.cell(DAYS, 1, "Days in month")
I.cell(OPEN, 1, "Hotel operates (1 = yes, 0 = closed month)")
for i, col in enumerate(MC):
    I[f"{col}{DAYS}"] = "=" + V(f'"DIAS|-|"&{col}${MROW}'); I[f"{col}{DAYS}"].number_format = "0"
    I[f"{col}{OPEN}"] = "=" + V(f'"ABRE|-|"&{col}${MROW}'); I[f"{col}{OPEN}"].number_format = "0"
    I[f"{col}{OPEN}"].font = BLUE

# Canales
r = OPEN + 2
month_header(I, r, "Sales channels (FinPlan)", extra=("Channel", "", ""), year=False)
CH = {}
for n in range(1, 5):
    rr = r + 2 * n - 1
    I.cell(rr, 1, f"Channel {n} · mix %"); I.cell(rr + 1, 1, f"Channel {n} · commission %")
    I.cell(rr, 2, "=" + T(f'"CANAL|{n}|0"')); I.cell(rr + 1, 2, f"=B{rr}")
    for i, col in enumerate(MC):
        I[f"{col}{rr}"] = f'=IF($B{rr}="","",{V(chr(34) + "MIX|" + chr(34) + "&$B" + str(rr) + "&" + chr(34) + "|" + chr(34) + "&" + col + "$" + str(MROW))})'
        I[f"{col}{rr+1}"] = f'=IF($B{rr}="","",{V(chr(34) + "COM|" + chr(34) + "&$B" + str(rr) + "&" + chr(34) + "|" + chr(34) + "&" + col + "$" + str(MROW))})'
        I[f"{col}{rr}"].number_format = PCT; I[f"{col}{rr+1}"].number_format = PCT4
        I[f"{col}{rr}"].font = BLUE; I[f"{col}{rr+1}"].font = BLUE
NF_FP = r + 9; NF_MINE = r + 10; NF = r + 11
I.cell(NF_FP, 1, "Net factor · FinPlan (Σ mix × (1 − commission))").font = B
I.cell(NF_MINE, 1, "Net factor · Mine (blank = FinPlan)")
I.cell(NF, 1, "Net factor · USED").font = B
for i, col in enumerate(MC):
    I[f"{col}{NF_FP}"] = "=" + V(f'"NF|-|"&{col}${MROW}'); I[f"{col}{NF_FP}"].number_format = PCT4
    I[f"{col}{NF_FP}"].font = BLUE
    I[f"{col}{NF_MINE}"].fill = F_IN; I[f"{col}{NF_MINE}"].number_format = PCT4
    I[f"{col}{NF}"] = f'=IF({col}{NF_MINE}="",{col}{NF_FP},{col}{NF_MINE})'; I[f"{col}{NF}"].number_format = PCT4
    I[f"{col}{NF}"].font = B

# Perillas
r = NF + 2
for j, t in enumerate(["Revenue Checkbook knobs", "FinPlan key", "FinPlan", "Mine", "Used"]):
    I.cell(r, 1 + j, t).font = B
for c in range(1, 6):
    I.cell(r, c).fill = F_H
KN = {}
KROWS = []
knobs = [("food", "Food · full pension, rack per guest-night ($)", USD),
         ("tours", "Tours · rack per guest-STAY ($)", USD),
         ("transport", "Transport · rack per guest-STAY ($)", USD),
         ("nights_per_stay", "Nights per stay (divides Tours and Transport)", "0.0"),
         ("bev_ratio", "Beverage as % of Food (34 = 34%)", "0.0"),
         ("no_consume_pct", "% that does not consume — Food, Bev, Tours, Transport (5 = 5%)", "0.0"),
         ("sust_rate", "Sustainability fee per guest-night ($, no commission)", USD),
         ("sust_non_pay", "Sustainability · % that does not pay (10 = 10%)", "0.0"),
         ("retail_pct", "Retail as % of Room Revenue (1 = 1%)", "0.00"),
         ("innoceana_pct", "Innoceana as % of Room Revenue", "0.00")]
for k, lab, f in knobs:
    r += 1
    I.cell(r, 1, lab); I.cell(r, 2, k).font = GR
    c = I.cell(r, 3, "=" + V(f'"PERILLA|"&$B{r}&"|0"')); c.font = BLUE; c.number_format = f
    m = I.cell(r, 4); m.fill = F_IN; m.number_format = f
    u = I.cell(r, 5, f'=IF(D{r}="",C{r},D{r})'); u.font = B; u.number_format = f
    KN[k] = f"'RV3 Inputs'!$E${r}"
    KROWS.append(r)

# Categorías (10 lugares)
r += 2
for j, t in enumerate(["Room categories (FinPlan order)", "Code", "Set", "Units FinPlan", "Units Mine", "Units USED"]):
    I.cell(r, 1 + j, t).font = B
for c in range(1, 7):
    I.cell(r, c).fill = F_H
CAT = []
for n in range(1, SLOTS + 1):
    r += 1
    I.cell(r, 2, "=" + T(f'"ORDEN|{n}|0"'))
    I.cell(r, 1, f'=IF(B{r}="","(slot {n} empty)",' + T(f'"NOMBRE|"&B{r}&"|0"') + ")")
    I.cell(r, 3, f'=IF(B{r}="","",' + T(f'"SET|"&B{r}&"|0"') + ")")
    c = I.cell(r, 4, f'=IF(B{r}="","",' + V(f'"UNID|"&B{r}&"|0"') + ")"); c.font = BLUE
    I.cell(r, 5).fill = F_IN
    I.cell(r, 6, f'=IF(B{r}="","",IF(E{r}="",D{r},E{r}))').font = B
    CAT.append(r)
CAT_FIRST, CAT_LAST = CAT[0], CAT[-1]


def grid(title, key, fmt, blank_if_missing=False):
    """FinPlan E:P · Mine S:AD · Used AG:AR, una fila por lugar."""
    global r
    r += 2
    I.cell(r, 1, title).font = B
    I.cell(r, 2, "Code").font = B; I.cell(r, 3, "Set").font = B
    for i in range(12):
        for cols, lab in ((MC, "FinPlan"), (MINE, "Mine"), (USED, "USED")):
            I[f"{cols[i]}{r}"] = f"{M[i]}"; I[f"{cols[i]}{r}"].font = B
            I[f"{cols[i]}{r}"].fill = F_FP if cols is MC else (F_IN if cols is MINE else F_T)
    I[f"{MC[0]}{r-1}"] = "FinPlan"; I[f"{MINE[0]}{r-1}"] = "Mine (blank = FinPlan)"; I[f"{USED[0]}{r-1}"] = "USED"
    for col in (MC[0], MINE[0], USED[0]):
        I[f"{col}{r-1}"].font = B
    rows = []
    for n, cr in enumerate(CAT):
        r += 1
        I.cell(r, 1, f"=A{cr}"); I.cell(r, 2, f"=B{cr}"); I.cell(r, 3, f"=C{cr}")
        for i in range(12):
            fp = I[f"{MC[i]}{r}"]
            fp.value = f'=IF($B{r}="","",{V(chr(34) + key + "|" + chr(34) + "&$B" + str(r) + "&" + chr(34) + "|" + chr(34) + "&" + MC[i] + "$" + str(MROW), blank_if_missing)})'
            fp.font = BLUE; fp.number_format = fmt
            mi = I[f"{MINE[i]}{r}"]; mi.fill = F_IN; mi.number_format = fmt
            us = I[f"{USED[i]}{r}"]; us.value = f'=IF({MINE[i]}{r}="",{MC[i]}{r},{MINE[i]}{r})'
            us.number_format = fmt
        rows.append(r)
    return rows


G = {}
G["occ"] = grid("Occupancy % by category", "OCC", PCT)
G["rack"] = grid("RACK rate per night ($)", "RACK", USD)
G["netman"] = grid("NET rate fixed by hand ($) — blank = rack × net factor", "NETMAN", USD, blank_if_missing=True)
G["pax"] = grid("Guests per occupied room", "PAX", "0.00")
I.freeze_panes = "E4"


def used(key, n, i):
    return f"'RV3 Inputs'!{USED[i]}{G[key][n]}"


UNITS = [f"'RV3 Inputs'!$F${cr}" for cr in CAT]
SETC = [f"'RV3 Inputs'!$C${cr}" for cr in CAT]
CODEC = [f"'RV3 Inputs'!$B${cr}" for cr in CAT]
NAMEC = [f"'RV3 Inputs'!$A${cr}" for cr in CAT]
DAYSC = [f"'RV3 Inputs'!{MC[i]}${DAYS}" for i in range(12)]
OPENC = [f"'RV3 Inputs'!{MC[i]}${OPEN}" for i in range(12)]
NFC = [f"'RV3 Inputs'!{MC[i]}${NF}" for i in range(12)]
_rangos = [f"'RV3 Inputs'!D{KROWS[0]}:D{KROWS[-1]}", f"'RV3 Inputs'!E{CAT_FIRST}:E{CAT_LAST}",
           f"'RV3 Inputs'!{MC[0]}{NF_MINE}:{MC[-1]}{NF_MINE}"]
_rangos += [f"'RV3 Inputs'!{MINE[0]}{G[g][0]}:{MINE[-1]}{G[g][-1]}" for g in ("occ", "rack", "netman", "pax")]
# Solo celdas de captura (sin fórmulas): COUNTA contaría un "" de fórmula como lleno.
MINE_COUNT = "+".join(f"COUNTA({x})" for x in _rangos)

# ════════════════════════════ RV4 Rooms ════════════════════════════
R = wb.create_sheet("RV4 Rooms")
base(R, "RV4 · Rooms — nights, guests and Room Revenue by category and set",
     "Available = units × days × operates · Occupied = occupancy % × available · Guests = occupied × guests/room · "
     "Net rate = hand-fixed net if any, else rack × net factor · Revenue = occupied × net rate. All from RV3 «USED».")
R.freeze_panes = "E4"
r = 3; RR = {}


def rblock(metric, title, fmt, fcell, totals=True):
    global r
    r += 1
    month_header(R, r, title)
    RR[metric] = {"rows": []}
    for n in range(SLOTS):
        r += 1
        R.cell(r, 1, f"={NAMEC[n]}"); R.cell(r, 2, f"={CODEC[n]}"); R.cell(r, 3, f"={SETC[n]}")
        R.cell(r, 4, f"={UNITS[n]}")
        for i in range(12):
            c = R[f"{MC[i]}{r}"]
            c.value = f'=IF($B{r}="",0,{fcell(n, i, r)})'; c.number_format = fmt
        if totals:
            R[f"{YC}{r}"] = f"=SUM(E{r}:P{r})"; R[f"{YC}{r}"].number_format = fmt
        RR[metric]["rows"].append(r)
    if not totals:
        r += 1
        return
    a, z = RR[metric]["rows"][0], RR[metric]["rows"][-1]
    for setn in ("Standard", "Villas"):
        r += 1
        R.cell(r, 1, f"Subtotal {setn}").font = B; R.cell(r, 3, setn)
        for i in range(12):
            c = R[f"{MC[i]}{r}"]; c.value = f'=SUMIF($C${a}:$C${z},"{setn}",{MC[i]}${a}:{MC[i]}${z})'
            c.number_format = fmt; c.font = B
        R[f"{YC}{r}"] = f"=SUM(E{r}:P{r})"; R[f"{YC}{r}"].number_format = fmt; R[f"{YC}{r}"].font = B
        for cc in range(1, 18):
            R.cell(r, cc).fill = F_S
        RR[metric][setn] = r
    r += 1
    R.cell(r, 1, "TOTAL HOTEL").font = B; R.cell(r, 3, "Total")
    for i in range(12):
        c = R[f"{MC[i]}{r}"]; c.value = f"=SUM({MC[i]}{a}:{MC[i]}{z})"; c.number_format = fmt; c.font = B
    R[f"{YC}{r}"] = f"=SUM(E{r}:P{r})"; R[f"{YC}{r}"].number_format = fmt; R[f"{YC}{r}"].font = B
    for cc in range(1, 18):
        R.cell(r, cc).fill = F_T; R.cell(r, cc).border = TOP
    RR[metric]["Total"] = r
    r += 1


rblock("avail", "Available room nights", USD0,
       lambda n, i, rw: f"N($D{rw})*{DAYSC[i]}*{OPENC[i]}")
rblock("occ", "Occupied room nights (Rooms Occupied)", N1,
       lambda n, i, rw: f"N({used('occ', n, i)})*{MC[i]}{RR['avail']['rows'][n]}")
rblock("pax", "Guest-nights (guests × nights)", N1,
       lambda n, i, rw: f"{MC[i]}{RR['occ']['rows'][n]}*N({used('pax', n, i)})")
rblock("net", "NET rate applied per night ($)", USD,
       lambda n, i, rw: (f"IF(ISNUMBER({used('netman', n, i)}),{used('netman', n, i)},"
                         f"N({used('rack', n, i)})*{NFC[i]})"), totals=False)
rblock("rev", "Room Revenue (occupied × net rate)", USD,
       lambda n, i, rw: f"{MC[i]}{RR['occ']['rows'][n]}*{MC[i]}{RR['net']['rows'][n]}")
r += 1
month_header(R, r, "KPIs by set", extra=("", "Set", ""))
KPI = {}
for setn in ("Standard", "Villas", "Total"):
    a, o, p, v = (RR[k][setn] for k in ("avail", "occ", "pax", "rev"))
    for lab, f, fmt, yf in (
            ("Occupancy %", lambda c: f"=IF({c}{a}=0,0,{c}{o}/{c}{a})", PCT, f"=IF(Q{a}=0,0,Q{o}/Q{a})"),
            ("Net ADR", lambda c: f"=IF({c}{o}=0,0,{c}{v}/{c}{o})", USD, f"=IF(Q{o}=0,0,Q{v}/Q{o})"),
            ("RevPAR", lambda c: f"=IF({c}{a}=0,0,{c}{v}/{c}{a})", USD, f"=IF(Q{a}=0,0,Q{v}/Q{a})"),
            ("Guests per room", lambda c: f"=IF({c}{o}=0,0,{c}{p}/{c}{o})", "0.00", f"=IF(Q{o}=0,0,Q{p}/Q{o})")):
        r += 1
        R.cell(r, 1, f"{lab} · {setn}"); R.cell(r, 3, setn)
        for i in range(12):
            R[f"{MC[i]}{r}"] = f(MC[i]); R[f"{MC[i]}{r}"].number_format = fmt
        R[f"{YC}{r}"] = yf; R[f"{YC}{r}"].number_format = fmt
    r += 1

# ════════════════════════════ RV5 Revenue lines ════════════════════════════
Lw = wb.create_sheet("RV5 Revenue lines")
base(Lw, "RV5 · Every revenue line: Standard + Villas = Total, against the Revenue Checkbook",
     "Same formula as the «Fill from drivers» button. The green «FinPlan» row is what is saved in the checkbook. "
     "With no «Mine» assumptions the Difference must be 0; with Mine it is the effect of your assumptions.",
     a=50, b=14, c=12, d=4)
Lw.freeze_panes = "E4"
r = 3; LR = {}


def P(s, i): return f"'RV4 Rooms'!{MC[i]}{RR['pax'][s]}"
def RVN(s, i): return f"'RV4 Rooms'!{MC[i]}{RR['rev'][s]}"
def K(k): return KN[k]


CONS = f"(1-{K('no_consume_pct')}/100)"
lines = [
    ("ROOMS", "4000 · Rooms", "Σ occupied nights × net rate of each category (RV4)",
     lambda s, i: f"={RVN(s, i)}"),
    ("FOOD", "4110 · Food", "guest-nights × Food rack × net factor × (1 − % no consume)",
     lambda s, i: f"={P(s, i)}*{K('food')}*{NFC[i]}*{CONS}"),
    ("BEVERAGE", "4120 · Beverage", "Food of the same row × Beverage % (inherits the no-consume)", None),
    ("ACTIVITIES", "4400 · Tours / Activities", "guest-nights ÷ nights per stay × Tours rack × net factor × (1 − % no consume)",
     lambda s, i: f"={P(s, i)}/{K('nights_per_stay')}*{K('tours')}*{NFC[i]}*{CONS}"),
    ("TRANSPORT", "4500 · Transportation", "guest-nights ÷ nights per stay × Transport rack × net factor × (1 − % no consume)",
     lambda s, i: f"={P(s, i)}/{K('nights_per_stay')}*{K('transport')}*{NFC[i]}*{CONS}"),
    ("SUSTAINABILITY", "4880 · Sustainability Fee", "guest-nights × fee × (1 − % that does not pay) — NO net factor",
     lambda s, i: f"={P(s, i)}*{K('sust_rate')}*(1-{K('sust_non_pay')}/100)"),
    ("RETAIL", "4301 · Retail Gift Shop", "Room Revenue × Retail %",
     lambda s, i: f"={RVN(s, i)}*{K('retail_pct')}/100"),
    ("INNOCEANA", "4600 · Innoceana", "Room Revenue × Innoceana %",
     lambda s, i: f"={RVN(s, i)}*{K('innoceana_pct')}/100"),
]


def cb_row(row, key_lines):
    for i in range(12):
        c = Lw[f"{MC[i]}{row}"]
        c.value = "=" + "+".join(V(f'"CB|{k}|"&\'RV3 Inputs\'!{MC[i]}${MROW}') for k in key_lines)
        c.number_format = USD; c.font = GREEN
    Lw[f"{YC}{row}"] = f"=SUM(E{row}:P{row})"; Lw[f"{YC}{row}"].number_format = USD; Lw[f"{YC}{row}"].font = GREEN


for key, lab, form, fn in lines:
    r += 1
    month_header(Lw, r, lab, extra=("Set", "", ""))
    Lw.cell(r + 1, 1, form).font = GR
    r += 1
    LR[key] = {}
    for setn in ("Standard", "Villas", "Total"):
        r += 1
        Lw.cell(r, 1, f"{lab} · {setn}" + (" (all sets)" if setn == "Total" else "")); Lw.cell(r, 2, setn)
        for i in range(12):
            c = Lw[f"{MC[i]}{r}"]
            c.value = (f"={MC[i]}{LR['FOOD'][setn]}*{K('bev_ratio')}/100" if key == "BEVERAGE" else fn(setn, i))
            c.number_format = USD
            if setn == "Total":
                c.font = B
        Lw[f"{YC}{r}"] = f"=SUM(E{r}:P{r})"; Lw[f"{YC}{r}"].number_format = USD
        if setn == "Total":
            Lw[f"{YC}{r}"].font = B
            for cc in range(1, 18):
                Lw.cell(r, cc).fill = F_T
        LR[key][setn] = r
    r += 1
    Lw.cell(r, 1, "FinPlan · Revenue Checkbook (what the P&L reads)").font = GREEN; Lw.cell(r, 2, "FinPlan")
    cb_row(r, [key]); LR[key]["CB"] = r
    r += 1
    Lw.cell(r, 1, "Difference (FinPlan − calculated)")
    for i in range(12):
        Lw[f"{MC[i]}{r}"] = f"={MC[i]}{LR[key]['CB']}-{MC[i]}{LR[key]['Total']}"; Lw[f"{MC[i]}{r}"].number_format = USD
    Lw[f"{YC}{r}"] = f"=SUM(E{r}:P{r})"; Lw[f"{YC}{r}"].number_format = USD
    LR[key]["DIF"] = r
    r += 1

fixed = [("SPA", "4201 · Spa", "Typed month by month in FinPlan: no driver (neither occupancy nor guests)", ["SPA"]),
         ("LAUNDRY", "4700 · Laundry (outside customers)", "Typed fixed amount", ["LAUNDRY"]),
         ("FNB_MISC", "4132 · F&B Misc", "Typed", ["FNB_MISC"]),
         ("CLUB", "Club (3 accounts)", "Typed", ["CLUB", "CLUB_ACTIVIDAD", "CLUB_VISITANTES"])]
for key, lab, form, ks in fixed:
    r += 1
    month_header(Lw, r, lab, extra=("Set", "", ""))
    Lw.cell(r + 1, 1, form).font = GR
    r += 2
    Lw.cell(r, 1, f"{lab} · hotel (not split by set)").font = GREEN; Lw.cell(r, 2, "Hotel")
    cb_row(r, ks); LR[key] = {"CB": r, "Total": r}
    r += 1

# Retail: el monto viejo de revenue_other, para el control
r += 1
Lw.cell(r, 1, "Retail typed in revenue_other (what a drivers P&L would use)").font = GR
for i in range(12):
    Lw[f"{MC[i]}{r}"] = "=" + V(f'"OTRO|RETAIL|"&\'RV3 Inputs\'!{MC[i]}${MROW}'); Lw[f"{MC[i]}{r}"].number_format = USD
Lw[f"{YC}{r}"] = f"=SUM(E{r}:P{r})"; Lw[f"{YC}{r}"].number_format = USD
RETAIL_OTRO = r

# ════════════════════════════ RV1 Revenue Build ════════════════════════════
X = wb.create_sheet("RV1 Revenue Build", 0)
X["A1"] = "RV1 · Revenue build — Standard vs Villas"; X["A1"].font = H1
X["A2"] = ("Every line rebuilt from its inputs (RV3) with formulas. Data → Refresh All brings the scenario chosen in RV3. "
           "Yellow cells in RV3 are your own assumptions.")
X["A2"].font = GR
X["A3"] = '="Scenario: "&\'RV3 Inputs\'!B8&"   ·   P&L source: "&\'RV3 Inputs\'!B9&"   ·   read "&\'RV3 Inputs\'!B10'
X["A3"].font = B
cols = ["Line", "Standard", "Villas", "Hotel (not split)", "Total calculated", "FinPlan checkbook", "Difference", "% Villas"]
for j, c in enumerate(cols):
    X.cell(5, 1 + j, c).font = B; X.cell(5, 1 + j).fill = F_H
xr = 6
q = lambda row: f"='RV5 Revenue lines'!Q{row}"
for key, lab, *_ in lines + [(k, l, None, None) for k, l, _, _ in fixed]:
    X.cell(xr, 1, lab)
    if "Standard" in LR[key]:
        X.cell(xr, 2, q(LR[key]["Standard"])); X.cell(xr, 3, q(LR[key]["Villas"])); X.cell(xr, 4, 0)
        X.cell(xr, 5, q(LR[key]["Total"]))
    else:
        X.cell(xr, 2, 0); X.cell(xr, 3, 0); X.cell(xr, 4, q(LR[key]["CB"])); X.cell(xr, 5, f"=B{xr}+C{xr}+D{xr}")
    X.cell(xr, 6, q(LR[key]["CB"])); X.cell(xr, 7, f"=F{xr}-E{xr}"); X.cell(xr, 8, f"=IF(E{xr}=0,0,C{xr}/E{xr})")
    for c in range(2, 8):
        X.cell(xr, c).number_format = USD
    X.cell(xr, 8).number_format = PCT
    xr += 1
X.cell(xr, 1, "TOTAL REVENUE").font = B
for c in range(2, 8):
    X.cell(xr, c, f"=SUM({L(c)}6:{L(c)}{xr-1})").number_format = USD
    X.cell(xr, c).font = B; X.cell(xr, c).fill = F_T; X.cell(xr, c).border = TOP
X.cell(xr, 8, f"=IF(E{xr}=0,0,C{xr}/E{xr})").number_format = PCT
TOT = xr
xr += 1; X.cell(xr, 1, "% of total revenue").font = GR
for c in range(2, 6):
    X.cell(xr, c, f"=IF($E${TOT}=0,0,{L(c)}{TOT}/$E${TOT})").number_format = PCT

xr += 2
for j, c in enumerate(["Statistics (full year)", "Standard", "Villas", "", "Total hotel"]):
    X.cell(xr, 1 + j, c).font = B; X.cell(xr, 1 + j).fill = F_H
ST = {}
for lab, k, f in (("Available room nights", "avail", USD0), ("Rooms Occupied (occupied nights)", "occ", N1),
                  ("Guest-nights", "pax", N1)):
    xr += 1; X.cell(xr, 1, lab)
    for c, s in ((2, "Standard"), (3, "Villas"), (5, "Total")):
        X.cell(xr, c, f"='RV4 Rooms'!Q{RR[k][s]}").number_format = f
    ST[k] = xr
for lab, f, fm in (("Occupancy %", lambda c: f"=IF({c}{ST['avail']}=0,0,{c}{ST['occ']}/{c}{ST['avail']})", PCT),
                   ("Net ADR (Room Revenue ÷ occupied)", lambda c: f"=IF({c}{ST['occ']}=0,0,{c}6/{c}{ST['occ']})", USD),
                   ("Guests per room", lambda c: f"=IF({c}{ST['occ']}=0,0,{c}{ST['pax']}/{c}{ST['occ']})", "0.00"),
                   ("Share of occupied nights", lambda c: f"=IF($E${ST['occ']}=0,0,{c}{ST['occ']}/$E${ST['occ']})", PCT),
                   ("Share of guests", lambda c: f"=IF($E${ST['pax']}=0,0,{c}{ST['pax']}/$E${ST['pax']})", PCT),
                   ("Revenue per occupied night (Rooms + package + Retail)",
                    lambda c: f"=IF({c}{ST['occ']}=0,0,{c}{TOT}/{c}{ST['occ']})", USD)):
    xr += 1; X.cell(xr, 1, lab)
    for c in ("B", "C"):
        X[f"{c}{xr}"] = f(c); X[f"{c}{xr}"].number_format = fm
    if "Revenue per" not in lab:
        X[f"E{xr}"] = f("E"); X[f"E{xr}"].number_format = fm

# Controles
xr += 2
for j, c in enumerate(["Controls", "Value", "Status", "", "What it means"]):
    X.cell(xr, 1 + j, c).font = B; X.cell(xr, 1 + j).fill = F_H
MINES = xr + 1
sum_abs = "+".join(f"ABS('RV5 Revenue lines'!Q{LR[k]['DIF']})" for k, *_ in lines)
ctrls = [
    ("Your own assumptions typed in RV3 (Mine)", f"={MINE_COUNT}", f'=IF(B{{r}}=0,"FinPlan only","{{0}} — differences are YOUR effect")',
     "0 = everything is FinPlan. Any yellow cell filled turns the Difference column into the effect of your assumptions."),
    ("Scenario loaded", "='RV3 Inputs'!B8", '=IF(B{r}="","REFRESH","OK")',
     "Blank = no data yet: Data → Refresh All (key in Config!C5)."),
    ("Room categories in FinPlan (sheet has 10 slots)", "=IFERROR(VALUE(" + T('"INFO|categorias|0"') + "),0)",
     f'=IF(B{{r}}>{SLOTS},"ADD SLOTS",IF(B{{r}}=0,"REFRESH","OK"))',
     "FinPlan sends the categories in its own order; more than 10 needs the sheet rebuilt."),
    ("Nights in sets other than Standard / Villas",
     f"='RV4 Rooms'!Q{RR['occ']['Total']}-'RV4 Rooms'!Q{RR['occ']['Standard']}-'RV4 Rooms'!Q{RR['occ']['Villas']}",
     '=IF(ABS(B{r})<0.01,"OK","CHECK")', "A category assigned to Residences (or a new set) would show here."),
    ("|FinPlan − calculated|, all calculated lines", f"={sum_abs}",
     f'=IF(B{MINES}>0,"n/a (Mine active)",IF(\'RV3 Inputs\'!B9="drivers","n/a (P&L on drivers)",IF(B{{r}}<1,"OK","CHECK")))',
     "With FinPlan inputs only, must be under $1. Otherwise someone typed the checkbook by hand or the inputs changed after «Fill from drivers»."),
    ("Retail: checkbook − revenue_other", f"='RV5 Revenue lines'!Q{LR['RETAIL']['CB']}-'RV5 Revenue lines'!Q{RETAIL_OTRO}",
     '=IF(ABS(B{r})<1,"OK","TWO NUMBERS")', "Retail lives in two places. The P&L reads the checkbook only while the source is «checkbook»."),
    ("Average guests per room (full year)", f"=E{ST['pax']-0}/MAX(1,E{ST['occ']})",
     '=IF(ABS(B{r}-1.8)<0.005,"=1.8","not 1.8")', "Every 0.1 guest moves Food, Beverage, Tours, Transport and Sustainability ~5%."),
]
for lab, val, st, expl in ctrls:
    xr += 1
    X.cell(xr, 1, lab)
    c = X.cell(xr, 2, val); c.number_format = USD if "ABS" in val or "Retail" in lab or "Nights" in lab else "0.00"
    X.cell(xr, 3, st.replace("{r}", str(xr)).replace("{0}", '"&B' + str(xr) + '&"')).font = B
    X.cell(xr, 5, expl).font = GR
X.column_dimensions["A"].width = 56
for c in "BCDEFG":
    X.column_dimensions[c].width = 17
X.column_dimensions["H"].width = 10
X.sheet_view.showGridLines = False

# ════════════════════════════ RV2 Per guest-night ════════════════════════════
C = wb.create_sheet("RV2 Per guest-night", 1)
C["A1"] = "RV2 · From rack rate to the dollar that comes in, per guest-night"; C["A1"].font = H1
C["A2"] = ("What ONE guest leaves in ONE night in each package line. Same for Standard and Villas: the package does not look at the "
           "category. Net factor shown = January's (RV3).")
C["A2"].font = GR
hd = ["Line", "Rack", "Unit", "÷ nights per stay", "× net factor", "× (1 − no consume)", "× (1 − does not pay)",
      "Net per guest-night", "Guest-nights Standard", "Guest-nights Villas", "Revenue Standard", "Revenue Villas"]
for j, t in enumerate(hd):
    C.cell(4, 1 + j, t).font = B; C.cell(4, 1 + j).fill = F_H; C.cell(4, 1 + j).alignment = Alignment(wrap_text=True)
nf1 = NFC[0]
pS = f"'RV4 Rooms'!Q{RR['pax']['Standard']}"; pV = f"'RV4 Rooms'!Q{RR['pax']['Villas']}"
cad = [("Food", f"={K('food')}", "per guest-night", 1, f"={nf1}", f"={CONS}", 1),
       ("Beverage (% of Food)", f"={K('food')}*{K('bev_ratio')}/100", "derived from Food", 1, f"={nf1}", f"={CONS}", 1),
       ("Tours", f"={K('tours')}", "per guest-stay", f"={K('nights_per_stay')}", f"={nf1}", f"={CONS}", 1),
       ("Transport", f"={K('transport')}", "per guest-stay", f"={K('nights_per_stay')}", f"={nf1}", f"={CONS}", 1),
       ("Sustainability Fee", f"={K('sust_rate')}", "per guest-night", 1, 1, 1, f"=1-{K('sust_non_pay')}/100")]
for k, (lab, rk, u, div, nf_, co, np_) in enumerate(cad):
    rr = 5 + k
    C.cell(rr, 1, lab); C.cell(rr, 2, rk).number_format = USD; C.cell(rr, 3, u)
    C.cell(rr, 4, div).number_format = "0.0"; C.cell(rr, 5, nf_).number_format = PCT4
    C.cell(rr, 6, co).number_format = PCT; C.cell(rr, 7, np_).number_format = PCT
    C.cell(rr, 8, f"=IF(D{rr}=0,0,B{rr}/D{rr}*E{rr}*F{rr}*G{rr})").number_format = USD; C.cell(rr, 8).font = B
    C.cell(rr, 9, f"={pS}").number_format = N1; C.cell(rr, 10, f"={pV}").number_format = N1
    C.cell(rr, 11, f"=H{rr}*I{rr}").number_format = USD; C.cell(rr, 12, f"=H{rr}*J{rr}").number_format = USD
C.cell(10, 1, "Full package per guest-night").font = B
for c, f in ((8, "=SUM(H5:H9)"), (11, "=SUM(K5:K9)"), (12, "=SUM(L5:L9)")):
    C.cell(10, c, f).number_format = USD; C.cell(10, c).font = B; C.cell(10, c).fill = F_T
C["A12"] = ("Revenue columns use the full-year guest-nights × January's net factor: they match RV5 only while the net factor is the same "
            "every month (true in FinPlan today). RV5 is the month-by-month truth.")
C["A12"].font = GR
C.column_dimensions["A"].width = 30
for j in range(2, 13):
    C.column_dimensions[L(j)].width = 15
C.row_dimensions[4].height = 32
C.sheet_view.showGridLines = False

# ════════════════════════════ RV Data ════════════════════════════
D = wb.create_sheet("RV Data")
D["A1"] = "Clave"; D["B1"] = "Valor"; D["C1"] = "Texto"
for k, f in enumerate(MUESTRA, start=2):
    D.cell(k, 1, f["clave"]); D.cell(k, 2, f["valor"]); D.cell(k, 3, f["texto"])
D.column_dimensions["A"].width = 26; D.column_dimensions["C"].width = 30

wb.save(OUT)

# Dónde quedó cada dato de RV3 Inputs, para `cablear_revision.py`: las pestañas
# de revisión del owner leen de su «Supuestos» y esa hoja pasa a leer de acá.
json.dump({
    "MROW": MROW, "DAYS": DAYS, "OPEN": OPEN, "NF": NF,
    "knobs": {k: int(KN[k].split("$")[-1]) for k in KN},
    "cat": CAT, "grids": G, "used_cols": USED, "used_units_col": "F",
}, open(OUT.rsplit(".", 1)[0] + "_mapa.json", "w", encoding="utf-8"), indent=1)
print("ok", OUT, "| RV3 filas", I.max_row, "| RV4", R.max_row, "| RV5", Lw.max_row)
