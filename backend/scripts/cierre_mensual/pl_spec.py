import sys, json, collections, openpyxl
sys.stdout.reconfigure(encoding="utf-8")
SRC = sys.argv[1]; OUT = sys.argv[2]
ws = openpyxl.load_workbook(SRC, data_only=True)["GL"]
rows = list(ws.iter_rows(min_row=2, values_only=True))
lineas = collections.OrderedDict(); cuentas = {}; mov = set()
for r in rows:
    lineas.setdefault(r[4], (r[3], r[5]))
    cuentas.setdefault((r[11], str(r[8])), r[9])
    if any(abs(float(v or 0)) > 0.004 for v in r[15:27]): mov.add((r[11], str(r[8])))
def de(sec): return [(k, v[1]) for k, v in lineas.items() if v[0] == sec]

M = [f"M{i:02d}" for i in range(1, 13)]
COLS = "EFGHIJKLMNOP"
out = []; r = [0]
def fila(estilo, a="", b="", c="", d="", meses=None, anual=None, pct=False):
    r[0] += 1; n = r[0]
    celdas = [a, b, str(c), d]
    for j, m in enumerate(M):
        celdas.append(meses(n, m, COLS[j]) if meses else "")
    celdas.append(anual(n) if anual else (f"=SUM(E{n}:P{n})" if meses else ""))
    celdas.append(f'=IF($Q${{REV}}=0,"",Q{n}/$Q${{REV}})' if pct else "")
    out.append({"r": n, "estilo": estilo, "celdas": celdas}); return n
def linea(n, m, c): return f"=$C{n}*SUMIFS(tGL[{m}],tGL[Etiqueta],$B$3,tGL[P&L line],$A{n})"
def cat(n, m, c): return f"=$C{n}*SUMIFS(tGL[{m}],tGL[Etiqueta],$B$3,tGL[Category],$D{n})"
def cta(n, m, c): return f"=$C{n}*SUMIFS(tGL[{m}],tGL[Etiqueta],$B$3,tGL[Account],$A{n},tGL[Category],$D{n})"
def suma(a, b): return lambda n, m, c: f"=SUM({c}{a}:{c}{b})"
def expr(pares): return lambda n, m, c: "=" + "".join(f"{s}{c}{x}" for s, x in pares)

fila("titulo", b=(sys.argv[3] if len(sys.argv) > 3 else "Hotel") + " · P&L USALI — en vivo desde la tabla del GL")
fila("nota", b="Elegí la versión en B3 (las mismas etiquetas de Config). Ingresos y gastos en positivo; utilidad = ingresos − gastos. Se recalcula sola al hacer Datos → Actualizar todo.")
fila("selector", a="Versión:", b="Pre-Cierre 2026")
fila("blanco")
fila("blanco")
fila("encabezado", a="Línea / cuenta", b="Descripción", c="Signo", d="Categoría")  # meses en PS

# ---- Resumen por naturaleza
fila("seccion", b="RESUMEN POR NATURALEZA")
nat = {}
for k, nom, s in [("REVENUE","Ingreso",-1),("COST_OF_SALES","Costo de ventas",1),("PAYROLL","Payroll (planilla)",1),
                  ("OPERATING_EXPENSES","Opex (gasto operativo)",1),("ALLOCATIONS","Reparto (distribución)",1)]:
    nat[k] = fila("linea", a=k, b=nom, c=s, d=k, meses=cat)
gop_nat = fila("subtotal", b="GOP (ingreso − costo − payroll − opex − reparto)",
               meses=expr([("", nat["REVENUE"])] + [("-", nat[k]) for k in ("COST_OF_SALES","PAYROLL","OPERATING_EXPENSES","ALLOCATIONS")]))
bajo_nat = fila("linea", a="BELOW_GOP", b="Bajo el GOP (dueños, capital, financieros, depreciación, impuesto)", c=1, d="BELOW_GOP", meses=cat)
neta_nat = fila("total", b="UTILIDAD NETA", meses=expr([("", gop_nat), ("-", bajo_nat)]))
fila("blanco")

# ---- P&L USALI
fila("seccion", b="P&L USALI")
def bloque(titulo, secciones, signo):
    fila("grupo", b=titulo)
    ini = r[0] + 1
    for sec in secciones:
        for k, nom in de(sec):
            fila("linea", a=k, b=nom, c=signo, meses=linea, pct=True)
    return ini, r[0]
