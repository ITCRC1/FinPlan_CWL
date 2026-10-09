# -*- coding: utf-8 -*-
"""Las doce secciones del informe.

Los CUADROS se arman solos a partir de `datos.Datos`. El TEXTO viene de un
modulo de narrativa por mes (`narrativa/n2026_09.py`). Esa division es
deliberada:

* los cuadros son identicos todos los meses y no se opinan;
* el analisis es juicio, cambia cada mes y no se puede generar.

Si falta una clave de narrativa, el informe se arma igual y deja una marca
«[PENDIENTE: clave]» en el lugar. Un hueco visible es mejor que una seccion
que desaparece sin avisar.
"""
from __future__ import annotations

from app.informes.datos import OPERATIVOS, OVERHEAD
from app.informes.formato import (AZUL, GRIS, NEGRO, Pt, bullet, h1, h2, h3, nota, par, pc,
                     pct_var, tabla, us, var, var_gasto)

FALTANTES: list[str] = []


def N(nar: dict, clave: str, default=None):
    """Una clave de narrativa. Si falta, lo anota y devuelve una marca."""
    if clave in nar and nar[clave]:
        return nar[clave]
    FALTANTES.append(clave)
    return default if default is not None else [f"[PENDIENTE: {clave}]"]


def textos(d, nar, clave):
    v = N(nar, clave)
    for p in (v if isinstance(v, (list, tuple)) else [v]):
        par(d, p, size=9.5, space=4)


# ───────────────────────────────────────────────────────────── portada e indice
def portada(d, D, nar):
    p = d.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(nar.get("propiedad", "CORCOVADO WILDERNESS LODGE"))
    r.bold = True
    r.font.size = Pt(16)
    r.font.color.rgb = AZUL
    p = d.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(f"Informe operativo de variaciones  ·  "
                  f"{D.mes_nombre.capitalize()} {D.anio}")
    r.font.size = Pt(13)
    r.font.color.rgb = NEGRO
    p = d.add_paragraph()
    p.paragraph_format.space_after = Pt(10)
    linea = " contra ".join([D.rotulo("ACT"),
                             " y ".join(D.rotulo(e) for e in D.escs if e != "ACT")])
    r = p.add_run(linea + "\nDocumento de trabajo para control de costos — "
                          "no es el resumen ejecutivo a propietarios")
    r.font.size = Pt(9.5)
    r.italic = True
    r.font.color.rgb = GRIS


SECCIONES = [
    ("1", "Proposito, alcance y como leer este documento"),
    ("2", "Resumen ejecutivo operativo"),
    ("3", "Contexto operativo: que clase de mes fue"),
    ("4", "Analisis por departamento operativo"),
    ("5", "Overhead: los departamentos sin ingreso"),
    ("6", "Planilla: analisis transversal"),
    ("7", "Costo de ventas y margenes"),
    ("8", "Opex: favorabilidades e impactos"),
    ("9", "Gastos de propiedad (clase 8)"),
    ("10", "Hallazgos de clasificacion y de sistema"),
    ("11", "Agenda de reunion por responsable"),
    ("12", "Anexos"),
]


def indice(d, D):
    h1(d, "Contenido")
    for num, txt in SECCIONES:
        p = d.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        r = p.add_run(f"{num}.  {txt}")
        r.font.size = Pt(10)
        r.bold = True
        lista = {"4": OPERATIVOS, "5": OVERHEAD}.get(num)
        if lista:
            q = d.add_paragraph()
            q.paragraph_format.space_after = Pt(1)
            rr = q.add_run("   " + "  ·  ".join(n for n, _ in lista))
            rr.font.size = Pt(8.5)
            rr.font.color.rgb = GRIS


