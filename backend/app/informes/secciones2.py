# -*- coding: utf-8 -*-
"""Secciones 4 a 12. Los cuadros son automaticos; el texto viene de la narrativa."""
from __future__ import annotations

from app.informes.datos import CONCEPTOS, OPERATIVOS, OVERHEAD
from app.informes.formato import (GRIS, bullet, h1, h2, h3, nota, par, pc, pct_var, tabla, us,
                     var, var_gasto)
from app.informes.secciones import FALTANTES, N, bloque, textos


def seccion4(d, D, agg, nar):
    h1(d, "Analisis por departamento operativo", 4)
    par(d, "El orden es el del P&L. Cada departamento se mide en sus cuatro planos "
           "—ingreso, costo de ventas, planilla y opex— contra Budget y contra "
           "Forecast, y se cierra con las preguntas que el mayor no puede responder.")

    h2(d, "4.0  Resumen: el resultado departamental de un vistazo")
    filas = []
    for nombre, ds in OPERATIVOS:
        A, Bu = D.cuatro(ds, "ACT"), D.cuatro(ds, "BUD")
        ga = A["cost"] + A["payroll"] + A["opex"]
        gb = Bu["cost"] + Bu["payroll"] + Bu["opex"]
        ra, rb = A["revenue"] - ga, Bu["revenue"] - gb
        if max(abs(A["revenue"]), abs(Bu["revenue"]), abs(ga), abs(gb)) < 0.005:
            continue
        filas.append([nombre, us(A["revenue"]), us(Bu["revenue"]), us(ga), us(gb),
                      us(ra), us(rb), var(ra, rb)])
    ia = sum(D.cuatro(ds, "ACT")["revenue"] for _, ds in OPERATIVOS)
    ib = sum(D.cuatro(ds, "BUD")["revenue"] for _, ds in OPERATIVOS)
    gta = sum(sum(D.cuatro(ds, "ACT")[c] for c in ("cost", "payroll", "opex"))
              for _, ds in OPERATIVOS)
    gtb = sum(sum(D.cuatro(ds, "BUD")[c] for c in ("cost", "payroll", "opex"))
              for _, ds in OPERATIVOS)
    filas.append([("TOTAL OPERATIVO", "tot"), (us(ia), "tot"), (us(ib), "tot"),
                  (us(gta), "tot"), (us(gtb), "tot"), (us(ia - gta), "tot"),
                  (us(ib - gtb), "tot"), (var(ia - gta, ib - gtb)[0], "tot")])
    tabla(d, ["Departamento", "Ing. act", "Ing. bud", "Gasto act", "Gasto bud",
              "Result. act", "Result. bud", "Var $"], filas,
          nota_pie="Gasto = costo de ventas + planilla + opex del departamento. "
                   "Cafeteria y Lavanderia aparecen con gasto y sin su credito de "
                   "reparto: ver la seccion 10.1.")
    textos(d, nar, "dept_resumen")

    for i, (nombre, ds) in enumerate(OPERATIVOS, 1):
        A, Bu = D.cuatro(ds, "ACT"), D.cuatro(ds, "BUD")
        if max(abs(v) for v in list(A.values()) + list(Bu.values())) < 0.005:
            continue
        con_ing = abs(A["revenue"]) > 0.005 or abs(Bu["revenue"]) > 0.005
        cods = " + ".join(sorted(ds))
        bloque(d, D, agg, nar, f"4.{i}  {nombre} ({cods})", nombre, ds,
               con_ingreso=con_ing)


