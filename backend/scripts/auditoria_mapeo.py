# -*- coding: utf-8 -*-
"""Auditoria COMPLETA del mapeo de cuentas: estructura + ruteo con plata detras.

## Por que existe

`foto_lineas` dice SI algo se movio; no dice POR QUE ni deja ver un borde suelto
que todavia no movio plata pero la va a mover el dia que alguien cargue un dato.
Este script mira el mapeo en si mismo:

  ESTRUCTURA (offline, del JSON — no necesita base)
    1. reglas huerfanas: `report_line_code` que no existe en `report_line_config`
    2. lineas del reporte sin ninguna regla activa que las alimente
    3. pares (dept_code, account_code) con MAS DE UNA regla activa — ahi la
       linea la decide el orden fisico de las filas, no una decision
    4. `source_department` (texto) contra `dept_code`: dos nombres para el mismo
       codigo, o un nombre compartido por dos codigos
    5. campos denormalizados (`report_line_name`, `report_section`,
       `display_order`) contra `report_line_config`
    6. departamentos HIJOS con reglas de gasto (clase 5 o 7) — el gasto es del
       padre (owner, 2026-08-14)
    7. la `4999` de cada departamento cayendo en SU PROPIA linea

  ARCHIVO vs BASE (necesita la base)
    8. filas en `account_mapping` que NO estan en el JSON. El seed NO borra lo
       que sobra, asi que una fila vieja sobrevive para siempre y puede
       duplicar la llave de negocio.
    9. diferencias campo por campo entre el JSON y la base.

  RUTEO (necesita la base)
   10. cada fila con plata de CADA escenario, en TODAS las tablas fuente,
       resuelta contra el mapeo. Lo que cae por FALLBACK o DROP se reporta con
       su monto: FALLBACK = la plata aterriza en la linea de OTRO departamento;
       DROP = no llega al P&L.
   11. `nonop_entries` no pasa por el mapeo — siembra la linea directo. Si su
       `report_line_code` no existe en el reporte, el monto se pierde sin aviso.

Uso:
    python -m scripts.auditoria_mapeo              # todo (lee PRODUCCION)
    python -m scripts.auditoria_mapeo --estructura # solo lo offline, sin base

Salida a stderr/stdout legible; codigo 1 si hay hallazgos que muevan plata.
"""
from __future__ import annotations

import asyncio
import collections
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ARCHIVO = pathlib.Path(__file__).resolve().parents[1] / "app" / "seed_data" / "mapping_pl.json"

# Columnas de `account_mapping` que el JSON define. `id` es por instalacion.
CAMPOS_MAPEO = (
    "active_status", "report_id", "report_line_code", "report_line_name",
    "report_section", "display_order", "source_origin", "source_department",
    "account_code", "account_name_example", "financial_nature",
    "rollup_operator", "sign_rule", "notes", "dept_code",
)


def _titulo(n: int, texto: str) -> None:
    print(f"\n{'─' * 78}\n{n}. {texto}\n{'─' * 78}")


