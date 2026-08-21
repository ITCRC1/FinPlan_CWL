# -*- coding: utf-8 -*-
"""Que reglas del break-even estan MUERTAS de verdad. SOLO LECTURA.

    python -m scripts.reglas_muertas_break_even

«Sin movimiento» es relativo al escenario que estas mirando: la semilla cubre
los 22 departamentos y cada escenario mueve una parte, asi que sobren reglas es
lo normal. Lo que si es basura es una regla que **no encuentra su cuenta en
NINGUN escenario**: esa suele ser una cuenta renombrada, o semilla cargada
contra un año que no existe.

Este medidor cruza los 20 escenarios y separa las dos cosas. No borra nada.
"""
from __future__ import annotations

import asyncio
import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


async def main() -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()

    from app.api import _be_base
    from app.api.break_even_api import _reglas
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from sqlalchemy import select

    async with SessionLocal() as db:
        escenarios = (await db.execute(select(Scenario))).scalars().all()
        reglas = await _reglas(db)

    #: Las llaves exactas que existen en la semilla.
    exactas = {(r.dept_code, r.account) for r in reglas if r.account}
    vivas: set[tuple[str, str]] = set()
    por_escenario: dict[str, int] = {}

    for s in escenarios:
        async with SessionLocal() as db:
            base = await _be_base.construir(db, s, 0)
        vistos = {(m.dept_code, m.account) for m in base.costos()}
        tocadas = exactas & vistos
        vivas |= tocadas
        por_escenario[f"{s.type} {s.version} {s.year}"] = len(tocadas)

    muertas = sorted(exactas - vivas)
    print(f"reglas con cuenta exacta: {len(exactas)}")
    print(f"  vivas en al menos un escenario: {len(vivas)}")
    print(f"  MUERTAS en los {len(escenarios)}: {len(muertas)}")

    print("\ncuantas usa cada escenario:")
    for nombre, n in sorted(por_escenario.items(), key=lambda kv: -kv[1]):
        print(f"   {nombre:<28} {n:>4}")

    if muertas:
        print("\nlas muertas, por departamento:")
        porde = collections.Counter(d for d, _ in muertas)
        for d, n in porde.most_common():
            print(f"   {d:>8} {n:>4}")
        print("\n(muestra)")
        for d, a in muertas[:25]:
            print(f"   {d}:{a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