def seccion5(d, D, agg, nar):
    h1(d, "Overhead: los departamentos sin ingreso", 5)
    par(d, "El overhead es, en un mes de baja ocupacion, el verdadero campo de "
           "batalla: es gasto que no tiene ingreso contra el cual compararse y que por "
           "definicion no deberia moverse con el volumen. Si sube cuando el negocio "
           "baja, sube por decision o por descontrol, no por actividad.")

    h2(d, "5.0  Resumen de overhead")
    filas = []
    ta = tb = 0.0
    for nombre, ds in OVERHEAD:
        A, Bu = D.cuatro(ds, "ACT"), D.cuatro(ds, "BUD")
        F = D.cuatro(ds, "FCT") if "FCT" in D.escs else None
        ga = A["cost"] + A["payroll"] + A["opex"]
        gb = Bu["cost"] + Bu["payroll"] + Bu["opex"]
        gf = (F["cost"] + F["payroll"] + F["opex"]) if F else None
        ta += ga
        tb += gb
        r = [nombre, us(A["payroll"]), us(A["opex"]), us(ga), us(gb),
             var_gasto(ga, gb), pct_var(ga, gb)]
        if F:
            r.append(us(gf))
        filas.append(r)
    r = [("TOTAL OVERHEAD", "tot"), "", "", (us(ta), "tot"), (us(tb), "tot"),
         (var_gasto(ta, tb)[0], "tot"), (pct_var(ta, tb), "tot")]
    if "FCT" in D.escs:
        r.append("")
    filas.append(r)
    cab = ["Departamento", "Planilla", "Opex", "Gasto act", "Gasto bud", "Var $",
           "Var %"] + (["Gasto fcst"] if "FCT" in D.escs else [])
    tabla(d, cab, filas)
    textos(d, nar, "overhead_resumen")

    for i, (nombre, ds) in enumerate(OVERHEAD, 1):
        A, Bu = D.cuatro(ds, "ACT"), D.cuatro(ds, "BUD")
        if max(abs(v) for v in list(A.values()) + list(Bu.values())) < 0.005:
            continue
        cods = " + ".join(sorted(ds))
        bloque(d, D, agg, nar, f"5.{i}  {nombre} ({cods})", nombre, ds,
               con_ingreso=False)


def seccion6(d, D, nar):
    h1(d, "Planilla: analisis transversal", 6)
    pay = D.total("ACT", "payroll")
    gas = D.tot_gasto("ACT")
    par(d, f"La planilla merece una seccion propia porque es el "
           f"{pc(pay/gas) if gas else '—'} del gasto operativo del mes y porque su "
           f"variacion —{us(pay - D.total('BUD','payroll'))}, "
           f"{pct_var(pay, D.total('BUD','payroll'))}— pesa sobre el resultado mas "
           f"que ninguna otra. Y sobre todo porque conviene mirar DONDE esta el "
           f"desvio: rara vez esta en el salario base.")

    h2(d, "6.1  Por concepto de nomina")
    pcs = D.payroll_concepto()
    orden = {"devengado": 0, "carga": 1, "provision": 2, "beneficio": 3}
    cab = ["Concepto", "Tipo", "Actual", "Budget", "Var $", "Var %"] + \
          (["Forecast"] if "FCT" in D.escs else [])
    filas = []
    for cod, v in sorted(pcs.items(),
                         key=lambda x: (orden.get(x[1]["tipo"], 9),
                                        -abs(x[1].get("ACT", 0) - x[1].get("BUD", 0)))):
        a, b = v.get("ACT", 0), v.get("BUD", 0)
        f = v.get("FCT", 0)
        if max(abs(a), abs(b), abs(f)) < 0.005:
            continue
        r = [f"{cod}  {v['nombre']}", v["tipo"], us(a), us(b), var_gasto(a, b),
             pct_var(a, b)]
        if "FCT" in D.escs:
            r.append(us(f))
        filas.append(r)
    ta = sum(v.get("ACT", 0) for v in pcs.values())
    tb = sum(v.get("BUD", 0) for v in pcs.values())
    tf = sum(v.get("FCT", 0) for v in pcs.values())
    r = [("TOTAL PLANILLA", "tot"), "", (us(ta), "tot"), (us(tb), "tot"),
         (var_gasto(ta, tb)[0], "tot"), (pct_var(ta, tb), "tot")]
    if "FCT" in D.escs:
        r.append((us(tf), "tot"))
    filas.append(r)
    tabla(d, cab, filas,
          nota_pie="Excluye Cafeteria (0220) y Lavanderia (0161) del Budget y del "
                   "Forecast por la regla de allocation; el Actual los incluye.")

    h2(d, "6.2  Los conceptos que explican el desvio")
    textos(d, nar, "payroll_conceptos")
    nt = nar.get("payroll_nota")
    if nt:
        nota(d, nt[0], nt[1])

    h2(d, "6.3  Por departamento")
    pd_ = D.payroll_depto()
    rev = D.det("ACT", "revenue")
    cab = ["Departamento", "Actual", "Budget", "Var $", "Var %"] + \
          (["Forecast"] if "FCT" in D.escs else []) + ["% s/ing."]
    filas = []
    for k in sorted(pd_, key=lambda x: -abs(pd_[x].get("ACT", 0) - pd_[x].get("BUD", 0))):
        v = pd_[k]
        a, b, f = v.get("ACT", 0), v.get("BUD", 0), v.get("FCT", 0)
        if max(abs(a), abs(b), abs(f)) < 0.005:
            continue
        rr = rev.get(k, 0)
        r = [D.nom(k)[:34], us(a), us(b), var_gasto(a, b), pct_var(a, b)]
        if "FCT" in D.escs:
            r.append(us(f))
        r.append(pc(a / rr) if abs(rr) > 0.005 else "—")
        filas.append(r)
    sa = sum(v.get("ACT", 0) for v in pd_.values())
    sb = sum(v.get("BUD", 0) for v in pd_.values())
    sf = sum(v.get("FCT", 0) for v in pd_.values())
    r = [("TOTAL", "tot"), (us(sa), "tot"), (us(sb), "tot"),
         (var_gasto(sa, sb)[0], "tot"), (pct_var(sa, sb), "tot")]
    if "FCT" in D.escs:
        r.append((us(sf), "tot"))
    r.append("")
    filas.append(r)
    tabla(d, cab, filas,
          nota_pie="«% s/ing.» es la planilla del departamento sobre su propio "
                   "ingreso. Se omite donde el departamento no factura.")

    h2(d, "6.4  Los conceptos sin presupuesto, por departamento")
    par(d, "Horas extra (6001), dia libre laborado (6002) y provision de vacaciones "
           "(6023) suelen tener presupuesto cero o simbolico. Mientras siga asi, toda "
           "variacion de planilla sale desfavorable todos los meses y la variacion "
           "deja de senalar algo.", size=9.5)
    filas = []
    for cod in ("6001", "6002", "6024", "6023"):
        por = D.concepto_por_depto(cod)
        if not por:
            continue
        nombre = next(c[2] for c in CONCEPTOS if c[1] == cod)
        bud = D.payroll_concepto()[cod].get("BUD", 0)
        filas.append([(f"{cod}  {nombre}", "sub"), (us(sum(por.values())), "sub"),
                      (us(bud), "sub"), ""])
        for dep, v in sorted(por.items(), key=lambda x: -abs(x[1]))[:6]:
            filas.append(["      " + D.nom(dep)[:32], us(v), "", ("", "gris")])
    if filas:
        tabla(d, ["Concepto · departamento", "Actual", "Budget", ""], filas, size=8)


