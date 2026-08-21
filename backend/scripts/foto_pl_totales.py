# -*- coding: utf-8 -*-
"""Foto de los totales del P&L de TODOS los escenarios, para comparar antes y despues.

Existe por el cambio de las cuentas clase 5 a lineas de costo (owner, 2026-08-14).
La regla que puso el owner es que el resultado NO se mueve: es como se presenta
el costo, no un cambio de numeros. Esto lo prueba en vez de suponerlo.

    python -m scripts.foto_pl_totales antes.json
    ...cambios y deploy...
    python -m scripts.foto_pl_totales despues.json
    python -m scripts.foto_pl_totales --comparar antes.json despues.json
"""
import asyncio
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

LINEAS = ["TOTAL_REVENUES", "TOTAL_OPERATING_EXPENSES", "TOTAL_OVERHEAD_EXPENSES",
          "TOTAL_GOP", "EBITDA_BEFORE_CAPITAL", "EBT", "NET_PROFIT"]


def comparar(a: str, b: str) -> int:
    x = json.load(open(a, encoding="utf-8"))
    y = json.load(open(b, encoding="utf-8"))
    malos = 0
    for esc in sorted(set(x) | set(y)):
        if esc not in x or esc not in y:
            print(f"  !! {esc}: esta en uno y no en el otro"); malos += 1; continue
        for ln in LINEAS:
            va, vb = x[esc].get(ln, 0), y[esc].get(ln, 0)
            if abs(va - vb) > 0.01:
                print(f"  !! {esc} {ln}: {va:,.2f} -> {vb:,.2f}  ({vb - va:+,.2f})")
                malos += 1
    print(f"\n{'SE MOVIO ALGO: ' + str(malos) + ' diferencias' if malos else 'IDENTICO: nada se movio'}")
    return 1 if malos else 0


async def tomar(salida: str, desde_json: bool = False):
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import get_session
    from app.models.scenario import Scenario
    from app.engine import recalculate as recalc, pl_engine

    foto = {}
    async with get_session() as s:
        escs = (await s.execute(select(Scenario))).scalars().all()
        if desde_json:
            # ⚠️ El mapeo se lee del ARCHIVO, no de la base. Asi se puede probar
            # un cambio del seed contra los datos reales ANTES de desplegarlo:
            # el seed corre en el arranque, o sea que si se espera al deploy, el
            # cambio ya esta en produccion cuando uno se entera de que movio algo.
            import json as _j, pathlib as _p
            arch = _p.Path(__file__).resolve().parents[1] / "app" / "seed_data" / "mapping_pl.json"
            d = _j.loads(arch.read_text(encoding="utf-8"))
            # ⚠️ MISMO filtro que el motor: `load_active_account_mappings` solo
            # toma el reporte P&L_DETAIL_OWNERS. Sin esto la foto incluia reglas
            # de otros reportes que el motor nunca usa, y la comparacion
            # denunciaba diferencias que no existian — $92.176,75 en Budget
            # Working 2027, que costo media hora perseguir.
            #
            # Una herramienta de auditoria que grita en falso es peor que no
            # tenerla: la proxima vez que grite, nadie le va a creer.
            REPORTE = "P&L_DETAIL_OWNERS"
            maps = [{"account_code": r["account_code"],
                     "dept_code": r.get("dept_code") or "",
                     "report_line_code": r["report_line_code"],
                     "active_status": r["active_status"],
                     "rollup_operator": r.get("rollup_operator", "SUM")}
                    for r in d["account_mapping"]
                    if r.get("active_status") == "YES" and r.get("report_id") == REPORTE]
            cfg = [r for r in d["report_line_config"] if r.get("active", True)]
            cfg.sort(key=lambda r: r["display_order"])
            print(f"  (mapeo leido del JSON: {len(maps)} reglas, {len(cfg)} lineas)")
        else:
            maps = await recalc.load_active_account_mappings(s)
            cfg = await recalc.load_report_line_config(s)
        for e in escs:
            tot = {ln: 0.0 for ln in LINEAS}
            for m in range(1, 13):
                filas = await recalc.actual_rows_for_month(s, e.id, m)
                if not filas:
                    filas = await recalc.checkbook_account_rows_for_month(s, e.id, m)
                if not filas:
                    continue
                for l in pl_engine.calculate_pl_from_mapping(filas, maps, cfg):
                    if l.line_code in tot:
                        tot[l.line_code] += float(l.amount_usd)
            clave = f"{e.type} {e.version} {e.year}"
            foto[clave] = {k: round(v, 2) for k, v in tot.items()}
            print(f"  {clave:34} GOP {tot['TOTAL_GOP']:>15,.2f}")
    json.dump(foto, open(salida, "w", encoding="utf-8"), indent=1, sort_keys=True)
    print(f"\n{len(foto)} escenarios -> {salida}")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--comparar"]:
        sys.exit(comparar(sys.argv[2], sys.argv[3]))
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    asyncio.run(tomar(args[0] if args else "foto_pl.json", "--json" in sys.argv))
