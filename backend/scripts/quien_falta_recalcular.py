# -*- coding: utf-8 -*-
"""Que escenarios quedaron con el factor nuevo escrito y el P&L viejo.

**El estado que no avisa.** Aplicar el mixer escribe el factor; el P&L se queda
con el numero anterior hasta que alguien recalcula. En el medio el escenario se
ve perfectamente normal: los reportes cuadran, nada falla, y estan contando la
historia del factor viejo.

La cola del boton en la pantalla es de la sesion: si se recarga, se pierde. Esto
lo lee de la base, asi que sirve aunque nadie se acuerde de que aplico.

    python -m scripts.quien_falta_recalcular
"""
import asyncio
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


async def main() -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import get_session
    from app.models.scenario import Scenario
    from app.engine import mixer_canales as mixer

    async with get_session() as s:
        escs = list((await s.execute(select(Scenario).order_by(
            Scenario.year, Scenario.type, Scenario.version))).scalars())

    listos, faltan = [], []
    for e in escs:
        if not mixer.gobierna(e)[0]:
            continue
        (listos if e.last_recalc_at else faltan).append(e)

    print(f"\n{'escenario':30} {'ultimo recalculo':26}")
    print("-" * 58)
    for e in listos + faltan:
        cuando = str(e.last_recalc_at) if e.last_recalc_at else "NUNCA"
        print(f"{e.type + ' ' + e.version + ' ' + str(e.year):30} {cuando:26}")

    if faltan:
        print(f"\nFALTAN {len(faltan)}: tienen el factor nuevo y el P&L viejo.")
        print("Se arreglan con el boton Recalcular en Master Data -> Canales,")
        print("que corre en el backend y tarda segundos por escenario.")
        print("")
        print("Ojo: un escenario en NUNCA puede estar simplemente VACIO — sin")
        print("datos cargados no hay P&L que actualizar. Se ve igual en esta")
        print("lista y no es lo mismo.")
    else:
        print(f"\nLos {len(listos)} estan recalculados.")
    return 1 if faltan else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
