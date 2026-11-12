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
    # Al final: agregar una versión no corre las filas de las demás en AM98.
    ("B26", "Budget 2026 Final", "Budget 2026 approved (FTE reference: the Actual and Forecast carry no FTE)"),
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
        self.conservar = False   # True = aplicar.ps1 la crea una vez y nunca la rehace
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
                "horizontal": self.horizontal, "ocultar_a": self.ocultar_a,
                "conservar": self.conservar}


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


# ══ Análisis para decidir (owner, 2026-11-12) ════════════════════════════════
# «metamos un tab de key indicators y necesito un tab de decisiones: cuando crece
# ingresos versus budget, cuánto crece opex y salarios, el FTE, cuánto crece en
# noches, separado Standard Rooms y Villas… márgenes por departamento… en overhead
# igual» · «un tab solo de análisis de Rate por mes, cuartos» · «un tab solo de
# volumen por mes, por cuartos y full year comparativo side by side».

K = "13"   # columna del año en tMotor/tGL/tEstadisticas

# Columnas del P&L por departamento, por departamento del GL. «Other (not
# listed)» = total operado − lo listado: un depto nuevo cae ahí y el total cuadra.
DEPTOS_OPERADOS = [
    ("Standard rooms", ["0110"]),
    ("Villas", ["0115", "0116"]),
    ("F&B", ["0120", "0121"]),
    ("Spa", ["0130", "0140"]),
    ("Tours", ["0150"]),
    ("Transportation", ["0152"]),
    ("Gift shop / store", ["0151", "0165"]),
    ("Laundry", ["0161", "0162"]),
    ("Innoceana & Crowther", ["0155", "0156"]),
    ("Other income", ["280"]),
]
DEPTOS_OVERHEAD = [
    ("Administrative & General", ["0180"]),
    ("Sales & Marketing", ["0190"]),
    ("Maintenance", ["0200"]),
    ("Utilities", ["0210"]),
    ("Information systems (IT)", ["0230"]),
    ("Claro del Bosque (Huerta)", ["0205"]),
    ("Staff cafeteria (allocated, net)", ["0220"]),
]
OH_CODIGOS = [d for _, ds in DEPTOS_OVERHEAD for d in ds]
CENTROS = ["0220", "0161"]          # acumulan y reparten: su costo bruto ya está en los deptos

TIPOS = [   # código de tipo en tHabitaciones (Opera) · nombre corto · set
    ("BL01", "Corcovado Deluxe King", "Standard"),
    ("BI02", "Carate Deluxe Double", "Standard"),
    ("PO03", "Agujas Villa 2 Queen", "Standard"),
    ("RO04", "Sirena Suites", "Standard"),
    ("BI05", "Treehouse King", "Standard"),
    ("BL06", "5 Elements Treehouse", "Standard"),
    ("SH07", "Villas Deluxe", "Villas"),
    ("SH08", "Residencia", "Villas"),
]


def glt(v, cat, col_k, deptos=None, signo=1):
    """tGL por categoría; sin deptos = todo el hotel."""
    if deptos is None:
        s = "-" if signo < 0 else ""
        return (f'IFERROR({s}SUMIFS(INDEX(tGL[[M01]:[Annual]],0,{col_k}),tGL[Etiqueta],{v},'
                f'tGL[Category],"{cat}"),0)')
    return gl(v, cat, deptos, col_k, signo)


def gl_costo(v, deptos, col_k):
    """Todo lo de esos deptos (payroll + costo + opex + reparto): para overhead, sin ingreso."""
    dep = f'"{deptos[0]}"' if len(deptos) == 1 else _lista(deptos)
    f = f'SUMIFS(INDEX(tGL[[M01]:[Annual]],0,{col_k}),tGL[Etiqueta],{v},tGL[Dept code],{dep})'
    return f'IFERROR(SUM({f}),0)'


def hab_t(v, campo, codigo, mes_celda):
    """tHabitaciones de UN tipo de habitación; mes_celda None = el año."""
    mes = "" if mes_celda is None else f",tHabitaciones[Mes],{mes_celda}"
    return (f'IFERROR(SUMIFS(tHabitaciones[{campo}],tHabitaciones[Etiqueta],{v},'
            f'tHabitaciones[Nivel],"Tipo",tHabitaciones[Codigo],"{codigo}"{mes}),0)')


def var_cols(n, c_ant="D", c_nue="E", pct=False):
    """Δ y Δ% (o Δ en puntos si la fila es un %)."""
    if pct:
        return [f'=IF(OR({c_ant}{n}="",{c_nue}{n}=""),"",{c_nue}{n}-{c_ant}{n})', ""]
    return [f'=IF(OR({c_ant}{n}="",{c_nue}{n}=""),"",{c_nue}{n}-{c_ant}{n})',
            f'=IF(OR({c_ant}{n}="",{c_nue}{n}="",ABS(N({c_ant}{n}))<1),"",({c_nue}{n}-{c_ant}{n})/ABS({c_ant}{n}))']


# ── AM09 Key Indicators ──────────────────────────────────────────────────────

