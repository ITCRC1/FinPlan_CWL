# -*- coding: utf-8 -*-
"""Arma el corte del mes: todo lo que el informe operativo necesita, en un dict.

Vive adentro del backend —y no en un script suelto— porque el boton del informe
corre EN EL SERVIDOR. Railway despliega solo `backend/`, asi que un generador
fuera de esa carpeta no existe para el servicio.

Toma la sesion que le den: la del request cuando lo llama el endpoint, o una
abierta contra produccion cuando lo llama el script de linea de comandos. Es
el mismo codigo en los dos caminos, a proposito — dos extracciones distintas
serian dos verdades para el mismo mes.

⚠️ **Los totales por clase NO se calculan aca.** Salen de
`gasto_por_clase_api._por_mes`, que es la misma funcion que alimenta la pantalla
*Month-End Close — P&L*, y se la llama **con el objeto escenario**: de eso
depende la regla de allocation. Sin el objeto el parametro queda en `None`, la
regla cae al caso general y los totales se van —medido: $10.943,00 en el costo
de setiembre 2026—.
"""
from __future__ import annotations

from sqlalchemy import text

MESES_COL = ["jan", "feb", "mar", "apr", "may", "jun",
             "jul", "aug", "sep", "oct", "nov", "dec"]

#: Los 17 conceptos de nomina. El rotulo NO se inventa aca: es el de
#: `payroll_catalog_importer.CONCEPTO_NOMBRES`.
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

TABLAS = [("revenue", "revenue_account_entries"),
          ("cost", "cost_entries"),
          ("opex", "opex_entries"),
          ("property", "belowgop_account_entries")]

#: Como se llama la version del FORECAST de cada mes, en los dos idiomas en que
#: el owner las nombra.
_PREFIJOS = {1: ("jan", "ene"), 2: ("feb",), 3: ("mar",), 4: ("apr", "abr"),
             5: ("may",), 6: ("jun",), 7: ("jul",), 8: ("aug", "ago"),
             9: ("sep", "set"), 10: ("oct",), 11: ("nov",), 12: ("dec", "dic")}


class FaltaDato(Exception):
    """Falta algo sin lo cual el informe no se puede armar."""


def _forecast_del_mes(filas, mes: int):
    fcst = [f for f in filas if f["type"] == "FORECAST"]
    for f in fcst:
        v = (f["version"] or "").strip().lower()
        if any(v.startswith(n) for n in _PREFIJOS[mes]):
            return f, True
    return (fcst[0] if fcst else None), False