def seccion7(d, D, nar):
    h1(d, "Costo de ventas y margenes", 7)
    par(d, "El costo de ventas es donde la variacion absoluta engana mas. Un "
           "departamento que vende la mitad y gasta un poco menos muestra variacion "
           "favorable de costo y margen destruido. Por eso este cuadro se lee en "
           "porcentaje antes que en dolares.")

    h2(d, "7.1  Margen por departamento")
    rv_a, rv_b = D.det("ACT", "revenue"), D.det("BUD", "revenue")
    cs_a, cs_b = D.det("ACT", "cost"), D.det("BUD", "cost")
    filas = []
    for k in sorted(set(rv_a) | set(rv_b) | set(cs_a) | set(cs_b)):
        ra, rb = rv_a.get(k, 0), rv_b.get(k, 0)
        ca, cb = cs_a.get(k, 0), cs_b.get(k, 0)
        if max(abs(ra), abs(rb), abs(ca), abs(cb)) < 0.005:
            continue
        ma = (ra - ca) / ra if abs(ra) > 0.005 else None
        mb = (rb - cb) / rb if abs(rb) > 0.005 else None
        delta = ((f"{(ma-mb)*100:+.1f} pp", "neg" if (ma - mb) < 0 else "pos")
                 if (ma is not None and mb is not None) else ("—", "gris"))
        filas.append([D.nom(k)[:32], us(ra), us(ca),
                      pc(ma) if ma is not None else "—", us(rb), us(cb),
                      pc(mb) if mb is not None else "—", delta])
    tabla(d, ["Departamento", "Ing. act", "Costo act", "Margen act", "Ing. bud",
              "Costo bud", "Margen bud", "Delta"], filas, size=8,
          nota_pie="Margen = (ingreso − costo de ventas) / ingreso. No incluye "
                   "planilla ni opex. Delta en puntos porcentuales.")
    textos(d, nar, "margenes")

    extra = nar.get("margen_detalle")
    if extra:
        h2(d, "7.2  " + extra["titulo"])
        par(d, extra.get("intro", ""), size=9.5)
        tabla(d, extra["cabeceras"], extra["filas"], nota_pie=extra.get("nota"))
        for p in extra.get("cierre", []):
            par(d, p, size=9.5)


