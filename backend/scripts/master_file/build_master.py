# -*- coding: utf-8 -*-
"""Master File de CWL: el reporte a dueños Forecast 2026 vs Budget 2027, en vivo.

Owner, 2026-11-12: «crear esto para CWL tal como está AMA pero ajustado a la
realidad de CWL» · «el archivo y la presentación deben ser blindados para que se
actualicen sin ningún problema en caso de cambio de datos» · «los forecast 2026
pueden ir cambiando, ahora la última es October; seguro terminemos con
noviembre y diciembre».

Formato del Master File de Amarena (hojas AM + Reporte), armado sobre el libro
en vivo de CWL (`../gl_en_vivo`). Las reglas de blindaje:

* **Versión por etiqueta, nunca por nombre.** «Forecast 2026» va SIN versión en
  Config: FinPlan devuelve el ★ Current (hoy October). Cuando se marque
  November, el próximo refresh lo trae solo. El nombre real se muestra con
  fórmula (`AM98 Versions`).
* **Cada número se busca por código de línea** del P&L (`tMotor[Linea]`) o por
  categoría/depto del GL, con SUMIFS: ninguna fórmula apunta a un número de fila
  de una tabla de datos.
* **Cada sección cierra con «otras líneas» = total − lo listado**: si FinPlan
  agrega una línea, aparece ahí y los totales siguen cuadrando.
* **Controles** que tienen que dar 0 (`AM97 Controls`).

    python build_master.py <spec.json>

El spec lo escribe en el libro `aplicar.ps1` (COM de Excel), DESPUÉS de que las
tablas existen: escribir fórmulas con referencias a tablas que todavía no
existen las rompe al abrir.
"""
import json
import sys

MESES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
COLS = "CDEFGHIJKLMN"          # meses; O = año

# Versiones del reporte: código, etiqueta en Config (tVersiones), qué es.
VERSIONES = [
    ("A25", "Actual 2025", "2025 actual (same period last year)"),
    ("A26", "Actual 2026", "2026 actual"),
    ("F26", "Forecast 2026", "FinPlan ★ Current: the latest forecast marked"),
    ("B27", "Budget 2027 Working", "Budget 2027 work in progress"),
]

# ── Las secciones del P&L de CWL (códigos de tMotor) ─────────────────────────
INGRESOS = [
    ("Rooms", ["REV_ROOMS", "REV_ROOMS_OTHER"]),
    ("F&B", ["REV_FB", "REV_FB_BEV", "REV_FB_MISC", "REV_PRIVATE_BAR"]),
    ("Tours", ["REV_TOURS"]),
    ("Transportation", ["REV_TRANSPORTATION"]),
    ("Spa", ["REV_SPA"]),
    ("Gift Shop / Store", ["REV_RETAIL", "REV_TIENDA"]),
    ("Laundry", ["REV_LAUNDRY"]),
    ("Innoceana", ["REV_INNOCEANA"]),
    ("Crowther Lab", ["REV_CROWTHER_LAB"]),
    ("Claro del Bosque", ["REV_CLARO_HUERTA"]),
    ("Sustainability Fee", ["REV_SUSTAINABILITY"]),
    ("Other revenue", ["REV_MISC_OTHER"]),
]
GASTOS_DEPTO = [   # payroll + costo + opex del departamento (USALI)
    ("Rooms", ["OPEX_ROOMS"]),
    ("F&B", ["OPEX_FB", "OPEX_PRIVATE_BAR", "COS_FB_FOOD", "COS_FB_BEV", "COS_FB_MISC", "COS_PRIVATE_BAR"]),
    ("Tours", ["OPEX_TOURS", "COS_TOURS"]),
    ("Transportation", ["OPEX_TRANSPORTATION", "COS_TRANSPORTATION"]),
    ("Spa", ["OPEX_SPA", "COS_SPA"]),
    ("Gift Shop / Store", ["OPEX_RETAIL", "OPEX_TIENDA", "COS_RETAIL", "COS_TIENDA"]),
    ("Laundry", ["OPEX_LAUNDRY", "COS_LAUNDRY"]),
    ("Innoceana", ["OPEX_INNOCEANA", "COS_INNOCEANA"]),
    ("Crowther Lab", ["OPEX_CROWTHER_LAB", "COS_CROWTHER_LAB"]),
    ("Other", ["OPEX_MISCELLANEOUS"]),
]
UTILIDAD_DEPTO = [
    ("Rooms", ["PROFIT_ROOMS"]),
    ("F&B", ["PROFIT_FB", "PROFIT_PRIVATE_BAR"]),
    ("Tours", ["PROFIT_TOURS"]),
    ("Transportation", ["PROFIT_TRANSPORTATION"]),
    ("Spa", ["PROFIT_SPA"]),
    ("Gift Shop / Store", ["PROFIT_RETAIL", "PROFIT_TIENDA"]),
    ("Laundry", ["PROFIT_LAUNDRY"]),
    ("Innoceana", ["PROFIT_INNOCEANA"]),
    ("Crowther Lab", ["PROFIT_CROWTHER_LAB"]),
    ("Claro del Bosque", ["PROFIT_CLARO_HUERTA"]),
    ("Sustainability Fee", ["PROFIT_SUSTAINABILITY"]),
    ("Other", ["PROFIT_MISC_OTHER"]),
]
OVERHEAD = [
    ("Administrative & General", ["OH_ADMIN", "OH_EMPLOYEE_BENEFITS", "COH_EMPLOYEE_BENEFITS"]),
    ("Sales & Marketing", ["OH_SALES_MARKETING"]),
    ("Credit card commissions", ["OH_CC_COMMISSIONS"]),
    ("Maintenance", ["OH_MAINTENANCE"]),
    ("Information systems (IT)", ["OH_INFORMATION_SYSTEM", "COH_INFORMATION_SYSTEM"]),
    ("Utilities (energy & water)", ["OH_UTILITIES"]),
    ("Claro Huerta", ["OH_CLARO_HUERTA", "COH_CLARO_HUERTA"]),
    ("Staff cafeteria & laundry (allocation)", ["OH_CAFETERIA", "COH_CAFETERIA", "OH_LAUNDRY", "COH_LAUNDRY"]),
]
NO_OPERATIVOS = [
    ("Rent", ["RENT"]),
    ("Management fee (3%)", ["MGMT_FEE_3"]),
    ("Royalties (5%)", ["MGMT_FEE_5_ROYALTIES"]),
    ("Property insurance", ["PROPERTY_INSURANCE"]),
    ("Other expenses", ["OTHER_EXPENSES"]),
]
DEBAJO_EBITDA = [
    ("Capital reserve", ["CAPITAL_RESERVE"]),
    ("Large capex", ["LARGE_CAPEX"]),
]
FINANCIEROS = [
    ("Financial expenses", ["FINANCIAL_EXPENSES"]),
    ("Depreciation", ["TOTAL_DEPRECIATIONS"]),
]


