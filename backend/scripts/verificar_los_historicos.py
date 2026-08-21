# -*- coding: utf-8 -*-
"""SOLO LECTURA. Que diria la verificacion del upload sobre lo que YA esta cargado.

No escribe nada. Simula el viaje redondo completo para cada escenario:

    bajar la plantilla  ->  volver a subirla sin tocar nada  ->  ¿que dice la puerta?

  · El bloque de VERIFICACION de arriba se llena con lo que HOY reporta el
    sistema (`compute_pl_month`) — es literalmente lo que escribe la descarga.
  · El DETALLE de abajo se consolida con el motor desde `actual_entries`, que es
    lo que hace la subida.
  · Y se comparan por BUCKET, con `app/importers/verificacion.comparar`.

Si algo no cuadra, no es un defecto de esta medicion: es plata que sale del
detalle y no llega al resumen, o al reves.

    python -m scripts.verificar_los_historicos
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# La consola de Windows sale en cp437 y se come las tildes del informe. Un
# informe ilegible es un informe que no se lee.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


async def main() -> None:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from app.models.actual_entry import ActualEntry
    from app.models.department_catalog import DepartmentCatalog
    from app.engine import pl_engine, recalculate as recalc
    from app.importers.verificacion import CONTROLES, comparar, meses_comparables

    async with SessionLocal() as db:
        cat = (await db.execute(select(DepartmentCatalog))).scalars().all()
        pl_engine.set_dept_catalog([{"dept_code": r.dept_code,
                                     "default_pl_group": r.default_pl_group,
                                     "parent_dept_code": r.parent_dept_code} for r in cat])
        mappings = await recalc.load_active_account_mappings(db)
        report_lines = await recalc.load_report_line_config(db)

        con_detalle = {r[0] for r in (await db.execute(
            select(ActualEntry.scenario_id).distinct())).all()}
        escs = [s for s in (await db.execute(select(Scenario))).scalars().all()
                if s.id in con_detalle]
        escs.sort(key=lambda s: (s.type, s.year, s.version))

        print("=" * 108)
        print("LA VERIFICACION DEL UPLOAD, CORRIDA CONTRA LO QUE YA ESTA CARGADO")
        print("=" * 108)

        for s in escs:
            comparables, cerrados = meses_comparables(s.type, getattr(s, "actuals_through", 0))

            # Arriba: lo que escribe la DESCARGA (el P&L que hoy reporta el sistema).
            verif: dict[str, dict] = {}
            for m in comparables:
                lineas = {L.line_code: L.amount_usd for L in
                          await recalc.compute_pl_month(db, s, m)}
                for c in CONTROLES:
                    if c.line_code in lineas:
                        verif.setdefault(c.codigo, {})[m] = lineas[c.line_code]

            # Abajo: lo que consolida la SUBIDA desde el mayor.
            consolidado: dict[int, dict] = {}
            for m in comparables:
                filas = await recalc.actual_rows_for_month(db, s.id, m)
                consolidado[m] = {L.line_code: L.amount_usd for L in
                                  pl_engine.calculate_pl_from_mapping(
                                      filas, mappings, report_lines)}

            rep = comparar(verif, consolidado, comparables, cerrados)
            estado = ("CUADRA" if rep["cuadra"]
                      else ("BLOQUEA" if rep["bloquea"] else "avisa"))
            print("\n%-46s  %s  (meses %d)" % (
                f"{s.type} · {s.version} · {s.year}", estado, len(comparables)))
            if cerrados:
                print("    meses no comparados (los toma del Actual): %s" %
                      ", ".join("%02d" % m for m in cerrados))
            for L in rep["lineas"]:
                marca = "  " if L["cuadra"] else ("!!" if L["bloquea"] else " ~")
                print("   %s %-36s archivo %16s   detalle %16s   dif %14s" % (
                    marca, L["etiqueta"],
                    "{:,.2f}".format(L["archivo"]), "{:,.2f}".format(L["detalle"]),
                    "{:,.2f}".format(L["dif"])))
                if L["nota"]:
                    print("        -> " + L["nota"])


if __name__ == "__main__":
    asyncio.run(main())