# ─────────────────────────────────────────────────────────────────────────────
# ESTRUCTURA — todo esto sale del JSON, sin tocar la base.
# ─────────────────────────────────────────────────────────────────────────────
def auditar_estructura(datos: dict) -> list[str]:
    """Devuelve la lista de hallazgos (vacia = limpio). Imprime el detalle."""
    from app.engine import pl_engine
    from app.seed_department_catalog import build_rows

    am = datos["account_mapping"]
    rl = datos["report_line_config"]
    lineas = {r["line_code"]: r for r in rl}
    activas = [m for m in am if m.get("active_status") == "YES"]
    hallazgos: list[str] = []

    _titulo(1, "Reglas huerfanas (report_line_code que no existe en el reporte)")
    orf = collections.Counter(m["report_line_code"] for m in am
                              if m["report_line_code"] not in lineas)
    if orf:
        for k, v in orf.most_common():
            print(f"  !! {k}: {v} reglas apuntan a una linea inexistente")
        hallazgos.append(f"{sum(orf.values())} reglas huerfanas")
    else:
        print(f"  OK — las {len(am)} reglas apuntan a lineas que existen")

    _titulo(2, "Lineas del reporte sin ninguna regla activa que las alimente")
    usadas = collections.Counter(m["report_line_code"] for m in activas)
    huecas = [r for r in rl
              if r["line_type"].startswith("MAPPED") and not usadas.get(r["line_code"])]
    for r in huecas:
        print(f"  ·  {r['line_code']:<26} {r['line_name']}")
    print(f"  {len(huecas)} lineas MAPPED sin regla — vacias, no rotas: no pierden plata,"
          f"\n  pero nada que se cargue puede aterrizar ahi.")

    _titulo(3, "Pares (dept_code, account_code) con MAS DE UNA regla activa")
    biz = collections.defaultdict(list)
    for m in activas:
        biz[((m.get("dept_code") or "").strip(), m["account_code"].strip())].append(m)
    dups = {k: v for k, v in biz.items() if len(v) > 1}
    for (dc, ac), v in sorted(dups.items()):
        destinos = sorted({x["report_line_code"] for x in v})
        print(f"  !! ({dc or '(sin dept)'}, {ac}): {len(v)} reglas → {destinos}")
        for x in v:
            print(f"       origin={x['source_origin']!r} src_dept={x['source_department']!r}")
        hallazgos.append(f"llave de negocio duplicada ({dc}, {ac})")
    if not dups:
        print("  OK — la llave de negocio (departamento, cuenta) es unica:"
              "\n  ninguna cuenta tiene dos lineas posibles.")

    _titulo(4, "source_department (texto) contra dept_code")
    por_codigo = collections.defaultdict(set)
    por_nombre = collections.defaultdict(set)
    for m in am:
        dc = (m.get("dept_code") or "").strip()
        sd = (m.get("source_department") or "").strip()
        por_codigo[dc].add(sd)
        por_nombre[sd].add(dc)
    for k, v in sorted(por_codigo.items()):
        if len(v) > 1:
            print(f"  ·  el {k} lleva {len(v)} nombres: {sorted(v)}")
    compartidos = {k: v for k, v in por_nombre.items() if len(v) > 1}
    for k, v in sorted(compartidos.items()):
        print(f"  !! el nombre {k!r} lo comparten {sorted(v)} — dos departamentos, un nombre")
        hallazgos.append(f"source_department {k!r} compartido por {sorted(v)}")
    if not compartidos:
        print("  OK — ningun nombre de departamento apunta a dos codigos.")

    _titulo(5, "Campos denormalizados contra report_line_config")
    problemas = []
    for code, filas in sorted(collections.defaultdict(
            list, {k: [m for m in am if m["report_line_code"] == k]
                   for k in {x["report_line_code"] for x in am}}).items()):
        if code not in lineas:
            continue
        for campo, campo_rl in (("report_line_name", "line_name"),
                                ("report_section", "section"),
                                ("display_order", "display_order")):
            vals = {m[campo] for m in filas}
            if len(vals) > 1:
                problemas.append((code, campo, "INCONSISTENTE entre reglas", sorted(map(str, vals))))
            elif next(iter(vals)) != lineas[code][campo_rl]:
                problemas.append((code, campo, "difiere del reporte",
                                  [str(next(iter(vals))), str(lineas[code][campo_rl])]))
    for code, campo, que, vals in problemas:
        print(f"  !! {code:<26} {campo:<18} {que}: {vals}")
    if problemas:
        hallazgos.append(f"{len(problemas)} campos denormalizados fuera de sincronia")
    else:
        print("  OK — nombre, seccion y orden coinciden con report_line_config.")

    _titulo(6, "Departamentos HIJOS con reglas de gasto (clase 5 o 7)")
    catalogo = {r["dept_code"]: r for r in build_rows()}
    hijos = {c for c, r in catalogo.items() if (r.get("parent_dept_code") or "").strip()}
    con_gasto = collections.defaultdict(list)
    for m in activas:
        dc = (m.get("dept_code") or "").strip()
        if dc in hijos and m["account_code"][:1] in ("5", "7"):
            con_gasto[dc].append(m["account_code"])
    for dc, cuentas in sorted(con_gasto.items()):
        print(f"  !! el {dc} ({catalogo[dc]['dept_name']}) es hijo de "
              f"{catalogo[dc]['parent_dept_code']} y lleva {len(cuentas)} reglas de gasto")
        hallazgos.append(f"hijo {dc} con {len(cuentas)} reglas de gasto")
    if not con_gasto:
        print(f"  OK — ninguno de los {len(hijos)} departamentos hijos lleva gasto propio:"
              "\n  el gasto es del padre y los hijos lo heredan por la cadena.")

    _titulo(7, "La 4999 de cada departamento cae en SU PROPIA linea")
    pl_engine.set_dept_catalog(build_rows())
    resolve = pl_engine.construir_resolvedor(activas)
    # La linea propia de un departamento = la que usan sus reglas de gasto.
    propias = collections.defaultdict(collections.Counter)
    for m in activas:
        dc = (m.get("dept_code") or "").strip()
        if dc and m["account_code"][:1] in ("5", "6", "7"):
            propias[dc][m["report_line_code"]] += 1
    malos = 0
    for dc in sorted(propias):
        regla, modo = resolve(dc, "4999")
        destino = regla["report_line_code"] if regla else "(DROP)"
        esperadas = set(propias[dc])
        if destino not in esperadas:
            print(f"  !! el {dc}: 4999 → {destino} ({modo}), pero su gasto va a {sorted(esperadas)}")
            malos += 1
    if malos:
        hallazgos.append(f"{malos} departamentos con la 4999 fuera de su linea")
    else:
        print(f"  OK — los {len(propias)} departamentos con gasto anulan su credito de"
              "\n  reparto sobre su propia linea. No le restan a otro.")

    return hallazgos