def hoja_ki(rooms_filas):
    h = Hoja("AM09 Key Indicators", [8, 46, 16, 16, 16, 15, 11], ocultar_a=True)
    h.fila("titulo", ["", "CWL · Key indicators — full year"])
    h.fila("nota", ["", "PAR = per available room night · POR = per occupied room night · pp = percentage points. "
                        "Payroll, cost of sales and opex exclude the gross cost of the staff cafeteria (0220) and "
                        "internal laundry (0161): it is already inside the departments that receive it."])
    h.saltar()
    h.fila("encabezado", ["", "Indicator", "=" + rotulo("A25"), "=" + rotulo("F26"), "=" + rotulo("B27"),
                          "Var. B27 − F26", "Var. %"])
    rf = rooms_filas
    A1 = "'AM01 Rooms KPIs'!O"
    f = {}

    def ind(nombre, fv, estilo="normal", clave=None):
        n = h.r + 1
        h.fila(estilo, ["", nombre] + ["=" + fv(c) for c in ("A25", "F26", "B27")] +
               var_cols(n, pct=(estilo == "pct")))
        f[clave or nombre] = n
        return n

    m = lambda c, cs: motor(f"ver_{c}", cs, K)
    pay = lambda c: f"({glt(f'ver_{c}', 'PAYROLL', K)}-{glt(f'ver_{c}', 'PAYROLL', K, CENTROS)})"
    cos = lambda c: f"({glt(f'ver_{c}', 'COST_OF_SALES', K)}-{glt(f'ver_{c}', 'COST_OF_SALES', K, CENTROS)})"
    opx = lambda c: f"({glt(f'ver_{c}', 'OPERATING_EXPENSES', K)}-{glt(f'ver_{c}', 'OPERATING_EXPENSES', K, CENTROS)})"
    disp = lambda c: f"{A1}{rf[(c, 'hotel')]['disp']}"
    ocu = lambda c: f"{A1}{rf[(c, 'hotel')]['ocu']}"
    rev = lambda c: m(c, ["TOTAL_REVENUES"])
    rrev = lambda c: m(c, ["REV_ROOMS", "REV_ROOMS_OTHER"])

    h.fila("seccion", ["", "Volume"])
    ind("Rooms available (room nights)", disp)
    ind("Rooms sold (occupied)", ocu)
    ind("Occupancy %", lambda c: f"{A1}{rf[(c, 'hotel')]['occ']}", "pct")
    ind("Guests", lambda c: f"{A1}{rf[(c, 'hotel')]['pax']}")
    ind("Guests per occupied room", lambda c: div(f"{A1}{rf[(c, 'hotel')]['pax']}", ocu(c)), "usd2")
    h.fila("seccion", ["", "Rate"])
    ind("Average rate (ADR)", lambda c: f"{A1}{rf[(c, 'hotel')]['adr']}", "usd2")
    ind("RevPAR", lambda c: f"{A1}{rf[(c, 'hotel')]['revpar']}", "usd2")
    ind("Rooms total PAR (P&L rooms revenue / available)", lambda c: div(rrev(c), disp(c)), "usd2")
    ind("TRevPAR (total revenue / available)", lambda c: div(rev(c), disp(c)), "usd2")
    h.fila("seccion", ["", "Revenue"])
    ind("Gross operating revenue", rev, clave="rev")
    ind("Rooms revenue", rrev)
    ind("F&B revenue", lambda c: m(c, ["REV_FB", "REV_FB_BEV", "REV_FB_MISC", "REV_PRIVATE_BAR"]))
    ind("Spa revenue", lambda c: m(c, ["REV_SPA"]))
    ind("Tours revenue", lambda c: m(c, ["REV_TOURS"]))
    ind("Non-room revenue %", lambda c: div(f"{rev(c)}-{rrev(c)}", rev(c)), "pct")
    ind("F&B revenue POR", lambda c: div(m(c, ["REV_FB", "REV_FB_BEV", "REV_FB_MISC", "REV_PRIVATE_BAR"]), ocu(c)), "usd2")
    ind("Total revenue per guest", lambda c: div(rev(c), f"{A1}{rf[(c, 'hotel')]['pax']}"), "usd2")
    h.fila("seccion", ["", "Profitability"])
    g = ind("Gross operating profit (GOP)", lambda c: m(c, ["TOTAL_GOP"]), "subtotal")
    ind("GOP %", lambda c: div(m(c, ["TOTAL_GOP"]), rev(c)), "pct")
    ind("GOP PAR", lambda c: div(m(c, ["TOTAL_GOP"]), disp(c)), "usd2")
    n = h.r + 1
    h.fila("pct", ["", "GOP flow-through (Δ GOP ÷ Δ revenue, B27 vs F26)", "", "", "",
                   f'=IF(ABS(F{f["rev"]})<1,"",F{g}/F{f["rev"]})', ""])
    e = ind("EBITDA before capital", lambda c: m(c, ["EBITDA_BEFORE_CAPITAL"]), "subtotal")
    ind("EBITDA %", lambda c: div(m(c, ["EBITDA_BEFORE_CAPITAL"]), rev(c)), "pct")
    ind("Net profit", lambda c: m(c, ["NET_PROFIT"]), "total")
    ind("Rooms profit %", lambda c: div(m(c, ["PROFIT_ROOMS"]), rrev(c)), "pct")
    ind("F&B retention (F&B profit / F&B revenue)",
        lambda c: div(m(c, ["PROFIT_FB", "PROFIT_PRIVATE_BAR"]), m(c, ["REV_FB", "REV_FB_BEV", "REV_FB_MISC", "REV_PRIVATE_BAR"])), "pct")
    h.fila("seccion", ["", "Departmental cost & productivity"])
    ind("Food cost %", lambda c: div(m(c, ["COS_FB_FOOD"]), m(c, ["REV_FB"])), "pct")
    ind("Beverage cost %", lambda c: div(m(c, ["COS_FB_BEV"]), m(c, ["REV_FB_BEV"])), "pct")
    ind("Rooms cost % (rooms expenses / rooms revenue)", lambda c: div(m(c, ["OPEX_ROOMS"]), rrev(c)), "pct")
    ind("Rooms expenses POR", lambda c: div(m(c, ["OPEX_ROOMS"]), ocu(c)), "usd2")
    ind("F&B total cost POR", lambda c: div(m(c, ["OPEX_FB", "OPEX_PRIVATE_BAR", "COS_FB_FOOD", "COS_FB_BEV",
                                                   "COS_FB_MISC", "COS_PRIVATE_BAR"]), ocu(c)), "usd2")
    h.fila("seccion", ["", "Undistributed expenses"])
    ind("Admin & General PAR (incl. credit card commissions)", lambda c: div(m(c, ["OH_ADMIN", "OH_EMPLOYEE_BENEFITS", "COH_EMPLOYEE_BENEFITS", "OH_CC_COMMISSIONS"]), disp(c)), "usd2")
    ind("Sales & Marketing PAR", lambda c: div(m(c, ["OH_SALES_MARKETING"]), disp(c)), "usd2")
    ind("Sales & Marketing % of revenue", lambda c: div(m(c, ["OH_SALES_MARKETING"]), rev(c)), "pct")
    ind("IT / telecom PAR", lambda c: div(m(c, ["OH_INFORMATION_SYSTEM", "COH_INFORMATION_SYSTEM"]), disp(c)), "usd2")
    ind("Maintenance PAR", lambda c: div(m(c, ["OH_MAINTENANCE"]), disp(c)), "usd2")
    ind("Utilities PAR", lambda c: div(m(c, ["OH_UTILITIES"]), disp(c)), "usd2")
    ind("Total overhead % of revenue", lambda c: div(m(c, ["TOTAL_OVERHEAD_EXPENSES"]), rev(c)), "pct")
    h.fila("seccion", ["", "Payroll & cost structure"])
    ind("Payroll % of revenue", lambda c: div(pay(c), rev(c)), "pct")
    ind("Payroll POR", lambda c: div(pay(c), ocu(c)), "usd2")
    ind("Cost of sales % of revenue", lambda c: div(cos(c), rev(c)), "pct")
    ind("Operating expenses % of revenue", lambda c: div(opx(c), rev(c)), "pct")
    h.formato(f"C5:F{h.r}", USD)
    h.formato(f"G5:G{h.r}", PCT)
    return h


