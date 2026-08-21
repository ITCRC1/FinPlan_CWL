# -*- coding: utf-8 -*-
"""EL CUADRE QUE FALTABA: el costo del equilibrio contra el costo del P&L.

    python -m scripts.cuadre_costo_break_even

`scripts/cuadre_base_break_even` validaba el INGRESO y daba «TODO CUADRA» en
verde mientras al `BUDGET Working 2027` le faltaban **$1.577.905,52** de costo.
El dato de que «el costo cierra a 4 centavos» venia de una medicion vieja hecha
sobre el `BUDGET Final 2026`, y nunca se repitio sobre 2027.

La identidad que se controla, sacada del propio reporte:

    costo (sin impuesto) = TOTAL_REVENUES - NET_PROFIT - INCOME_TAXES

Se resta el impuesto porque el costo del equilibrio (variable + fijo) no lo
incluye: su regla lo marca `excluded_from_be`.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ESCENARIOS = [
    ("df32afa3-7711-43b8-9586-a01a22b2473b", "BUDGET Final 2026", "BUDGET"),
    ("294f775d-ada2-4a9c-8f72-95d2dfec2eb4", "BUDGET Working 2027", "BUDGET"),
    ("347c5012-1c97-403c-a78e-f47ac32cbf32", "BUDGET Final 2027", "BUDGET"),
    ("8afbc06b-c3e7-466c-b11f-c6325397601e", "FORECAST April 2026", "FORECAST"),
    ("fcb1ab27-96c9-421c-95d8-81e2fb8b8329", "ACTUAL 2025", "ACTUAL"),
    ("1eb311e2-d9dd-4d52-a3ab-db4aac8b889b", "ACTUAL 2024", "ACTUAL"),
]

TOLERANCIA = Decimal("1")


def f(x):
    return f"{float(x):,.2f}"


async def main() -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()

    from app.api import _be_base
    from app.api.break_even_api import _reglas, costo_del_pl, pl_engine_totales
    from app.db import SessionLocal
    from app.engine import break_even as be
    from app.engine.recalculate import compute_pl_month
    from app.models.scenario import Scenario
    from sqlalchemy import select

    malos = 0
    print(f"{'escenario':<24}{'costo BE':>16}{'costo P&L':>16}{'brecha':>15}"
          f"{'equilibrio':>15}")
    print("-" * 88)
    for sid, etq, dv in ESCENARIOS:
        async with SessionLocal() as db:
            s = (await db.execute(
                select(Scenario).where(Scenario.id == sid))).scalar_one()
            base = await _be_base.construir(db, s, 0)
            reglas = await _reglas(db)
            pl = await pl_engine_totales(db, s, 0)
            cpl = await costo_del_pl(db, s, 0)
            neto_pl = Decimal("0")
            for m in range(1, 13):
                for ln in await compute_pl_month(db, s, m):
                    if ln.line_code == "NET_PROFIT":
                        neto_pl += Decimal(str(ln.amount_usd))

        r = be.calcular(data_version=dv, revenue=pl["revenue"],
                        revenue_rooms=pl["revenue_rooms"], montos=base.costos(),
                        reglas=reglas, adr=pl["adr"],
                        rooms_available=pl["rooms_available"])
        costo_be = r.variable_cost + r.fixed_cost
        brecha = costo_be - cpl
        marca = "OK " if abs(brecha) <= TOLERANCIA else "!! "
        if abs(brecha) > TOLERANCIA:
            malos += 1
        print(f"{marca}{etq:<21}{f(costo_be):>16}{f(cpl):>16}{f(brecha):>15}"
              f"{f(r.be_revenue) if r.be_revenue else '—':>15}")
        print(f"{'':<24}{'neto BE ' + f(r.net):>32}"
              f"{'neto P&L ' + f(neto_pl):>31}")

    print("-" * 88)
    print("EL COSTO CUADRA" if not malos else f"{malos} escenario(s) sin cuadrar")
    return 0 if not malos else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