# ── Fórmulas ─────────────────────────────────────────────────────────────────

def _lista(codigos):
    return "{" + ",".join(f'"{c}"' for c in codigos) + "}"


def motor(version_name, codigos, col_k):
    """Suma de líneas del P&L de una versión; col_k = celda con el n.º de columna (1-13)."""
    if len(codigos) == 1:
        return (f'IFERROR(SUMIFS(INDEX(tMotor[[M01]:[Annual]],0,{col_k}),tMotor[Etiqueta],{version_name},'
                f'tMotor[Linea],"{codigos[0]}"),0)')
    return (f'IFERROR(SUM(SUMIFS(INDEX(tMotor[[M01]:[Annual]],0,{col_k}),tMotor[Etiqueta],{version_name},'
            f'tMotor[Linea],{_lista(codigos)})),0)')


def gl(version_name, categoria, deptos, col_k, signo=1):
    """Suma del GL por categoría y departamento(s). El ingreso viene negativo."""
    s = "-" if signo < 0 else ""
    dep = f'"{deptos[0]}"' if len(deptos) == 1 else _lista(deptos)
    f = (f'SUMIFS(INDEX(tGL[[M01]:[Annual]],0,{col_k}),tGL[Etiqueta],{version_name},'
         f'tGL[Category],"{categoria}",tGL[Dept code],{dep})')
    return f'IFERROR({s}SUM({f}),0)' if len(deptos) > 1 else f'IFERROR({s}{f},0)'


def hab(version_name, campo, nivel, depto, mes_celda):
    """tHabitaciones: Nivel Hotel/Set; mes_celda vacía = el año entero."""
    dep = "" if depto is None else f',tHabitaciones[Depto],"{depto}"'
    mes = "" if mes_celda is None else f",tHabitaciones[Mes],{mes_celda}"
    return (f'IFERROR(SUMIFS(tHabitaciones[{campo}],tHabitaciones[Etiqueta],{version_name},'
            f'tHabitaciones[Nivel],"{nivel}"{dep}{mes}),0)')


def est(version_name, indicador, col_k):
    return (f'IFERROR(SUMIFS(INDEX(tEstadisticas[[M01]:[Anio]],0,{col_k}),tEstadisticas[Etiqueta],{version_name},'
            f'tEstadisticas[Indicador],"{indicador}"),0)')


def div(a, b, pct=False):
    return f'IF(ABS({b})<0.005,"",({a})/({b}))'


# ── Armado de hojas: filas con celdas desde la columna A ─────────────────────

class Hoja:
    def __init__(self, nombre, anchos, horizontal=False, ocultar_a=False):
        self.nombre, self.anchos = nombre, anchos
        self.filas, self.graficos, self.formatos = [], [], []
        self.horizontal, self.ocultar_a = horizontal, ocultar_a
        self.r = 0

    def fila(self, estilo, celdas, alto=None):
        self.r += 1
        self.filas.append({"r": self.r, "estilo": estilo, "celdas": [("" if c is None else str(c)) for c in celdas],
                           "alto": alto})
        return self.r

    def saltar(self, n=1):
        for _ in range(n):
            self.fila("blanco", [])

    def formato(self, rango, fmt):
        self.formatos.append({"rango": rango, "fmt": fmt})

    def grafico(self, **kw):
        self.graficos.append(kw)

    def json(self):
        return {"nombre": self.nombre, "anchos": self.anchos, "filas": self.filas,
                "graficos": self.graficos, "formatos": self.formatos,
                "horizontal": self.horizontal, "ocultar_a": self.ocultar_a}


USD = '#,##0;(#,##0);"-"'
USD2 = '#,##0.00;(#,##0.00);"-"'
PCT = '0.0%;-0.0%;""'
NUM = '#,##0;(#,##0);"-"'


def hoja_versiones():
    h = Hoja("AM98 Versions", [10, 26, 18, 22, 60])
    h.fila("titulo", ["", "CWL · Report versions"])
    h.fila("nota", ["", "Each version is looked up by its LABEL (the one in Config). «Forecast 2026» has no version: FinPlan "
                        "returns the ★ Current — October today; when November or December is marked, the next "
                        "Data → Refresh All brings it in and the whole report follows."])
    h.saltar()
    h.fila("encabezado", ["Code", "Label in Config", "Actual version (FinPlan)", "Loaded?", "What it is"])
    for cod, etq, que in VERSIONES:
        n = h.r + 1
        h.fila("normal", [cod, etq,
                          f'=IFERROR(INDEX(tMotor[Version],MATCH(B{n},tMotor[Etiqueta],0)),"—")',
                          f'=IF(COUNTIF(tMotor[Etiqueta],B{n})>0,"YES","NO — check Config")', que])
    return h


def nombres_version(fila0):
    """ver_A25… = la etiqueta; lA25… = el rótulo con el nombre real («Forecast 2026 · October»)."""
    out = {}
    for i, (cod, _, _) in enumerate(VERSIONES):
        r = fila0 + i
        out[f"ver_{cod}"] = f"='AM98 Versions'!$B${r}"
        out[f"l{cod}"] = None  # se arma en la hoja como fórmula
    return out


def rotulo(cod):
    """Rótulo de la versión: la etiqueta y, si dice algo más, el nombre real que tiene en
    FinPlan («Forecast 2026 · October»). No repite («Budget 2027 Working · Working») ni
    agrega «actual»."""
    real = f"INDEX('AM98 Versions'!$C:$C,MATCH(ver_{cod},'AM98 Versions'!$B:$B,0))"
    return (f'ver_{cod}&IFERROR(IF(OR({real}="—",{real}="",LOWER({real})="actual",'
            f'ISNUMBER(SEARCH({real},ver_{cod}))),""," · "&{real}),"")')


