# -*- coding: utf-8 -*-
"""Deja el `0250` (Property Expenses) con SOLO lo suyo: los gastos de la propiedad.

Owner, 2026-08-14: «ambos son lo mismo, inactivemos el que no tiene reglas» y
«**0250 no hay planilla, solo gastos de la propiedad**».

El `0240` y el `0250` son el MISMO departamento con dos codigos: el **dato**
esta en `0240` y las **10 reglas** del mapeo estan en `0250`. Como la plata esta
en el `0240`, no es inactivarlo: es **mover el dato**, y despues el `0240`
desaparece solo.

Dos movidas, las dos de ETIQUETA — no se toca ni un monto, ni un mes, ni una
cuenta:

  A. `belowgop_account_entries`: `0240` -> `0250`.
     Hoy esas cuentas 8xxx llegan a su linea por FALLBACK (tomando prestada la
     regla del `0250`, que es el unico depto con cuentas 8xxx); despues llegan a
     la MISMA linea por regla exacta.

  B. `revenue_account_entries`: `0250` -> `280`.
     Las 48xx de Miscelaneos/Sustainability no son gasto de la propiedad. Es la
     misma correccion que ya se aplico en `actual_entries`
     (`retag_0240_a_280.py`), sobre la tabla que quedo afuera. Tambien llegan
     hoy por FALLBACK a la misma linea a la que llegaran por regla exacta.

**El P&L no se mueve.** El script lo comprueba cuenta por cuenta ANTES de
escribir y aborta si alguna cambiaria de linea. Para el total, comparar con
`scripts.foto_pl_totales` antes y despues.

Uso:
    python -m scripts.consolidar_0240_en_0250 --prod              # ensayo
    python -m scripts.consolidar_0240_en_0250 --prod --aplicar
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

if "--prod" in sys.argv:
    from scripts._prodenv import usar_produccion
    usar_produccion()

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.engine import pl_engine  # noqa: E402
from app.engine.recalculate import load_active_account_mappings  # noqa: E402
from app.models.belowgop_account_entry import BelowGopAccountEntry  # noqa: E402
from app.models.revenue_account_entry import RevenueAccountEntry  # noqa: E402
from app.models.scenario import Scenario  # noqa: E402

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]

# (modelo, viejo, nuevo, por que)
MOVIDAS = [
    (BelowGopAccountEntry, "0240", "0250",
     "gastos de la propiedad (8xxx): el dato estaba en el codigo sin reglas"),
    (RevenueAccountEntry, "0250", "280",
     "ingreso de Miscelaneos/Sustainability (48xx): no es gasto de la propiedad"),
]


def _total(fila) -> Decimal:
    return sum(Decimal(str(getattr(fila, m) or 0)) for m in MESES)


async def _una_movida(db, resolve, nombres, Modelo, viejo, nuevo, motivo, aplicar) -> int:
    filas = [f for f in (await db.execute(select(Modelo))).scalars().all()
             if (f.dept_code or "").strip() == viejo]
    print(f"\n=== {Modelo.__tablename__}: {viejo} -> {nuevo} ===")
    print(f"    {motivo}")
    if not filas:
        print("    Nada que mover.")
        return 0

    print(f"\n    {len(filas)} filas\n")
    print(f"    {'escenario':<24} {'cuenta':<7} {'total':>14}  "
          f"{'linea hoy':<22} {'modo':<9} -> {'linea nueva':<22} modo")
    problemas = []
    for f in sorted(filas, key=lambda x: (nombres.get(x.scenario_id, ""),
                                          x.account_code or "")):
        r_viejo, modo_viejo = resolve(viejo, f.account_code)
        r_nuevo, modo_nuevo = resolve(nuevo, f.account_code)
        l_viejo = r_viejo.get("report_line_code") if r_viejo else None
        l_nuevo = r_nuevo.get("report_line_code") if r_nuevo else None
        print(f"    {nombres.get(f.scenario_id, '?'):<24} {f.account_code:<7} "
              f"{float(_total(f)):>14,.2f}  {str(l_viejo):<22} {modo_viejo:<9} -> "
              f"{str(l_nuevo):<22} {modo_nuevo}")
        if l_viejo != l_nuevo:
            problemas.append((f.account_code, l_viejo, l_nuevo))

    if problemas:
        print(f"\n    X ABORTADO: {len(problemas)} cuenta(s) cambiarian de linea "
              f"del P&L: {problemas}")
        return -1
    print("\n    OK Ninguna cuenta cambia de linea del P&L — solo el modo de ruteo.")

    if not aplicar:
        return 0

    # La llave unica es (scenario_id, dept_code, account_code): si el destino ya
    # tiene esa cuenta, se SUMA y se borra la de origen. Hoy no pasa en ninguna
    # de las dos tablas, pero re-etiquetar sin mirar la llave es como se pierde
    # una fila sin que nada avise.
    destino = {}
    for f in (await db.execute(select(Modelo))).scalars().all():
        if (f.dept_code or "").strip() == nuevo:
            destino[(f.scenario_id, (f.account_code or "").strip())] = f

    movidas = fusionadas = 0
    for f in filas:
        llave = (f.scenario_id, (f.account_code or "").strip())
        gemela = destino.get(llave)
        if gemela is None:
            f.dept_code = nuevo
            destino[llave] = f
            movidas += 1
        else:
            for m in MESES:
                setattr(gemela, m, (Decimal(str(getattr(gemela, m) or 0))
                                    + Decimal(str(getattr(f, m) or 0))))
            await db.delete(f)
            fusionadas += 1
    print(f"    OK {movidas} re-etiquetadas"
          + (f", {fusionadas} fusionadas con una fila ya existente en {nuevo}"
             if fusionadas else ""))
    return 0


async def main(aplicar: bool) -> int:
    async with SessionLocal() as db:
        resolve = pl_engine.construir_resolvedor(await load_active_account_mappings(db))
        nombres = {s.id: f"{s.type} {s.version} {s.year}" for s in
                   (await db.execute(select(Scenario))).scalars().all()}

        for Modelo, viejo, nuevo, motivo in MOVIDAS:
            if await _una_movida(db, resolve, nombres, Modelo,
                                 viejo, nuevo, motivo, aplicar) < 0:
                await db.rollback()
                return 1

        if not aplicar:
            print("\n· Ensayo. Para escribirlo, agrega --aplicar.")
            return 0
        await db.commit()
        print("\nOK Escrito.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
