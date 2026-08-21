# -*- coding: utf-8 -*-
"""Abre el impuesto de renta del Budget 2026 por mes, en la cuenta 8060.

Owner, 2026-08-14: los doce montos que paso son exactamente el 30% del EBT de
ese presupuesto, mes a mes. Verificado: coinciden al centavo en los doce.

**El resultado del año NO cambia.** El total de los doce da 5,669.50, que es
justo el impuesto que el escenario ya tenia (EBT 18,898.35 - neto 13,228.85). Lo
que falta es que ese impuesto este ABIERTO por mes y en su cuenta, en vez de
existir solo como un total.

Se escribe en los DOS lados, que es lo que evita contarlo dos veces:

  · `actual_entries` cuenta 8060 -> aparece en la apertura por cuenta
  · `actual_pl_lines` INCOME_TAXES -> el P&L lo muestra mes a mes

El P&L de un escenario importado sale del RESUMEN, asi que la primera escritura
sola no lo movia; y la segunda sola no lo abria por cuenta. Las dos juntas dejan
una sola verdad.

Sin --aplicar no escribe nada.
"""
import sys
import asyncio
from decimal import Decimal

if "--prod" in sys.argv:
    from scripts._prodenv import usar_produccion
    usar_produccion()

from sqlalchemy import select, delete
from app.db import get_session
from app.models.actual_entry import ActualEntry
from app.models.actual_pl_line import ActualPLLine
from app.models.scenario import Scenario

APLICAR = "--aplicar" in sys.argv
CUENTA, DEPTO, NOMBRE = "8060", "0250", "INCOME TAX"
LINEA = "INCOME_TAXES"
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]
MONTOS = [Decimal("80859.34"), Decimal("69726.43"), Decimal("59964.65"),
          Decimal("-9574.25"), Decimal("-39607.03"), Decimal("-49994.20"),
          Decimal("-3541.27"), Decimal("-29610.18"), Decimal("-62625.67"),
          Decimal("-96852.79"), Decimal("-1105.48"), Decimal("88029.95")]


async def _pl(s, e):
    from app.api import pl_api
    men = await pl_api._monthly_results(s, e)
    a = pl_api._aggregate(men, 12)
    d = {l["line_code"]: l["amount_usd"] for l in a["lines"]}
    return d.get("EBT", 0.0), d.get("INCOME_TAXES", 0.0), d.get("NET_PROFIT", 0.0)


async def main():
    async with get_session() as s:
        e = (await s.execute(select(Scenario).where(
            Scenario.year == 2026, Scenario.type == "BUDGET"))).scalars().first()
        print(f"escenario: {e.type} {e.version} {e.year}  status={e.status}")
        ebt, imp, neto = await _pl(s, e)
        print(f"ANTES   EBT {ebt:>13,.2f}   impuesto {imp:>11,.2f}   neto {neto:>13,.2f}")
        print(f"a cargar: {float(sum(MONTOS)):,.2f} repartido en 12 meses")

        if not APLICAR:
            print("\n(ensayo — no se escribio nada)")
            return

        if e.status == "locked":
            e.status = "draft"
            await s.flush()
            print("desenllavado")

        # 1) el detalle, cuenta 8060
        fila = (await s.execute(select(ActualEntry).where(
            ActualEntry.scenario_id == e.id,
            ActualEntry.account_code == CUENTA))).scalars().first()
        if fila is None:
            fila = ActualEntry(scenario_id=e.id, hotel_id=e.hotel_id,
                               dept_code=DEPTO, account_code=CUENTA,
                               account_name=NOMBRE, outlet="")
            s.add(fila)
        for i, m in enumerate(MESES):
            setattr(fila, m, MONTOS[i])

        # 2) el resumen, linea INCOME_TAXES — se REEMPLAZA, no se suma: si no,
        #    el impuesto quedaria contado dos veces.
        await s.execute(delete(ActualPLLine).where(
            ActualPLLine.scenario_id == e.id, ActualPLLine.line_code == LINEA))
        for i in range(12):
            s.add(ActualPLLine(scenario_id=e.id, month=i + 1,
                               line_code=LINEA, amount_usd=MONTOS[i]))

        # 3) el NETO, que en este snapshot venia SIN restar el impuesto: su
        #    NET_PROFIT era identico al EBT, mes a mes.
        #
        #    Los 13,228.85 que se veian antes no estaban guardados: los
        #    sintetizaba `_apply_tax_correction`, que aplica el 30% cuando NO
        #    encuentra linea de impuesto. Al cargar una de verdad dejo de
        #    sintetizar y afloro el neto sin restar — 18,898.35.
        #
        #    Escribir el neto lo deja consistente consigo mismo y el motor ya no
        #    necesita adivinar. Enero da 188,671.79, que es exactamente lo que
        #    dice el cuadro del owner.
        ebts = {f.month: Decimal(str(f.amount_usd or 0)) for f in (await s.execute(
            select(ActualPLLine).where(ActualPLLine.scenario_id == e.id,
                                       ActualPLLine.line_code == "EBT"))).scalars().all()}
        await s.execute(delete(ActualPLLine).where(
            ActualPLLine.scenario_id == e.id, ActualPLLine.line_code == "NET_PROFIT"))
        for i in range(12):
            s.add(ActualPLLine(scenario_id=e.id, month=i + 1, line_code="NET_PROFIT",
                               amount_usd=ebts.get(i + 1, Decimal("0")) - MONTOS[i]))
        await s.commit()
        print("escrito: detalle, impuesto y neto")

    async with get_session() as s:
        e = (await s.execute(select(Scenario).where(
            Scenario.year == 2026, Scenario.type == "BUDGET"))).scalars().first()
        ebt, imp, neto = await _pl(s, e)
        print(f"DESPUES EBT {ebt:>13,.2f}   impuesto {imp:>11,.2f}   neto {neto:>13,.2f}")
        # El neto tiene que ser el mismo: solo se abrio por mes lo que ya estaba.
        if abs(neto - 13228.85) < 1.0:
            e.status = "locked"
            await s.commit()
            print("vuelto a enllavar")
        else:
            print("OJO: el neto no dio 13,228.85 — queda en draft para revisar")


asyncio.run(main())
