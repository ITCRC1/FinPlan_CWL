# -*- coding: utf-8 -*-
"""Le pone NÚMERO al pendiente 1 del Break-Even: ¿cuánto mueve ajustar los %?

    python -m scripts.mover_los_porcentajes                 # los 3 escenarios
    python -m scripts.mover_los_porcentajes <scenario_id>   # uno solo

**SOLO LECTURA.** No escribe una fila. Clona las reglas en memoria, les cambia
el `pct_variable` y vuelve a correr el MISMO motor del módulo — así lo que sale
es exactamente lo que el owner vería en pantalla si moviera los porcentajes.

## Por qué existe

`docs/PENDIENTES.md` A0.-10 punto 1 dice que la semilla 100/0 «no es un
diagnóstico» y que al marcar la planilla fija el equilibrio «va a subir de forma
material». Eso estaba escrito pero **no medido**: sin el número, el owner tiene
que decidir a ciegas cuánto le importa el ajuste.

## Los cinco cortes que mide

| | qué cambia | por qué |
|---|---|---|
| BASE | nada — la semilla como está hoy | el punto de partida |
| A | planilla del **Spa** → 100% variable | incoherencia contable de A0.-10 §2: las MISMAS cuentas GL están `Variable` en Rooms, F&B y Tours |
| B | `Renting – Transfers Cost` → 100% variable | idem: está `Fixed Cost` siendo costo de venta |
| C | **toda** la planilla → 100% fija | la realidad de CWL: personal de planta. Es el corte que el owner tiene que mirar |
| D | A + B + C | los tres juntos |

⚠️ A y B **bajan** el equilibrio y C lo **sube**. Un ajuste que baja el
equilibrio se lee como buena noticia y por eso hay que verlos separados: si
salieran mezclados, C podría tapar a A+B o al revés.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

#: Los tres que el owner mira. Uno por tipo de dato, porque el módulo exige que
#: el `data_version` coincida con el tipo del escenario.
ESCENARIOS = [
    ("df32afa3-7711-43b8-9586-a01a22b2473b", "BUDGET Final 2026", "BUDGET"),
    ("294f775d-ada2-4a9c-8f72-95d2dfec2eb4", "BUDGET Working 2027", "BUDGET"),
    ("fcb1ab27-96c9-421c-95d8-81e2fb8b8329", "ACTUAL 2025", "ACTUAL"),
]

UNO = Decimal("1")
CERO = Decimal("0")


def _clonar(reglas, cambio):
    """Copia las reglas aplicando `cambio(regla) -> pct | None`."""
    import dataclasses
    out = []
    for r in reglas:
        nuevo = cambio(r)
        out.append(r if nuevo is None
                   else dataclasses.replace(r, pct_variable=Decimal(str(nuevo))))
    return out


def _spa_payroll(r):
    return UNO if (r.be_section == "PAYROLL" and r.dept_slug == "spa") else None


def _renting(r):
    return UNO if r.pl_line == "COS_TRANSPORTATION" else None


def _payroll_fija(r):
    return CERO if r.be_section == "PAYROLL" else None


def _combinado(r):
    # C se aplica DESPUÉS de A: la planilla del Spa termina fija, como el resto.
    if r.be_section == "PAYROLL":
        return CERO
    return _renting(r)


CORTES = [
    ("BASE   semilla de hoy", None),
    ("A      Spa planilla -> 100% variable", _spa_payroll),
    ("B      Renting Transfers -> 100% variable", _renting),
    ("C      TODA la planilla -> 100% fija", _payroll_fija),
    ("D      A + B + C juntos", _combinado),
]


def _f(x, dec=0):
    if x is None:
        return "     —"
    return f"{float(x):,.{dec}f}"


async def medir(scenario_id: str, etiqueta: str, data_version: str) -> None:
    from app.engine import break_even as be
    from app.api.break_even_api import (
        montos_del_escenario, _reglas, pl_engine_totales,
    )
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from sqlalchemy import select

    async with SessionLocal() as db:
        s = (await db.execute(
            select(Scenario).where(Scenario.id == scenario_id))).scalar_one()
        montos = await montos_del_escenario(db, s, 0)
        reglas = await _reglas(db)
        pl = await pl_engine_totales(db, s, 0)

    print(f"\n{'='*100}")
    print(f"  {etiqueta}   ·   ingreso {_f(pl['revenue'], 2)}   ·   "
          f"{len(montos)} montos   ·   {len(reglas)} reglas")
    print(f"{'='*100}")
    print(f"{'corte':<42} {'variable':>13} {'fijo':>13} {'CM%':>7} "
          f"{'EQUILIBRIO':>14} {'ocup.eq':>8} {'holgura':>13}")
    print("-" * 100)

    base = None
    for nombre, cambio in CORTES:
        rs = reglas if cambio is None else _clonar(reglas, cambio)
        r = be.calcular(
            data_version=data_version, revenue=pl["revenue"],
            revenue_rooms=pl["revenue_rooms"], montos=montos, reglas=rs,
            adr=pl["adr"], rooms_available=pl["rooms_available"],
        )
        if base is None:
            base = r
        ocup = (f"{float(r.be_occupancy)*100:5.1f}%"
                if r.be_occupancy is not None else "    —")
        cm = f"{float(r.cm_pct)*100:5.1f}%" if r.cm_pct else "    —"
        print(f"{nombre:<42} {_f(r.variable_cost):>13} {_f(r.fixed_cost):>13} "
              f"{cm:>7} {_f(r.be_revenue):>14} {ocup:>8} "
              f"{_f(r.margin_of_safety):>13}")
        if cambio is not None and base.be_revenue and r.be_revenue:
            d = r.be_revenue - base.be_revenue
            signo = "sube" if d > 0 else "baja"
            print(f"{'':>42} {'':>13} {'':>13} {'':>7} "
                  f"{'(' + signo + ' ' + _f(abs(d)) + ')':>14}")

    print(f"\n  sin clasificar: {len(base.sin_clasificar)} montos "
          f"({_f(sum(x.amount for x in base.sin_clasificar), 2)})   ·   "
          f"reglas sin monto: {len(base.reglas_huerfanas)}")
    print(f"  neto del motor: {_f(base.net, 2)}")


async def main() -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()

    pedidos = ESCENARIOS
    if len(sys.argv) > 1:
        pedidos = [e for e in ESCENARIOS if e[0] == sys.argv[1]]
        if not pedidos:
            print("escenario no está en la lista de este medidor")
            return 2
    for sid, etiqueta, dv in pedidos:
        await medir(sid, etiqueta, dv)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