def seccion8(d, D, nar):
    h1(d, "Opex: favorabilidades e impactos", 8)
    a, b = D.total("ACT", "opex"), D.total("BUD", "opex")
    par(d, f"El opex total fue ${us(a)} contra ${us(b)} presupuestados: "
           f"{pct_var(a, b)}. Ese neto, sin embargo, suele ser el resultado de "
           f"compensaciones grandes en los dos sentidos, y tratarlo como un solo "
           f"porcentaje de desvio haria perder de vista lo que de verdad paso.")

    h2(d, "8.1  Las veinte cuentas que mueven el opex")
    pcta = D.por_cuenta("opex")
    cab = ["Depto · cuenta", "Descripcion", "Actual", "Budget", "Var $"] + \
          (["Forecast"] if "FCT" in D.escs else [])
    filas = []
    for k, v in sorted(pcta.items(),
                       key=lambda x: -abs(x[1]["ACT"] - x[1]["BUD"]))[:20]:
        if max(abs(v["ACT"]), abs(v["BUD"]), abs(v.get("FCT", 0))) < 0.005:
            continue
        r = [f"{k[0]} · {k[1]}", v["nombre"][:30], us(v["ACT"]), us(v["BUD"]),
             var_gasto(v["ACT"], v["BUD"])]
        if "FCT" in D.escs:
            r.append(us(v.get("FCT", 0)))
        filas.append(r)
    tabla(d, cab, filas, size=8,
          nota_pie="Agrupado por departamento y cuenta — nunca por nombre: el real y "
                   "el presupuesto escriben la misma cuenta distinto, y agrupar por "
                   "nombre las separa en dos filas que no se ven como la misma cuenta.")

    for clave, titulo, intro in (
            ("opex_favorables", "8.2  Favorabilidades: cuanto es ahorro y cuanto es "
             "diferimiento", "La distincion es la unica que importa para proyectar "
             "el cierre del ano."),
            ("opex_impactos", "8.3  Impactos: el gasto que no estaba previsto", "")):
        bloq = nar.get(clave)
        h2(d, titulo)
        if intro:
            par(d, intro, size=9.5)
        if not bloq:
            FALTANTES.append(clave)
            par(d, f"[PENDIENTE: {clave}]", color=GRIS, italic=True)
            continue
        tabla(d, bloq["cabeceras"], bloq["filas"], nota_pie=bloq.get("nota"))
        for p in bloq.get("cierre", []):
            par(d, p, size=9.5)


def seccion9(d, D, nar):
    h1(d, "Gastos de propiedad (clase 8)", 9)
    a, b = D.total("ACT", "property"), D.total("BUD", "property")
    par(d, f"No afectan el GOP pero si el resultado final. En el mes fueron ${us(a)} "
           f"contra ${us(b)} presupuestados.")
    pcta = D.por_cuenta("property")
    cab = ["Cuenta", "Actual", "Budget", "Var $"] + \
          (["Forecast"] if "FCT" in D.escs else [])
    filas = []
    for k, v in sorted(pcta.items(), key=lambda x: -abs(x[1]["ACT"] - x[1]["BUD"])):
        if max(abs(v["ACT"]), abs(v["BUD"]), abs(v.get("FCT", 0))) < 0.005:
            continue
        r = [f"{k[1]}  {v['nombre'][:30]}", us(v["ACT"]), us(v["BUD"]),
             var_gasto(v["ACT"], v["BUD"])]
        if "FCT" in D.escs:
            r.append(us(v.get("FCT", 0)))
        filas.append(r)
    ta = sum(v["ACT"] for v in pcta.values())
    tb = sum(v["BUD"] for v in pcta.values())
    tf = sum(v.get("FCT", 0) for v in pcta.values())
    r = [("TOTAL", "tot"), (us(ta), "tot"), (us(tb), "tot"),
         (var_gasto(ta, tb)[0], "tot")]
    if "FCT" in D.escs:
        r.append((us(tf), "tot"))
    filas.append(r)
    tabla(d, cab, filas)
    for p in N(nar, "propiedad_notas", []):
        bullet(d, p, size=9.5)


