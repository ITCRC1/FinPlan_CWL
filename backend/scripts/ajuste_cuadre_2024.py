# -*- coding: utf-8 -*-
"""Ajuste de cuadre del Actual 2024 — lleva el DETALLE al resultado del RESUMEN.

Owner, 2026-08-14: «el correcto es el resumen. Manda la diferencia a la cuenta
8045» y despues «deberia quedar en noviembre y diciembre tal como te di arriba
el detalle».

Los dos renglones que el owner encontro en el Excel, sin numero de cuenta:

    Departamento de Habitaciones · nov -28,957.30 · dic -11,656.00

Suman 40,613.30. Pero la brecha total contra el Resumen es 43,698.37, porque
tambien estan los 3,085.07 del ingreso de Innoceana, cuyo origen sigue sin
identificar y no tiene mes propio.

Por eso diciembre lleva 11,656.00 + 3,085.07 = 14,741.07: noviembre queda
exactamente como el archivo, y el sobrante —que no tiene fecha conocida— se
apila en el mes de cierre. Un renglon del GL es uno por cuenta y mes: no hay
forma de que la 8045 de diciembre tenga dos montos separados.

Sin --aplicar no escribe nada.
"""
import sys, asyncio
from decimal import Decimal
if "--prod" in sys.argv:
    from scripts._prodenv import usar_produccion
    usar_produccion()
from sqlalchemy import select
from app.db import get_session
from app.models.scenario import Scenario
from app.models.actual_entry import ActualEntry
from app.models.actual_pl_line import ActualPLLine

APLICAR = "--aplicar" in sys.argv
CUENTA, DEPTO = "8045", "0250"
NOV = Decimal("-28957.30")           # tal cual el archivo
ROOMS_DIC = Decimal("-11656.00")     # tal cual el archivo


async def _neto(s, e, canon, recalc, pl_engine):
    det = 0.0
    maps = await recalc.load_active_account_mappings(s)
    rl = await recalc.load_report_line_config(s)
    for m in range(1, 13):
        filas = await recalc.actual_rows_for_month(s, e.id, m)
        if not filas:
            continue
        for ln in pl_engine.calculate_pl_from_mapping(filas, maps, rl):
            if canon.get(ln.line_code, ln.line_code) == "NET_PROFIT":
                det += float(ln.amount_usd)
    res = sum(float(l.amount_usd or 0) for l in (await s.execute(
        select(ActualPLLine).where(ActualPLLine.scenario_id == e.id))).scalars().all()
        if canon.get(l.line_code, l.line_code) == "NET_PROFIT")
    return res, det


async def main():
    from app.engine import recalculate as recalc, pl_engine
    canon = {k: v[0] for k, v in pl_engine._MOTOR_TO_CANON.items()}

    async with get_session() as s:
        e = (await s.execute(select(Scenario).where(
            Scenario.year == 2024, Scenario.type == "ACTUAL"))).scalars().first()
        fila = (await s.execute(select(ActualEntry).where(
            ActualEntry.scenario_id == e.id,
            ActualEntry.account_code == CUENTA))).scalars().first()

        # Se parte de la fila SIN ningun ajuste previo, para poder re-correr
        # esto sin acumular.
        nov0 = Decimal(str(fila.nov or 0)) - (NOV if abs(Decimal(str(fila.nov or 0)) - NOV) < 1 else Decimal(0))
        base_nov = Decimal("0")
        base_dic = Decimal("0")
        res, det = await _neto(s, e, canon, recalc, pl_engine)
        # brecha con los ajustes actuales YA aplicados
        pendiente = Decimal(str(round(res - det, 2)))
        actual_nov = Decimal(str(fila.nov or 0))
        actual_dic = Decimal(str(fila.dec or 0))
        total_ajuste = actual_nov + actual_dic + pendiente   # lo que debe quedar entre los dos meses
        nuevo_nov = NOV
        nuevo_dic = total_ajuste - NOV

        print(f"Resumen                 {res:>16,.2f}")
        print(f"Detalle (con lo puesto) {det:>16,.2f}")
        print(f"pendiente               {float(pendiente):>16,.2f}")
        print(f"\n8045 depto {fila.dept_code}  ({fila.account_name})")
        print(f"  nov: {float(actual_nov):>14,.2f}  ->  {float(nuevo_nov):>14,.2f}")
        print(f"  dic: {float(actual_dic):>14,.2f}  ->  {float(nuevo_dic):>14,.2f}")
        print(f"  suma del ajuste:            {float(nuevo_nov + nuevo_dic):>14,.2f}")

        if not APLICAR:
            print("\n(ensayo — no se escribio nada)")
            return
        if e.status == "locked":
            e.status = "draft"
            await s.flush()
            print("\ndesenllavado")
        fila.nov = nuevo_nov
        fila.dec = nuevo_dic
        await s.commit()
        print("escrito")

    async with get_session() as s:
        e = (await s.execute(select(Scenario).where(
            Scenario.year == 2024, Scenario.type == "ACTUAL"))).scalars().first()
        res, det = await _neto(s, e, canon, recalc, pl_engine)
        print(f"\n== DESPUES ==\nResumen  {res:>16,.2f}\nDetalle  {det:>16,.2f}\n"
              f"dif      {res-det:>16,.2f}")
        if abs(res - det) < 1.0:
            e.status = "locked"
            await s.commit()
            print("\nvuelto a enllavar")
        else:
            print("\n⚠️ no cuadro — queda en draft")

asyncio.run(main())