# ─────────────────────────────────────────────────────────────────────────────
# ARCHIVO vs BASE
# ─────────────────────────────────────────────────────────────────────────────
async def auditar_archivo_contra_base(db, datos: dict) -> list[str]:
    from sqlalchemy import select
    from app.models.mapping import AccountMapping, ReportLineConfig

    hallazgos: list[str] = []
    am = datos["account_mapping"]
    rl = datos["report_line_config"]

    _titulo(8, "Filas en la BASE que no estan en el archivo (el seed no las borra)")
    del_archivo = {(m["report_id"], m["source_department"], m["account_code"], m["source_origin"])
                   for m in am}
    filas = (await db.execute(select(AccountMapping))).scalars().all()
    sobran = [f for f in filas
              if (f.report_id, f.source_department, f.account_code, f.source_origin)
              not in del_archivo]
    for f in sorted(sobran, key=lambda x: (x.dept_code or "", x.account_code)):
        print(f"  !! dept={f.dept_code!r} cuenta={f.account_code} → {f.report_line_code}"
              f"  activa={f.active_status}  src={f.source_department!r} origin={f.source_origin!r}")
    if sobran:
        hallazgos.append(f"{len(sobran)} filas huerfanas en account_mapping")
    else:
        print(f"  OK — las {len(filas)} filas de la base estan todas nombradas en el archivo.")

    lineas_archivo = {(r["report_id"], r["line_code"]) for r in rl}
    sobran_l = [f for f in (await db.execute(select(ReportLineConfig))).scalars().all()
                if (f.report_id, f.line_code) not in lineas_archivo]
    for f in sobran_l:
        print(f"  !! linea {f.line_code} en la base y no en el archivo")
    if sobran_l:
        hallazgos.append(f"{len(sobran_l)} lineas huerfanas en report_line_config")

    _titulo(9, "Diferencias campo por campo, archivo contra base")
    por_llave = {(f.report_id, f.source_department, f.account_code, f.source_origin): f
                 for f in filas}
    difs = 0
    for m in am:
        f = por_llave.get((m["report_id"], m["source_department"],
                           m["account_code"], m["source_origin"]))
        if f is None:
            print(f"  !! FALTA en la base: dept={m.get('dept_code')} cuenta={m['account_code']}")
            difs += 1
            continue
        for c in CAMPOS_MAPEO:
            if getattr(f, c) != m[c]:
                print(f"  !! dept={m.get('dept_code')} cuenta={m['account_code']} campo={c}:"
                      f" base={getattr(f, c)!r} archivo={m[c]!r}")
                difs += 1
    if difs:
        hallazgos.append(f"{difs} diferencias archivo/base (el seed no llego a correr o fallo)")
    else:
        print("  OK — la base dice exactamente lo que dice el archivo.")
    return hallazgos