def seccion10(d, D, nar):
    h1(d, "Hallazgos de clasificacion y de sistema", 10)
    par(d, "Esta seccion no es sobre gestion: es sobre registro. Son los casos en que "
           "la variacion que muestra el reporte no corresponde a lo que paso en la "
           "operacion, sino a donde quedo registrado el movimiento. Un controller "
           "tiene que separarlos antes de ir a preguntar, porque llevarle a un gerente "
           "una variacion que es un error de cuenta destruye la credibilidad del "
           "resto del informe.")

    cred = D.creditos_allocation()
    if cred:
        h2(d, "10.1  El credito de allocation no entra al reporte")
        par(d, "Es el hallazgo de sistema recurrente y explica el aviso amarillo de la "
               "pantalla. El tab incluye el GASTO de los departamentos de allocation "
               "—por decision expresa, para que la plata no se esconda durante la "
               "revision— y descarta el CREDITO de reparto, que vive en la cuenta 4999 "
               "y es lo que hace que esos departamentos neteen a cero. El GOP del "
               "reporte sale peor de lo que es.")
        filas = [[f"Credito 4999 {D.nom(k)}", us(v)] for k, v in sorted(cred.items())]
        suma = sum(cred.values())
        filas.append([("Credito descartado por el reporte", "tot"), (us(suma), "tot")])
        rep = D.gop("ACT")
        mot = D.pl("ACT", "GOP") or D.pl("ACT", "TOTAL_GOP")
        filas.append(["GOP del reporte", us(rep)])
        filas.append(["GOP del motor del P&L", us(mot)])
        filas.append([("Diferencia", "sec"), (us(rep - mot), "sec")])
        tabla(d, ["Concepto", D.mes_nombre.capitalize()], filas,
              nota_pie="La diferencia tiene que ser exactamente el credito descartado. "
                       "Si no lo es, hay otra causa y hay que buscarla antes de "
                       "publicar el informe.")
        nota(d, "Que significa para la lectura de este informe",
             f"El GOP real del mes, con el credito de reparto incluido, es "
             f"${us(mot)} y no ${us(rep)}. Todos los cuadros usan el numero del "
             f"reporte para que aten con la pantalla, pero la conversacion con la "
             f"gerencia general deberia hacerse sobre ${us(mot)}.")

    for clave, titulo in (("clasificacion", "10.2  Cuentas donde el presupuesto y el "
                           "real no aparean"),
                          ("sin_presupuesto", "10.3  Conceptos de nomina sin "
                           "presupuesto")):
        bloq = nar.get(clave)
        h2(d, titulo)
        if not bloq:
            FALTANTES.append(clave)
            par(d, f"[PENDIENTE: {clave}]", color=GRIS, italic=True)
            continue
        if bloq.get("intro"):
            par(d, bloq["intro"], size=9.5)
        tabla(d, bloq["cabeceras"], bloq["filas"], nota_pie=bloq.get("nota"), size=8)

    h2(d, "10.4  Brechas de informacion que impiden cerrar el analisis")
    for p in N(nar, "brechas", []):
        bullet(d, p, size=9.5)


def seccion11(d, D, nar):
    h1(d, "Agenda de reunion por responsable", 11)
    par(d, "Las preguntas de las secciones 4 y 5, reordenadas por la persona que las "
           "tiene que contestar. Cada bloque esta pensado como una reunion de 20 a 30 "
           "minutos con el detalle del mayor abierto en el Audit Integral.")
    ag = N(nar, "agenda", [])
    if not ag:
        par(d, "[PENDIENTE: agenda]", color=GRIS, italic=True)
        return
    for resp, foco, qs in ag:
        h3(d, f"{resp}  —  {foco}")
        for q in qs:
            bullet(d, q, size=9.5)


