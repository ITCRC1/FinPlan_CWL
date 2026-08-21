# -*- coding: utf-8 -*-
"""¿CUÁNTO puede estar mal el punto de equilibrio? SOLO LECTURA.

    python -m scripts.cuanto_puede_estar_malo

Deja de decir «hay cosas sin conectar» y dice **cuánto pueden mover el número**.
Para cada escenario:

  1. ¿Ve el break-even TODO el costo del P&L? (brecha en $ y en % del costo)
  2. ¿Ve TODO el ingreso? (idem)
  3. Si esa brecha entrara entera al costo FIJO —el peor caso, porque es el que
     más sube el equilibrio— ¿en cuánto cambiaría el equilibrio?
  4. ¿Cuánta plata está tomando el criterio por defecto, y cuánto movería si
     estuviera 100% variable en vez de 100% fija? (el otro extremo)

El resultado es una COTA: el equilibrio no puede estar mal por más que eso.
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


def d(x):
    return f"{float(x):,.2f}"


async def main() -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()

    from app.api import _be_base
    from app.api.break_even_api import _reglas, costo_del_pl, pl_engine_totales
    from app.db import SessionLocal
    from app.engine import break_even as be
    from app.models.scenario import Scenario
    from sqlalchemy import select

    for sid, etq, dv in ESCENARIOS:
        async with SessionLocal() as db:
            s = (await db.execute(
                select(Scenario).where(Scenario.id == sid))).scalar_one()
            base = await _be_base.construir(db, s, 0)
            reglas = await _reglas(db)
            pl = await pl_engine_totales(db, s, 0)
            cpl = await costo_del_pl(db, s, 0)

        montos = base.costos()
        r = be.calcular(data_version=dv, revenue=pl["revenue"],
                        revenue_rooms=pl["revenue_rooms"], montos=montos,
                        reglas=reglas, adr=pl["adr"],
                        rooms_available=pl["rooms_available"])
        costo_be = r.variable_cost + r.fixed_cost
        falta_costo = cpl - costo_be
        falta_ing = pl["revenue"] - base.total_ingreso()

        print(f"\n{'='*78}\n  {etq}\n{'='*78}")
        print(f"  equilibrio que muestra hoy : {d(r.be_revenue) if r.be_revenue else '—':>16}")
        print(f"  costo que NO ve            : {d(falta_costo):>16}"
              f"   ({float(abs(falta_costo) / cpl * 100) if cpl else 0:.3f}% del costo)")
        print(f"  ingreso que NO ve          : {d(falta_ing):>16}")

        # Peor caso: lo que falta entra TODO al costo fijo.
        if r.cm_pct and r.cm_pct > 0 and r.be_revenue:
            peor = (r.fixed_cost + falta_costo) / r.cm_pct
            print(f"  si eso entrara 100% FIJO   : {d(peor):>16}"
                  f"   (movería {d(peor - r.be_revenue)})")

        # El otro extremo: lo que hoy toma el criterio por defecto.
        sin_regla = sum((x.amount for x in r.sin_clasificar), Decimal("0"))
        if sin_regla and r.cm_pct and r.cm_pct > 0 and r.be_revenue:
            # Hoy está 100% fijo. Si fuera 100% variable: sale del fijo y entra
            # al variable, lo que baja el margen y sube... se calcula entero.
            nueva_cm = (r.revenue - (r.variable_cost + sin_regla)) / r.revenue
            if nueva_cm > 0:
                alt = (r.fixed_cost - sin_regla) / nueva_cm
                print(f"  por defecto 100% fijo      : {d(sin_regla):>16}"
                      f"   (si fuera variable: {d(alt)}, movería {d(alt - r.be_revenue)})")
            else:
                print(f"  por defecto 100% fijo      : {d(sin_regla):>16}")
        elif not sin_regla:
            print(f"  por defecto 100% fijo      : {'0.00':>16}   (nada sin criterio)")

        for a in base.avisos:
            print(f"  AVISO: {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
