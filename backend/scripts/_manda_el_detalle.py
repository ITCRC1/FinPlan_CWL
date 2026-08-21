# -*- coding: utf-8 -*-
"""SOLO LECTURA. Que pasa si para los historicos MANDA EL DETALLE.

No escribe NADA. Simula el cambio: computa el P&L anual de cada escenario por
los DOS caminos (Resumen `actual_pl_lines` y Detalle `actual_entries`), los
compara linea por linea, y **separa las dos causas del desacuerdo**:

  · PRESENTACION - el bucket (ingresos / gasto operativo / overhead / ...) da
    IGUAL en los dos, y la plata solo esta partida distinto. El Resumen que
    subio el owner viene pre-agregado mas grueso; el mayor lo abre. No es error.
  · DESALINEACION REAL - el bucket NO da igual: las dos hojas dicen cantidades
    distintas de plata. Aca si hay algo que corregir.

Ademas mide si el juego de lineas de los historicos es el MISMO que el de 2027
(comparabilidad linea por linea, que es el objetivo del owner).

    python -m scripts._manda_el_detalle              # informe a pantalla
    python -m scripts._manda_el_detalle salida.json  # + volcado JSON
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

TOL = Decimal("1")
Z = Decimal("0")

# Bucket = el total del reporte que agrupa esas lineas. Si el bucket cuadra, lo
# de adentro es corte/presentacion. Si no cuadra, es plata que no coincide.
BUCKETS = [
    ("INGRESOS",        ("REV_",),                          "TOTAL_REVENUES"),
    ("GASTO OPERATIVO", ("OPEX_", "COS_"),                  "TOTAL_OPERATING_EXPENSES"),
    ("OVERHEAD",        ("OH_", "COH_"),                    "TOTAL_OVERHEAD_EXPENSES"),
    ("NO OPERATIVO",    ("RENT", "MGMT_FEE_", "PROPERTY_INSURANCE", "OTHER_EXPENSES"),
                                                            "TOTAL_NON_OP_EXPENSES"),
    ("CAPITAL",         ("CAPITAL_RESERVE", "LARGE_CAPEX"), "CAPITAL_EXPENSE"),
    ("FINANCIEROS",     ("BANK_INTEREST", "LEASINGS_RENTS", "FINANCIAL_LOSSES"),
                                                            "FINANCIAL_EXPENSES"),
    ("DEPRECIACION",    ("DEPRECIATION", "ASSET_LOSS"),     "TOTAL_DEPRECIATIONS"),
    ("IMPUESTO",        ("INCOME_TAXES",),                  "INCOME_TAXES"),
]
DERIVADAS = ("PROFIT_", "OPERATING_PROFIT", "TOTAL_", "EBITDA_", "EBT",
             "NET_PROFIT", "SEC_", "KPI_")


def bucket_de(code):
    if any(code.startswith(p) or code == p for p in DERIVADAS):
        return None
    for nombre, prefijos, _tot in BUCKETS:
        if any(code.startswith(p) for p in prefijos):
            return nombre
    return None


# La FAMILIA es el negocio del que habla la linea, sin importar en que corte del
# reporte cae. `OPEX_FB`, `COS_FB_FOOD`, `COS_FB_BEV` y `COS_FB_MISC` son todos
# el gasto de A&B: si entre los cuatro la diferencia neta es cero, lo unico que
# paso es que el mayor abrio lo que el Resumen traia junto. Eso es PRESENTACION.
# Si la familia NO netea a cero, ahi si las dos hojas dicen plata distinta.
_FAM_PREF = ("REV_", "OPEX_", "COS_", "OH_", "COH_")
_FAM_ALIAS = {
    "FB_FOOD": "FB", "FB_BEV": "FB", "FB_MISC": "FB",
    "ROOMS_OTHER": "ROOMS",
    "CAPITAL_RESERVE": "CAPITAL", "LARGE_CAPEX": "CAPITAL",
    "MGMT_FEE_3": "MGMT_FEE", "MGMT_FEE_5_ROYALTIES": "MGMT_FEE",
}


def familia_de(code):
    """(bucket, familia) — el agrupador dentro del cual una reagrupacion netea."""
    b = bucket_de(code)
    if b is None:
        return None, None
    base = code
    for p in _FAM_PREF:
        if code.startswith(p):
            base = code[len(p):]
            break
    return b, _FAM_ALIAS.get(base, base)


def anual(lineas_por_mes):
    tot = defaultdict(Decimal)
    for mes in lineas_por_mes:
        for ln in mes:
            tot[ln.line_code] += ln.amount_usd
    return dict(tot)


async def main(salida):
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from app.models.actual_pl_line import ActualPLLine
    from app.models.department_catalog import DepartmentCatalog
    from app.engine import pl_engine, recalculate as recalc

    dump = {}
    juegos = {}

    async with SessionLocal() as db:
        cat = (await db.execute(select(DepartmentCatalog))).scalars().all()
        pl_engine.set_dept_catalog([{"dept_code": r.dept_code,
                                     "default_pl_group": r.default_pl_group,
                                     "parent_dept_code": r.parent_dept_code} for r in cat])

        mappings = await recalc.load_active_account_mappings(db)
        report_lines = await recalc.load_report_line_config(db)
        codigos_reporte = {r["line_code"] for r in report_lines
                           if r.get("line_type") != "KPI"
                           and not r["line_code"].startswith("SEC_")}
        plantilla_motor = {t.line_code for t in pl_engine.standard_pl_template()}
        canon = {k: v[0] for k, v in pl_engine._MOTOR_TO_CANON.items()}
        expresable = set(plantilla_motor)
        expresable |= {canon[c] for c in plantilla_motor if c in canon}
        for a, b in pl_engine._PL_ALIASES:
            if a in expresable or b in expresable:
                expresable |= {a, b}
        ciegas = sorted(codigos_reporte - expresable)

        escs = (await db.execute(select(Scenario))).scalars().all()
        con_resumen = {r[0] for r in (await db.execute(
            select(ActualPLLine.scenario_id).distinct())).all()}

        print("=" * 104)
        print("LINEAS QUE EL CAMINO RESUMEN NO PUEDE EXPRESAR (siempre 0, aunque el dato exista)")
        print("=" * 104)
        print("  %d de %d lineas del reporte:" % (len(ciegas), len(codigos_reporte)))
        for c in ciegas:
            print("    . " + c)

        resultados = {}
        for e in sorted(escs, key=lambda s: (s.year, s.type, s.version)):
            if e.id not in con_resumen:
                continue
            nombre = "%s %s %s" % (e.type, e.version, e.year)

            lineas_res, lineas_det = [], []
            codigos_subidos = defaultdict(Decimal)
            for m in range(1, 13):
                amounts = await recalc.actual_pl_lines_for_month(db, e.id, m)
                for k, v in amounts.items():
                    codigos_subidos[k] += Decimal(str(v or 0))
                ln = pl_engine.actual_pl_from_lines(amounts) if amounts else []
                lineas_res.append(pl_engine.canonicalize_pl_lines(
                    pl_engine.add_pl_aliases(ln)) if ln else [])

                filas = await recalc.actual_rows_for_month(db, e.id, m)
                ln2 = (pl_engine.calculate_pl_from_mapping(filas, mappings, report_lines)
                       if filas else [])
                lineas_det.append(pl_engine.canonicalize_pl_lines(
                    pl_engine.add_pl_aliases(ln2)) if ln2 else [])

            res, det = anual(lineas_res), anual(lineas_det)
            manda_det = await recalc._el_detalle_cuadra(db, e)

            tirados = {k: v for k, v in codigos_subidos.items()
                       if k not in plantilla_motor and abs(v) > Decimal("0.005")}

            info_buckets = []
            for bn, _pref, tot_code in BUCKETS:
                r, d = res.get(tot_code, Z), det.get(tot_code, Z)
                info_buckets.append({"bucket": bn, "total_code": tot_code,
                                     "resumen": float(r), "detalle": float(d),
                                     "dif": float(d - r), "cuadra": abs(d - r) <= TOL})
            bmal = set(b["bucket"] for b in info_buckets if not b["cuadra"])

            # ── El BUCKET es la autoridad. ────────────────────────────────
            # Si el total del bucket da igual, adentro solo hubo un corte
            # distinto: el Resumen trae el agregado y el mayor lo abre. Aunque
            # una familia parezca «rota» (p.ej. el Resumen 2025 guarda
            # TOTAL_NON_OP y deja RENT / PROPERTY_INSURANCE / OTHER en cero),
            # la plata no se movio del total que el owner valido.
            # La familia solo sirve para ATRIBUIR el descuadre DENTRO de un
            # bucket que ya se sabe roto.
            fam_dif = defaultdict(Decimal)
            for c in codigos_reporte:
                b, f = familia_de(c)
                if f is None:
                    continue
                fam_dif[(b, f)] += det.get(c, Z) - res.get(c, Z)
            fam_rotas = set(k for k, v in fam_dif.items()
                            if abs(v) > TOL and k[0] in bmal)

            filas_out = []
            for c in sorted(codigos_reporte):
                r, d = res.get(c, Z), det.get(c, Z)
                if abs(r) < Decimal("0.005") and abs(d) < Decimal("0.005"):
                    continue
                dif = d - r
                if abs(dif) <= Decimal("0.005"):
                    continue
                b, f = familia_de(c)
                if b is None:
                    causa = "DERIVADA (consecuencia)"
                elif (b, f) in fam_rotas:
                    causa = "DESALINEACION REAL"
                elif c in ciegas:
                    causa = "PRESENTACION (linea que el Resumen no tiene)"
                else:
                    causa = "PRESENTACION (misma familia, otro corte)"
                filas_out.append({"line_code": c, "resumen": float(r),
                                  "detalle": float(d), "dif": float(dif),
                                  "bucket": b or "-", "familia": f or "-",
                                  "causa": causa})

            fam_out = [{"bucket": k[0], "familia": k[1], "dif": float(v)}
                       for k, v in sorted(fam_dif.items(), key=lambda x: -abs(x[1]))
                       if k in fam_rotas]
            pres = sum(abs(f["dif"]) for f in filas_out if f["causa"].startswith("PRESENTACION"))
            # El numero honesto de «plata que las dos hojas cuentan distinto»
            # es la suma de los descuadres de BUCKET, no de linea.
            real = sum(abs(b["dif"]) for b in info_buckets if not b["cuadra"])

            resultados[nombre] = {
                "manda_hoy": "detalle" if manda_det else "resumen",
                "cambia_el_reporte": not manda_det,
                "neto_resumen": float(res.get("NET_PROFIT", Z)),
                "neto_detalle": float(det.get("NET_PROFIT", Z)),
                "gop_resumen": float(res.get("TOTAL_GOP", Z)),
                "gop_detalle": float(det.get("TOTAL_GOP", Z)),
                "buckets": info_buckets,
                "familias_que_no_netean": fam_out,
                "lineas": filas_out,
                "abs_presentacion": pres,
                "abs_real": real,
                "codigos_subidos_que_el_resumen_tira": {k: float(v) for k, v in tirados.items()},
                "n_lineas_resumen": len([c for c in codigos_reporte
                                         if abs(res.get(c, Z)) > Decimal("0.005")]),
                "n_lineas_detalle": len([c for c in codigos_reporte
                                         if abs(det.get(c, Z)) > Decimal("0.005")]),
            }
            dump[nombre] = {"resumen": {k: float(v) for k, v in res.items()},
                            "detalle": {k: float(v) for k, v in det.items()}}

        print()
        print("=" * 104)
        print("COMPARABILIDAD: juego de lineas que HOY produce cada escenario")
        print("=" * 104)
        for e in sorted(escs, key=lambda s: (s.year, s.type, s.version)):
            nombre = "%s %s %s" % (e.type, e.version, e.year)
            try:
                meses = [await recalc.compute_pl_month(db, e, m) for m in range(1, 13)]
                tot = anual(meses)
            except Exception as ex:                          # noqa: BLE001
                print("  !! %-28s %s %s" % (nombre, type(ex).__name__, str(ex)[:60]))
                continue
            vivas = set(c for c in codigos_reporte if abs(tot.get(c, Z)) > Decimal("0.005"))
            juegos[nombre] = vivas
            marca = ""
            if nombre in resultados and resultados[nombre]["cambia_el_reporte"]:
                marca = "   -> con DETALLE serian %d" % resultados[nombre]["n_lineas_detalle"]
            print("  %-28s %3d lineas con dato (de %d del reporte)%s"
                  % (nombre, len(vivas), len(codigos_reporte), marca))

        # ¿El juego de lineas de los historicos coincide con el de 2027?
        ref = None
        for k in sorted(juegos):
            if k.endswith("2027"):
                ref = ref | juegos[k] if ref else set(juegos[k])
        if ref:
            print()
            print("  -- contra el universo de lineas de los escenarios 2027 (%d lineas) --" % len(ref))
            for nombre, v in resultados.items():
                hoy = juegos.get(nombre, set())
                condet = set(c for c in codigos_reporte
                             if abs(Decimal(str(dump[nombre]["detalle"].get(c, 0)))) > Decimal("0.005"))
                print("  %-28s HOY: faltan %2d de 2027 / sobran %2d  |  "
                      "CON DETALLE: faltan %2d / sobran %2d"
                      % (nombre, len(ref - hoy), len(hoy - ref),
                         len(ref - condet), len(condet - ref)))
                if ref - condet:
                    print("       aun faltarian: " + ", ".join(sorted(ref - condet)))

        print()
        for k, v in resultados.items():
            print("=" * 104)
            print("%s   ·  manda hoy = %s   ·  %s"
                  % (k, v["manda_hoy"],
                     "EL REPORTE CAMBIA" if v["cambia_el_reporte"] else "sin cambio"))
            print("  NETO   resumen %15s   detalle %15s   dif %13s"
                  % ("{:,.2f}".format(v["neto_resumen"]),
                     "{:,.2f}".format(v["neto_detalle"]),
                     "{:,.2f}".format(v["neto_detalle"] - v["neto_resumen"])))
            print("  GOP    resumen %15s   detalle %15s   dif %13s"
                  % ("{:,.2f}".format(v["gop_resumen"]),
                     "{:,.2f}".format(v["gop_detalle"]),
                     "{:,.2f}".format(v["gop_detalle"] - v["gop_resumen"])))
            print("  lineas con dato: resumen %d  ->  detalle %d"
                  % (v["n_lineas_resumen"], v["n_lineas_detalle"]))
            print("  -- buckets --")
            for b in v["buckets"]:
                print("   %s%-17s resumen %14s  detalle %14s  dif %12s"
                      % ("OK " if b["cuadra"] else "!! ", b["bucket"],
                         "{:,.2f}".format(b["resumen"]), "{:,.2f}".format(b["detalle"]),
                         "{:,.2f}".format(b["dif"])))
            print("  -- QUIEN rompe cada bucket roto (familia que no netea) --")
            if not v["familias_que_no_netean"]:
                print("     nadie: TODO el movimiento es corte/presentacion")
            for f in v["familias_que_no_netean"]:
                print("     !! %-17s %-22s %14s"
                      % (f["bucket"], f["familia"], "{:,.2f}".format(f["dif"])))
            print("  -- movimiento de lineas por presentacion %s  |  DESALINEACION REAL (suma de buckets rotos) %s"
                  % ("{:,.2f}".format(v["abs_presentacion"]),
                     "{:,.2f}".format(v["abs_real"])))
            if v["codigos_subidos_que_el_resumen_tira"]:
                print("  !! codigos que el owner SUBIO en el Resumen y el camino Resumen DESCARTA:")
                for c, m in sorted(v["codigos_subidos_que_el_resumen_tira"].items(),
                                   key=lambda x: -abs(x[1])):
                    print("       %-28s %14s" % (c, "{:,.2f}".format(m)))
            print("  -- lineas que se mueven (top 30 por magnitud) --")
            for f in sorted(v["lineas"], key=lambda x: -abs(x["dif"]))[:30]:
                print("     %-26s %13s -> %13s  (%+13s)  %s"
                      % (f["line_code"], "{:,.2f}".format(f["resumen"]),
                         "{:,.2f}".format(f["detalle"]),
                         "{:,.2f}".format(f["dif"]), f["causa"]))
            print()

    if salida:
        pathlib.Path(salida).write_text(
            json.dumps({"escenarios": resultados,
                        "juegos_de_lineas": dict((k, sorted(v)) for k, v in juegos.items()),
                        "anuales": dump},
                       ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
        print("-> " + salida)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