# ─────────────────────────────────────────────────────────────────────────────
# RUTEO — la plata de verdad, escenario por escenario.
# ─────────────────────────────────────────────────────────────────────────────
async def auditar_ruteo(db) -> list[str]:
    from sqlalchemy import select
    from app.engine import pl_engine
    from app.engine.recalculate import (
        load_active_account_mappings, load_report_line_config, PAYROLL_ALL_COLS)
    from app.models.scenario import Scenario
    from app.models.opex_entry import OpexEntry
    from app.models.cost_entry import CostEntry
    from app.models.actual_entry import ActualEntry
    from app.models.allocation_entry import AllocationEntry
    from app.models.revenue_account_entry import RevenueAccountEntry
    from app.models.belowgop_account_entry import BelowGopAccountEntry
    from app.models.nonop_entry import NonOpEntry
    from app.models.payroll_concept_entry import PayrollConceptEntry

    M = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]
    hallazgos: list[str] = []
    mapeos = await load_active_account_mappings(db)
    resolve = pl_engine.construir_resolvedor(mapeos)
    cd = pl_engine.consolidate_dept
    lineas = {r["line_code"] for r in await load_report_line_config(db)}
    escenarios = (await db.execute(select(Scenario))).scalars().all()
    nombre = {e.id: f"{e.type} {e.version} {e.year}" for e in escenarios}

    _titulo(10, "Ruteo por descarte (FALLBACK) y plata que no llega (DROP)")
    # (modo, dept, cuenta) → [monto, {escenarios}, {tablas}]
    acum: dict[tuple, list] = collections.defaultdict(
        lambda: [0.0, set(), set()])

    def anotar(dept, cuenta, monto, tabla, esc):
        if not monto:
            return
        regla, modo = resolve(dept, cuenta)
        if modo in ("exact", "parent", "dept-agnostic"):
            return
        k = (modo, dept, cuenta, regla["report_line_code"] if regla else "")
        acum[k][0] += monto
        acum[k][1].add(nombre.get(esc, esc))
        acum[k][2].add(tabla)

    anuales = ((OpexEntry, "opex_entries", True), (CostEntry, "cost_entries", True),
               (ActualEntry, "actual_entries", False),
               (RevenueAccountEntry, "revenue_account_entries", False),
               (BelowGopAccountEntry, "belowgop_account_entries", False))
    for Model, tabla, consolidar in anuales:
        for e in (await db.execute(select(Model))).scalars().all():
            monto = float(sum(getattr(e, m) or 0 for m in M))
            dept = cd(e.dept_code or "") if consolidar else (e.dept_code or "")
            anotar(dept, e.account_code or "", monto, tabla, e.scenario_id)

    for e in (await db.execute(select(PayrollConceptEntry))).scalars().all():
        for col in PAYROLL_ALL_COLS:
            anotar(cd(e.dept_code or ""), pl_engine.payroll_account_for_column(col),
                   float(getattr(e, col, None) or 0), "payroll_concept_entries", e.scenario_id)

    for e in (await db.execute(select(AllocationEntry))).scalars().all():
        anotar(cd(e.target_dept or ""), e.account or "", float(e.amount_usd or 0),
               "allocation_entries", e.scenario_id)

    total_fb = total_drop = 0.0
    for (modo, dept, cuenta, destino), (monto, escs, tablas) in sorted(
            acum.items(), key=lambda kv: -abs(kv[1][0])):
        marca = "FALLBACK" if modo == "FALLBACK" else "DROP"
        if modo == "FALLBACK":
            total_fb += monto
        else:
            total_drop += monto
        print(f"  {marca:<9} dept={dept or '(vacio)':<7} cuenta={cuenta:<6}"
              f" {monto:>15,.2f}  → {destino or 'NO LLEGA AL P&L'}")
        print(f"            {len(escs)} escenario(s) · {sorted(tablas)}")
    print(f"\n  FALLBACK: {total_fb:,.2f}   DROP: {total_drop:,.2f}")
    if acum:
        hallazgos.append(f"ruteo: FALLBACK {total_fb:,.2f} / DROP {total_drop:,.2f}")

    _titulo(11, "nonop_entries: el report_line_code va directo, sin pasar por el mapeo")
    perdidos: dict[str, float] = collections.defaultdict(float)
    for e in (await db.execute(select(NonOpEntry))).scalars().all():
        if e.report_line_code not in lineas:
            perdidos[e.report_line_code or "(vacio)"] += float(
                sum(getattr(e, m) or 0 for m in M))
    for k, v in sorted(perdidos.items(), key=lambda kv: -abs(kv[1])):
        print(f"  !! {k}: {v:,.2f} apunta a una linea que no existe — se pierde sin aviso")
    if perdidos:
        hallazgos.append(f"{len(perdidos)} lineas below-GOP inexistentes")
    else:
        print("  OK — todo gasto del propietario apunta a una linea que existe.")
    return hallazgos


async def main(solo_estructura: bool) -> int:
    datos = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    print(f"Auditoria del mapeo · {len(datos['account_mapping'])} reglas ·"
          f" {len(datos['report_line_config'])} lineas del reporte")
    hallazgos = auditar_estructura(datos)
    if not solo_estructura:
        from app.db import SessionLocal
        async with SessionLocal() as db:
            hallazgos += await auditar_archivo_contra_base(db, datos)
            hallazgos += await auditar_ruteo(db)
    print(f"\n{'═' * 78}")
    if hallazgos:
        print("HALLAZGOS:")
        for h in hallazgos:
            print(f"  · {h}")
    else:
        print("Sin hallazgos.")
    return 1 if hallazgos else 0


if __name__ == "__main__":
    _solo_estructura = "--estructura" in sys.argv
    # ANTES de importar cualquier `app.*`: `app.db` arma el engine al importarse,
    # asi que apuntarlo despues lo deja hablando con localhost.
    if not _solo_estructura:
        from scripts._prodenv import usar_produccion
        usar_produccion()
    raise SystemExit(asyncio.run(main(_solo_estructura)))
