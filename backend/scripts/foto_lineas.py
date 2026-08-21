# -*- coding: utf-8 -*-
"""Foto del P&L LINEA POR LINEA de todos los escenarios, para comparar.

## Por que existe, si ya esta `foto_pl_totales`

`foto_pl_totales` tiene dos puntos ciegos, y los dos aparecen justo cuando se
toca el mapeo:

1. **Solo mira 7 totales** (ingresos, gastos operativos, overhead, GOP, EBITDA,
   EBT, neto). Mover una cuenta de `OH_UTILITIES` a `OH_CLARO_HUERTA` le pasa
   por debajo: las dos suman al mismo overhead, asi que dice «IDENTICO» mientras
   dos lineas del reporte cambiaron. Es exactamente el modo de falla caro de
   este sistema — **el total cuadra y la plata cambio de linea sola**.

2. **Lee el mapeo de la BASE**, no del JSON. Un cambio en
   `seed_data/mapping_pl.json` no existe para la base hasta que el deploy corre
   el seed. Sacar la foto antes y despues de editar el JSON compara la base
   contra si misma: siempre da IDENTICO, y no probo nada.

Por eso, para un cambio de mapeo, la unica comparacion que dice algo es
**antes del deploy contra despues del deploy**, y **a nivel de linea**.

    python -m scripts.foto_lineas antes.json          # ANTES de pushear
    ...push, Railway despliega y corre el seed...
    python -m scripts.foto_lineas despues.json
    python -m scripts.foto_lineas --comparar antes.json despues.json
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

TOLERANCIA = 0.01


def comparar(a: str, b: str) -> int:
    x = json.load(open(a, encoding="utf-8"))
    y = json.load(open(b, encoding="utf-8"))
    malos = 0
    for esc in sorted(set(x) | set(y)):
        if esc not in x or esc not in y:
            print(f"  !! {esc}: esta en uno y no en el otro")
            malos += 1
            continue
        lineas = sorted(set(x[esc]) | set(y[esc]))
        for ln in lineas:
            va, vb = x[esc].get(ln, 0.0), y[esc].get(ln, 0.0)
            if abs(va - vb) > TOLERANCIA:
                print(f"  !! {esc:<26} {ln:<26} {va:>15,.2f} -> {vb:>15,.2f}"
                      f"  ({vb - va:+,.2f})")
                malos += 1
    print(f"\n{'SE MOVIO ALGO: ' + str(malos) + ' lineas' if malos else 'IDENTICO: ninguna linea se movio'}")
    return 1 if malos else 0


async def tomar(salida: str) -> None:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from app.api.pl_api import _monthly_results

    foto: dict[str, dict[str, float]] = {}
    async with SessionLocal() as db:
        escs = (await db.execute(select(Scenario))).scalars().all()
        for e in sorted(escs, key=lambda s: (s.year, s.type, s.version)):
            nombre = f"{e.type} {e.version} {e.year}"
            try:
                meses = await _monthly_results(db, e)
            except Exception as ex:                       # noqa: BLE001
                print(f"  !! {nombre}: {str(ex)[:70]}")
                continue
            tot: dict[str, float] = {}
            for m in meses:
                for ln in m["lines"]:
                    tot[ln.line_code] = tot.get(ln.line_code, 0.0) + float(ln.amount_usd)
            foto[nombre] = {k: round(v, 2) for k, v in tot.items()}
            print(f"  {nombre:<26} {len(tot)} lineas")
    pathlib.Path(salida).write_text(
        json.dumps(foto, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"\n{len(foto)} escenarios -> {salida}")


if __name__ == "__main__":
    if "--comparar" in sys.argv:
        i = sys.argv.index("--comparar")
        raise SystemExit(comparar(sys.argv[i + 1], sys.argv[i + 2]))
    if len(sys.argv) < 2:
        raise SystemExit("uso: python -m scripts.foto_lineas <salida.json>")
    raise SystemExit(asyncio.run(tomar(sys.argv[1])))
