# -*- coding: utf-8 -*-
"""Qué hay en «Por defecto: 100% fijo» de cada escenario. SOLO LECTURA."""
from __future__ import annotations
import asyncio, pathlib, sys, collections
from decimal import Decimal
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ESC = [("df32afa3-7711-43b8-9586-a01a22b2473b", "BUDGET Final 2026", "BUDGET"),
       ("294f775d-ada2-4a9c-8f72-95d2dfec2eb4", "BUDGET Working 2027", "BUDGET"),
       ("347c5012-1c97-403c-a78e-f47ac32cbf32", "BUDGET Final 2027", "BUDGET"),
       ("fcb1ab27-96c9-421c-95d8-81e2fb8b8329", "ACTUAL 2025", "ACTUAL"),
       ("1eb311e2-d9dd-4d52-a3ab-db4aac8b889b", "ACTUAL 2024", "ACTUAL")]

async def main():
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from app.engine import break_even as be
    from app.api.break_even_api import montos_del_escenario, _reglas, pl_engine_totales
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from sqlalchemy import select
    for sid, etq, dv in ESC:
        async with SessionLocal() as db:
            s = (await db.execute(select(Scenario).where(Scenario.id == sid))).scalar_one()
            montos = await montos_del_escenario(db, s, 0)
            reglas = await _reglas(db)
            pl = await pl_engine_totales(db, s, 0)
        r = be.calcular(data_version=dv, revenue=pl["revenue"],
                        revenue_rooms=pl["revenue_rooms"], montos=montos,
                        reglas=reglas, adr=pl["adr"],
                        rooms_available=pl["rooms_available"])
        tot = sum(x.amount for x in r.sin_clasificar)
        print(f"\n### {etq}: {len(r.sin_clasificar)} montos, {float(tot):,.2f} "
              f"({float(tot/pl['revenue'])*100:.2f}% del ingreso)")
        g = collections.defaultdict(lambda: [0, Decimal(0)])
        for x in r.sin_clasificar:
            k = (x.dept_code, x.account, x.pl_line)
            g[k][0] += 1
            g[k][1] += x.amount
        for (d, a, l), (n, m) in sorted(g.items(), key=lambda kv: -abs(kv[1][1]))[:15]:
            print(f"   dept={d or '(vacio)':<8} cta={a or '(vacia)':<8} "
                  f"linea={l or '(SIN LINEA)':<26} n={n:<5} {float(m):>14,.2f}")
        if len(g) > 15:
            print(f"   ... y {len(g)-15} combinaciones mas")

asyncio.run(main())