# ─────────────────────────────────────────────────────────────────── seccion 1
def seccion1(d, D, nar):
    h1(d, "Proposito, alcance y como leer este documento", 1)
    par(d, "Este informe no es el resumen ejecutivo que se envia a los propietarios. "
           "Es el documento de trabajo de control de costos: esta escrito para "
           "sentarse con cada gerente de departamento y preguntarle por sus numeros "
           "con el detalle del mayor en la mano. Por eso cada seccion departamental "
           "termina en una lista de preguntas concretas, y por eso cada cifra que se "
           "discute se acompana del asiento, el proveedor o el concepto de nomina que "
           "la produjo.")

    h2(d, "1.1  De donde salen los numeros")
    par(d, "Los totales por clase de cuenta salen de la misma funcion que alimenta la "
           "pantalla Month-End Close — P&L del sistema, con el escenario pasado "
           "explicitamente para que se aplique su regla de allocation. Los totales "
           "del mes atan al centavo con lo que se ve en pantalla. Esto es deliberado: "
           "un informe que diga otro numero que la pantalla no se puede discutir en "
           "una reunion.")
    mayor = (f"{len(D.d['mayor']):,} lineas · "
             f"{len({x['seg1'] for x in D.d['mayor']})} cuentas · "
             f"{len({x['seg2'] for x in D.d['mayor']})} deptos de Integrity")
    tabla(d, ["Concepto", "Fuente", "Grano disponible"],
          [["Actual del mes", f"{D.rotulo('ACT')} — espejo del Balance de Comprobacion",
            "Cuenta, departamento, detalle y asiento"],
           ["Detalle del asiento",
            f"Mayor guardado — «{D.archivo_mayor or 'NO SUBIDO'}»", mayor],
           ["Budget", f"{D.rotulo('BUD')} — checkbooks", "Cuenta, departamento, detalle"],
           ["Forecast", (D.rotulo('FCT') + " — checkbooks") if "FCT" in D.escs
            else "no disponible", "Cuenta, departamento, detalle"],
           ["Estadistica de habitaciones",
            f"actual_room_stats del escenario {D.d['stats'].get('nota_actual') or '—'}",
            "Por tipo de villa"],
           ["Nombres de cuenta", "Catalogo de mapeo (account_mapping)",
            "Cuenta y departamento"]],
          nota_pie="Lectura de solo lectura sobre la base de produccion.")

    h2(d, "1.2  Las advertencias de lectura")
    par(d, "Antes de leer una sola variacion hay que tener presentes estas cosas. "
           "Todas cambian la interpretacion de numeros que, mirados sin este "
           "contexto, llevan a la conclusion equivocada.")

    cred = D.creditos_allocation()
    suma_cred = sum(cred.values())
    nota(d, "A · El Pre-Cierre y el presupuesto NO miden el mismo perimetro",
         "Los departamentos de allocation —Cafeteria (0220), Lavanderia (0161) y "
         "Laundry Revenue (0162)— se muestran en la columna del Pre-Cierre y se "
         "excluyen en Budget y Forecast. Es una regla deliberada del tab de revision. "
         "Consecuencia practica: su gasto aparece como variacion desfavorable completa "
         "cuando en parte SI esta presupuestado, solo que en otro departamento o en "
         "otra cuenta. En este informe se senala cada vez que aparece.")
    meses = D.meses_cargados()
    nota(d, f"B · El Pre-Cierre contiene {len(meses)} mes(es): "
            f"{', '.join(MES_CORTO(m) for m in meses)}",
         "No hay acumulado valido desde esta fuente. Por eso el analisis es mensual. "
         + ("El comparativo secuencial compara contra el mes anterior cargado."
            if len(meses) > 1 else
            "No hay comparativo secuencial porque el mes anterior no esta en el "
            "espejo."))
    if abs(suma_cred) > 0.005:
        rep = D.gop("ACT")
        mot = D.pl("ACT", "GOP") or D.pl("ACT", "TOTAL_GOP")
        nota(d, "C · El GOP de este reporte y el del motor no coinciden",
             f"El tab incluye el GASTO de allocation y descarta su CREDITO —la cuenta "
             f"4999—, que es lo que hace que esos departamentos neteen a cero. En el "
             f"mes el credito descartado es ${us(abs(suma_cred))}, y es exactamente la "
             f"diferencia entre el GOP del reporte (${us(rep)}) y el del motor del P&L "
             f"(${us(mot)}). Todos los cuadros de este informe usan el numero del "
             f"reporte para que aten con la pantalla, pero la conversacion con la "
             f"gerencia general deberia hacerse sobre el del motor. Ver la seccion 10.1.")
    nota(d, "D · El Pre-Cierre no trae estadistica de habitaciones",
         "El encabezado de la pantalla muestra «—» en ocupacion, ADR y RevPAR del "
         "Actual porque el espejo no carga esas lineas. Aqui la estadistica real se "
         "tomo del escenario ACTUAL, que si las tiene. Es el mismo mes y la misma "
         "propiedad, pero es otra tabla — conviene cerrar esa brecha para que el "
         "indicador y la plata salgan del mismo lugar.")
    for a in D.avisos:
        nota(d, "⚠ Aviso de la extraccion", a)

    h2(d, "1.3  Como esta construido el analisis")
    par(d, "Cada departamento se analiza con la misma estructura, en el orden del P&L, "
           "y siempre en cuatro planos:")
    bullet(d, "INGRESO — contra Budget y contra Forecast, y contra el volumen que lo "
              "deberia explicar (noches, huespedes, cobertura).")
    bullet(d, "COSTO DE VENTAS — en valor absoluto y como porcentaje del ingreso que "
              "le corresponde. Un costo que baja menos que su ingreso es un margen "
              "que se perdio, aunque la variacion absoluta parezca favorable.")
    bullet(d, "PLANILLA — contra Budget, y abierta por concepto cuando el desvio esta "
              "en horas extra, vacaciones o provisiones y no en el salario base.")
    bullet(d, "OPEX — contra Budget, separando lo que es diferimiento o adelanto de "
              "calendario de lo que es gasto estructural nuevo.")
    par(d, "Y cada seccion cierra con PREGUNTAS AL GERENTE: lo que no se puede "
           "responder desde el mayor y hay que preguntarle a la persona responsable. "
           "Esas preguntas son el producto de este informe.", italic=True)


