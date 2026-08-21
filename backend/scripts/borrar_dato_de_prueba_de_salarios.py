# -*- coding: utf-8 -*-
"""Saca el DATO DE PRUEBA del reparto de salarios de los cinco borradores 2027.

## Qué es, medido (2026-08-16)

Los cinco presupuestos 2027 que no son el `Working` —`Draft1`, `Draft2`,
`Draft3`, `Draft4-BIG` y `Final`— reparten **$51.886,44 cada uno** en concepto de
salarios, y se ve en el P&L como `OH_CAFETERIA`. Ese número **es inventado**, y
hay dos mediciones que lo prueban:

1. **El salario es basura tecleada.** La regla `CAMARERO (A)` (`0113` → `0220`)
   trae un `salary_override` de::

       [1000, 10000, 1, 0, 14, 1, 1, 1, 1, 11, 1, 1]

   Diez mil en febrero, uno en marzo, cero en abril, catorce en mayo. Ningún
   salario se parece a eso. La regla `COCINERO A - SUPERVISOR` trae `[1500, 0…]`
   y encima **sin ningún destino**.

2. **La posición no existe.** Las seis reglas de esos escenarios apuntan a los
   códigos de la planilla 2026 (`508`, `525`, `598`, `604`, `608`, `612`) y **los
   129 puestos de los seis escenarios 2027 no tienen ni uno**: el head count
   nuevo usa `0113-04`, `0150-01`, `0200-09`… Sin override, esas reglas calculan
   contra el vacío y dan cero — que es la verdad. **Todo lo que sale hoy sale del
   override.**

O sea: no hay salario real detrás de esos $51.886. Es un dato de prueba que se
copió al abrir cada versión y sobrevivió a los recálculos — el último los volvió
a escribir el 2026-08-16 a la 1 AM, así que no se va a morir solo.

## Qué hace y qué NO hace

**Hace:** poner en cero el `salary_override` de esas reglas y recalcular los cinco
escenarios, para que el reparto quede en $0 — que es lo que corresponde a un
escenario cuyas reglas no encuentran su posición.

**NO hace:** rearmar las reglas contra el head count 2027. Eso es lo que se hizo
en el `Working` (y da **$103.662,39**), pero es una decisión del owner sobre qué
deben decir esos cinco presupuestos, no una corrección de dato sucio. Acá solo se
saca lo fabricado.

    python -m scripts.borrar_dato_de_prueba_de_salarios              # simula
    python -m scripts.borrar_dato_de_prueba_de_salarios --aplicar    # escribe
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ZERO = Decimal("0")
CODIGOS_VIEJOS = {"508", "525", "598", "604", "608", "612"}


async def main(aplicar: bool) -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from app.models.salary_allocation_config import SalaryAllocationConfig
    from app.models.allocation_entry import AllocationEntry
    from app.models.payroll_position import PayrollPosition

    async with SessionLocal() as db:
        escenarios = [s for s in (await db.execute(
            select(Scenario).where(Scenario.year == 2027, Scenario.type == "BUDGET")
        )).scalars() if s.version != "Working"]

        print(f"\n{'escenario':<26}{'regla':<26}{'override hoy':>34}")
        print("=" * 88)
        tocar: list = []
        for s in sorted(escenarios, key=lambda x: x.version):
            puestos = {p.position_code for p in (await db.execute(
                select(PayrollPosition).where(PayrollPosition.scenario_id == s.id)
            )).scalars()}
            reglas = (await db.execute(select(SalaryAllocationConfig).where(
                SalaryAllocationConfig.scenario_id == s.id))).scalars().all()
            for r in reglas:
                ov = [Decimal(str(v or 0)) for v in (r.salary_override or [])]
                if not any(ov):
                    continue
                # La baranda: solo se toca si la posición NO existe en la
                # planilla del escenario. Si existiera, ese override podría ser
                # un salario que alguien cargó a mano y no es basura.
                if r.position_code in puestos:
                    print(f"  ⚠ {s.version} {r.position_code}: la posición SÍ existe "
                          f"— NO se toca, puede ser un salario cargado a mano.")
                    continue
                assert r.position_code in CODIGOS_VIEJOS, r.position_code
                print(f"{s.version:<26}{r.position_name[:24]:<26}"
                      f"{str([float(x) for x in ov]):>34}")
                tocar.append(r)

        reparto = {}
        for s in escenarios:
            filas = (await db.execute(select(AllocationEntry).where(
                AllocationEntry.scenario_id == s.id,
                AllocationEntry.allocation_type == "SALARY"))).scalars().all()
            reparto[s.version] = sum(
                (Decimal(str(f.amount_usd)) for f in filas
                 if Decimal(str(f.amount_usd)) > 0), ZERO)

        print("\nReparto de salarios HOY (lo que este arreglo lleva a 0,00):")
        for v, m in sorted(reparto.items()):
            print(f"  {v:<20}{m:>14,.2f}")
        print(f"  {'TOTAL':<20}{sum(reparto.values()):>14,.2f}")

        if not aplicar:
            print(f"\nSIMULACIÓN: {len(tocar)} regla(s) quedarían en cero. "
                  f"Nada se escribió. Correr con --aplicar.")
            return 0

        for r in tocar:
            r.salary_override = [0.0] * 12
        await db.commit()
        print(f"\n✓ {len(tocar)} override(s) en cero.")

    # El recálculo va de a UNO y en sesión propia: recorre los 12 meses y
    # reescribe el P&L entero (ver `scripts/recalcular_escenarios`).
    from app.engine.recalculate import recalculate_scenario
    for s in sorted(escenarios, key=lambda x: x.version):
        async with SessionLocal() as db:
            esc = await db.get(Scenario, s.id)
            await recalculate_scenario(db, esc)
            await db.commit()
        print(f"✓ recalculado {esc.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