# ── AM10 Decisions ──────────────────────────────────────────────────────────

def hoja_decisiones(rooms_filas):
    h = Hoja("AM10 Decisions", [8, 46] + [14] * 12, ocultar_a=True)
    h.fila("titulo", ["", "CWL · Decisions — what grows, how much, and what each area contributes"])
    h.fila("nota", ["", "Budget 2027 against Forecast 2026 (Actual 2025 as reference). «x revenue growth» = the line's "
                        "% growth ÷ the revenue % growth: above 1.00 it grows FASTER than revenue, below 1.00 slower. "
                        "Expenses by department come from the GL (Dept code × category) and tie to the P&L GOP "
                        "(check at the end of section 2)."])
    A1 = "'AM01 Rooms KPIs'!O"
    rf = rooms_filas
    # ── 1. Qué crece ────────────────────────────────────────────────────────
    h.saltar()
    h.fila("seccion", ["", "1 · GROWTH: revenue, volume, payroll, opex and FTE"])
    h.fila("encabezado", ["", "Line", "=" + rotulo("A25"), "=" + rotulo("F26"), "=" + rotulo("B27"),
                          "Δ B27 − F26", "Δ %", "x revenue growth"])
    f = {}

    def lin(nombre, fv, estilo="normal", clave=None, multiplo=True):
        n = h.r + 1
        celdas = ["", nombre] + ["=" + fv(c) for c in ("A25", "F26", "B27")] + var_cols(n, pct=(estilo == "pct"))
        if multiplo and estilo != "pct" and "rev" in f:
            celdas.append(f'=IF(OR(G{n}="",G${f["rev"]}="",N(G${f["rev"]})=0),"",G{n}/G${f["rev"]})')
        h.fila(estilo, celdas)
        f[clave or nombre] = n
        return n

    m = lambda c, cs: motor(f"ver_{c}", cs, K)
    v = lambda c: f"ver_{c}"
    lin("Total revenue", lambda c: m(c, ["TOTAL_REVENUES"]), "subtotal", clave="rev")
    lin("Rooms revenue — Standard", lambda c: glt(v(c), "REVENUE", K, ["0110"], -1))
    lin("Rooms revenue — Villas", lambda c: glt(v(c), "REVENUE", K, ["0115", "0116"], -1))
    lin("Non-room revenue", lambda c: f"{m(c, ['TOTAL_REVENUES'])}-{m(c, ['REV_ROOMS', 'REV_ROOMS_OTHER'])}")
    on = lin("Occupied room nights — hotel", lambda c: f"{A1}{rf[(c, 'hotel')]['ocu']}", clave="ocu")
    lin("Occupied room nights — Standard",
        lambda c: f"{A1}{rf[(c, 'hotel')]['ocu']}-{A1}{rf[(c, '0115')]['ocu']}" if c != "A25" else f"{A1}{rf[(c, 'hotel')]['ocu']}")
    lin("Occupied room nights — Villas", lambda c: f"{A1}{rf[(c, '0115')]['ocu']}" if c != "A25" else "0")
    lin("Available room nights", lambda c: f"{A1}{rf[(c, 'hotel')]['disp']}", clave="disp")
    lin("Guests", lambda c: f"{A1}{rf[(c, 'hotel')]['pax']}", clave="pax")
    lin("ADR", lambda c: f"{A1}{rf[(c, 'hotel')]['adr']}", "usd2")
    lin("Occupancy %", lambda c: f"{A1}{rf[(c, 'hotel')]['occ']}", "pct")
    pay = lambda c: f"({glt(v(c), 'PAYROLL', K)}-{glt(v(c), 'PAYROLL', K, CENTROS)})"
    cos = lambda c: f"({glt(v(c), 'COST_OF_SALES', K)}-{glt(v(c), 'COST_OF_SALES', K, CENTROS)})"
    opx = lambda c: f"({glt(v(c), 'OPERATING_EXPENSES', K)}-{glt(v(c), 'OPERATING_EXPENSES', K, CENTROS)})"
    lin("Payroll (all departments)", pay, clave="pay")
    lin("Cost of sales", cos, clave="cos")
    lin("Operating expenses (opex)", opx, clave="opx")
    lin("Undistributed expenses (overhead, P&L)", lambda c: m(c, ["TOTAL_OVERHEAD_EXPENSES"]))
    lin("Departmental profit", lambda c: m(c, ["OPERATING_PROFIT"]), "subtotal")
    lin("GOP", lambda c: m(c, ["TOTAL_GOP"]), "total")
    fte = lambda c: f'IF(SUMIFS(tPosiciones[FTE prom],tPosiciones[Etiqueta],{v(c)})=0,"",SUMIFS(tPosiciones[FTE prom],tPosiciones[Etiqueta],{v(c)}))'
    lin("FTE (average for the year) ¹", fte, "usd2", clave="fte")
    n = h.r + 1
    h.fila("usd2", ["", "FTE — Budget 2026 Final (reference) ¹", "", "=" + fte("B26"), "=E" + str(f["fte"]),
                    f'=IF(OR(D{n}="",E{n}=""),"",E{n}-D{n})', f'=IF(OR(D{n}="",E{n}="",N(D{n})=0),"",(E{n}-D{n})/D{n})'])
    h.fila("seccion", ["", "Per unit"])
    lin("Payroll per occupied night", lambda c: div(pay(c), f"{A1}{rf[(c, 'hotel')]['ocu']}"), "usd2")
    lin("Payroll per guest", lambda c: div(pay(c), f"{A1}{rf[(c, 'hotel')]['pax']}"), "usd2")
    lin("Opex per occupied night", lambda c: div(opx(c), f"{A1}{rf[(c, 'hotel')]['ocu']}"), "usd2")
    lin("Revenue per guest", lambda c: div(m(c, ["TOTAL_REVENUES"]), f"{A1}{rf[(c, 'hotel')]['pax']}"), "usd2")
    lin("Payroll % of revenue", lambda c: div(pay(c), m(c, ["TOTAL_REVENUES"])), "pct")
    lin("Occupied nights per FTE", lambda c: f'IFERROR({A1}{rf[(c, "hotel")]["ocu"]}/{fte(c)},"")', "usd2")
    lin("Payroll per FTE (annual)", lambda c: f'IFERROR({pay(c)}/{fte(c)},"")', "usd2")
    h.fila("nota", ["", "¹ FTE exists only where the budget is built by position (Budget 2026 and 2027). The Actual and "
                        "the Forecast take payroll from the GL, with no FTE: compare FTE Budget 2027 vs Budget 2026."])
    p1 = 6
    h.formato(f"C{p1}:F{h.r}", USD)
    h.formato(f"G{p1}:G{h.r}", PCT)
    h.formato(f"H{p1}:H{h.r}", '0.00"x";-0.00"x";""')

    # ── 2. Márgenes por departamento ────────────────────────────────────────
    nombres = [n for n, _ in DEPTOS_OPERADOS] + ["Other (not listed)", "Total operated"]
    cols = "CDEFGHIJKLMN"
    bloques = {}
    for cod in ("F26", "B27"):
        vv = v(cod)
        h.saltar()
        h.fila("seccion", ["", "=\"2 · DEPARTMENTAL MARGINS — \"&" + rotulo(cod)])
        h.fila("encabezado", ["", "USD"] + nombres)
        filas = {}

        def cat_fila(etq, cat, signo, estilo="normal"):
            n = h.r + 1
            celdas = ["", etq]
            for nom, deps in DEPTOS_OPERADOS:
                celdas.append("=" + glt(vv, cat, K, deps, signo))
            listado = f"SUM(C{n}:L{n})"
            total = f"({glt(vv, cat, K, None, signo)})-({glt(vv, cat, K, OH_CODIGOS + ['0250'], signo)})"
            celdas += [f"=N{n}-{listado}", "=" + total]
            return h.fila(estilo, celdas)

        filas["rev"] = cat_fila("Revenue", "REVENUE", -1, "subtotal")
        filas["pay"] = cat_fila("Payroll", "PAYROLL", 1)
        filas["cos"] = cat_fila("Cost of sales", "COST_OF_SALES", 1)
        filas["opx"] = cat_fila("Operating expenses", "OPERATING_EXPENSES", 1)
        filas["alo"] = cat_fila("Allocation credit (laundry centre)", "ALLOCATIONS", 1)
        n = h.r + 1
        filas["gas"] = h.fila("normal", ["", "Departmental expenses"] +
                              [f"={c}{filas['pay']}+{c}{filas['cos']}+{c}{filas['opx']}+{c}{filas['alo']}" for c in cols])
        n = h.r + 1
        filas["pro"] = h.fila("total", ["", "Departmental profit"] + [f"={c}{filas['rev']}-{c}{filas['gas']}" for c in cols])
        h.fila("pct", ["", "Margin (profit / revenue)"] + [f'=IF(ABS({c}{filas["rev"]})<1,"",{c}{filas["pro"]}/{c}{filas["rev"]})' for c in cols])
        h.fila("pct", ["", "Share of revenue"] + [f'=IF(ABS($N{filas["rev"]})<1,"",{c}{filas["rev"]}/$N{filas["rev"]})' for c in cols])
        h.fila("pct", ["", "Contribution to departmental profit"] + [f'=IF(ABS($N{filas["pro"]})<1,"",{c}{filas["pro"]}/$N{filas["pro"]})' for c in cols])
        h.fila("pct", ["", "Payroll % of revenue"] + [f'=IF(ABS({c}{filas["rev"]})<1,"",{c}{filas["pay"]}/{c}{filas["rev"]})' for c in cols])
        h.fila("pct", ["", "Cost of sales % of revenue"] + [f'=IF(ABS({c}{filas["rev"]})<1,"",{c}{filas["cos"]}/{c}{filas["rev"]})' for c in cols])
        h.fila("pct", ["", "Opex % of revenue"] + [f'=IF(ABS({c}{filas["rev"]})<1,"",{c}{filas["opx"]}/{c}{filas["rev"]})' for c in cols])
        oh = h.fila("normal", ["", "Undistributed expenses (overhead departments, GL)", "", "", "", "", "", "", "", "", "", "", "",
                               "=" + gl_costo(vv, OH_CODIGOS, K)])
        h.fila("total", ["", "GOP (departmental profit − overhead)"] + [""] * 11 + [f"=N{filas['pro']}-N{oh}"])
        h.fila("control", ["", "Check: against the P&L GOP (must be 0)"] + [""] * 11 +
               [f"=ROUND(N{h.r}-{motor(vv, ['TOTAL_GOP'], K)},0)"])
        h.formato(f"C{filas['rev']}:N{h.r}", USD)
        bloques[cod] = filas

    # Δ por departamento
    h.saltar()
    h.fila("seccion", ["", "2b · CHANGE BY DEPARTMENT — Budget 2027 vs Forecast 2026"])
    h.fila("encabezado", ["", "USD"] + nombres)
    a, b = bloques["F26"], bloques["B27"]
    d0 = h.r + 1
    dr = h.fila("normal", ["", "Δ revenue"] + [f"={c}{b['rev']}-{c}{a['rev']}" for c in cols])
    dp = h.fila("normal", ["", "Δ payroll"] + [f"={c}{b['pay']}-{c}{a['pay']}" for c in cols])
    h.fila("normal", ["", "Δ cost of sales"] + [f"={c}{b['cos']}-{c}{a['cos']}" for c in cols])
    do = h.fila("normal", ["", "Δ opex"] + [f"={c}{b['opx']}-{c}{a['opx']}" for c in cols])
    dpro = h.fila("total", ["", "Δ departmental profit"] + [f"={c}{b['pro']}-{c}{a['pro']}" for c in cols])
    h.fila("pct", ["", "Δ revenue %"] + [f'=IF(ABS({c}{a["rev"]})<1,"",{c}{dr}/ABS({c}{a["rev"]}))' for c in cols])
    h.fila("pct", ["", "Δ payroll %"] + [f'=IF(ABS({c}{a["pay"]})<1,"",{c}{dp}/ABS({c}{a["pay"]}))' for c in cols])
    h.fila("pct", ["", "Δ opex %"] + [f'=IF(ABS({c}{a["opx"]})<1,"",{c}{do}/ABS({c}{a["opx"]}))' for c in cols])
    h.fila("pct", ["", "Flow-through (Δ profit / Δ revenue)"] + [f'=IF(ABS({c}{dr})<1,"",{c}{dpro}/{c}{dr})' for c in cols])
    h.fila("pct", ["", "Margin change (pp)"] + [f'=IF(OR(ABS({c}{a["rev"]})<1,ABS({c}{b["rev"]})<1),"",{c}{b["pro"]}/{c}{b["rev"]}-{c}{a["pro"]}/{c}{a["rev"]})' for c in cols])
    h.formato(f"C{d0}:N{h.r}", USD)

    # ── 3. Overhead contra el negocio ───────────────────────────────────────
    h.saltar()
    h.fila("seccion", ["", "3 · OVERHEAD — does it grow faster than the business?"])
    h.fila("encabezado", ["", "Department", "=" + rotulo("A25"), "=" + rotulo("F26"), "=" + rotulo("B27"),
                          "Δ B27 − F26", "Δ %", "x revenue growth", "% revenue F26", "% revenue B27",
                          "PAR B27", "Per occ. night F26", "Per occ. night B27", "Reading"])
    o0 = h.r + 1
    rev_r = f["rev"]
    for i, (nom, deps) in enumerate(DEPTOS_OVERHEAD + [("Total overhead (GL)", OH_CODIGOS)]):
        n = h.r + 1
        estilo = "total" if i == len(DEPTOS_OVERHEAD) else "normal"
        celdas = ["", nom] + ["=" + gl_costo(v(c), deps, K) for c in ("A25", "F26", "B27")] + var_cols(n)
        celdas += [f'=IF(OR(G{n}="",N(G${rev_r})=0),"",G{n}/G${rev_r})',
                   f'=IF(N(D${rev_r})=0,"",D{n}/D${rev_r})', f'=IF(N(E${rev_r})=0,"",E{n}/E${rev_r})',
                   f'=IF(N(E${f["disp"]})=0,"",E{n}/E${f["disp"]})',
                   f'=IF(N(D${f["ocu"]})=0,"",D{n}/D${f["ocu"]})', f'=IF(N(E${f["ocu"]})=0,"",E{n}/E${f["ocu"]})',
                   f'=IF(OR(H{n}="",ABS(F{n})<1),"",IF(H{n}>1.05,"grows faster than revenue",IF(H{n}<0.95,"grows slower than revenue","grows with revenue")))']
        h.fila(estilo, celdas)
    h.fila("control", ["", "Check: GL overhead − P&L undistributed expenses (difference in the mapping)"] +
           [f"=ROUND({c}{h.r}-{motor(v(cod), ['TOTAL_OVERHEAD_EXPENSES'], K)},0)" for c, cod in zip("CDE", ("A25", "F26", "B27"))])
    h.fila("seccion", ["", "Business drivers for reference"])
    for etq, clave in (("Total revenue", "rev"), ("Occupied room nights", "ocu"), ("Guests", "pax"),
                       ("Available room nights", "disp")):
        n = h.r + 1
        h.fila("normal", ["", etq, f"=C{f[clave]}", f"=D{f[clave]}", f"=E{f[clave]}"] + var_cols(n))
    h.formato(f"C{o0}:F{h.r}", USD)
    h.formato(f"G{o0}:G{h.r}", PCT)
    h.formato(f"H{o0}:H{h.r}", '0.00"x";-0.00"x";""')
    h.formato(f"I{o0}:J{h.r}", PCT)
    h.formato(f"K{o0}:M{h.r}", USD2)
    return h


