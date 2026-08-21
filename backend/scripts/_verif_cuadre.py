# -*- coding: utf-8 -*-
"""SOLO LECTURA. Cuadre Resumen vs Detalle — el chequeo INDEPENDIENTE de la plata.

`actual_pl_lines` (hoja Resumen del archivo del owner) NO se tocó hoy.
`actual_entries` (hoja Detalle) SÍ: es la tabla donde se re-etiquetaron y se
FUSIONARON filas. Si una fusión hubiera sumado mal, el Detalle dejaría de cuadrar
contra el Resumen, que es un registro externo al cambio.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


async def main() -> None:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from app.models.actual_pl_line import ActualPLLine
    from app.models.department_catalog import DepartmentCatalog
    from app.engine.pl_engine import set_dept_catalog
    from app.api.cuadre_api import cuadre

    async with SessionLocal() as db:
        rows = (await db.execute(select(DepartmentCatalog))).scalars().all()
        set_dept_catalog([{"dept_code": r.dept_code,
                           "default_pl_group": r.default_pl_group,
                           "parent_dept_code": r.parent_dept_code} for r in rows])
        escs = (await db.execute(select(Scenario))).scalars().all()
        con_resumen = {r[0] for r in (await db.execute(
            select(ActualPLLine.scenario_id).distinct())).all()}

    for e in sorted(escs, key=lambda s: (s.year, s.type, s.version)):
        if e.id not in con_resumen:
            continue
        nombre = f"{e.type} {e.version} {e.year}"
        try:
            r = await cuadre(e.id, None)
        except Exception as ex:                                  # noqa: BLE001
            print(f"{nombre:<26} ERROR {type(ex).__name__}: {ex}")
            continue
        print(f"\n=== {nombre} · manda={r['manda']} · meses_con_detalle={r['meses_con_detalle']}")
        print(f"    neto resumen {r['neto_resumen']:>15,.2f}  detalle {r['neto_detalle']:>15,.2f}"
              f"  dif {r['neto_diferencia']:>13,.2f}   descuadres={r['descuadres']}")
        for f in sorted(r["filas"], key=lambda x: -abs(x["diferencia"])):
            if not f["cuadra"]:
                print(f"      !! {f['line_code']:<26} resumen {f['resumen']:>14,.2f}"
                      f"  detalle {f['detalle']:>14,.2f}  dif {f['diferencia']:>13,.2f}")


if __name__ == "__main__":
    asyncio.run(main())