def MES_CORTO(m):
    return ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set",
            "oct", "nov", "dic"][m - 1]


# ─────────────────────────────────────────────────────────────────── seccion 2
def seccion2(d, D, nar):
    h1(d, "Resumen ejecutivo operativo", 2)
    rev = {e: D.total(e, "revenue") for e in D.escs}
    gas = {e: D.tot_gasto(e) for e in D.escs}
    g = {e: D.gop(e) for e in D.escs}
    prop = {e: D.total(e, "property") for e in D.escs}
    textos(d, nar, "resumen")

    h2(d, "2.1  El mes en una tabla")
    cab = ["Linea", "Actual", "Budget", "Var $", "Var %"]
    if "FCT" in D.escs:
        cab.append("Forecast")
    cab.append("% ing.")
    filas = []

    def fila(et, a, b, f, gasto=True, estilo=None):
        vv = var_gasto(a, b) if gasto else var(a, b)
        r = [et, us(a), us(b), vv[0] if estilo else vv, pct_var(a, b)]
        if "FCT" in D.escs:
            r.append(us(f))
        r.append(pc(a / rev["ACT"]) if abs(rev["ACT"]) > 0.005 else "—")
        return [(x, estilo) if estilo else x for x in r] if estilo else r

    filas.append(fila("Ingreso total", rev["ACT"], rev["BUD"], rev.get("FCT"), False))
    for et, c in (("Costo de ventas", "cost"), ("Planilla y cargas", "payroll"),
                  ("Gasto operativo (opex)", "opex")):
        filas.append(fila(et, D.total("ACT", c), D.total("BUD", c),
                          D.total("FCT", c) if "FCT" in D.escs else None))
    filas.append(fila("GASTO OPERATIVO TOTAL", gas["ACT"], gas["BUD"],
                      gas.get("FCT"), True, "tot"))
    filas.append(fila("GOP", g["ACT"], g["BUD"], g.get("FCT"), False, "sec"))
    filas.append(fila("Gastos de propiedad (clase 8)", prop["ACT"], prop["BUD"],
                      prop.get("FCT")))
    ra, rb = g["ACT"] - prop["ACT"], g["BUD"] - prop["BUD"]
    rf = (g["FCT"] - prop["FCT"]) if "FCT" in D.escs else None
    filas.append(fila("RESULTADO DESPUES DE PROPIEDAD", ra, rb, rf, False, "sec"))
    tabla(d, cab, filas,
          nota_pie="Var $ = Actual − Budget. En las lineas de gasto el rojo indica "
                   "desfavorable (se gasto mas de lo presupuestado). El % de ingreso "
                   "se calcula sobre el ingreso real del mes.")

    h2(d, "2.2  Los hallazgos, ordenados por impacto")
    par(d, "Es el orden en que conviene atacar la conversacion. El monto entre "
           "parentesis es el impacto sobre el resultado del mes.")
    hall = N(nar, "hallazgos", [])
    if not hall:
        par(d, "[PENDIENTE: hallazgos]", color=GRIS, italic=True)
    for i, h in enumerate(hall, 1):
        titulo, monto, texto = h
        h3(d, f"{i}.  {titulo}   ({monto})")
        par(d, texto, size=9.5, space=3)


