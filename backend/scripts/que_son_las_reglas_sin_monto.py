# -*- coding: utf-8 -*-
"""Que SON las reglas sin movimiento en ningun escenario. SOLO LECTURA.

No alcanza con «no aparece en ningun escenario»: eso puede significar dos cosas
muy distintas, y solo una justifica borrar.

  A) La cuenta NO EXISTE como combinacion valida (no esta en `account_mapping`):
     la regla apunta a algo que el sistema no sabe rutear. Basura real.
  B) La cuenta EXISTE y esta bien mapeada, pero nadie le presupuesto plata
     TODAVIA. Borrarla seria un error: el dia que alguien la use, cae al
     default 100% fijo y nadie se entera.
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
    from app.engine.recalculate import load_active_account_mappings
    from app.models.scenario import Scenario
    from sqlalchemy import select

    async with SessionLocal() as db:
        escenarios = (await db.execute(select(Scenario))).scalars().all()
        reglas = await _reglas(db)
        mappings = await load_active_account_mappings(db)

    por_llave = {(r.dept_code, r.account): r for r in reglas if r.account}
    vivas: set[tuple[str, str]] = set()
    for s in escenarios:
        async with SessionLocal() as db:
            base = await _be_base.construir(db, s, 0)
        vivas |= {(m.dept_code, m.account) for m in base.costos()}

    muertas = sorted(set(por_llave) - vivas)

    #: Las combinaciones que el mapeo SI sabe rutear.
    ruteables = {(str(m.get("dept_code") or ""), str(m.get("account_code") or ""))
                 for m in mappings}
    #: Y las cuentas que el mapeo conoce, en cualquier departamento.
    cuentas_conocidas = {c for _, c in ruteables}

    A, B, C = [], [], []
    for k in muertas:
        if k in ruteables:
            B.append(k)                       # valida y ruteable, sin plata aun
        elif k[1] in cuentas_conocidas:
            C.append(k)                       # la cuenta existe, ese depto no
        else:
            A.append(k)                       # ni la cuenta existe

    print(f"reglas con cuenta exacta : {len(por_llave)}")
    print(f"  vivas en algun escenario: {len(vivas & set(por_llave))}")
    print(f"  sin movimiento en los {len(escenarios)}: {len(muertas)}\n")
    print(f"  A · ni la cuenta existe en el mapeo      : {len(A)}"
          "   <- basura real")
    print(f"  B · combinacion VALIDA, sin plata todavia: {len(B)}"
          "   <- BORRARLAS SERIA UN ERROR")
    print(f"  C · la cuenta existe, ese depto no       : {len(C)}")

    for etq, grupo in (("A", A), ("B", B), ("C", C)):
        if not grupo:
            continue
        print(f"\n--- {etq} por departamento:")
        for d, n in collections.Counter(d for d, _ in grupo).most_common(8):
            print(f"      {d:>8} {n:>4}")
        print(f"    muestra: {', '.join(f'{d}:{a}' for d, a in grupo[:8])}")

    print("\n--- de donde salieron (source_rows), muestra de 10 muertas:")
    for k in muertas[:10]:
        r = por_llave[k]
        print(f"   {k[0]}:{k[1]:<8} {r.account_name[:38]:<38} "
              f"seccion={r.be_section[:18]:<18} pct={r.pct_variable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
