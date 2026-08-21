# -*- coding: utf-8 -*-
"""El checkbook de ingresos contra el P&L, linea por linea. SOLO LECTURA."""
from __future__ import annotations
import asyncio, collections, pathlib, sys
from decimal import Decimal
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

SID = "294f775d-ada2-4a9c-8f72-95d2dfec2eb4"  # BUDGET Working 2027

M = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
     "nov", "dec"]


async def main():
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from app.db import SessionLocal
    from app.engine import pl_engine
    from app.engine.recalculate import compute_pl_month
    from app.models.revenue_entry import RevenueEntry
    from app.models.scenario import Scenario
    from sqlalchemy import select

    async with SessionLocal() as db:
        s = (await db.execute(select(Scenario).where(Scenario.id == SID))).scalar_one()
        filas = (await db.execute(select(RevenueEntry).where(
            RevenueEntry.scenario_id == SID))).scalars().all()
        pl = collections.defaultdict(Decimal)
        for m in range(1, 13):
            for ln in await compute_pl_month(db, s, m):
                pl[ln.line_code] += Decimal(str(ln.amount_usd))

    # checkbook -> linea del P&L, con el mismo mapa que usa el motor
    porlinea = collections.defaultdict(Decimal)
    crudo = {}
    for e in filas:
        tot = sum((getattr(e, c) or Decimal(0)) for c in M)
        crudo[e.line] = tot
        attr = e.line.lower()
        destino = pl_engine.REVENUE_LINE_TO_REPORT_LINE.get(attr, "(SIN MAPA)")
        porlinea[destino] += tot

    print(f"{'linea P&L':<24}{'checkbook':>16}{'P&L':>16}{'dif':>14}")
    total_cb = total_pl = Decimal(0)
    for linea in sorted(set(porlinea) | {k for k in pl if k.startswith("REV_")}):
        cb, v = porlinea.get(linea, Decimal(0)), pl.get(linea, Decimal(0))
        if not cb and not v:
            continue
        total_cb += cb
        total_pl += v
        marca = "" if abs(cb - v) < Decimal("0.01") else "   <<<"
        print(f"{linea:<24}{float(cb):>16,.2f}{float(v):>16,.2f}"
              f"{float(cb - v):>14,.2f}{marca}")
    print("-" * 70)
    print(f"{'SUMA':<24}{float(total_cb):>16,.2f}{float(total_pl):>16,.2f}"
          f"{float(total_cb - total_pl):>14,.2f}")
    print(f"{'TOTAL_REVENUES del P&L':<24}{'':>16}"
          f"{float(pl.get('TOTAL_REVENUES', 0)):>16,.2f}")
    print(f"\ncheckbook crudo: {float(sum(crudo.values())):,.2f}")
    for k, v in sorted(crudo.items(), key=lambda kv: -kv[1]):
        attr = k.lower()
        print(f"   {k:<20} {float(v):>14,.2f}  -> "
              f"{pl_engine.REVENUE_LINE_TO_REPORT_LINE.get(attr, '(SIN MAPA)')}")

asyncio.run(main())
