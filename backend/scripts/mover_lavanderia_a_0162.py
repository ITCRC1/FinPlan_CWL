# -*- coding: utf-8 -*-
"""Pasa el INGRESO de lavanderia del 0161 al 0162.

Owner, 2026-08-14: «corrige 0161 y asigna laundry revenue 0162».

La decision de diseño ya estaba tomada y registrada: **0162 es el departamento
de ingreso de lavanderia y 0161 es el que lleva el gasto y lo reparte**. Pero el
dato venia cargado al reves — la cuenta 4701 «Lavanderia 2» estaba en el 0161.

Mientras el ingreso viva en el 0161, ese departamento nunca cierra en cero como
esta diseñado: el reparto se calcula sobre el gasto y le queda una venta adentro.

**Solo se mueve el ingreso.** Las cuentas de REPARTO (4900/4901/4999) se quedan
en el 0161: son el credito con el que ese departamento se vacia, y son
exactamente lo que tiene que quedar ahi.

Sin --aplicar no escribe nada.
"""
import sys
import asyncio
from decimal import Decimal

if "--prod" in sys.argv:
    from scripts._prodenv import usar_produccion
    usar_produccion()

from sqlalchemy import select
from app.db import get_session
from app.models.actual_entry import ActualEntry
from app.models.scenario import Scenario

APLICAR = "--aplicar" in sys.argv
ORIGEN, DESTINO = "0161", "0162"
REPARTO = {"4900", "4901", "4999"}
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]


async def main():
    async with get_session() as s:
        escs = (await s.execute(select(Scenario).order_by(
            Scenario.year, Scenario.type))).scalars().all()
        for e in escs:
            filas = (await s.execute(select(ActualEntry).where(
                ActualEntry.scenario_id == e.id,
                ActualEntry.dept_code == ORIGEN))).scalars().all()
            mueven = [f for f in filas
                      if (f.account_code or "").startswith("4")
                      and f.account_code not in REPARTO]
            if not mueven:
                continue
            print(f"\n{e.type} {e.version} {e.year}  (status {e.status})")
            for f in mueven:
                tot = sum(float(getattr(f, m) or 0) for m in MESES)
                print(f"   {f.account_code:<8} {tot:>12,.2f}  {f.account_name[:40]}"
                      f"   {ORIGEN} -> {DESTINO}")

            if not APLICAR:
                continue
            if e.status == "locked":
                print("   (enllavado — se salta; hay que desenllavarlo a mano)")
                continue

            ya = {f.account_code: f for f in (await s.execute(select(ActualEntry).where(
                ActualEntry.scenario_id == e.id,
                ActualEntry.dept_code == DESTINO))).scalars().all()}
            for f in mueven:
                gemela = ya.get(f.account_code)
                if gemela is None:
                    # No hay fila en el destino: se muda la misma, que conserva
                    # el nombre de cuenta y los doce meses tal cual.
                    f.dept_code = DESTINO
                else:
                    # Ya existe: se SUMA mes a mes y se borra la de origen.
                    # Asignar perderia lo que el destino ya tenia.
                    for m in MESES:
                        setattr(gemela, m, Decimal(str(getattr(gemela, m) or 0))
                                + Decimal(str(getattr(f, m) or 0)))
                    await s.delete(f)
            await s.commit()
            print("   movido")

    if not APLICAR:
        print("\n(ensayo — no se escribio nada; agregá --aplicar)")


asyncio.run(main())