# ── AM11 Rate by month · AM12 Volume by month ────────────────────────────────
#
# ⚠️ Por tipo de habitación el Forecast solo trae los meses que ya cerraron con
# Room Stats (hoy ene–sep); sus meses propios vienen «Sin tipo». Comparar por tipo
# 9 meses del Forecast contra 12 del Budget infla todas las variaciones. Por eso
# la tabla por tipo compara LOS MISMOS MESES en las dos versiones (hasta el último
# mes que el Forecast tiene por tipo, que se calcula solo), y el año completo va
# aparte con hotel, Standard (= hotel − Villas) y Villas.

def hab_hasta(v, campo, nivel, filtro, hasta):
    """tHabitaciones de enero hasta el mes `hasta` (celda). filtro = ('Codigo'|'Depto', valor) o None."""
    extra = "" if filtro is None else f',tHabitaciones[{filtro[0]}],"{filtro[1]}"'
    return (f'IFERROR(SUMIFS(tHabitaciones[{campo}],tHabitaciones[Etiqueta],{v},tHabitaciones[Nivel],"{nivel}"'
            f'{extra},tHabitaciones[Mes],"<="&{hasta}),0)')


def _grupos():
    """(rótulo, nivel, filtro) de cada renglón por tipo: tipos, los dos sets y el hotel."""
    g = [(f"{n} ({cd})", "Tipo", ("Codigo", cd), "normal") for cd, n, _ in TIPOS]
    g += [("Standard rooms (set)", "Set", ("Depto", "0110"), "subtotal"),
          ("Villas (set)", "Set", ("Depto", "0115"), "subtotal"),
          ("Hotel", "Hotel", None, "total")]
    return g