def encabezado_meses(h, titulo_formula):
    h.fila("encabezado", ["", "=" + titulo_formula] + MESES + ["FY"])


def fila_aux(h):
    """Fila 5: el n.º de columna de cada mes (1-12) y 13 = año, para INDEX(tabla,0,k)."""
    h.fila("aux", ["", "column # (helper)"] + [str(i) for i in range(1, 14)])
    return h.r


def bloque_motor(h, cod, aux_r, secciones):
    """Filas de P&L de una versión: cada sección con sus líneas, «otras» y el total."""
    v = f"ver_{cod}"
    k = lambda col: f"{col}${aux_r}"
    for titulo, items, total_cod, estilo_total in secciones:
        h.fila("seccion", ["", titulo])
        primeras = h.r + 1
        for nombre, codigos in items:
            h.fila("normal", ["|".join(codigos), nombre] +
                   [f"={motor(v, codigos, k(c))}" for c in COLS + "O"])
        ultima = h.r
        if total_cod:
            # Lo que no está listado: total − lo listado (una línea nueva nunca se pierde).
            h.fila("resto", ["", "Other lines (not listed)"] +
                   [f"={motor(v, [total_cod], k(c))}-SUM({c}{primeras}:{c}{ultima})" for c in COLS + "O"])
            h.fila(estilo_total, [total_cod, "Total " + titulo.split(" (")[0].lower()] +
                   [f"={motor(v, [total_cod], k(c))}" for c in COLS + "O"])


def resultados(h, cod, aux_r):
    v = f"ver_{cod}"
    k = lambda col: f"{col}${aux_r}"
    filas = {}
    for codigo, nombre, estilo in [
        ("TOTAL_GOP", "GOP (gross operating profit)", "total"),
        ("TOTAL_NON_OP_EXPENSES", "Non-operating expenses (rent, fees, insurance)", "normal"),
        ("EBITDA_BEFORE_CAPITAL", "EBITDA before capital", "total"),
        ("CAPITAL_EXPENSE", "Capital reserve & capex", "normal"),
        ("EBITDA_AFTER_CAPITAL", "EBITDA after capital", "total"),
        ("FINANCIAL_EXPENSES", "Financial expenses", "normal"),
        ("TOTAL_DEPRECIATIONS", "Depreciation", "normal"),
        ("EBT", "Earnings before income taxes", "subtotal"),
        ("INCOME_TAXES", "Income taxes", "normal"),
        ("NET_PROFIT", "NET PROFIT", "total"),
    ]:
        filas[codigo] = h.fila(estilo, [codigo, nombre] + [f"={motor(v, [codigo], k(c))}" for c in COLS + "O"])
    return filas


# ── AM03 Monthly P&L ─────────────────────────────────────────────────────────

def hoja_pl():
    h = Hoja("AM03 Monthly P&L", [26, 40] + [11] * 12 + [13], ocultar_a=True)
    h.fila("titulo", ["", "CWL · USALI income statement — monthly"])
    h.fila("nota", ["", "USD · expenses shown positive · every line is looked up by its FinPlan P&L code "
                        "(P&L Motor table). «Other lines» = total − listed lines: a new line lands there "
                        "and the total never changes."])
    h.saltar(2)
    aux = fila_aux(h)
    secciones = [
        ("REVENUE", INGRESOS, "TOTAL_REVENUES", "total"),
        ("DEPARTMENTAL EXPENSES (payroll + cost of sales + opex)", GASTOS_DEPTO, "TOTAL_OPERATING_EXPENSES", "subtotal"),
        ("DEPARTMENTAL PROFIT", UTILIDAD_DEPTO, "OPERATING_PROFIT", "total"),
        ("UNDISTRIBUTED EXPENSES (overhead)", OVERHEAD, "TOTAL_OVERHEAD_EXPENSES", "subtotal"),
    ]
    marcas = {}
    for cod in ("F26", "B27", "A25"):
        h.saltar()
        encabezado_meses(h, rotulo(cod))
        bloque_motor(h, cod, aux, secciones)
        marcas[cod] = resultados(h, cod, aux)
    h.formato(f"C{aux + 1}:O{h.r}", USD)
    return h, aux, marcas


# ── AM01 Rooms KPIs (hotel y sets) ───────────────────────────────────────────

