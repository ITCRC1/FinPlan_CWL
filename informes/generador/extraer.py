# -*- coding: utf-8 -*-
"""Extrae de produccion todo lo que el informe operativo necesita. SOLO LECTURA.

    python informes/generador/extraer.py --anio 2026 --mes 10

Deja un unico JSON en `informes/generador/datos/AAAA_MM.json`. A partir de ahi
el informe se arma sin volver a tocar la base: si hay que corregir una tabla o
reescribir un comentario, no se vuelve a consultar produccion.

⚠️ **Los totales por clase NO se recalculan aca.** Salen de
`gasto_por_clase_api._por_mes`, que es la misma funcion que alimenta la pantalla
*Month-End Close — P&L*. Reimplementar esa suma es la forma mas facil de que el
informe diga un numero y la pantalla otro, y un informe que no coincide con la
pantalla no se puede discutir en una reunion.

⚠️ **Y hay que pasarle el `escenario`**, no solo su id. De eso depende la regla
de allocation: con el objeto, el espejo del Pre-Cierre muestra Cafeteria y
Lavanderia; sin el, el parametro queda en `None`, la regla cae al caso general y
los totales se van —medido: $10.943,00 en el costo de setiembre—.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

# La consola de Windows viene en cp1252 y los avisos llevan acentos y
# simbolos. Sin esto el script revienta al IMPRIMIR el aviso, que es el
# momento en que mas falta hace que se lea.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
os.environ.setdefault(
    "FINPLAN_PGVARS",
    str(pathlib.Path(os.environ.get("TEMP", "/tmp")) / "claude" / "pgvars.json"))

MESES_COL = ["jan", "feb", "mar", "apr", "may", "jun",
             "jul", "aug", "sep", "oct", "nov", "dec"]

#: Los 17 conceptos de nomina, con su codigo, su rotulo y su naturaleza.
#: El rotulo NO se inventa aca: es el de `payroll_catalog_importer`.
CONCEPTOS = [
    ("c6000_sw", "6000", "Salarios y jornales", "devengado"),
    ("c6001_overtime", "6001", "Horas extra", "devengado"),
    ("c6002_day_off", "6002", "Dia libre laborado", "devengado"),
    ("c6003_working_holiday", "6003", "Feriado trabajado", "devengado"),
    ("c6004_disabilities", "6004", "Incapacidades", "devengado"),
    ("c6010_commissions", "6010", "Comisiones", "devengado"),
    ("c6024_vacations_taken", "6024", "Vacaciones disfrutadas", "devengado"),
    ("c6027_incentive_bonus", "6027", "Bono de incentivo", "devengado"),
    ("c6020_ccss", "6020", "CCSS patronal 26,83%", "carga"),
    ("c6022_occ_hazard", "6022", "Riesgos del trabajo (INS)", "carga"),
    ("c6021_aguinaldo", "6021", "Aguinaldo (1/12)", "provision"),
    ("c6023_vacation_prov", "6023", "Provision de vacaciones", "provision"),
    ("c6026_severance", "6026", "Preaviso y cesantia", "provision"),
    ("c6025_cafeteria", "6025", "Cafeteria", "beneficio"),
    ("c6028_housing", "6028", "Vivienda", "beneficio"),
    ("c6029_transport", "6029", "Transporte", "beneficio"),
    ("c6030_other", "6030", "Otros beneficios", "beneficio"),
]

#: Las cuatro clases y de que tabla sale la apertura por cuenta de cada una.
TABLAS = [("revenue", "revenue_account_entries"),
          ("cost", "cost_entries"),
          ("opex", "opex_entries"),
          ("property", "belowgop_account_entries")]


async def elegir_escenarios(c, hotel: str, anio: int):
    """Los tres escenarios del informe, por su papel y no por su id.

    * ACT — el espejo del Pre-Cierre (`es_precierre`), que es el actual del mes.
    * BUD — el BUDGET del ano. Si hubiera mas de uno, el mas reciente.
    * FCT — el FORECAST cuya version nombra el mes del informe; si no existe,
      el FORECAST mas reciente del ano.
    """
    from sqlalchemy import text
    filas = (await c.execute(text("""
        SELECT id, type, version, COALESCE(es_precierre,false) AS pre, created_at
        FROM scenarios WHERE hotel_id=:h AND year=:a
        ORDER BY created_at DESC"""), {"h": hotel, "a": anio})).mappings().all()
    act = next((f for f in filas if f["pre"]), None)
    bud = next((f for f in filas if f["type"] == "BUDGET"), None)
    return filas, act, bud


def forecast_del_mes(filas, mes: int):
    """El FORECAST que corresponde al mes, por el nombre de su version.

    Las versiones se llaman «September», «Aug», «June»… asi que se busca por
    prefijo en espanol e ingles. Si ninguna coincide, se devuelve el mas
    reciente y el informe lo dice.
    """
    nombres = {
        1: ("jan", "ene"), 2: ("feb",), 3: ("mar",), 4: ("apr", "abr"),
        5: ("may",), 6: ("jun",), 7: ("jul",), 8: ("aug", "ago"),
        9: ("sep", "set"), 10: ("oct",), 11: ("nov",), 12: ("dec", "dic"),
    }[mes]
    fcst = [f for f in filas if f["type"] == "FORECAST"]
    for f in fcst:
        v = (f["version"] or "").strip().lower()
        if any(v.startswith(n) for n in nombres):
            return f, True
    return (fcst[0] if fcst else None), False


def _tot(d, esc, clase, mes):
    f = next((x for x in d["meses"].get(esc, []) if int(x["month"]) == mes), None)
    if f and clase in f:
        return float(f[clase])
    out = 0.0
    for ser in d["detalle"].get(esc, {}).get(clase, {}).values():
        if isinstance(ser, dict):
            out += float(ser.get(str(mes), ser.get(mes, 0)) or 0)
        else:
            out += float(ser[mes - 1] or 0)
    return out


def _por_cuenta(d):
    out = {}
    for clase, filas in d.get("lineas", {}).items():
        for x in filas:
            if x["esc"] != "ACT":
                continue
            k = (clase, x["dept_code"], x["account_code"])
            out[k] = out.get(k, 0.0) + float(x["mes"] or 0)
    return out


def _comparar(ant, nuevo, mes):
    """Que se movio entre dos extracciones del mismo mes.

    Se comparan los totales por escenario y clase, el mayor, los escenarios
    elegidos y las cuentas con mas de un dolar de diferencia. No se compara
    todo: la idea es que la lista quepa en la pantalla y diga QUE PARRAFOS del
    analisis hay que repasar.
    """
    fuera = []
    for esc in ("ACT", "BUD", "FCT"):
        if esc not in nuevo["meses"]:
            continue
        for clase in ("revenue", "cost", "payroll", "opex", "property"):
            a = _tot(ant, esc, clase, mes)
            b = _tot(nuevo, esc, clase, mes)
            if abs(a - b) > 0.01:
                fuera.append(f"{esc} {clase:9s} {a:>14,.2f} -> {b:>14,.2f}"
                             f"   ({b - a:+,.2f})")
    na, nb = len(ant.get("mayor", [])), len(nuevo.get("mayor", []))
    if na != nb:
        fuera.append(f"mayor: {na:,} lineas -> {nb:,} lineas")
    aa = (ant.get("mayor") or [{}])[0].get("archivo")
    ab = (nuevo.get("mayor") or [{}])[0].get("archivo")
    if aa != ab:
        fuera.append(f"archivo del mayor: <{aa}> -> <{ab}>")
    for k, v in nuevo["escenarios"].items():
        prev = ant.get("escenarios", {}).get(k, {})
        if prev.get("id") and prev["id"] != v["id"]:
            fuera.append(f"{k}: <{prev.get('rotulo')}> -> <{v['rotulo']}>")
    pa, pb = _por_cuenta(ant), _por_cuenta(nuevo)
    movidas = []
    for k in set(pa) | set(pb):
        va, vb = pa.get(k, 0.0), pb.get(k, 0.0)
        if abs(va - vb) > 1.0:
            movidas.append((abs(va - vb), k, va, vb))
    movidas.sort(reverse=True)
    for _, k, va, vb in movidas[:12]:
        fuera.append(f"  {k[0]:8s} {k[1]} - {k[2]}   {va:>12,.2f} -> {vb:>12,.2f}")
    if len(movidas) > 12:
        fuera.append(f"  ...y {len(movidas) - 12} cuentas mas")
    return fuera


async def main(anio: int, mes: int, hotel: str):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from scripts._prodenv import usar_produccion
    usar_produccion()

    from app.api import gasto_por_clase_api as g
    from app.api.auditoria_gl_api import _puente_de_departamentos
    from app.db import engine
    from app.engine import pl_engine, recalculate as recalc
    from app.importers.integrity_final import signo_de
    from app.models.scenario import Scenario

    idx = mes - 1
    col = MESES_COL[idx]
    out: dict = {"hotel": hotel, "anio": anio, "mes": mes, "escenarios": {},
                 "avisos": []}

    S = async_sessionmaker(engine, expire_on_commit=False)
    async with S() as db:
        c = db
        filas, act, bud = await elegir_escenarios(c, hotel, anio)
        fct, exacto = forecast_del_mes(filas, mes)
        if act is None:
            raise SystemExit(f"No hay espejo de Pre-Cierre para {hotel} {anio}. "
                             "Suba el Balance de Comprobacion antes de armar el informe.")
        if bud is None:
            raise SystemExit(f"No hay BUDGET para {hotel} {anio}.")
        if not exacto and fct is not None:
            out["avisos"].append(
                f"No existe un FORECAST cuya version nombre el mes {mes}; se uso "
                f"«{fct['version']}». Verificar que sea el correcto.")
        ESC = {"ACT": act["id"], "BUD": bud["id"]}
        if fct is not None:
            ESC["FCT"] = fct["id"]
        out["escenarios"] = {
            k: {"id": v,
                "rotulo": next(f"{f['type']} {f['version']}" for f in filas
                               if f["id"] == v)}
            for k, v in ESC.items()}
        print("escenarios:")
        for k, v in out["escenarios"].items():
            print(f"   {k}: {v['rotulo']}  ({v['id'][:12]})")

        # ── los totales y la apertura, de la fuente oficial ────────────────
        out["meses"] = {}
        out["detalle"] = {}
        out["pl"] = {}
        for k, sid in ESC.items():
            sc = await db.get(Scenario, sid)
            det: dict = {}
            out["meses"][k] = await g._por_mes(db, sid, detalle=det, escenario=sc)
            out["detalle"][k] = det
            pl = {}
            for etq, meses in (("mes", [mes]), ("ytd", list(range(1, mes + 1)))):
                acum: dict = {}
                for m in meses:
                    for L in await recalc.compute_pl_month(db, sc, m):
                        cod = (getattr(L, "line_code", None) if not isinstance(L, dict)
                               else L.get("line_code"))
                        val = float((getattr(L, "amount_usd", 0) if not isinstance(L, dict)
                                     else L.get("amount_usd")) or 0)
                        acum[cod] = acum.get(cod, 0.0) + val
                pl[etq] = acum
            out["pl"][k] = pl

        # ── el catalogo de departamentos ───────────────────────────────────
        out["deptos"] = {r.dept_code: r.dept_name for r in (await c.execute(text(
            "SELECT dept_code, dept_name FROM department_catalog"))).all()}

        # ── la apertura por cuenta de las cuatro clases ────────────────────
        ytd_sql = " + ".join(f"COALESCE({m},0)" for m in MESES_COL[:mes])
        out["lineas"] = {}
        for clase, tabla in TABLAS:
            out["lineas"][clase] = []
            for k, sid in ESC.items():
                extra = ", detail_code, detail_desc" if tabla == "opex_entries" else ""
                for f in (await c.execute(text(f"""
                        SELECT dept_code, account_code, account_name{extra},
                               COALESCE({col},0) AS mes, ({ytd_sql}) AS ytd
                        FROM {tabla} WHERE scenario_id=:s"""),
                        {"s": sid})).mappings().all():
                    d = dict(f)
                    d["esc"] = k
                    d["mes"] = float(d["mes"])
                    d["ytd"] = float(d["ytd"])
                    out["lineas"][clase].append(d)

        # ── planilla por departamento y concepto ───────────────────────────
        out["payroll"] = {}
        sel = ", ".join(f"COALESCE(SUM({x[0]}),0) AS {x[0]}" for x in CONCEPTOS)
        for k, sid in ESC.items():
            for etq, filtro in (("mes", f"AND month={mes}"),
                                ("ytd", f"AND month BETWEEN 1 AND {mes}")):
                for f in (await c.execute(text(f"""
                        SELECT dept_code, {sel} FROM payroll_concept_entries
                        WHERE scenario_id=:s {filtro} GROUP BY dept_code"""),
                        {"s": sid})).mappings().all():
                    out["payroll"].setdefault(k, {}).setdefault(etq, []).append(
                        {kk: (vv if kk == "dept_code" else float(vv))
                         for kk, vv in f.items()})

        # ── el mayor del mes: el grano del Audit Integral ──────────────────
        puente = _puente_de_departamentos()
        out["mayor"] = []
        for f in (await c.execute(text("""
                SELECT seg1, seg2, seg3, cuenta, descripcion, desc_asiento, asiento,
                       fecha, origen, debito, credito, tc, moneda, moneda_archivo,
                       archivo
                FROM mayor_movimientos
                WHERE hotel_id=:h AND anio=:a AND mes=:m"""),
                {"h": hotel, "a": anio, "m": mes})).mappings().all():
            d = dict(f)
            neto = float(d["debito"] or 0) - float(d["credito"] or 0)
            if (d["moneda_archivo"] or "COL").upper().startswith("COL"):
                neto = neto / float(d["tc"] or 1)
            d["usd"] = signo_de(d["seg1"]) * neto
            d["dept"] = pl_engine.consolidate_dept(puente.get(d["seg2"], d["seg2"]))
            for x in ("debito", "credito", "tc"):
                d[x] = float(d[x] or 0)
            out["mayor"].append(d)
        if not out["mayor"]:
            out["avisos"].append(
                f"El mayor de {anio}-{mes:02d} no esta subido: el informe no va a "
                "poder nombrar proveedores ni asientos. Subalo en «Auditoria del "
                "mayor» y vuelva a extraer.")

        # ── estadistica de habitaciones ────────────────────────────────────
        #
        # ⚠️ El espejo del Pre-Cierre NO la trae —por eso el encabezado de la
        # pantalla muestra «—» en ocupacion, ADR y RevPAR—. El actual sale del
        # escenario ACTUAL, que si la tiene. Es el mismo mes y la misma
        # propiedad, pero es OTRA TABLA, y el informe lo dice.
        actual = next((f for f in filas if f["type"] == "ACTUAL" and not f["pre"]), None)
        out["stats"] = {"nota_actual": None}
        if actual is not None:
            out["stats"]["ACT"] = [dict(r) for r in (await c.execute(text("""
                SELECT room_type_name, month, units, nights_available,
                       nights_occupied, revenue, pax
                FROM actual_room_stats WHERE scenario_id=:s AND month=:m
                ORDER BY room_type_name"""),
                {"s": actual["id"], "m": mes})).mappings().all()]
            out["stats"]["nota_actual"] = f"ACTUAL {actual['version']}"
        else:
            out["stats"]["ACT"] = []
            out["avisos"].append("No hay escenario ACTUAL con estadistica de "
                                 "habitaciones: el informe sale sin ocupacion ni ADR.")
        for k in ("BUD", "FCT"):
            if k not in ESC:
                out["stats"][k] = None
                continue
            r = (await c.execute(text("""
                SELECT rooms_available, rooms_occupied, guests, occupancy_pct, adr
                FROM scenario_stats WHERE scenario_id=:s AND month=:m"""),
                {"s": ESC[k], "m": mes})).mappings().first()
            out["stats"][k] = dict(r) if r else None

    await engine.dispose()

    # ── el cuadre obligatorio ─────────────────────────────────────────────
    print("\nCUADRE — estos doce numeros son los que tienen que coincidir con la pantalla")
    for k in out["meses"]:
        f = next(x for x in out["meses"][k] if int(x["month"]) == mes)
        print(f"   {k}: planilla {f['payroll']:>13,.2f}  costo {f['cost']:>12,.2f}  "
              f"opex {f['opex']:>13,.2f}  propiedad {f['property']:>13,.2f}")
    for a in out["avisos"]:
        print("\n⚠  " + a)

    destino = AQUI / "datos" / f"{anio}_{mes:02d}.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    # ⚠️ Lo mas importante que imprime el script. Si el owner vuelve a subir el
    # P&L del Pre-Cierre o el mayor y se vuelve a extraer, los CUADROS se
    # actualizan solos y el TEXTO del analisis NO: las cifras citadas en la
    # narrativa quedan como estaban. Un cuadro que dice una cosa y el parrafo de
    # al lado que dice otra es peor que no tener informe.
    #
    # Asi que antes de sobreescribir se compara, se dice que se movio, y la
    # version anterior se guarda al lado por si hay que mirarla.
    if destino.exists():
        try:
            ant = json.loads(destino.read_text(encoding="utf-8"))
        except Exception:
            ant = None
        if ant:
            cambios = _comparar(ant, out, mes)
            copia = destino.with_suffix(".anterior.json")
            copia.write_text(destino.read_text(encoding="utf-8"), encoding="utf-8")
            if cambios:
                print("\n" + "=" * 70)
                print("CAMBIO desde la extraccion anterior - REVISAR EL TEXTO")
                print("=" * 70)
                for c in cambios:
                    print("   " + c)
                print("\n   Los cuadros ya salen con los numeros nuevos. Las cifras")
                print(f"   escritas en narrativa/n{anio}_{mes:02d}.py NO se actualizan")
                print("   solas: hay que repasar los parrafos que mencionen lo de "
                      "arriba.")
                print(f"\n   La extraccion anterior quedo en {copia.name}")
            else:
                print("\nSin cambios contra la extraccion anterior: el informe sale "
                      "igual.")

    destino.write_text(json.dumps(out, ensure_ascii=False, default=str),
                       encoding="utf-8")
    print(f"\nguardado: {destino}")
    print(f"   {len(out['mayor'])} lineas de mayor · "
          f"{sum(len(v) for v in out['lineas'].values())} lineas de checkbook")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--anio", type=int, required=True)
    ap.add_argument("--mes", type=int, required=True)
    ap.add_argument("--hotel", default="CWL")
    a = ap.parse_args()
    asyncio.run(main(a.anio, a.mes, a.hotel))