def _celda_hasta(h):
    """Último mes que el Forecast tiene por tipo: el período comparable."""
    r = h.fila("normal", ["", "Months compared by room type: January through month",
                          '=IFERROR(MAXIFS(tHabitaciones[Mes],tHabitaciones[Etiqueta],ver_F26,tHabitaciones[Nivel],"Tipo"),12)',
                          '=CHOOSE(C{R},"January","February","March","April","May","June","July","August","September","October","November","December")'])
    h.filas[-1]["celdas"] = [c.replace("{R}", str(r)) for c in h.filas[-1]["celdas"]]
    return f"$C${r}"


def _anio_completo(h, que):
    """Hotel, Standard (= hotel − Villas) y Villas, el año completo de cada versión."""
    A1 = None
    h.saltar()
    h.fila("seccion", ["", "FULL YEAR — hotel, standard and Villas (all twelve months)"])
    if que == "rate":
        h.fila("encabezado", ["", "", "=" + rotulo("A25"), "=" + rotulo("F26"), "=" + rotulo("B27"), "Δ B27 − F26", "Δ %"])
    else:
        h.fila("encabezado", ["", "", "=" + rotulo("A25"), "=" + rotulo("F26"), "=" + rotulo("B27"), "Δ B27 − F26", "Δ %"])
    p0 = h.r + 1
    hot = lambda c, k: hab(f"ver_{c}", k, "Hotel", None, None)
    vil = lambda c, k: hab(f"ver_{c}", k, "Set", "0115", None)
    fil = {}
    for etq, fn in (("Hotel", hot), ("Standard rooms", lambda c, k: f"{hot(c, k)}-{vil(c, k)}"), ("Villas", vil)):
        for campo, nombre in (("Disponibles", "available nights"), ("Ocupadas", "occupied nights"),
                              ("Pax", "guests"), ("Ingreso habitaciones", "rooms revenue")):
            n = h.r + 1
            fil[(etq, campo)] = h.fila("normal", ["", f"{etq} · {nombre}"] + ["=" + fn(c, campo) for c in ("A25", "F26", "B27")]
                                       + var_cols(n))
        n = h.r + 1
        d, o, i = fil[(etq, "Disponibles")], fil[(etq, "Ocupadas")], fil[(etq, "Ingreso habitaciones")]
        h.fila("pct", ["", f"{etq} · occupancy"] + [f'=IF(N({c}{d})=0,"",{c}{o}/{c}{d})' for c in "CDE"] + var_cols(n, pct=True))
        n = h.r + 1
        h.fila("usd2", ["", f"{etq} · ADR"] + [f'=IF(N({c}{o})=0,"",{c}{i}/{c}{o})' for c in "CDE"] + var_cols(n))
        n = h.r + 1
        h.fila("usd2", ["", f"{etq} · RevPAR"] + [f'=IF(N({c}{d})=0,"",{c}{i}/{c}{d})' for c in "CDE"] + var_cols(n))
    h.formato(f"C{p0}:F{h.r}", NUM)
    h.formato(f"G{p0}:G{h.r}", PCT)