def hoja_rooms():
    h = Hoja("AM01 Rooms KPIs", [8, 42] + [10] * 12 + [12], ocultar_a=True)
    h.fila("titulo", ["", "CWL · Rooms — key indicators, hotel and by room set (standard · Villas)"])
    h.fila("nota", ["", "Hotel: the P&L header indicators. Sets: the statistics by room type "
                        "(Room Stats in the Actual, drivers in the Budget). Occupancy, ADR and RevPAR come from the "
                        "period TOTALS, never averaging percentages."])
    h.saltar(2)
    aux = fila_aux(h)
    filas = {}
    for cod in ("F26", "B27", "A25"):
        v = f"ver_{cod}"
        h.saltar()
        encabezado_meses(h, rotulo(cod))
        h.fila("seccion", ["", "Hotel"])
        k = lambda c: f"{c}${aux}"
        d = h.fila("normal", ["", "Available room nights"] + [f"={est(v, 'Total rooms available', k(c))}" for c in COLS + "O"])
        o = h.fila("normal", ["", "Occupied room nights"] + [f"={est(v, 'Rooms occupied', k(c))}" for c in COLS + "O"])
        g = h.fila("normal", ["", "Guests"] + [f"={est(v, 'Huéspedes', k(c))}" for c in COLS + "O"])
        i = h.fila("normal", ["", "Rooms revenue"] + [f"={est(v, 'Ingreso de habitaciones', k(c))}" for c in COLS + "O"])
        oc = h.fila("pct", ["", "% Occupancy"] + [f"={div(f'{c}{o}', f'{c}{d}')}" for c in COLS + "O"])
        ad = h.fila("usd2", ["", "ADR"] + [f"={div(f'{c}{i}', f'{c}{o}')}" for c in COLS + "O"])
        rp = h.fila("usd2", ["", "Rooms RevPAR"] + [f"={div(f'{c}{i}', f'{c}{d}')}" for c in COLS + "O"])
        filas[(cod, "hotel")] = {"disp": d, "ocu": o, "ing": i, "occ": oc, "adr": ad, "revpar": rp, "pax": g}
        for depto, nombre in (("0110", "Standard rooms (0110)"), ("0115", "Villas (0115)")):
            h.fila("seccion", ["", nombre])
            mes = lambda c: f"{c}${aux}" if c != "O" else None
            d2 = h.fila("normal", ["", "Available room nights"] + [f"={hab(v, 'Disponibles', 'Set', depto, mes(c))}" for c in COLS + "O"])
            o2 = h.fila("normal", ["", "Occupied room nights"] + [f"={hab(v, 'Ocupadas', 'Set', depto, mes(c))}" for c in COLS + "O"])
            i2 = h.fila("normal", ["", "Rooms revenue"] + [f"={hab(v, 'Ingreso habitaciones', 'Set', depto, mes(c))}" for c in COLS + "O"])
            oc2 = h.fila("pct", ["", "% Occupancy"] + [f"={div(f'{c}{o2}', f'{c}{d2}')}" for c in COLS + "O"])
            ad2 = h.fila("usd2", ["", "ADR"] + [f"={div(f'{c}{i2}', f'{c}{o2}')}" for c in COLS + "O"])
            h.fila("usd2", ["", "RevPAR"] + [f"={div(f'{c}{i2}', f'{c}{d2}')}" for c in COLS + "O"])
            filas[(cod, depto)] = {"disp": d2, "ocu": o2, "ing": i2, "occ": oc2, "adr": ad2}
        h.fila("nota", ["", "=IF(SUMIFS(tHabitaciones[Ocupadas],tHabitaciones[Etiqueta]," + v +
                            ',tHabitaciones[Nivel],"Sin tipo")>0,"Note: some months of this version are not split by room type '
                            '(Actual 2024-2025 and the forecast own months): the sets are blank there and only '
                            'the hotel total counts.","")'])
    h.formato(f"C{aux + 1}:O{h.r}", NUM)
    return h, aux, filas


# ── AM08 Standard vs Villas ──────────────────────────────────────────────────

def hoja_sets(rooms_filas):
    h = Hoja("AM08 Standard vs Villas", [8, 46, 16, 16, 16, 4, 16, 16, 16], ocultar_a=True)
    h.fila("titulo", ["", "CWL · Standard rooms vs Villas — two products in one department"])
    h.fila("nota", ["", "Villas = GL department 0115 (and Residences 0116): its revenue, payroll and opex; its room nights from the room-type statistics. "
                        "Standard = hotel minus Villas (room nights) and P&L Rooms minus Villas (dollars). "
                        "So Standard + Villas always equals P&L Rooms. "
                        "Note: Villas carries no share of the common Rooms cost today (housekeeping, "
                        "front desk): its margin reads higher than it really is."])
    h.saltar()
    filas = {}
    for cod in ("F26", "B27"):
        v = f"ver_{cod}"
        h.saltar()
        h.fila("encabezado", ["", "=" + rotulo(cod), "Standard", "Villas", "Total Rooms", "", "% Standard", "% Villas", "Check"])
        K = "13"   # año
        rev_tot = motor(v, ["REV_ROOMS", "REV_ROOMS_OTHER"], K)
        rev_vil = gl(v, "REVENUE", ["0115", "0116"], K, -1)
        gas_tot = motor(v, ["OPEX_ROOMS"], K)
        cos_vil = gl(v, "COST_OF_SALES", ["0115", "0116"], K)
        pay_vil = gl(v, "PAYROLL", ["0115", "0116"], K)
        opx_vil = gl(v, "OPERATING_EXPENSES", ["0115", "0116"], K)
        n = h.r + 1
        ri = h.fila("normal", ["", "Rooms revenue", f"={rev_tot}-{rev_vil}", f"={rev_vil}", f"=C{n}+D{n}",
                               "", f"=IF(E{n}=0,\"\",C{n}/E{n})", f"=IF(E{n}=0,\"\",D{n}/E{n})",
                               f"=E{n}-({rev_tot})"])
        n = h.r + 1
        rp = h.fila("normal", ["", "Payroll", f"={gl(v, 'PAYROLL', ['0110', '0111', '0112', '0113', '0114'], K)}",
                               f"={pay_vil}", f"=C{n}+D{n}"])
        n = h.r + 1
        ro = h.fila("normal", ["", "Opex & cost of sales", f"=({gas_tot})-C{rp}-({pay_vil})-({opx_vil})-({cos_vil})",
                               f"=({opx_vil})+({cos_vil})", f"=C{n}+D{n}"])
        n = h.r + 1
        rg = h.fila("subtotal", ["", "Departmental expenses", f"=C{rp}+C{ro}", f"=D{rp}+D{ro}", f"=C{n}+D{n}",
                                 "", "", "", f"=E{n}-({gas_tot})"])
        n = h.r + 1
        ru = h.fila("total", ["", "Departmental profit", f"=C{ri}-C{rg}", f"=D{ri}-D{rg}", f"=C{n}+D{n}",
                              "", f"=IF(E{n}=0,\"\",C{n}/E{n})", f"=IF(E{n}=0,\"\",D{n}/E{n})",
                              f"=E{n}-({motor(v, ['PROFIT_ROOMS'], K)})"])
        n = h.r + 1
        h.fila("pct", ["", "Departmental margin", f"=IF(C{ri}=0,\"\",C{ru}/C{ri})", f"=IF(D{ri}=0,\"\",D{ru}/D{ri})",
                       f"=IF(E{ri}=0,\"\",E{ru}/E{ri})"])
        rf = rooms_filas
        n = h.r + 1
        h.fila("normal", ["", "Available room nights", f"='AM01 Rooms KPIs'!O{rf[(cod, 'hotel')]['disp']}-'AM01 Rooms KPIs'!O{rf[(cod, '0115')]['disp']}",
                          f"='AM01 Rooms KPIs'!O{rf[(cod, '0115')]['disp']}", f"=C{n}+D{n}"])
        nd = h.r
        n = h.r + 1
        h.fila("normal", ["", "Occupied room nights", f"='AM01 Rooms KPIs'!O{rf[(cod, 'hotel')]['ocu']}-'AM01 Rooms KPIs'!O{rf[(cod, '0115')]['ocu']}",
                          f"='AM01 Rooms KPIs'!O{rf[(cod, '0115')]['ocu']}", f"=C{n}+D{n}"])
        no = h.r
        h.fila("pct", ["", "% Occupancy", f"=IF(C{nd}=0,\"\",C{no}/C{nd})", f"=IF(D{nd}=0,\"\",D{no}/D{nd})",
                       f"=IF(E{nd}=0,\"\",E{no}/E{nd})"])
        h.fila("usd2", ["", "ADR (P&L revenue / occupied nights)", f"=IF(C{no}=0,\"\",C{ri}/C{no})",
                        f"=IF(D{no}=0,\"\",D{ri}/D{no})", f"=IF(E{no}=0,\"\",E{ri}/E{no})"])
        h.fila("usd2", ["", "Departmental profit per occupied night", f"=IF(C{no}=0,\"\",C{ru}/C{no})",
                        f"=IF(D{no}=0,\"\",D{ru}/D{no})", f"=IF(E{no}=0,\"\",E{ru}/E{no})"])
        filas[cod] = {"ing": ri, "util": ru}
        h.formato(f"C{ri}:E{ru}", USD)
        h.formato(f"I{ri}:I{ru}", USD)
        h.formato(f"G{ri}:H{ru}", PCT)
    return h, filas


