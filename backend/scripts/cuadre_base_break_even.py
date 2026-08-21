# -*- coding: utf-8 -*-
"""¿La base del break-even pega con el P&L? SOLO LECTURA.

    python -m scripts.cuadre_base_break_even

Corre `_be_base.construir` contra los escenarios vivos y compara, escenario por
escenario:

* el **ingreso** de la base contra el `TOTAL_REVENUES` del P&L;
* la **base de costo** contra la que devolvía `montos_del_escenario`, que es la
  que ya estaba validada — si esto se mueve un centavo, la capa nueva cambió
  algo que nadie pidió que cambiara;
* a dónde va el ingreso por departamento, y cuánto queda sin departamento.
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
    ("8afbc06b-c3e7-466c-b11f-c6325397601e", "FORECAST April 2026", "FORECAST"),
    ("fcb1ab27-96c9-421c-95d8-81e2fb8b8329", "ACTUAL 2025", "ACTUAL"),
    ("1eb311e2-d9dd-4d52-a3ab-db4aac8b889b", "ACTUAL 2024", "ACTUAL"),
]


def f(x, d=2):
    return f"{float(x):,.{d}f}"


async def main() -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()

    from app.api import _be_base
    from app.api.break_even_api import montos_del_escenario, pl_engine_totales
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from sqlalchemy import select

    malos = 0
    for sid, etq, _dv in ESCENARIOS:
        async with SessionLocal() as db:
            s = (await db.execute(
                select(Scenario).where(Scenario.id == sid))).scalar_one()
            base = await _be_base.construir(db, s, 0)
            viejos = await montos_del_escenario(db, s, 0)
            pl = await pl_engine_totales(db, s, 0)

        print(f"\n{'='*88}\n  {etq}\n{'='*88}")

        # 1 · el ingreso contra el P&L
        for c in _be_base.validar_contra_pl(base, pl["revenue"]):
            marca = "OK " if c.cuadra else "!! "
            print(f"  {marca}{c.concepto:<24} base {f(c.base):>16}   "
                  f"P&L {f(c.pl):>16}   dif {f(c.diferencia):>12}")
            if not c.cuadra:
                malos += 1

        # 2 · la base de COSTO no se puede haber movido
        nuevos = base.costos()
        sv = sum((m.amount for m in viejos), Decimal("0"))
        sn = sum((m.amount for m in nuevos), Decimal("0"))
        igual = (len(viejos) == len(nuevos)) and abs(sv - sn) <= Decimal("0.005")
        print(f"  {'OK ' if igual else '!! '}base de costo           "
              f"antes {len(viejos):>5} filas {f(sv):>16}   "
              f"ahora {len(nuevos):>5} filas {f(sn):>16}")
        if not igual:
            malos += 1

        # 3 · a dónde fue el ingreso
        gl = base.total_ingreso_del_gl()
        print(f"  control cruzado: el GL trae {f(gl):>16} de ingreso"
              + ("   (vacío: escenario por drivers)" if not gl else ""))
        pord = base.ingreso_por_departamento()
        huerfano = base.ingreso_sin_departamento()
        print(f"  ingreso por departamento ({len(pord)}):")
        for slug, v in sorted(pord.items(), key=lambda kv: -abs(kv[1])):
            gen = base.genera_ingreso.get(slug)
            nota = "" if gen else "   <-- marcado SIN ingreso en be_department"
            print(f"      {slug:<20} {f(v):>16}{nota}")
        if huerfano:
            sueltas = sorted(((l, m) for l, m in base.ingreso_pl.items()
                              if not base.depto_de_linea.get(l) and m),
                             key=lambda kv: -abs(kv[1]))
            print(f"      {'(SIN DEPARTAMENTO)':<20} {f(huerfano):>16}")
            for l, m in sueltas:
                print(f"          {l:<24} {f(m):>16}")

    print(f"\n{'='*88}")
    print("TODO CUADRA" if not malos else f"{malos} cuadre(s) fuera de tolerancia")
    return 0 if not malos else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