def hoja_rate():
    h = Hoja("AM11 Rate by month", [8, 40] + [11] * 12 + [13], ocultar_a=True)
    h.fila("titulo", ["", "CWL · Rate analysis — ADR by room type and by month"])
    h.fila("nota", ["", "ADR = rooms revenue ÷ occupied nights of that type. The Actual 2025 and the Forecast's own months "
                        "are not split by room type: the table by type compares the SAME months in both versions, and "
                        "the full year (hotel, standard, Villas) is at the end."])
    h.saltar()
    aux = fila_aux(h)
    hasta = _celda_hasta(h)
    h.saltar()
    h.fila("seccion", ["", "=\"BY ROOM TYPE — January to \"&CHOOSE(" + hasta + ",\"January\",\"February\",\"March\",\"April\",\"May\",\"June\",\"July\",\"August\",\"September\",\"October\",\"November\",\"December\")&\", same months in both versions\""])
    h.fila("encabezado", ["", "Room type", "ADR F26", "ADR B27", "Δ ADR", "Δ %", "RevPAR F26", "RevPAR B27",
                          "Rooms rev. F26", "Rooms rev. B27", "Δ revenue", "Rate effect ²", "Volume effect ²"])
    t0 = h.r + 1
    for etq, nivel, filtro, estilo in _grupos():
        n = h.r + 1
        rev = lambda c: hab_hasta(f"ver_{c}", "Ingreso habitaciones", nivel, filtro, hasta)
        ocu = lambda c: hab_hasta(f"ver_{c}", "Ocupadas", nivel, filtro, hasta)
        dsp = lambda c: hab_hasta(f"ver_{c}", "Disponibles", nivel, filtro, hasta)
        h.fila(estilo, ["", etq,
                        "=" + div(rev("F26"), ocu("F26")), "=" + div(rev("B27"), ocu("B27")),
                        f'=IF(OR(C{n}="",D{n}=""),"",D{n}-C{n})', f'=IF(OR(C{n}="",D{n}=""),"",(D{n}-C{n})/C{n})',
                        "=" + div(rev("F26"), dsp("F26")), "=" + div(rev("B27"), dsp("B27")),
                        "=" + rev("F26"), "=" + rev("B27"), f"=J{n}-I{n}",
                        f'=IF(E{n}="","",E{n}*({ocu("B27")}))', f'=IF(L{n}="","",K{n}-L{n})'])
    h.fila("nota", ["", "² Rate effect = Δ ADR × Budget occupied nights; volume effect = the rest of the revenue change."])
    h.formato(f"C{t0}:E{h.r}", USD2)
    h.formato(f"F{t0}:F{h.r}", PCT)
    h.formato(f"G{t0}:H{h.r}", USD2)
    h.formato(f"I{t0}:M{h.r}", USD)
    _anio_completo(h, "rate")
    # Mensual, por tipo
    mk = lambda col: f"{col}${aux}" if col != "O" else None
    for etq, nivel, filtro, _ in _grupos():
        h.saltar()
        h.fila("encabezado", ["", etq] + MESES + ["FY"])
        cods = ("A25", "F26", "B27") if nivel == "Hotel" else ("F26", "B27")
        dep = None if filtro is None else filtro[1]
        def campo(cod, k, col):
            if nivel == "Tipo":
                return hab_t(f"ver_{cod}", k, filtro[1], mk(col))
            return hab(f"ver_{cod}", k, nivel, dep, mk(col))
        fv = {}
        for cod in cods:
            fv[cod] = h.fila("usd2", ["", "=\"ADR · \"&" + rotulo(cod)] +
                             ["=" + div(campo(cod, "Ingreso habitaciones", col), campo(cod, "Ocupadas", col)) for col in COLS + "O"])
        a, b = fv["F26"], fv["B27"]
        h.fila("usd2", ["", "Δ ADR (B27 − F26)"] + [f'=IF(OR({c}{a}="",{c}{b}=""),"",{c}{b}-{c}{a})' for c in COLS + "O"])
        h.fila("pct", ["", "Δ %"] + [f'=IF(OR({c}{a}="",{c}{b}=""),"",({c}{b}-{c}{a})/{c}{a})' for c in COLS + "O"])
    return h