def seccion12(d, D, nar):
    h1(d, "Anexos", 12)
    for letra, titulo, clase, gasto in (
            ("A1", "Ingreso por cuenta", "revenue", False),
            ("A2", "Costo de ventas por cuenta", "cost", True),
            ("A3", "Opex por cuenta — completo", "opex", True)):
        h2(d, f"{letra}  {titulo}")
        pcta = D.por_cuenta(clase)
        cab = ["Depto · cuenta", "Descripcion", "Actual", "Budget", "Var $"] + \
              (["Forecast"] if "FCT" in D.escs else [])
        filas = []
        for k, v in sorted(pcta.items(), key=lambda x: (x[0][0], x[0][1])):
            if max(abs(v["ACT"]), abs(v["BUD"]), abs(v.get("FCT", 0))) < 0.005:
                continue
            r = [f"{k[0]} · {k[1]}", v["nombre"][:32], us(v["ACT"]), us(v["BUD"]),
                 var_gasto(v["ACT"], v["BUD"]) if gasto else var(v["ACT"], v["BUD"])]
            if "FCT" in D.escs:
                r.append(us(v.get("FCT", 0)))
            filas.append(r)
        ta = sum(v["ACT"] for v in pcta.values())
        tb = sum(v["BUD"] for v in pcta.values())
        tf = sum(v.get("FCT", 0) for v in pcta.values())
        r = [("TOTAL", "tot"), "", (us(ta), "tot"), (us(tb), "tot"),
             ((var_gasto if gasto else var)(ta, tb)[0], "tot")]
        if "FCT" in D.escs:
            r.append((us(tf), "tot"))
        filas.append(r)
        pie = None
        if clase == "opex":
            cred = sum(D.creditos_allocation().values())
            if abs(cred) > 0.005:
                pie = (f"El total de esta tabla (${us(ta)}) es el de los checkbooks del "
                       f"Pre-Cierre e incluye los creditos 4999; el total del reporte "
                       f"(${us(D.total('ACT','opex'))}) los descarta. La diferencia son "
                       f"los ${us(abs(cred))} de la seccion 10.1.")
        tabla(d, cab, filas, size=7.5, nota_pie=pie)

    h2(d, "A4  Planilla por departamento y concepto — Actual")
    cols = ["6000", "6001", "6002", "6010", "6020", "6021", "6023", "6024", "6025"]
    filas = []
    for f in sorted(D.d["payroll"].get("ACT", {}).get("mes", []),
                    key=lambda x: x["dept_code"]):
        vals = []
        for cod in cols:
            col = next(c[0] for c in CONCEPTOS if c[1] == cod)
            vals.append(us(f.get(col, 0)))
        tot = sum(f.get(c[0], 0) for c in CONCEPTOS)
        filas.append([D.nom(f["dept_code"])[:26]] + vals + [(us(tot), "sub")])
    if filas:
        tabla(d, ["Departamento"] + cols + ["Total"], filas, size=7,
              nota_pie="6000 salarios · 6001 horas extra · 6002 dia libre · 6010 "
                       "comisiones · 6020 CCSS · 6021 aguinaldo · 6023 provision vac. "
                       "· 6024 vac. disfrutadas · 6025 cafeteria.")

    h2(d, "A5  Nota metodologica")
    par(d, "Los totales por clase provienen de la funcion que alimenta la pantalla "
           "Month-End Close — P&L del sistema, invocada con el escenario explicito "
           "para que se aplique su regla de allocation. Se verifico que los totales "
           "del mes coinciden al centavo con la pantalla.", size=9)
    par(d, "La apertura por departamento y por cuenta proviene de los checkbooks "
           "(revenue_account_entries, cost_entries, opex_entries, "
           "belowgop_account_entries) y de payroll_concept_entries. El detalle de "
           f"asiento, proveedor y concepto proviene del mayor guardado "
           f"—{len(D.d['mayor']):,} lineas del archivo «{D.archivo_mayor or '—'}»— con "
           "el puente de departamentos de Integrity a FinPlan y la consolidacion del "
           "motor del P&L aplicados, que es el mismo camino que usa el Audit Integral.",
        size=9)
    par(d, "La estadistica de habitaciones proviene de actual_room_stats del escenario "
           f"{D.d['stats'].get('nota_actual') or '—'}, porque el espejo del Pre-Cierre "
           "no la carga. Los nombres de cuenta provienen del catalogo de mapeo "
           "(account_mapping).", size=9)
    par(d, "Todas las cifras estan en dolares de los Estados Unidos. El archivo del "
           "mayor venia en colones y la conversion se hizo con el tipo de cambio de "
           "cada asiento, no con un promedio del mes.", size=9)
