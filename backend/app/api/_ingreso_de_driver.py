# -*- coding: utf-8 -*-
"""Lo que calcula un driver de ingreso aterriza en las DOS fuentes.

## El agujero que esto cierra

Un driver de ingreso —el Spa con su capture rate, el Club con su cuota— no se
guarda el resultado en su propia tabla y ya: tiene que dejarlo en la fuente de
ingresos **que el P&L lee**. El problema era que hay dos, según el modo del
escenario:

    modo `checkbook` → `RevenueEntry`   (una fila por línea, doce columnas)
    modo `drivers`   → `RevenueOther`   (una fila por línea × mes)

y los drivers escribían **solo en la primera**. En un escenario en modo
`drivers` uno guardaba, la pantalla mostraba el ingreso, y el estado de
resultados seguía en cero: sin excepción, sin 4xx, sin nada en los logs. Se
descubre semanas después, cuando no cuadra un total. Es exactamente lo que le
pasó al Club Madresal — $125.180 al año que no llegaban.

## La regla, y por qué no es un puente para el Club

**Un departamento no debería tener que saber en qué modo está su escenario.** Su
driver calcula el ingreso del departamento; el ingreso es el mismo en los dos
modos; entonces se deposita en los dos lados y se acabó la pregunta. No es un
caso especial del Club: es el camino de todos los drivers, y el Club dejó de
necesitar excepción justamente porque pasa por acá.

El día que un driver nuevo aparezca, lo único que tiene que hacer es llamar a
`persistir_ingreso_de_driver`. `tests/test_los_drivers_llegan_al_pl.py` falla si
alguno escribe una línea de ingreso por su cuenta.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from app.models.revenue_entry import REVENUE_LINES, RevenueEntry
from app.models.revenue_other import OTHER_REVENUE_LINES, RevenueOther

_MESES_COL = ["jan", "feb", "mar", "apr", "may", "jun",
              "jul", "aug", "sep", "oct", "nov", "dec"]


async def persistir_ingreso_de_driver(
    db, scenario, montos: dict[str, list[Decimal]],
) -> None:
    """Deja el ingreso calculado en `RevenueEntry` **y** en `RevenueOther`.

    `montos` es `{LINEA: [doce montos, enero primero]}`. Solo toca las líneas
    que vienen: mandar las del Club no roza la del Spa.
    """
    lineas = sorted(montos)
    desconocidas = [ln for ln in lineas if ln not in REVENUE_LINES]
    if desconocidas:
        raise ValueError(f"líneas de ingreso desconocidas: {desconocidas}")
    for ln, valores in montos.items():
        if len(valores) != 12:
            raise ValueError(f"{ln}: se esperaban 12 montos, vinieron {len(valores)}")

    sid = scenario.id
    dec = {ln: [Decimal(str(v or 0)) for v in vs] for ln, vs in montos.items()}

    # ── modo checkbook: una fila por línea, doce columnas ────────────────────
    filas = {e.line: e for e in (await db.execute(select(RevenueEntry).where(
        RevenueEntry.scenario_id == sid, RevenueEntry.line.in_(lineas),
    ))).scalars()}
    for ln in lineas:
        fila = filas.get(ln)
        if fila is None:
            fila = RevenueEntry(scenario_id=sid, hotel_id=scenario.hotel_id, line=ln)
            db.add(fila)
        for i, col in enumerate(_MESES_COL):
            setattr(fila, col, dec[ln][i])

    # ── modo drivers: una fila por línea × mes ───────────────────────────────
    # Una línea derivada (ROOMS, FOOD…) no vive en `RevenueOther`: ahí el motor
    # la calcula, y escribirla sería pisar el cálculo con una copia vieja.
    planas = [ln for ln in lineas if ln in OTHER_REVENUE_LINES]
    if not planas:
        return
    sueltas = {(o.line, o.month): o for o in (await db.execute(select(RevenueOther).where(
        RevenueOther.scenario_id == sid, RevenueOther.line.in_(planas),
    ))).scalars()}
    for ln in planas:
        for mes in range(1, 13):
            o = sueltas.get((ln, mes))
            if o is None:
                o = RevenueOther(id=str(uuid.uuid4()), scenario_id=sid,
                                 hotel_id=scenario.hotel_id, line=ln, month=mes,
                                 amount_usd=Decimal("0"))
                db.add(o)
            o.amount_usd = dec[ln][mes - 1]