# ── AM02 FY Summary ──────────────────────────────────────────────────────────

def hoja_resumen(pl_marcas, rooms_filas):
    h = Hoja("AM02 FY Summary", [30, 44, 16, 16, 16, 15, 11, 13], ocultar_a=True)
    h.fila("titulo", ["", "CWL · Full-year summary — Forecast 2026 vs Budget 2027"])
    h.fila("nota", ["", "=\"USD · Forecast = \"&" + rotulo("F26") + "&\" · Budget = \"&" + rotulo("B27") +
                        "&\" · reference: \"&" + rotulo("A25")])
    h.saltar()
    h.fila("encabezado", ["", "Indicator", "=" + rotulo("A25"), "=" + rotulo("F26"), "=" + rotulo("B27"),
                          "Var. B27 − F26", "Var. %", "% of B27 revenue"])
    K = "13"
    filas = {}

    def linea(nombre, f_por_version, estilo="normal", pct_ing=True, codigo=""):
        n = h.r + 1
        celdas = [codigo, nombre] + [("=" + f_por_version(c)) for c in ("A25", "F26", "B27")]
        if estilo in ("pct", "usd2"):
            celdas += [f"=IF(OR(D{n}=\"\",E{n}=\"\"),\"\",E{n}-D{n})", ""]
        else:
            celdas += [f"=E{n}-D{n}", f"=IF(D{n}=0,\"\",(E{n}-D{n})/ABS(D{n}))"]
        celdas += [f"=IF($E${{TOT}}=0,\"\",E{n}/$E${{TOT}})" if pct_ing else ""]
        r = h.fila(estilo, celdas)
        filas[nombre] = r
        return r

    rf = rooms_filas
    h.fila("seccion", ["", "Rooms — key indicators"])
    linea("% Occupancy", lambda c: f"'AM01 Rooms KPIs'!O{rf[(c, 'hotel')]['occ']}", "pct", False)
    linea("ADR (USD)", lambda c: f"'AM01 Rooms KPIs'!O{rf[(c, 'hotel')]['adr']}", "usd2", False)
    linea("Rooms RevPAR (USD)", lambda c: f"'AM01 Rooms KPIs'!O{rf[(c, 'hotel')]['revpar']}", "usd2", False)
    linea("Occupied room nights", lambda c: f"'AM01 Rooms KPIs'!O{rf[(c, 'hotel')]['ocu']}", "normal", False)
    linea("Guests", lambda c: f"'AM01 Rooms KPIs'!O{rf[(c, 'hotel')]['pax']}", "normal", False)
    h.fila("seccion", ["", "Revenue by department"])
    for nombre, codigos in INGRESOS:
        linea(nombre, lambda c, cs=codigos: motor(f"ver_{c}", cs, K), codigo="|".join(codigos))
    tot = linea("Total revenue", lambda c: motor(f"ver_{c}", ["TOTAL_REVENUES"], K), "total", codigo="TOTAL_REVENUES")
    h.fila("seccion", ["", "Results"])
    for cod_l, nombre, estilo in [
        ("OPERATING_PROFIT", "Departmental profit", "subtotal"),
        ("TOTAL_OVERHEAD_EXPENSES", "Undistributed expenses (overhead)", "normal"),
        ("TOTAL_GOP", "GOP", "total"),
        ("TOTAL_NON_OP_EXPENSES", "Non-operating expenses", "normal"),
        ("MGMT_FEE_3", "  of which: management fee (3%)", "normal"),
        ("EBITDA_BEFORE_CAPITAL", "EBITDA before capital", "total"),
        ("CAPITAL_EXPENSE", "Capital reserve & capex", "normal"),
        ("EBITDA_AFTER_CAPITAL", "EBITDA after capital", "total"),
        ("NET_PROFIT", "Net profit", "total"),
    ]:
        linea(nombre, lambda c, cl=cod_l: motor(f"ver_{c}", [cl], K), estilo, codigo=cod_l)
    h.fila("seccion", ["", "Margins"])
    for nombre, cl in [("GOP margin", "GOP"), ("EBITDA before capital margin", "EBITDA before capital")]:
        r_val = filas[cl]
        n = h.r + 1
        h.fila("pct", ["", nombre] + [f"=IF({c}{tot}=0,\"\",{c}{r_val}/{c}{tot})" for c in "CDE"] +
               [f"=IF(OR(D{n}=\"\",E{n}=\"\"),\"\",E{n}-D{n})", "", ""])
    # Reemplazar el marcador del total.
    for f in h.filas:
        f["celdas"] = [c.replace("{TOT}", str(tot)) for c in f["celdas"]]
    h.formato(f"C5:F{h.r}", USD)
    h.formato(f"G5:H{h.r}", PCT)
    return h, filas, tot


# ── AM07 Flow-through ────────────────────────────────────────────────────────