async def extraer(db, anio: int, mes: int, hotel: str | None = None) -> dict:
    """El corte del mes. No escribe nada: solo lee.

    El hotel sale de `hotel_actual`, no de un literal: una instalacion
    es de una propiedad y el informe tiene que seguir a esa.
    """
    from app.hotel_actual import HOTEL_ID
    hotel = hotel or HOTEL_ID
    from app.api import gasto_por_clase_api as g
    from app.api.auditoria_gl_api import _puente_de_departamentos
    from app.engine import pl_engine, recalculate as recalc
    from app.importers.integrity_final import signo_de
    from app.models.scenario import Scenario

    if not 1 <= mes <= 12:
        raise FaltaDato("El mes tiene que estar entre 1 y 12.")
    col = MESES_COL[mes - 1]
    out: dict = {"hotel": hotel, "anio": anio, "mes": mes, "avisos": []}

    filas = (await db.execute(text("""
        SELECT id, type, version, COALESCE(es_precierre,false) AS pre, created_at
        FROM scenarios WHERE hotel_id=:h AND year=:a
        ORDER BY created_at DESC"""), {"h": hotel, "a": anio})).mappings().all()
    act = next((f for f in filas if f["pre"]), None)
    bud = next((f for f in filas if f["type"] == "BUDGET"), None)
    fct, exacto = _forecast_del_mes(filas, mes)
    if act is None:
        raise FaltaDato(
            f"No hay espejo de Pre-Cierre para {hotel} {anio}. Suba el Balance de "
            "Comprobacion antes de pedir el informe.")
    if bud is None:
        raise FaltaDato(f"No hay BUDGET para {hotel} {anio}.")
    if not exacto and fct is not None:
        out["avisos"].append(
            f"No existe un FORECAST cuya version nombre el mes {mes}; se uso "
            f"«{fct['version']}». Verificar que sea el correcto.")

    ESC = {"ACT": act["id"], "BUD": bud["id"]}
    if fct is not None:
        ESC["FCT"] = fct["id"]
    rot = {f["id"]: f"{f['type']} {f['version']}" for f in filas}
    out["escenarios"] = {k: {"id": v, "rotulo": rot[v]} for k, v in ESC.items()}

    # ── los totales y la apertura, de la fuente oficial ───────────────────
    out["meses"], out["detalle"], out["pl"] = {}, {}, {}
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

    out["deptos"] = {r.dept_code: r.dept_name for r in (await db.execute(text(
        "SELECT dept_code, dept_name FROM department_catalog"))).all()}

    # ── la apertura por cuenta de las cuatro clases ───────────────────────
    ytd_sql = " + ".join(f"COALESCE({m},0)" for m in MESES_COL[:mes])
    out["lineas"] = {}
    for clase, tabla in TABLAS:
        out["lineas"][clase] = []
        for k, sid in ESC.items():
            extra = ", detail_code, detail_desc" if tabla == "opex_entries" else ""
            for f in (await db.execute(text(f"""
                    SELECT dept_code, account_code, account_name{extra},
                           COALESCE({col},0) AS mes, ({ytd_sql}) AS ytd
                    FROM {tabla} WHERE scenario_id=:s"""),
                    {"s": sid})).mappings().all():
                d = dict(f)
                d["esc"] = k
                d["mes"] = float(d["mes"])
                d["ytd"] = float(d["ytd"])
                out["lineas"][clase].append(d)

    # ── planilla por departamento y concepto ──────────────────────────────
    out["payroll"] = {}
    sel = ", ".join(f"COALESCE(SUM({x[0]}),0) AS {x[0]}" for x in CONCEPTOS)
    for k, sid in ESC.items():
        for etq, filtro in (("mes", f"AND month={mes}"),
                            ("ytd", f"AND month BETWEEN 1 AND {mes}")):
            for f in (await db.execute(text(f"""
                    SELECT dept_code, {sel} FROM payroll_concept_entries
                    WHERE scenario_id=:s {filtro} GROUP BY dept_code"""),
                    {"s": sid})).mappings().all():
                out["payroll"].setdefault(k, {}).setdefault(etq, []).append(
                    {kk: (vv if kk == "dept_code" else float(vv))
                     for kk, vv in f.items()})

    # ── el mayor del mes: el grano del Audit Integral ─────────────────────
    puente = _puente_de_departamentos()
    out["mayor"] = []
    for f in (await db.execute(text("""
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
        d["fecha"] = str(d["fecha"] or "")
        out["mayor"].append(d)
    if not out["mayor"]:
        out["avisos"].append(
            f"El mayor de {anio}-{mes:02d} no esta subido: el informe sale sin "
            "proveedores ni asientos. Subalo en «Auditoria del mayor».")

    # ── estadistica de habitaciones ───────────────────────────────────────
    #
    # ⚠️ El espejo del Pre-Cierre NO la trae —por eso el encabezado de la
    # pantalla muestra «—» en ocupacion, ADR y RevPAR—. Sale del escenario
    # ACTUAL, que si la tiene. Mismo mes, misma propiedad, OTRA TABLA, y el
    # informe lo dice en la nota al pie.
    actual = next((f for f in filas if f["type"] == "ACTUAL" and not f["pre"]), None)
    out["stats"] = {"nota_actual": None, "ACT": []}
    if actual is not None:
        out["stats"]["ACT"] = [dict(r) for r in (await db.execute(text("""
            SELECT room_type_name, month, units, nights_available,
                   nights_occupied, revenue, pax
            FROM actual_room_stats WHERE scenario_id=:s AND month=:m
            ORDER BY room_type_name"""),
            {"s": actual["id"], "m": mes})).mappings().all()]
        out["stats"]["nota_actual"] = f"ACTUAL {actual['version']}"
    else:
        out["avisos"].append("No hay escenario ACTUAL con estadistica de "
                             "habitaciones: el informe sale sin ocupacion ni ADR.")
    for k in ("BUD", "FCT"):
        if k not in ESC:
            out["stats"][k] = None
            continue
        r = (await db.execute(text("""
            SELECT rooms_available, rooms_occupied, guests, occupancy_pct, adr
            FROM scenario_stats WHERE scenario_id=:s AND month=:m"""),
            {"s": ESC[k], "m": mes})).mappings().first()
        out["stats"][k] = {kk: float(vv) if vv is not None else None
                           for kk, vv in dict(r).items()} if r else None

    return out


# ── comparacion entre dos cortes del mismo mes ────────────────────────────
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


def comparar(ant: dict, nuevo: dict, mes: int) -> list:
    """Que se movio entre dos cortes del mismo mes.

    ⚠️ Esta es la lista de PARRAFOS A REPASAR. Si el mes se vuelve a subir, los
    cuadros se actualizan solos y las cifras escritas en el analisis NO. Un
    cuadro que dice una cosa y el parrafo de al lado que dice otra es peor que
    no tener informe.
    """
    fuera = []
    for esc in ("ACT", "BUD", "FCT"):
        if esc not in nuevo["meses"]:
            continue
        for clase in ("revenue", "cost", "payroll", "opex", "property"):
            a, b = _tot(ant, esc, clase, mes), _tot(nuevo, esc, clase, mes)
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
