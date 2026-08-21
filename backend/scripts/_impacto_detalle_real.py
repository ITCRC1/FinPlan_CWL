# -*- coding: utf-8 -*-
"""SOLO LECTURA. El impacto VERDADERO de que mande el Detalle, respetando el corte.

## Por que este script y no `_manda_el_detalle`

`_manda_el_detalle` compara el Resumen contra el Detalle sobre los DOCE meses del
escenario. Para un ACTUAL eso esta bien. Para un FORECAST con `actuals_through`
NO: los meses cerrados del reporte **no salen de ese escenario**, salen del
ACTUAL enlazado (`_compute_pl_month_core` los delega). Comparar los doce mide
meses que el reporte ya ignora.

Medido contra produccion el 2026-08-16, esa diferencia lo es TODO:

    · FORECAST Working 2026, comparando los 12 meses -> 68 lineas descuadran y
      el ingreso difiere en +24.997,15.
    · El mismo escenario, respetando `actuals_through=6` -> el ingreso, el GOP,
      el EBITDA, el EBT y el NETO dan IDENTICO. Todo el descuadre vivia en MAYO,
      un mes cerrado que el reporte ya toma del Actual 2026.

O sea: el numero que hacia parecer «desalineado» al Working 2026 no estaba
llegando al reporte. Decidir con los 12 meses es decidir con datos muertos.

Este script mide las dos cosas y localiza EN QUE MES esta cada divergencia, que
es lo unico que permite distinguir «el Resumen quedo viejo» de «las dos hojas se
contradicen».

    python -m scripts._impacto_detalle_real
"""
from __future__ import annotations

import asyncio
import sys
import pathlib
from collections import defaultdict
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

Z = Decimal("0")
TOL = Decimal("1")
CASCADA = ("TOTAL_REVENUES", "TOTAL_OPERATING_EXPENSES", "TOTAL_OVERHEAD_EXPENSES",
           "TOTAL_GOP", "EBITDA_BEFORE_CAPITAL", "EBT", "INCOME_TAXES", "NET_PROFIT")


def val(lineas, code):
    return next((x.amount_usd for x in lineas if x.line_code == code), Z)


async def main() -> None:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from app.models.actual_pl_line import ActualPLLine
    from app.models.department_catalog import DepartmentCatalog
    from app.engine import pl_engine, recalculate as recalc

    async with SessionLocal() as db:
        cat = (await db.execute(select(DepartmentCatalog))).scalars().all()
        pl_engine.set_dept_catalog([{"dept_code": r.dept_code,
                                     "default_pl_group": r.default_pl_group,
                                     "parent_dept_code": r.parent_dept_code} for r in cat])
        mp = await recalc.load_active_account_mappings(db)
        rl = await recalc.load_report_line_config(db)
        codigos = [r["line_code"] for r in rl
                   if r.get("line_type") != "KPI" and not r["line_code"].startswith("SEC_")]

        escs = (await db.execute(select(Scenario))).scalars().all()
        con_resumen = {r[0] for r in (await db.execute(
            select(ActualPLLine.scenario_id).distinct())).all()}

        for e in sorted(escs, key=lambda s: (s.year, s.type, s.version)):
            if e.id not in con_resumen:
                continue
            thr = e.actuals_through or 0
            nombre = "%s %s %s" % (e.type, e.version, e.year)
            print("=" * 100)
            print("%s   ·  actuals_through = %d  ->  meses ABIERTOS: %s"
                  % (nombre, thr, "%d-12" % (thr + 1) if thr else "1-12"))

            hoy, nuevo = defaultdict(Decimal), defaultdict(Decimal)
            por_mes = []
            for m in range(1, 13):
                rep = await recalc.compute_pl_month(db, e, m)     # lo reportado HOY
                for x in rep:
                    hoy[x.line_code] += x.amount_usd
                if thr >= m:
                    alt = rep                                      # mes cerrado: no cambia
                else:
                    filas = await recalc.actual_rows_for_month(db, e.id, m)
                    alt = (pl_engine.canonicalize_pl_lines(pl_engine.add_pl_aliases(
                        pl_engine.calculate_pl_from_mapping(filas, mp, rl))) if filas else rep)
                for x in alt:
                    nuevo[x.line_code] += x.amount_usd

                # divergencia PROPIA del mes entre las dos hojas del escenario
                am = await recalc.actual_pl_lines_for_month(db, e.id, m)
                lr = pl_engine.canonicalize_pl_lines(pl_engine.add_pl_aliases(
                    pl_engine.actual_pl_from_lines(am))) if am else []
                filas = await recalc.actual_rows_for_month(db, e.id, m)
                ld = pl_engine.canonicalize_pl_lines(pl_engine.add_pl_aliases(
                    pl_engine.calculate_pl_from_mapping(filas, mp, rl))) if filas else []
                rotos = [c for c in CASCADA if abs(val(ld, c) - val(lr, c)) > TOL]
                por_mes.append((m, m <= thr, rotos,
                                float(val(ld, "TOTAL_REVENUES") - val(lr, "TOTAL_REVENUES"))))

            print("  -- lo que CAMBIA en el reporte si manda el Detalle --")
            for c in CASCADA:
                a, b = float(hoy.get(c, Z)), float(nuevo.get(c, Z))
                mark = "  " if abs(b - a) <= 1 else "!!"
                print("   %s %-26s %15s -> %15s  (%+13s)"
                      % (mark, c, "{:,.2f}".format(a), "{:,.2f}".format(b),
                         "{:,.2f}".format(b - a)))
            movidas = [c for c in codigos
                       if abs(nuevo.get(c, Z) - hoy.get(c, Z)) > TOL]
            print("  lineas del reporte que se mueven: %d" % len(movidas))

            print("  -- DONDE discrepan las dos hojas, mes a mes (cascada de 8 totales) --")
            for m, cerrado, rotos, drev in por_mes:
                if not rotos:
                    continue
                print("     m%-2d %-8s rev_dif %12s   rompe: %s"
                      % (m, "CERRADO" if cerrado else "abierto",
                         "{:,.2f}".format(drev), ", ".join(rotos)))
            if not any(r for _, _, r, _ in por_mes):
                print("     ninguno: las dos hojas dicen lo mismo los 12 meses")
            abiertos = [m for m, cer, r, _ in por_mes if r and not cer]
            print("  >> discrepancias en meses ABIERTOS (las unicas que llegan al reporte): %s"
                  % (abiertos or "NINGUNA"))
            print()


if __name__ == "__main__":
    asyncio.run(main())