def hoja_flow():
    h = Hoja("AM07 Flow-through", [30, 40, 16, 16, 16, 14], ocultar_a=True)
    h.fila("titulo", ["", "CWL · Flow-through Forecast 2026 → Budget 2027"])
    h.fila("nota", ["", "How much of each additional revenue dollar reaches profit. Flow-through = Δ profit "
                        "÷ Δ revenue. The EBITDA bridge ties to the P&L (check at the end)."])
    h.saltar()
    h.fila("encabezado", ["", "Department", "Δ revenue", "Δ departmental profit", "Flow-through", ""])
    K = "13"
    pares = [(n, ing, util) for (n, ing), (_, util) in zip(INGRESOS, UTILIDAD_DEPTO)]
    primeras = h.r + 1
    for nombre, ing, util in pares:
        n = h.r + 1
        h.fila("normal", ["", nombre, f"={motor('ver_B27', ing, K)}-{motor('ver_F26', ing, K)}",
                          f"={motor('ver_B27', util, K)}-{motor('ver_F26', util, K)}", f"=IF(ABS(C{n})<1,\"\",D{n}/C{n})"])
    ult = h.r
    n = h.r + 1
    h.fila("total", ["", "Total", f"={motor('ver_B27', ['TOTAL_REVENUES'], K)}-{motor('ver_F26', ['TOTAL_REVENUES'], K)}",
                     f"={motor('ver_B27', ['OPERATING_PROFIT'], K)}-{motor('ver_F26', ['OPERATING_PROFIT'], K)}",
                     f"=IF(ABS(C{n})<1,\"\",D{n}/C{n})"])
    h.formato(f"C{primeras}:D{n}", USD)
    h.formato(f"E{primeras}:E{n}", PCT)
    h.saltar()
    h.fila("encabezado", ["", "EBITDA bridge (before capital)", "USD", "", "", ""])
    p0 = h.r + 1
    h.fila("subtotal", ["", "=\"EBITDA \"&" + rotulo("F26"), f"={motor('ver_F26', ['EBITDA_BEFORE_CAPITAL'], K)}"])
    h.fila("normal", ["", "+ Δ departmental profit", f"={motor('ver_B27', ['OPERATING_PROFIT'], K)}-{motor('ver_F26', ['OPERATING_PROFIT'], K)}"])
    h.fila("normal", ["", "− Δ undistributed expenses", f"=-({motor('ver_B27', ['TOTAL_OVERHEAD_EXPENSES'], K)}-{motor('ver_F26', ['TOTAL_OVERHEAD_EXPENSES'], K)})"])
    h.fila("normal", ["", "− Δ non-operating expenses (rent, fees, insurance)", f"=-({motor('ver_B27', ['TOTAL_NON_OP_EXPENSES'], K)}-{motor('ver_F26', ['TOTAL_NON_OP_EXPENSES'], K)})"])
    n = h.r + 1
    h.fila("total", ["", "=\"EBITDA \"&" + rotulo("B27"), f"=SUM(C{p0}:C{n - 1})"])
    h.fila("control", ["", "Check: against the P&L (must be 0)", f"=ROUND(C{n}-{motor('ver_B27', ['EBITDA_BEFORE_CAPITAL'], K)},2)"])
    h.formato(f"C{p0}:C{h.r}", USD)
    h.saltar()
    h.fila("encabezado", ["", "Approximate break-even (Budget 2027)", "USD", "", "", ""])
    q0 = h.r + 1
    h.fila("normal", ["", "Total revenue", f"={motor('ver_B27', ['TOTAL_REVENUES'], K)}"])
    h.fila("normal", ["", "Departmental profit", f"={motor('ver_B27', ['OPERATING_PROFIT'], K)}"])
    h.fila("pct", ["", "Departmental margin (contribution)", f"=IF(C{q0}=0,\"\",C{q0 + 1}/C{q0})"])
    h.fila("normal", ["", "Fixed costs: overhead + non-operating", f"={motor('ver_B27', ['TOTAL_OVERHEAD_EXPENSES'], K)}+{motor('ver_B27', ['TOTAL_NON_OP_EXPENSES'], K)}"])
    n = h.r + 1
    h.fila("total", ["", "Revenue for EBITDA = 0", f"=IF(OR(C{q0 + 2}=\"\",C{q0 + 2}<=0),\"\",C{q0 + 3}/C{q0 + 2})"])
    h.fila("pct", ["", "Cushion: how far Budget revenue can drop", f"=IF(OR(C{n}=\"\",C{q0}=0),\"\",1-C{n}/C{q0})"])
    h.fila("nota", ["", "Approximation: assumes the departmental margin holds and that overhead and "
                        "non-operating expenses are fixed. A conversation guide, not an exact figure."])
    h.formato(f"C{q0}:C{q0 + 1}", USD)
    h.formato(f"C{q0 + 3}:C{n}", USD)
    return h


# ── AM97 Controls ───────────────────────────────────────────────────────────

def hoja_controles():
    h = Hoja("AM97 Controls", [8, 70, 16, 16, 16, 16])
    h.fila("titulo", ["", "CWL · Master File checks (everything must be 0)"])
    h.fila("nota", ["", "If a check is not 0: Data → Refresh All and look again. If it persists, FinPlan data "
                        "changed in a way the report did not foresee: flag it before sending the PDF."])
    h.saltar()
    h.fila("encabezado", ["", "Check", "A25", "F26", "B27", "Status"])
    K = "13"
    controles = [
        ("P&L total revenue − GL revenue total",
         lambda c: f"ROUND({motor(c, ['TOTAL_REVENUES'], K)}-(-SUMIFS(tGL[Annual],tGL[Etiqueta],{c},tGL[Category],\"REVENUE\")),0)"),
        ("GOP − (departmental profit − overhead)",
         lambda c: f"ROUND({motor(c, ['TOTAL_GOP'], K)}-({motor(c, ['OPERATING_PROFIT'], K)}-{motor(c, ['TOTAL_OVERHEAD_EXPENSES'], K)}),0)"),
        ("Departmental profit − (revenue − departmental expenses)",
         lambda c: f"ROUND({motor(c, ['OPERATING_PROFIT'], K)}-({motor(c, ['TOTAL_REVENUES'], K)}-{motor(c, ['TOTAL_OPERATING_EXPENSES'], K)}),0)"),
        ("Net profit − (EBT − income taxes)",
         lambda c: f"ROUND({motor(c, ['NET_PROFIT'], K)}-({motor(c, ['EBT'], K)}-{motor(c, ['INCOME_TAXES'], K)}),0)"),
        ("Version not loaded (0 = loaded)", lambda c: f"IF(COUNTIF(tMotor[Etiqueta],{c})>0,0,1)"),
    ]
    p0 = h.r + 1
    for nombre, f in controles:
        n = h.r + 1
        h.fila("normal", ["", nombre] + [f"={f(v)}" for v in ("ver_A25", "ver_F26", "ver_B27")] +
               [f"=IF(SUMPRODUCT(ABS(C{n}:E{n}))=0,\"OK\",\"CHECK\")"])
    h.formato(f"C{p0}:E{h.r}", USD)
    return h


