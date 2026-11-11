# -*- coding: utf-8 -*-
"""Specs de las hojas «P&L Mes» y «P&L YTD» del Cierre Mensual.

Owner, 2026-11-11, revisando la v1: *«necesito que si compara YTD pero en un tab
aparte, y el analisis propiamente del mes sea solo del mes. quiero tener side to
side mismo mes 2024-2025-2026 precierre mes anterior, 2026 precierre mes de
analisis y Forecast y budget y varianza versus Budget y versus Forecast.»*
Preguntado aparte: «precierre mes anterior» = el Pre-Cierre del mes anterior.

Después, mirando la v2 en octubre: *«este mes hay que quitarlo no aplica porque
no se ha cerrado y el comparativo se hace versus esta columna debe ser versus
precierre del mes»*. Por eso P&L Mes NO lleva el Actual 2026 del mes y la base
de la varianza (celda E3, elegible) es el Pre-Cierre del mes. En el YTD la
columna de 2026 es «cerrado + Pre-Cierre»: el Actual hasta el mes anterior más
el Pre-Cierre del mes — y si ese mes no tiene Pre-Cierre (ya se cerró sin él),
su Actual, para no perder un mes entero del acumulado.

Cada columna es una suma de tGL por etiqueta y por campo («Mes», «Mes anterior»,
«Acumulado» — columnas calculadas de la tabla, ver mes_columnas.ps1). Lee la
hoja GL ya refrescada solo para el orden de las líneas y las cuentas con
movimiento.

    python -I pl_vistas_spec.py <libro_refrescado.xlsx> <carpeta_salida>
    -> pl_vista_mes.json, pl_vista_ytd.json
"""
import collections
import json
import pathlib
import sys

import openpyxl

sys.stdout.reconfigure(encoding="utf-8")
SRC, OUTDIR = sys.argv[1], pathlib.Path(sys.argv[2])
ws = openpyxl.load_workbook(SRC, data_only=True, read_only=True)["GL"]
enc = None
lineas = collections.OrderedDict()
cuentas, mov = {}, set()
for r in ws.iter_rows(values_only=True):
    if enc is None:
        enc = {h: i for i, h in enumerate(r)}
        continue
    if r[enc["Version"]] == "ERROR":
        continue
    lineas.setdefault(r[enc["P&L line"]], (r[enc["Section"]], r[enc["Report line"]]))
    clave = (r[enc["Category"]], str(r[enc["Account"]]))
    cuentas.setdefault(clave, r[enc["Account name"]])
    if any(abs(float(r[enc[f"M{i:02d}"]] or 0)) > 0.004 for i in range(1, 13)):
        mov.add(clave)

LETRAS = "EFGHIJKLMNOPQRSTUVWXYZ"
MES_NOMBRE = '"&pMesNombre&"'


def S(campo, etiqueta, crit):
    return f'SUMIFS(tGL[{campo}],tGL[Etiqueta],"{etiqueta}"{crit})'


