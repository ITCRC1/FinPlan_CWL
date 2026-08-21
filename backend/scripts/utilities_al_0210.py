# -*- coding: utf-8 -*-
"""Las ocho cuentas de servicios se postean en Utilities `0210`, no en el `0205`.

Owner, 2026-08-14, sobre 7055 Chilled Water, 7105 Contract Services, 7160
Electricity, 7230 Gas, 7395 Oil & Gas, 7420 Other Fuels, 7550 Steam y 7710
Water/Sewer: **«todas estas cuentas son utilities, favor mover todo lo demas a
Claro del bosque»**.

Su propio archivo de orden (`ORDEN PARA EL UPLOAD.xlsx` ->
`seed_data/orden_plantilla.json`) dice lo mismo: el `0210` lista **esas ocho y
ninguna mas**, y el `0205` Claro del Bosque lista las otras 32.

## Es el DATO el que esta mal etiquetado, no la regla

El primer intento fue darle al `0205` reglas de mapeo que apuntaran a la linea
de Utilities. **Tres pruebas lo frenaron, con razon.** El 2026-08-13 el owner ya
habia separado estos dos departamentos justamente porque las 8 reglas de Utility
vivian bajo el `dept_code` 0205 — «dos departamentos distintos amontonados bajo
el mismo codigo». Darle otra vez reglas de Utilities al `0205` era volver a
mezclarlos, en la direccion contraria.

Si la 7395 es Utilities, entonces $1,5M de combustible de generador **estan
posteados en el departamento equivocado**. Se mueve el dato y cada departamento
se queda con sus propias reglas, intactas. Es la misma forma del
`consolidar_0240_en_0250.py`.

## No mueve el P&L

Hoy esas filas llegan a `OH_UTILITIES` por **DESCARTE**, tomando prestada la
regla del `0210`; despues llegan a la MISMA linea por **regla exacta**. El
script lo comprueba cuenta por cuenta antes de escribir y aborta si alguna
cambiaria.

Ademas cierra un desempate alfabetico: la 7160, la 7420 y la 7710 tienen DOS
reglas —`0210 -> OH_UTILITIES` y `260 -> OPEX_CLUB`— y hoy gana Utilities solo
porque «0210» va antes que «260». Son $44.675,67 cuya linea no la decidio nadie.

Uso:
    python -m scripts.utilities_al_0210 --prod              # ensayo
    python -m scripts.utilities_al_0210 --prod --aplicar
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
from app.models.actual_entry import ActualEntry  # noqa: E402
from app.models.cost_entry import CostEntry  # noqa: E402
from app.models.opex_entry import OpexEntry  # noqa: E402
from app.models.revenue_account_entry import RevenueAccountEntry  # noqa: E402
from app.models.scenario import Scenario  # noqa: E402

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]
TABLAS = (RevenueAccountEntry, CostEntry, OpexEntry, ActualEntry)

UTILITIES = {"7055", "7105", "7160", "7230", "7395", "7420", "7550", "7710"}

# La 7105 Contract Services esta en la lista del owner porque el `0210` la tiene,
# no porque sea de Utilities: es una cuenta COMPARTIDA que en su propio archivo
# de orden aparece en ONCE departamentos (0110, 0120, 0140, 0155, 0161, 0180,
# 0181, 0190, 0200, 0210 y 0205). El `0205` tiene regla propia para ella y sus
# servicios contratados son suyos, asi que no se mueve — moverla se llevaria el
# gasto de contratistas de la huerta a Utilities. La atajo el guard del script,
# que aborta si una cuenta cambiaria de linea del P&L. Hoy vale $0,00.
SE_QUEDAN = {"7105"}
MUEVEN = UTILITIES - SE_QUEDAN
HUERTA, UTIL = "0205", "0210"


def _total(fila) -> Decimal:
    return sum(Decimal(str(getattr(fila, m) or 0)) for m in MESES)


async def _mover(db, resolve, nombres, Modelo, viejo, nuevo, quiero, titulo,
                 aplicar) -> int:
    """`quiero(cuenta) -> bool` decide que filas del depto `viejo` se mueven."""
    filas = [f for f in (await db.execute(select(Modelo))).scalars().all()
             if (f.dept_code or "").strip() == viejo
             and quiero((f.account_code or "").strip())]
    if not filas:
        return 0

    print(f"\n--- {Modelo.__tablename__}: {titulo} ---")
    print(f"    {'escenario':<24} {'cuenta':<7} {'total':>14}  "
          f"{'linea hoy':<20} {'modo':<9} -> {'linea nueva':<20} modo")
    problemas = []
    for f in sorted(filas, key=lambda x: (nombres.get(x.scenario_id, ""),
                                          x.account_code or "")):
        cuenta = (f.account_code or "").strip()
        r_v, modo_v = resolve(viejo, cuenta)
        r_n, modo_n = resolve(nuevo, cuenta)
        l_v = r_v.get("report_line_code") if r_v else None
        l_n = r_n.get("report_line_code") if r_n else None
        print(f"    {nombres.get(f.scenario_id, '?'):<24} {cuenta:<7} "
              f"{float(_total(f)):>14,.2f}  {str(l_v):<20} {modo_v:<9} -> "
              f"{str(l_n):<20} {modo_n}")
        if l_v != l_n:
            problemas.append((cuenta, l_v, l_n))

    if problemas:
        print(f"\n    X ABORTADO: {len(problemas)} cuenta(s) cambiarian de linea "
              f"del P&L: {problemas}")
        return -1

    if not aplicar:
        return len(filas)

    # Llave unica: (scenario_id, dept_code, account_code). Si el destino ya tiene
    # esa cuenta se SUMA y se borra la de origen — re-etiquetar sin mirar la
    # llave revienta el UNIQUE o pierde una fila sin que nada avise.
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
                setattr(gemela, m, Decimal(str(getattr(gemela, m) or 0))
                        + Decimal(str(getattr(f, m) or 0)))
            await db.delete(f)
            fusionadas += 1
    print(f"    OK {movidas} re-etiquetadas"
          + (f", {fusionadas} fusionadas con una fila ya existente en {nuevo}"
             if fusionadas else ""))
    return len(filas)


async def main(aplicar: bool) -> int:
    async with SessionLocal() as db:
        resolve = pl_engine.construir_resolvedor(await load_active_account_mappings(db))
        nombres = {s.id: f"{s.type} {s.version} {s.year}" for s in
                   (await db.execute(select(Scenario))).scalars().all()}

        total = 0
        print(f"=== A. {HUERTA} -> {UTIL}: las siete de servicios "
              f"(la 7105 se queda, es compartida) ===")
        for Modelo in TABLAS:
            n = await _mover(db, resolve, nombres, Modelo, HUERTA, UTIL,
                             lambda c: c in MUEVEN,
                             f"{HUERTA} -> {UTIL}", aplicar)
            if n < 0:
                await db.rollback()
                return 1
            total += n
        if total == 0:
            print("    Nada que mover.")

        print(f"\n=== B. {UTIL} -> {HUERTA}: todo lo demas ===")
        total_b = 0
        for Modelo in TABLAS:
            n = await _mover(db, resolve, nombres, Modelo, UTIL, HUERTA,
                             lambda c: c not in UTILITIES and c != "4999",
                             f"{UTIL} -> {HUERTA}", aplicar)
            if n < 0:
                await db.rollback()
                return 1
            total_b += n
        if total_b == 0:
            print("    Nada que mover: fuera de las ocho, el 0210 no tiene "
                  "una sola fila. (La 4999 no se toca: es el credito de "
                  "reparto y se anula contra su propia linea.)")

        if not aplicar:
            print("\n· Ensayo. Para escribirlo, agrega --aplicar.")
            return 0
        await db.commit()
        print("\nOK Escrito.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