# ── Reporte (para PDF) ───────────────────────────────────────────────────────

def hoja_reporte(res_filas, tot, sets_filas, flow_r=None):
    h = Hoja("Report", [3, 46, 16, 16, 16, 13, 4])
    R = "'AM02 FY Summary'!"
    h.fila("portada", ["", "CORCOVADO WILDERNESS LODGE"], alto=30)
    h.fila("subportada", ["", "Owners report — Forecast 2026 vs Budget 2027"])
    h.fila("nota", ["", "=\"Forecast: \"&" + rotulo("F26") + "&\"   ·   Budget: \"&" + rotulo("B27") +
                        "&\"   ·   Updated: \"&TEXT(NOW(),\"dd-mmm-yyyy\")"])
    h.saltar()
    h.fila("seccion", ["", "HIGHLIGHTS"])
    ing_f, ing_b = f"{R}D{tot}", f"{R}E{tot}"
    gop_f, gop_b = f"{R}D{res_filas['GOP']}", f"{R}E{res_filas['GOP']}"
    eb_f, eb_b = f"{R}D{res_filas['EBITDA before capital']}", f"{R}E{res_filas['EBITDA before capital']}"
    occ_f, occ_b = f"{R}D{res_filas['% Occupancy']}", f"{R}E{res_filas['% Occupancy']}"
    adr_f, adr_b = f"{R}D{res_filas['ADR (USD)']}", f"{R}E{res_filas['ADR (USD)']}"
    h.fila("texto", ["", f'="The 2027 Budget projects revenue of $"&FIXED({ing_b},0)&", "&IF({ing_b}>={ing_f},"an increase","a decrease")&" of "&FIXED(ABS(IFERROR(({ing_b}-{ing_f})/{ing_f},0))*100,1)&"%"&" against the 2026 Forecast ($"&FIXED({ing_f},0)&")."'], alto=32)
    h.fila("texto", ["", f'="Occupancy moves from "&FIXED(({occ_f})*100,1)&"%"&" to "&FIXED(({occ_b})*100,1)&"%"&" and ADR from $"&FIXED({adr_f},0)&" to $"&FIXED({adr_b},0)&"."'], alto=32)
    h.fila("texto", ["", f'="GOP reaches $"&FIXED({gop_b},0)&" ("&FIXED((IFERROR({gop_b}/{ing_b},0))*100,1)&"%"&" of revenue) and EBITDA before capital of $"&FIXED({eb_b},0)&", "&IF({eb_b}>={eb_f},"$"&FIXED({eb_b}-{eb_f},0)&" more","$"&FIXED({eb_f}-{eb_b},0)&" less")&" than in the Forecast."'], alto=32)
    sv = "'AM08 Standard vs Villas'!"
    vil = sets_filas["B27"]
    h.fila("texto", ["", f'="Villas (department 0115) contributes $"&FIXED({sv}D{vil["ing"]},0)&" of rooms revenue in the 2027 Budget ("&FIXED((IFERROR({sv}D{vil["ing"]}/{sv}E{vil["ing"]},0))*100,1)&"%"&" of Rooms)."'], alto=32)
    h.saltar()
    h.fila("seccion", ["", "KEY INDICATORS"])
    h.fila("encabezado", ["", "Indicator", "=" + rotulo("F26"), "=" + rotulo("B27"), "Var.", "Var. %"])
    p0 = h.r + 1
    for nombre in ["% Occupancy", "ADR (USD)", "Rooms RevPAR (USD)", "Occupied room nights", "Total revenue",
                   "Departmental profit", "GOP", "EBITDA before capital", "EBITDA after capital",
                   "Net profit"]:
        r = tot if nombre == "Total revenue" else res_filas[nombre]
        estilo = "pct" if nombre.startswith("%") else ("usd2" if "USD" in nombre else
                                                      ("total" if nombre in ("GOP", "Net profit") else "normal"))
        h.fila(estilo, ["", nombre, f"={R}D{r}", f"={R}E{r}", f"={R}F{r}", f"=IF({R}G{r}=\"\",\"\",{R}G{r})"])
    h.formato(f"C{p0}:E{h.r}", USD)
    h.formato(f"F{p0}:F{h.r}", PCT)
    h.saltar()
    h.fila("seccion", ["", "REVENUE BY DEPARTMENT · FULL YEAR"])
    h.fila("encabezado", ["", "Department", "=" + rotulo("F26"), "=" + rotulo("B27"), "Var.", "Var. %"])
    q0 = h.r + 1
    for nombre, _ in INGRESOS:
        r = res_filas[nombre]
        h.fila("normal", ["", nombre, f"={R}D{r}", f"={R}E{r}", f"={R}F{r}", f"=IF({R}G{r}=\"\",\"\",{R}G{r})"])
    h.fila("total", ["", "Total revenue", f"={R}D{tot}", f"={R}E{tot}", f"={R}F{tot}", f"={R}G{tot}"])
    h.formato(f"C{q0}:E{h.r}", USD)
    h.formato(f"F{q0}:F{h.r}", PCT)
    h.saltar()
    h.fila("seccion", ["", "ROOMS · STANDARD ROOMS VS VILLAS (BUDGET 2027)"])
    h.fila("encabezado", ["", "", "Standard", "Villas", "Total Rooms", ""])
    s0 = h.r + 1
    base = sets_filas["B27"]["ing"]
    for i, nombre in enumerate(["Rooms revenue", "Payroll", "Opex & cost of sales", "Departmental expenses",
                                "Departmental profit", "Departmental margin", "Available room nights",
                                "Occupied room nights", "% Occupancy", "ADR (P&L revenue / occupied nights)"]):
        r = base + i
        estilo = "pct" if nombre.startswith(("%", "Departmental margin")) else ("usd2" if nombre.startswith("ADR") else
                                                                   ("total" if nombre.startswith("Departmental profit") else "normal"))
        h.fila(estilo, ["", nombre, f"={sv}C{r}", f"={sv}D{r}", f"={sv}E{r}"])
    h.formato(f"C{s0}:E{s0 + 4}", USD)
    h.saltar()
    h.fila("seccion", ["", "MONTHLY REVENUE AND GOP"])
    g0 = h.r + 1
    h.grafico(titulo="Monthly total revenue: Forecast 2026 vs Budget 2027", celda=f"B{g0}", ancho=520, alto=230,
              series=[{"nombre": "PL_HDR_F26", "ref": "PL_TOT_F26"},
                      {"nombre": "PL_HDR_B27", "ref": "PL_TOT_B27"}], tipo="columnas")
    h.saltar(22)
    g1 = h.r + 1
    h.grafico(titulo="Monthly GOP", celda=f"B{g1}", ancho=520, alto=230,
              series=[{"nombre": "PL_HDR_F26", "ref": "PL_GOP_F26"},
                      {"nombre": "PL_HDR_B27", "ref": "PL_GOP_B27"}], tipo="lineas")
    h.saltar(22)
    h.fila("seccion", ["", "NOTES"])
    for t in ["Source: FinPlan, live (Data → Refresh All). The Forecast is the system ★ Current; when another one is "
              "marked (November, December) the report picks it up and the titles say which one.",
              "Revenue and expenses in USD. Departmental expenses = payroll + cost of sales + departmental opex "
              "(USALI format).",
              "Villas (0115) carries no share of the common Rooms cost today: its departmental margin is a ceiling.",
              "The workbook checks are on sheet AM97 Controls: all must read OK before sending."]:
        h.fila("texto", ["", t], alto=30)
    return h