# Una columna = (encabezado fijo para elegir la base, encabezado visible, expr(crit)).
VISTAS = {
    "mes": {
        "hoja": "P&L Mes",
        "titulo": "Corcovado Wilderness Lodge · P&L del mes — Cierre Contable Mensual",
        "nota": "SOLO el mes de Config!C7, la misma columna de cada año. El acumulado está en la hoja P&L YTD. "
                "Varianzas: Pre-Cierre del mes − Budget y − Forecast. Ingresos y gastos en positivo.",
        "base": "Pre-Cierre 2026",
        "columnas": [
            ("Actual 2024", f'=pMesNombre&" 2024"', lambda c: S("Mes", "Actual 2024", c)),
            ("Actual 2025", f'=pMesNombre&" 2025"', lambda c: S("Mes", "Actual 2025", c)),
            ("Pre-Cierre mes anterior", '="Pre-Cierre "&IF(pMes=1,"(no hay)",INDEX({"Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov"},pMes-1)&" 2026")',
             lambda c: S("Mes anterior", "Pre-Cierre 2026", c)),
            ("Pre-Cierre 2026", f'="Pre-Cierre "&pMesNombre&" 2026"', lambda c: S("Mes", "Pre-Cierre 2026", c)),
            ("Forecast 2026", f'="Forecast "&pMesNombre', lambda c: S("Mes", "Forecast 2026", c)),
            ("Budget 2026", f'="Budget "&pMesNombre', lambda c: S("Mes", "Budget 2026", c)),
        ],
    },
    "ytd": {
        "hoja": "P&L YTD",
        "titulo": "Corcovado Wilderness Lodge · P&L acumulado (YTD) — Cierre Contable Mensual",
        "nota": "Acumulado enero → mes de Config!C7. 2026 = Actual cerrado hasta el mes anterior + el Pre-Cierre del "
                "mes (si el mes no tiene Pre-Cierre, su Actual). Ingresos y gastos en positivo.",
        "base": "2026 cerrado + Pre-Cierre",
        # Celda bandera: ¿el Pre-Cierre trae algo en el mes elegido?
        "bandera": '=SUMPRODUCT((tGL[Etiqueta]="Pre-Cierre 2026")*(ABS(tGL[Mes])>0.004))>0',
        "columnas": [
            ("Actual 2024", '="YTD "&pMesNombre&" 2024"', lambda c: S("Acumulado", "Actual 2024", c)),
            ("Actual 2025", '="YTD "&pMesNombre&" 2025"', lambda c: S("Acumulado", "Actual 2025", c)),
            ("2026 cerrado + Pre-Cierre", '="YTD "&pMesNombre&" 2026: cerrado a mes ant. + Pre-Cierre "&pMesNombre',
             lambda c: f'({S("Acumulado", "Actual 2026", c)}-{S("Mes", "Actual 2026", c)}'
                       f'+IF($FLAG$4,{S("Mes", "Pre-Cierre 2026", c)},{S("Mes", "Actual 2026", c)}))'),
            ("Forecast 2026", '="Forecast YTD "&pMesNombre', lambda c: S("Acumulado", "Forecast 2026", c)),
            ("Budget 2026", '="Budget YTD "&pMesNombre', lambda c: S("Acumulado", "Budget 2026", c)),
        ],
    },
}