def hoja_volumen():
    h = Hoja("AM12 Volume by month", [8, 40] + [11] * 12 + [13, 11, 11], ocultar_a=True)
    h.fila("titulo", ["", "CWL · Volume analysis — room nights and occupancy by room type and by month"])
    h.fila("nota", ["", "Occupancy comes from the TOTALS (never an average of percentages). The table by room type "
                        "compares the SAME months in both versions; the full year (hotel, standard, Villas) is below it."])
    h.saltar()
    aux = fila_aux(h)
    hasta = _celda_hasta(h)
    h.saltar()
    h.fila("seccion", ["", "=\"BY ROOM TYPE — January to \"&CHOOSE(" + hasta + ",\"January\",\"February\",\"March\",\"April\",\"May\",\"June\",\"July\",\"August\",\"September\",\"October\",\"November\",\"December\")&\", same months in both versions\""])
    h.fila("encabezado", ["", "Room type", "Units B27", "Avail. F26", "Avail. B27", "Occ. nights F26", "Occ. nights B27",
                          "Δ nights", "Δ %", "Occ. % F26", "Occ. % B27", "Δ (pp)", "Guests F26", "Guests B27", "Δ guests",
                          "Share of B27 nights"])
    t0 = h.r + 1
    hotel_r = t0 + len(_grupos()) - 1
    for etq, nivel, filtro, estilo in _grupos():
        n = h.r + 1
        val = lambda c, k: hab_hasta(f"ver_{c}", k, nivel, filtro, hasta)
        crit = "" if filtro is None else f',tHabitaciones[{filtro[0]}],"{filtro[1]}"'
        h.fila(estilo, ["", etq,
                        f'=IFERROR(MAXIFS(tHabitaciones[Unidades],tHabitaciones[Etiqueta],ver_B27,tHabitaciones[Nivel],"{nivel}"{crit}),0)',
                        "=" + val("F26", "Disponibles"), "=" + val("B27", "Disponibles"),
                        "=" + val("F26", "Ocupadas"), "=" + val("B27", "Ocupadas"),
                        f"=G{n}-F{n}", f'=IF(F{n}=0,"",(G{n}-F{n})/F{n})',
                        f'=IF(D{n}=0,"",F{n}/D{n})', f'=IF(E{n}=0,"",G{n}/E{n})',
                        f'=IF(OR(J{n}="",K{n}=""),"",K{n}-J{n})',
                        "=" + val("F26", "Pax"), "=" + val("B27", "Pax"), f"=N{n}-M{n}",
                        f'=IF(N(G${hotel_r})=0,"",G{n}/G${hotel_r})'])
    h.formato(f"C{t0}:H{h.r}", NUM)
    h.formato(f"I{t0}:L{h.r}", PCT)
    h.formato(f"M{t0}:O{h.r}", NUM)
    h.formato(f"P{t0}:P{h.r}", PCT)
    _anio_completo(h, "volumen")
    # Mensual
    mk = lambda col: f"{col}${aux}" if col != "O" else None
    for etq, nivel, filtro, _ in _grupos():
        h.saltar()
        h.fila("encabezado", ["", etq] + MESES + ["FY"])
        cods = ("A25", "F26", "B27") if nivel == "Hotel" else ("F26", "B27")
        dep = None if filtro is None else filtro[1]
        def fn(cod, k, col):
            if nivel == "Tipo":
                return hab_t(f"ver_{cod}", k, filtro[1], mk(col))
            return hab(f"ver_{cod}", k, nivel, dep, mk(col))
        oc, ds = {}, {}
        p0 = h.r + 1
        for cod in cods:
            oc[cod] = h.fila("normal", ["", "=\"Occupied nights · \"&" + rotulo(cod)] + ["=" + fn(cod, "Ocupadas", col) for col in COLS + "O"])
        h.fila("normal", ["", "Δ nights (B27 − F26)"] + [f"={c}{oc['B27']}-{c}{oc['F26']}" for c in COLS + "O"])
        for cod in cods:
            ds[cod] = h.fila("aux", ["", "available"] + ["=" + fn(cod, "Disponibles", col) for col in COLS + "O"])
        for cod in cods:
            h.fila("pct", ["", "=\"Occupancy · \"&" + rotulo(cod)] + [f'=IF({c}{ds[cod]}=0,"",{c}{oc[cod]}/{c}{ds[cod]})' for c in COLS + "O"])
        h.fila("pct", ["", "Δ occupancy (pp)"] + [f'=IF(OR({c}{ds["F26"]}=0,{c}{ds["B27"]}=0),"",{c}{oc["B27"]}/{c}{ds["B27"]}-{c}{oc["F26"]}/{c}{ds["F26"]})' for c in COLS + "O"])
        if nivel != "Tipo":
            for cod in ("F26", "B27"):
                h.fila("normal", ["", "=\"Guests · \"&" + rotulo(cod)] + ["=" + fn(cod, "Pax", col) for col in COLS + "O"])
        h.formato(f"C{p0}:O{h.r}", NUM)
    return h


# ── On the Books 2027 (Opera, a mano) ────────────────────────────────────────
# Owner, 2026-11-12: «un tab de análisis On the Books: Forecast 2026, Budget 2027 y
# on the books 2027 que viene de Opera. Rooms only y full revenue… lo dejás listo
# para llenar, yo lo hago manual» · «también Budget 2026 total revenue y rooms only».
#
# ⚠️ Lo que el owner escribe vive en «OTB Input», hoja CONSERVADA: aplicar.ps1 la
# crea una sola vez y no la vuelve a tocar. Si viviera en una hoja AM, el próximo
# armado del libro le borraría lo cargado.
OTB_FILAS = [   # fila de OTB Input · qué se carga
    (7, "Rooms revenue on the books (USD)"),
    (8, "Room nights on the books"),
    (9, "Total revenue on the books (USD) — optional"),
]