def construir(salida):
    versiones = hoja_versiones()
    pl, pl_aux, pl_marcas = hoja_pl()
    rooms, rooms_aux, rooms_filas = hoja_rooms()
    sets, sets_filas = hoja_sets(rooms_filas)
    resumen, res_filas, tot = hoja_resumen(pl_marcas, rooms_filas)
    flow = hoja_flow()
    controles = hoja_controles()
    reporte = hoja_reporte(res_filas, tot, sets_filas)

    # Rangos con nombre para los gráficos: la fila del total y del GOP de cada versión en AM03.
    rangos = {}
    for f in pl.filas:
        cod = f["celdas"][0] if f["celdas"] else ""
        if cod in ("TOTAL_REVENUES", "TOTAL_GOP"):
            rangos.setdefault(cod, []).append(f["r"])
    # Orden de los bloques en AM03: F26, B27, A25.
    nombres = {
        "PL_TOT_F26": f"='AM03 Monthly P&L'!$C${rangos['TOTAL_REVENUES'][0]}:$N${rangos['TOTAL_REVENUES'][0]}",
        "PL_TOT_B27": f"='AM03 Monthly P&L'!$C${rangos['TOTAL_REVENUES'][1]}:$N${rangos['TOTAL_REVENUES'][1]}",
        "PL_GOP_F26": f"='AM03 Monthly P&L'!$C${rangos['TOTAL_GOP'][0]}:$N${rangos['TOTAL_GOP'][0]}",
        "PL_GOP_B27": f"='AM03 Monthly P&L'!$C${rangos['TOTAL_GOP'][1]}:$N${rangos['TOTAL_GOP'][1]}",
    }
    # Encabezados de cada bloque de AM03 (F26, B27, A25): dan los meses (Ene…Dic) y el
    # nombre de la serie con la versión real.
    hdr = [f["r"] for f in pl.filas if f["estilo"] == "encabezado"]
    nombres["PL_MESES"] = f"='AM03 Monthly P&L'!$C${hdr[0]}:$N${hdr[0]}"
    nombres["PL_HDR_F26"] = f"='AM03 Monthly P&L'!$B${hdr[0]}"
    nombres["PL_HDR_B27"] = f"='AM03 Monthly P&L'!$B${hdr[1]}"
    fila0 = 5
    for i, (cod, _, _) in enumerate(VERSIONES):
        nombres[f"ver_{cod}"] = f"='AM98 Versions'!$B${fila0 + i}"

    indice = Hoja("00 Index", [6, 30, 90])
    indice.fila("titulo", ["", "CWL · Master File — Forecast 2026 vs Budget 2027"])
    indice.fila("nota", ["", "Everything updates with Data → Refresh All. The key goes in Config!C5 and is NOT saved "
                             "in the file you share."])
    indice.saltar()
    indice.fila("encabezado", ["#", "Sheet", "Content"])
    for i, (n, d) in enumerate([
        ("Report", "Owners report ready for PDF: highlights, indicators, revenue, standard vs Villas, charts"),
        ("AM01 Rooms KPIs", "Occupancy, ADR, RevPAR, room nights and guests, monthly: hotel, standard and Villas"),
        ("AM02 FY Summary", "Full-year summary: Actual 2025, Forecast 2026 and Budget 2027 with variances"),
        ("AM03 Monthly P&L", "Monthly USALI income statement by version"),
        ("AM07 Flow-through", "Flow-through by department, EBITDA bridge and break-even"),
        ("AM08 Standard vs Villas", "The two Rooms products: revenue, payroll, opex, profit and statistics"),
        ("AM97 Controls", "Checks that must be 0 before sending"),
        ("AM98 Versions", "Which version each column is (the current forecast is picked automatically)"),
    ]):
        indice.fila("normal", [str(i), n, d])

    hojas = [indice, reporte, rooms, resumen, pl, flow, sets, controles, versiones]
    spec = {"hojas": [h.json() for h in hojas], "nombres": nombres}
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
    print(f"spec: {salida} · {sum(len(h.filas) for h in hojas)} filas en {len(hojas)} hojas")


if __name__ == "__main__":
    construir(sys.argv[1] if len(sys.argv) > 1 else "master_spec.json")