a, b = bloque("INGRESOS", ["REVENUES"], -1)
rev = fila("subtotal", b="TOTAL INGRESOS", meses=suma(a, b), pct=True)
a, b = bloque("COSTO DE VENTAS — departamentos operados", ["COST OF SALES"], 1)
cos = fila("subtotal", b="TOTAL COSTO DE VENTAS", meses=suma(a, b), pct=True)
a, b = bloque("GASTOS DEPARTAMENTALES — payroll + opex + reparto", ["OPERATING EXPENSES"], 1)
dep = fila("subtotal", b="TOTAL GASTOS DEPARTAMENTALES", meses=suma(a, b), pct=True)
udep = fila("total", b="UTILIDAD DEPARTAMENTAL", meses=expr([("", rev), ("-", cos), ("-", dep)]), pct=True)
a, b = bloque("GASTOS NO DISTRIBUIDOS — costo, payroll, opex y reparto de overhead", ["OVERHEAD COST OF SALES", "OVERHEAD EXPENSES"], 1)
und = fila("subtotal", b="TOTAL GASTOS NO DISTRIBUIDOS", meses=suma(a, b), pct=True)
gop = fila("total", b="GROSS OPERATING PROFIT (GOP)", meses=expr([("", udep), ("-", und)]), pct=True)
a, b = bloque("GASTOS DE LA PROPIEDAD (NON-OPERATING)", ["OWNER / NON-OP EXPENSES"], 1)
nonop = fila("subtotal", b="TOTAL NON-OPERATING", meses=suma(a, b), pct=True)
ebitda = fila("total", b="EBITDA ANTES DE CAPITAL", meses=expr([("", gop), ("-", nonop)]), pct=True)
a, b = bloque("CAPITAL", ["CAPITAL"], 1)
capi = fila("subtotal", b="TOTAL CAPITAL", meses=suma(a, b), pct=True)
ebitda2 = fila("total", b="EBITDA DESPUÉS DE CAPITAL", meses=expr([("", ebitda), ("-", capi)]), pct=True)
a, b = bloque("GASTOS FINANCIEROS", ["FINANCIAL EXPENSES"], 1)
fin = fila("subtotal", b="TOTAL FINANCIEROS", meses=suma(a, b), pct=True)
a, b = bloque("DEPRECIACIÓN", ["DEPRECIATION"], 1)
dpr = fila("subtotal", b="TOTAL DEPRECIACIÓN", meses=suma(a, b), pct=True)
ebt = fila("total", b="UTILIDAD ANTES DE IMPUESTOS (EBT)", meses=expr([("", ebitda2), ("-", fin), ("-", dpr)]), pct=True)
a, b = bloque("IMPUESTO SOBRE LA RENTA", ["TAX / NET PROFIT"], 1)
tax = fila("subtotal", b="TOTAL IMPUESTO", meses=suma(a, b), pct=True)
neta = fila("total", b="UTILIDAD NETA", meses=expr([("", ebt), ("-", tax)]), pct=True)
ctl = fila("resto", b="Utilidad neta − (−Σ tabla GL): da 0 salvo que haya cuentas SIN MAPEO", meses=lambda n, m, c: f"=ROUND({c}{neta}+SUMIFS(tGL[{m}],tGL[Etiqueta],$B$3),2)")
# CWL, 2026-11-11: en el Pre-Cierre de septiembre la 0250-8050 llegó SIN MAPEO (el
# P&L no la ve). Se muestra aparte en vez de esconderla: el control de abajo es el que da 0.
sinmap = fila("resto", b="   de eso: cuentas SIN MAPEO del mayor (plata que el P&L no ve)", meses=lambda n, m, c: f'=ROUND(SUMIFS(tGL[{m}],tGL[Etiqueta],$B$3,tGL[Status],"SIN MAPEO"),2)')
fila("control", b="Control: diferencia sin explicar  → debe dar 0", meses=lambda n, m, c: f"=ROUND({c}{ctl}-{c}{sinmap},2)")
fila("control", b="Control: GOP USALI − GOP por naturaleza  → debe dar 0", meses=lambda n, m, c: f"=ROUND({c}{gop}-{c}{gop_nat},2)")
fila("blanco")

# ---- Detalle por cuenta
fila("seccion", b="DETALLE POR CUENTA (todos los departamentos sumados)")
totales = {}
for k, nom, s in [("REVENUE","INGRESO",-1),("COST_OF_SALES","COSTO DE VENTAS",1),("PAYROLL","PAYROLL",1),
                  ("OPERATING_EXPENSES","OPEX",1),("ALLOCATIONS","REPARTO",1),("BELOW_GOP","BAJO EL GOP",1)]:
    fila("grupo", b=nom)
    ini = r[0] + 1
    for (c, ac), nm in sorted(cuentas.items(), key=lambda x: x[0][1]):
        if c == k and (c, ac) in mov:
            fila("linea", a=ac, b=nm or "", c=s, d=k, meses=cta)
    fin_ = r[0]
    fila("resto", b="Otras cuentas del mapeo (hoy sin movimiento en las versiones bajadas)", c=s, d=k,
         meses=(lambda i, f: lambda n, m, c: f"=$C{n}*SUMIFS(tGL[{m}],tGL[Etiqueta],$B$3,tGL[Category],$D{n})-SUM({c}{i}:{c}{f})")(ini, fin_) if fin_ >= ini
               else cat)
    totales[k] = fila("subtotal", b=f"TOTAL {nom}", meses=suma(ini, r[0]))
fila("control", b="Control: Σ detalle → utilidad, contra la del P&L más SIN MAPEO  → debe dar 0",
     meses=lambda n, m, c: f"=ROUND({c}{totales['REVENUE']}-" + "-".join(f"{c}{totales[k]}" for k in ("COST_OF_SALES","PAYROLL","OPERATING_EXPENSES","ALLOCATIONS","BELOW_GOP")) + f"-{c}{neta}+{c}{sinmap},2)")

for o in out:
    o["celdas"] = [x.replace("{REV}", str(rev)) for x in o["celdas"]]
json.dump({"filas": out, "rev": rev, "neta": neta, "gop": gop}, open(OUT, "w", encoding="utf-8"), ensure_ascii=False)
print("filas", len(out), "rev", rev, "neta", neta, "cuentas", sum(1 for o in out if o["estilo"]=="linea" and o["celdas"][3] and o["celdas"][0] not in nat and o["celdas"][0]!="BELOW_GOP"))