# ─────────────────────────────────────────────────────────────────── seccion 3
def seccion3(d, D, nar):
    h1(d, f"Contexto operativo: que clase de mes fue {D.mes_nombre}", 3)
    s = D.stats()
    a, b, f = s["ACT"], s["BUD"], s.get("FCT")
    par(d, "Ninguna variacion de costo se puede juzgar sin saber cuanto negocio hubo.")
    textos(d, nar, "contexto")

    h2(d, "3.1  Indicadores de habitaciones")
    cab = ["Indicador", "Actual", "Budget", "Var"] + (["Forecast"] if f else [])

    def tri(k, dec=2, pct=False):
        va = a[k] if a else None
        vb = b[k] if b else None
        vf = f[k] if f else None
        if pct:
            dd = ((f"{(va-vb)*100:+.2f} pp", "neg" if va < vb else "pos")
                  if (va is not None and vb is not None) else ("—", "gris"))
            r = [pc(va, dec), pc(vb, dec), dd]
            if f:
                r.append(pc(vf, dec))
            return r
        r = [us(va, dec), us(vb, dec), var(va, vb)]
        if f:
            r.append(us(vf, dec))
        return r

    filas = [["Noches disponibles"] + tri("disp", 0),
             ["Noches ocupadas"] + tri("occ", 1),
             ["% de ocupacion"] + tri("ocup", 2, True),
             ["Huespedes (pax)"] + tri("pax", 0),
             ["ADR (tarifa media)"] + tri("adr"),
             ["RevPAR"] + tri("revpar")]
    fr = [("Ingreso de habitaciones", "tot")] + [(x, "tot") if not isinstance(x, tuple)
                                                 else (x[0], "tot") for x in tri("rev")]
    filas.append(fr)
    tabla(d, cab, filas,
          nota_pie=f"Actual de actual_room_stats del escenario "
                   f"{D.d['stats'].get('nota_actual') or '—'}.")
    textos(d, nar, "contexto_kpi")

    if a["tipos"]:
        h2(d, "3.2  Ocupacion por tipo de villa")
        filas = []
        for t in sorted(a["tipos"], key=lambda x: -float(x["nights_occupied"] or 0)):
            na = float(t["nights_available"] or 0)
            no = float(t["nights_occupied"] or 0)
            rv = float(t["revenue"] or 0)
            px = float(t["pax"] or 0)
            filas.append([str(t["room_type_name"])[:38], us(na, 0), us(no, 1),
                          pc(no / na if na else 0, 1), us(rv),
                          us(rv / no) if no else "—", us(px, 0)])
        filas.append([("TOTAL", "tot"), (us(a["disp"], 0), "tot"),
                      (us(a["occ"], 1), "tot"), (pc(a["ocup"], 2), "tot"),
                      (us(a["rev"]), "tot"), (us(a["adr"]), "tot"),
                      (us(a["pax"], 0), "tot")])
        tabla(d, ["Tipo de villa", "Disp.", "Ocup.", "%", "Ingreso", "ADR", "Pax"],
              filas)
        textos(d, nar, "contexto_tipos")

    meses = D.meses_cargados()
    anteriores = [m for m in meses if m < D.mes]
    if anteriores:
        prev = max(anteriores)
        h2(d, f"3.3  {D.mes_nombre.capitalize()} contra "
              f"{datos_mes(prev)}: la prueba de si el costo reacciono")
        par(d, "El Pre-Cierre contiene los dos meses, asi que la comparacion "
               "secuencial sale de la misma fuente y con la misma regla.")
        filas = []
        for et, c in (("Ingreso total", "revenue"), ("Costo de ventas", "cost"),
                      ("Planilla y cargas", "payroll"), ("Gasto operativo (opex)", "opex")):
            p, n = D.total("ACT", c, prev), D.total("ACT", c)
            filas.append([et, us(p), us(n),
                          var(n, p) if c == "revenue" else var_gasto(n, p),
                          pct_var(n, p)])
        gp, gn = D.tot_gasto("ACT", prev), D.tot_gasto("ACT")
        filas.append([("GASTO OPERATIVO TOTAL", "tot"), (us(gp), "tot"), (us(gn), "tot"),
                      (var_gasto(gn, gp)[0], "tot"), (pct_var(gn, gp), "tot")])
        filas.append([("GOP", "sec"), (us(D.gop("ACT", prev)), "sec"),
                      (us(D.gop("ACT")), "sec"),
                      (var(D.gop("ACT"), D.gop("ACT", prev))[0], "sec"),
                      (pct_var(D.gop("ACT"), D.gop("ACT", prev)), "sec")])
        tabla(d, ["Linea", datos_mes(prev).capitalize(),
                  D.mes_nombre.capitalize(), "Var $", "Var %"], filas)
        textos(d, nar, "contexto_secuencial")

    nt = nar.get("contexto_nota")
    if nt:
        nota(d, nt[0], nt[1])


