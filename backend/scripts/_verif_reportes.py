# -*- coding: utf-8 -*-
"""SOLO LECTURA. Verificación independiente post-tanda 2026-08-14.

Para los 20 escenarios de producción:
  A) traza cada fila fuente con el resolvedor REAL (`construir_resolvedor`) y
     reporta DROP (plata que no llega al P&L), FALLBACK (cae en la línea de otro
     depto) y el descuadre Σfuentes vs P&L del motor;
  B) corre P&L mensual, pl-full-detail y la plantilla del Detalle, y reporta
     cualquier excepción;
  C) reconstruye los totales crudos por tabla/depto/cuenta.

No escribe nada. `python -m scripts._verif_reportes [--rapido]`
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

SALIDA = pathlib.Path(__file__).resolve().parent / "_verif_salida.json"


async def cargar_catalogo_en_motor(db) -> int:
    """Réplica del startup de main.py: el motor lee el catálogo de la base."""
    from sqlalchemy import select
    from app.models.department_catalog import DepartmentCatalog
    from app.engine.pl_engine import set_dept_catalog
    rows = (await db.execute(select(DepartmentCatalog))).scalars().all()
    set_dept_catalog([
        {"dept_code": r.dept_code, "default_pl_group": r.default_pl_group,
         "parent_dept_code": r.parent_dept_code} for r in rows
    ])
    return len(rows)


async def main(rapido: bool = False) -> None:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.scenario import Scenario

    resumen: dict = {}
    async with SessionLocal() as db:
        n = await cargar_catalogo_en_motor(db)
        print(f"motor cargado con {n} deptos del catalogo de PROD\n")
        escs = (await db.execute(select(Scenario))).scalars().all()
        escs = sorted(escs, key=lambda s: (s.year, s.type, s.version))
        print(f"{len(escs)} escenarios\n")

    from app.api.audit_api import trace_scenario
    from app.api.pl_api import _monthly_results
    from app.api.pl_full_detail_api import pl_full_detail
    from app.api.scenarios_api import export_scenario_detail

    print(f"{'escenario':<30} {'mode':<10} {'fuente':>14} {'DROP':>12} "
          f"{'#drop':>6} {'#fb':>5} {'#agn':>5} {'desc.max':>12}  reportes")
    print("-" * 130)
    for e in escs:
        nombre = f"{e.type} {e.version} {e.year}"
        fila: dict = {"id": e.id, "source_mode": getattr(e, "source_mode", "?")}
        async with SessionLocal() as db:
            await cargar_catalogo_en_motor(db)
            try:
                t = await trace_scenario(e.id, 0, db)
                fila["totales"] = t["totales"]
                fila["pl_control"] = t["pl_control"]
                malas = [L for L in t["by_line"] if not L["ok"]]
                fila["lineas_descuadradas"] = [
                    {"line": L["line_code"], "fuentes": L["amount_sources"],
                     "pl": L["amount_pl"], "dif": L["dif"]} for L in malas]
                fila["drops"] = sorted(
                    ({"dept": p["dept_code"], "cta": p["account_code"],
                      "nombre": p["account_name"][:40], "monto": p["amount"],
                      "origin": p["origin"]} for p in t["problems"]["DROP"]),
                    key=lambda x: -abs(x["monto"]))[:40]
                fila["fallbacks"] = sorted(
                    ({"dept": p["dept_code"], "cta": p["account_code"],
                      "linea": p["line_code"], "de": p["fallback_from"],
                      "monto": p["amount"]} for p in t["problems"]["FALLBACK"]),
                    key=lambda x: -abs(x["monto"]))[:40]
                fila["agnosticos"] = sorted(
                    ({"dept": p["dept_code"], "cta": p["account_code"],
                      "linea": p["line_code"], "monto": p["amount"]}
                     for p in t["problems"]["dept-agnostic"]),
                    key=lambda x: -abs(x["monto"]))[:40]
                fila["avisos"] = t.get("avisos", [])
                desc = max((abs(L["dif"]) for L in t["by_line"]), default=0.0)
            except Exception as ex:                             # noqa: BLE001
                fila["trace_error"] = f"{type(ex).__name__}: {ex}"
                fila["trace_tb"] = traceback.format_exc()[-1500:]
                desc = -1

        reportes = []
        for etiqueta, fn in (("pl", lambda db: _monthly_results(db, e)),
                             ("full_detail", lambda db: pl_full_detail(e.id, db=db)),
                             ("plantilla", lambda db: export_scenario_detail(e.id, 0, db))):
            if rapido and etiqueta != "pl":
                continue
            async with SessionLocal() as db:
                await cargar_catalogo_en_motor(db)
                try:
                    await fn(db)
                    reportes.append(f"{etiqueta}:OK")
                except Exception as ex:                         # noqa: BLE001
                    reportes.append(f"{etiqueta}:ERROR")
                    fila[f"error_{etiqueta}"] = f"{type(ex).__name__}: {ex}"
                    fila[f"tb_{etiqueta}"] = traceback.format_exc()[-1500:]
        fila["reportes"] = reportes
        resumen[nombre] = fila

        tt = fila.get("totales", {})
        print(f"{nombre:<30} {fila['source_mode']:<10} "
              f"{tt.get('monto_fuente', 0):>14,.0f} {tt.get('monto_perdido_DROP', 0):>12,.2f} "
              f"{tt.get('filas_DROP', 0):>6} {tt.get('filas_FALLBACK', 0):>5} "
              f"{tt.get('filas_dept_agnostic', 0):>5} {desc:>12,.2f}  {' '.join(reportes)}")

    SALIDA.write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n-> {SALIDA}")


if __name__ == "__main__":
    asyncio.run(main("--rapido" in sys.argv))