def armar(clave):
    v = VISTAS[clave]
    cols = v["columnas"]
    nd = len(cols)
    dl = LETRAS[:nd]                         # columnas de datos
    sep = LETRAS[nd]                         # separador (fila 4: la bandera, si hay)
    cols = [(k, h, (lambda fx: (lambda c: fx(c).replace("$FLAG$4", f"${sep}$4")))(fx)) for k, h, fx in cols]
    var = LETRAS[nd + 1: nd + 5]             # Var Budget $, %, Var Forecast $, %
    ultima_dato = dl[-1]
    cb = dl[[c[0] for c in cols].index("Budget 2026")]
    cf = dl[[c[0] for c in cols].index("Forecast 2026")]
    ncel = 4 + nd + 1 + 4
    out, r = [], [0]

    def fila(estilo, a="", b="", c="", d="", crit=None, celda=None, var_=False):
        r[0] += 1
        n = r[0]
        cel = [a, b, str(c), d]
        for j, (_k, _h, fx) in enumerate(cols):
            if celda:
                cel.append(celda(n, dl[j]))
            elif crit:
                cel.append(f"=$C{n}*{fx(crit(n))}")
            else:
                cel.append("")
        cel.append("")
        if var_:
            base = f"INDEX($E{n}:${ultima_dato}{n},MATCH($E$3,$E$6:${ultima_dato}$6,0))"
            cel += [f'=IFERROR({base}-{cb}{n},"")', f'=IFERROR(IF({cb}{n}=0,"",({base}-{cb}{n})/ABS({cb}{n})),"")',
                    f'=IFERROR({base}-{cf}{n},"")', f'=IFERROR(IF({cf}{n}=0,"",({base}-{cf}{n})/ABS({cf}{n})),"")']
        else:
            cel += [""] * 4
        assert len(cel) == ncel
        out.append({"r": n, "estilo": estilo, "celdas": cel})
        return n

    por_linea = lambda n: f",tGL[P&L line],$A{n}"
    por_cat = lambda n: f",tGL[Category],$D{n}"
    por_cta = lambda n: f",tGL[Account],$A{n},tGL[Category],$D{n}"
    suma = lambda i, f: (lambda n, col: f"=SUM({col}{i}:{col}{f})")
    expr = lambda pares: (lambda n, col: "=" + "".join(f"{s}{col}{x}" for s, x in pares))

    fila("titulo", b=v["titulo"])
    fila("nota", b=v["nota"])
    fila("selector")
    fila("blanco")
    fila("versiones")
    fila("encabezado", a="Línea / cuenta", b="Descripción", c="Signo", d="Categoría")

    fila("seccion", b="RESUMEN POR NATURALEZA")
    nat = {}
    for k, nom, s in [("REVENUE", "Ingreso", -1), ("COST_OF_SALES", "Costo de ventas", 1),
                      ("PAYROLL", "Payroll (planilla)", 1), ("OPERATING_EXPENSES", "Opex (gasto operativo)", 1),
                      ("ALLOCATIONS", "Reparto (distribución)", 1)]:
        nat[k] = fila("linea", a=k, b=nom, c=s, d=k, crit=por_cat, var_=True)
    gop_nat = fila("subtotal", b="GOP (ingreso − costo − payroll − opex − reparto)",
                   celda=expr([("", nat["REVENUE"])] + [("-", nat[k]) for k in
                                                        ("COST_OF_SALES", "PAYROLL", "OPERATING_EXPENSES", "ALLOCATIONS")]),
                   var_=True)
    bajo_nat = fila("linea", a="BELOW_GOP", b="Bajo el GOP (dueños, capital, financieros, depreciación, impuesto)",
                    c=1, d="BELOW_GOP", crit=por_cat, var_=True)
    fila("total", b="UTILIDAD NETA", celda=expr([("", gop_nat), ("-", bajo_nat)]), var_=True)
    fila("blanco")
    fila("seccion", b="P&L USALI")

    def bloque(titulo, secciones, signo):
        fila("grupo", b=titulo)
        ini = r[0] + 1
        for sec in secciones:
            for k, nom in [(k, x[1]) for k, x in lineas.items() if x[0] == sec]:
                fila("linea", a=k, b=nom, c=signo, crit=por_linea, var_=True)
        return ini, r[0]

    a, b = bloque("INGRESOS", ["REVENUES"], -1)
    rev = fila("subtotal", b="TOTAL INGRESOS", celda=suma(a, b), var_=True)
    a, b = bloque("COSTO DE VENTAS — departamentos operados", ["COST OF SALES"], 1)
    cos = fila("subtotal", b="TOTAL COSTO DE VENTAS", celda=suma(a, b), var_=True)
    a, b = bloque("GASTOS DEPARTAMENTALES — payroll + opex + reparto", ["OPERATING EXPENSES"], 1)
    dep = fila("subtotal", b="TOTAL GASTOS DEPARTAMENTALES", celda=suma(a, b), var_=True)
    udep = fila("total", b="UTILIDAD DEPARTAMENTAL", celda=expr([("", rev), ("-", cos), ("-", dep)]), var_=True)
    a, b = bloque("GASTOS NO DISTRIBUIDOS — costo, payroll, opex y reparto de overhead",
                  ["OVERHEAD COST OF SALES", "OVERHEAD EXPENSES"], 1)
    und = fila("subtotal", b="TOTAL GASTOS NO DISTRIBUIDOS", celda=suma(a, b), var_=True)
    gop = fila("total", b="GROSS OPERATING PROFIT (GOP)", celda=expr([("", udep), ("-", und)]), var_=True)
    a, b = bloque("GASTOS DE LA PROPIEDAD (NON-OPERATING)", ["OWNER / NON-OP EXPENSES"], 1)
    nonop = fila("subtotal", b="TOTAL NON-OPERATING", celda=suma(a, b), var_=True)
    ebitda = fila("total", b="EBITDA ANTES DE CAPITAL", celda=expr([("", gop), ("-", nonop)]), var_=True)
    a, b = bloque("CAPITAL", ["CAPITAL"], 1)
    capi = fila("subtotal", b="TOTAL CAPITAL", celda=suma(a, b), var_=True)
    ebitda2 = fila("total", b="EBITDA DESPUÉS DE CAPITAL", celda=expr([("", ebitda), ("-", capi)]), var_=True)
    a, b = bloque("GASTOS FINANCIEROS", ["FINANCIAL EXPENSES"], 1)
    fin = fila("subtotal", b="TOTAL FINANCIEROS", celda=suma(a, b), var_=True)
    a, b = bloque("DEPRECIACIÓN", ["DEPRECIATION"], 1)
    dpr = fila("subtotal", b="TOTAL DEPRECIACIÓN", celda=suma(a, b), var_=True)
    ebt = fila("total", b="UTILIDAD ANTES DE IMPUESTOS (EBT)", celda=expr([("", ebitda2), ("-", fin), ("-", dpr)]), var_=True)
    a, b = bloque("IMPUESTO SOBRE LA RENTA", ["TAX / NET PROFIT"], 1)
    tax = fila("subtotal", b="TOTAL IMPUESTO", celda=suma(a, b), var_=True)
    neta = fila("total", b="UTILIDAD NETA", celda=expr([("", ebt), ("-", tax)]), var_=True)

    # Controles por columna: la misma expresión de la columna sin filtro de línea.
    def ctl_col(extra):
        def f(n, col):
            j = dl.index(col)
            return cols[j][2](extra)
        return f
    tod = ctl_col("")
    sm = ctl_col(',tGL[Status],"SIN MAPEO"')
    ctl = fila("resto", b="Utilidad neta − (−Σ GL): da 0 salvo que haya cuentas SIN MAPEO",
               celda=lambda n, col: f"=ROUND({col}{neta}+{tod(n, col)},2)")
    sinmap = fila("resto", b="   de eso: cuentas SIN MAPEO del mayor (plata que el P&L no ve)",
                  celda=lambda n, col: f"=ROUND({sm(n, col)},2)")
    fila("control", b="Control: diferencia sin explicar  → debe dar 0",
         celda=lambda n, col: f"=ROUND({col}{ctl}-{col}{sinmap},2)")
    fila("control", b="Control: GOP USALI − GOP por naturaleza  → debe dar 0",
         celda=lambda n, col: f"=ROUND({col}{gop}-{col}{gop_nat},2)")
    fila("blanco")

    fila("seccion", b="DETALLE POR CUENTA (todos los departamentos sumados; por departamento, en la hoja GL)")
    totales = {}
    for k, nom, s in [("REVENUE", "INGRESO", -1), ("COST_OF_SALES", "COSTO DE VENTAS", 1), ("PAYROLL", "PAYROLL", 1),
                      ("OPERATING_EXPENSES", "OPEX", 1), ("ALLOCATIONS", "REPARTO", 1), ("BELOW_GOP", "BAJO EL GOP", 1)]:
        fila("grupo", b=nom)
        ini = r[0] + 1
        for (c, ac), nm in sorted(cuentas.items(), key=lambda x: x[0][1]):
            if c == k and (c, ac) in mov:
                fila("linea", a=ac, b=nm or "", c=s, d=k, crit=por_cta, var_=True)
        fin_ = r[0]
        catx = ctl_col(f',tGL[Category],"{k}"')
        if fin_ >= ini:
            resto = (lambda i, f, catx=catx, s=s: lambda n, col: f"={s}*{catx(n, col)}-SUM({col}{i}:{col}{f})")(ini, fin_)
        else:
            resto = (lambda catx=catx, s=s: lambda n, col: f"={s}*{catx(n, col)}")()
        fila("resto", b="Otras cuentas del mapeo (hoy sin movimiento en las versiones bajadas)", c=s, d=k, celda=resto)
        totales[k] = fila("subtotal", b=f"TOTAL {nom}", celda=suma(ini, r[0]), var_=True)
    fila("control", b="Control: Σ detalle → utilidad, contra la del P&L más SIN MAPEO  → debe dar 0",
         celda=lambda n, col: f"=ROUND({col}{totales['REVENUE']}-" + "-".join(
             f"{col}{totales[k]}" for k in ("COST_OF_SALES", "PAYROLL", "OPERATING_EXPENSES", "ALLOCATIONS", "BELOW_GOP"))
         + f"-{col}{neta}+{col}{sinmap},2)")

    spec = {
        "hoja": v["hoja"], "filas": out, "neta": neta, "ncel": ncel,
        "datos": list(dl), "sep": sep, "var": list(var), "base_defecto": v["base"], "bandera": v.get("bandera", ""),
        "fijos": [c[0] for c in cols], "visibles": [c[1] for c in cols],
        "var_titulos": ["Var vs Budget", "Var %", "Var vs Forecast", "Var %"],
    }
    (OUTDIR / f"pl_vista_{clave}.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    print(clave, "filas", len(out), "neta", neta, "columnas", "".join(dl))


for clave in VISTAS:
    armar(clave)