def datos_mes(m):
    return ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "setiembre", "octubre", "noviembre", "diciembre"][m - 1]


# ──────────────────────────────────── el bloque departamental, reutilizable
def bloque(d, D, agg, nar, titulo, clave, deptos, *, con_ingreso=True):
    h2(d, titulo)
    A = D.cuatro(deptos, "ACT")
    Bu = D.cuatro(deptos, "BUD")
    F = D.cuatro(deptos, "FCT") if "FCT" in D.escs else None
    cab = ["Linea", "Actual", "Budget", "Var $", "Var %"] + \
          (["Forecast"] if F else []) + ["% ing."]
    filas = []
    for et, c in (("Ingreso", "revenue"), ("Costo de ventas", "cost"),
                  ("Planilla y cargas", "payroll"), ("Gasto operativo (opex)", "opex")):
        if c == "revenue" and not con_ingreso:
            continue
        a, b = A[c], Bu[c]
        fv = F[c] if F else None
        if max(abs(a), abs(b), abs(fv or 0)) < 0.005:
            continue
        vv = var(a, b) if c == "revenue" else var_gasto(a, b)
        r = [et, us(a), us(b), vv, pct_var(a, b)]
        if F:
            r.append(us(fv))
        r.append(pc(a / A["revenue"]) if con_ingreso and abs(A["revenue"]) > 0.005
                 else "—")
        filas.append(r)
    ga = A["cost"] + A["payroll"] + A["opex"]
    gb = Bu["cost"] + Bu["payroll"] + Bu["opex"]
    gf = (F["cost"] + F["payroll"] + F["opex"]) if F else None
    r = [("Gasto total del departamento", "tot"), (us(ga), "tot"), (us(gb), "tot"),
         (var_gasto(ga, gb)[0], "tot"), (pct_var(ga, gb), "tot")]
    if F:
        r.append((us(gf), "tot"))
    r.append((pc(ga / A["revenue"]) if con_ingreso and abs(A["revenue"]) > 0.005
              else "—", "tot"))
    filas.append(r)
    if con_ingreso:
        ra, rb = A["revenue"] - ga, Bu["revenue"] - gb
        rf = (F["revenue"] - gf) if F else None
        r = [("RESULTADO DEPARTAMENTAL", "sec"), (us(ra), "sec"), (us(rb), "sec"),
             (var(ra, rb)[0], "sec"), (pct_var(ra, rb), "sec")]
        if F:
            r.append((us(rf), "sec"))
        r.append((pc(ra / A["revenue"]) if abs(A["revenue"]) > 0.005 else "—", "sec"))
        filas.append(r)
    tabla(d, cab, filas)

    # ⚠️ Con el prefijo del departamento: un «comentario» pelado en la lista de
    # pendientes no dice de cual de los quince es.
    sub = nar.get("dept", {}).get(clave, {})
    if sub.get("comentario"):
        for p_ in sub["comentario"]:
            par(d, p_, size=9.5, space=4)
    else:
        FALTANTES.append(f"dept.{clave}.comentario")
        par(d, f"[PENDIENTE: dept.{clave}.comentario]", size=9.5, color=GRIS,
            italic=True)

    ctas = nar.get("dept", {}).get(clave, {}).get("cuentas") or []
    if ctas and agg:
        h3(d, "El detalle del mayor")
        filas = []
        for dep, cta, etq in ctas:
            v = agg.get((dep, cta))
            if not v:
                continue
            filas.append([(f"{cta}  {etq}", "sub"), (us(v["usd"]), "sub"),
                          (str(v["n"]), "sub"), ""])
            for prov, monto in D.proveedores(agg, dep, cta, 4):
                filas.append(["      " + prov, us(monto), "", ("", "gris")])
        if filas:
            tabla(d, ["Cuenta · proveedor o concepto", "USD", "Asientos", ""],
                  filas, size=8)

    qs = nar.get("dept", {}).get(clave, {}).get("preguntas")
    if qs:
        h3(d, "Preguntas al gerente")
        for q in qs:
            bullet(d, q, size=9.5)
    elif clave:
        FALTANTES.append(f"dept.{clave}.preguntas")
        h3(d, "Preguntas al gerente")
        bullet(d, f"[PENDIENTE: dept.{clave}.preguntas]", size=9.5)
