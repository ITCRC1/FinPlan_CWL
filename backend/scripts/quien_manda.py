# -*- coding: utf-8 -*-
"""SOLO LECTURA. Cuál hoja produce el P&L de cada escenario, y por qué.

Cada escenario histórico tiene DOS fuentes y roles distintos: el **Detalle**
(`actual_entries`, el mayor) es con lo que se reporta, y el **Resumen**
(`actual_pl_lines`) es el control que confirma que el detalle está bien. El
motor elige una — y hasta el 2026-08-16 la elegía **en silencio**, así que un
escenario podía estar reportando contra un control viejo sin que nada avisara.

Esto imprime la decisión del motor con su evidencia, escenario por escenario.
Es la MISMA función que arma el P&L (`recalculate.veredicto_del_detalle`): no
reimplementa el criterio, se lo pregunta.

Para el desglose línea por línea de un escenario, usar `/reports/cuadre/{id}/`;
para el viaje redondo del archivo de actuales, `scripts.verificar_los_historicos`.

    python -m scripts.quien_manda
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


async def main() -> None:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.actual_pl_line import ActualPLLine
    from app.models.department_catalog import DepartmentCatalog
    from app.models.scenario import Scenario
    from app.engine import pl_engine, recalculate as recalc

    async with SessionLocal() as db:
        cat = (await db.execute(select(DepartmentCatalog))).scalars().all()
        pl_engine.set_dept_catalog([{"dept_code": r.dept_code,
                                     "default_pl_group": r.default_pl_group,
                                     "parent_dept_code": r.parent_dept_code} for r in cat])

        con_resumen = {r[0] for r in (await db.execute(
            select(ActualPLLine.scenario_id).distinct())).all()}
        escs = [e for e in (await db.execute(select(Scenario))).scalars().all()
                if e.id in con_resumen]
        escs.sort(key=lambda e: (e.year, e.type, e.version))

        print("=" * 100)
        print("QUIÉN MANDA — Resumen (control) vs Detalle (mayor), por escenario")
        print("=" * 100)
        for e in escs:
            v = await recalc.veredicto_del_detalle(db, e)
            meses = v["meses_evaluados"]
            print(f"\n{e.type} {e.version} {e.year}")
            print(f"  manda            : {v['manda'].upper()}")
            print(f"  meses evaluados  : {meses[0]}–{meses[-1]}"
                  f"  (corte={v['actuals_through']})")
            print(f"  motivo           : {v['motivo']}")
            for d in v["diferencias"]:
                print(f"      · {d['total']:<28} resumen {d['resumen']:>14,.2f}"
                      f"   detalle {d['detalle']:>14,.2f}"
                      f"   dif {d['diferencia']:>+13,.2f}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