def hoja_otb_input():
    h = Hoja("OTB Input", [4, 46] + [12] * 12 + [14])
    h.conservar = True
    h.fila("titulo", ["", "On the Books 2027 — Opera (manual input)"])
    h.fila("nota", ["", "Type or paste the Opera figures in the yellow cells, one month per column. This sheet is "
                        "never rebuilt: what you type here stays. Sheet AM13 reads it."])
    h.fila("normal", ["", "As of (date of the Opera report)", ""])
    h.saltar()
    h.fila("encabezado", ["", "On the books 2027"] + MESES + ["FY"])
    h.saltar()
    for r, etq in OTB_FILAS:
        while h.r < r - 1:
            h.saltar()
        h.fila("entrada", ["", etq] + [""] * 12 + [f"=SUM(C{r}:N{r})"])
    return h


def hoja_otb():
    h = Hoja("AM13 On the Books", [8, 46] + [11] * 12 + [13], ocultar_a=True)
    h.fila("titulo", ["", "CWL · On the Books 2027 (Opera) against Budget 2027, Forecast 2026 and Budget 2026"])
    h.fila("nota", ["", "=\"OTB from sheet «OTB Input» (Opera, manual)\"&IF('OTB Input'!C3=\"\",\"\",\" · as of \"&TEXT('OTB Input'!C3,\"dd-mmm-yyyy\"))"
                        "&\". Pace = OTB ÷ Budget 2027: what is already sold of what the budget expects.\""])
    h.saltar()
    aux = fila_aux(h)
    k = lambda col: f"{col}${aux}"
    otb = lambda r: [f"='OTB Input'!{c}{r}" for c in COLS] + [f"=SUM(C{{R}}:N{{R}})"]

    def bloque(titulo, linea_fn, otb_r, estilo_val="normal"):
        h.saltar()
        h.fila("encabezado", ["", titulo] + MESES + ["FY"])
        filas = {}
        for cod in ("B26", "F26", "B27"):
            filas[cod] = h.fila(estilo_val, ["", "=" + rotulo(cod)] + ["=" + linea_fn(cod, k(c)) for c in COLS + "O"])
        n = h.r + 1
        filas["OTB"] = h.fila("subtotal", ["", "On the books 2027 (Opera)"] +
                              [c.replace("{R}", str(n)) for c in otb(otb_r)])
        o, b, f = filas["OTB"], filas["B27"], filas["F26"]
        h.fila("pct", ["", "Pace: OTB % of Budget 2027"] + [f'=IF(N({c}{b})=0,"",{c}{o}/{c}{b})' for c in COLS + "O"])
        h.fila("normal", ["", "Still to sell to reach Budget 2027"] + [f'=IF(N({c}{b})=0,"",{c}{b}-{c}{o})' for c in COLS + "O"])
        h.fila("pct", ["", "OTB % of Forecast 2026 (same month)"] + [f'=IF(N({c}{f})=0,"",{c}{o}/{c}{f})' for c in COLS + "O"])
        h.fila("pct", ["", "Budget 2027 vs Forecast 2026"] + [f'=IF(N({c}{f})=0,"",{c}{b}/{c}{f}-1)' for c in COLS + "O"])
        h.fila("pct", ["", "Budget 2027 vs Budget 2026"] + [f'=IF(N({c}{filas["B26"]})=0,"",{c}{b}/{c}{filas["B26"]}-1)' for c in COLS + "O"])
        return filas

    p0 = h.r + 1
    rr = bloque("ROOMS ONLY — rooms revenue", lambda c, kk: motor(f"ver_{c}", ["REV_ROOMS", "REV_ROOMS_OTHER"], kk), 7)
    nn = bloque("ROOM NIGHTS", lambda c, kk: est(f"ver_{c}", "Rooms occupied", kk), 8)
    h.saltar()
    h.fila("encabezado", ["", "ADR"] + MESES + ["FY"])
    for cod in ("B26", "F26", "B27", "OTB"):
        h.fila("usd2", ["", ("ADR · On the books 2027" if cod == "OTB" else "=\"ADR · \"&" + rotulo(cod))] +
               [f'=IF(N({c}{nn[cod]})=0,"",{c}{rr[cod]}/{c}{nn[cod]})' for c in COLS + "O"])
    bloque("FULL REVENUE — total revenue", lambda c, kk: motor(f"ver_{c}", ["TOTAL_REVENUES"], kk), 9)
    h.formato(f"C{p0}:O{h.r}", USD)
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
    ki = hoja_ki(rooms_filas)
    decisiones = hoja_decisiones(rooms_filas)
    rate = hoja_rate()
    volumen = hoja_volumen()
    otb_in = hoja_otb_input()
    otb = hoja_otb()

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
        ("AM09 Key Indicators", "All key indicators in one place, full year: Actual 2025, Forecast 2026, Budget 2027"),
        ("AM10 Decisions", "What grows vs revenue (payroll, opex, FTE, nights), margins by department, overhead vs the business"),
        ("AM11 Rate by month", "ADR by room type and month, side by side, with rate and volume effects"),
        ("AM12 Volume by month", "Room nights, occupancy and guests by room type and month, full year side by side"),
        ("AM13 On the Books", "On the Books 2027 from Opera (sheet OTB Input, manual) vs Budget 2027, Forecast 2026, Budget 2026"),
        ("OTB Input", "Where you type the Opera on-the-books figures (never rebuilt)"),
        ("AM97 Controls", "Checks that must be 0 before sending"),
        ("AM98 Versions", "Which version each column is (the current forecast is picked automatically)"),
    ]):
        indice.fila("normal", [str(i), n, d])

    hojas = [indice, reporte, rooms, resumen, pl, flow, sets, ki, decisiones, rate, volumen, otb, otb_in, controles, versiones]
    spec = {"hojas": [h.json() for h in hojas], "nombres": nombres}
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
    print(f"spec: {salida} · {sum(len(h.filas) for h in hojas)} filas en {len(hojas)} hojas")


if __name__ == "__main__":
    construir(sys.argv[1] if len(sys.argv) > 1 else "master_spec.json")
