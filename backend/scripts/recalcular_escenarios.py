# -*- coding: utf-8 -*-
"""Recalcula el P&L de los escenarios que el mixer gobierna.

**Por que existe.** Aplicar el mixer escribe el factor nuevo, pero el P&L sigue
mostrando el numero viejo hasta que se recalcula. Entre una cosa y la otra el
escenario queda en un estado que no avisa: el factor dice 0.7970 y los reportes
siguen contando la historia de 0.8220.

La pantalla tiene el boton, pero mientras no suba (tope de deploys de Vercel)
esto hace lo mismo.

    python -m scripts.recalcular_escenarios              # los que gobierna el mixer
    python -m scripts.recalcular_escenarios --listar     # ver que haria, sin tocar
    python -m scripts.recalcular_escenarios "BUDGET Working 2027"

Va de uno en uno a proposito: recalcular recorre los 12 meses y reescribe el P&L
entero. Varios a la vez tumban el backend y el error llega como un fallo
cualquiera, sin decir que fue por eso.
"""
import asyncio
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


async def main(argv: list[str]):
    solo_listar = "--listar" in argv
    nombres = [a for a in argv if not a.startswith("--")]

    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import get_session
    from app.models.scenario import Scenario
    from app.engine import mixer_canales as mixer
    from app.engine.recalculate import recalculate_scenario

    async with get_session() as s:
        escs = list((await s.execute(select(Scenario).order_by(
            Scenario.year, Scenario.type, Scenario.version))).scalars())

    def etiqueta(e) -> str:
        return f"{e.type} {e.version} {e.year}"

    if nombres:
        pedido = " ".join(nombres).lower()
        objetivo = [e for e in escs if etiqueta(e).lower() == pedido]
        if not objetivo:
            print(f"No encontre '{' '.join(nombres)}'. Hay:")
            for e in escs:
                print("  ", etiqueta(e))
            return 1
    else:
        objetivo = [e for e in escs if mixer.gobierna(e)[0]]

    print(f"\n{len(objetivo)} escenario(s):")
    for e in objetivo:
        print("  ", etiqueta(e))
    if solo_listar:
        print("\n(--listar: no se toco nada)")
        return 0

    print()
    listos, fallaron = 0, []
    for e in objetivo:
        print(f"  recalculando {etiqueta(e):32} ", end="", flush=True)
        try:
            async with get_session() as s:
                r = await recalculate_scenario(s, e.id)
                await s.commit()
            # `recalculate_scenario` devuelve distinto segun la version; se
            # reporta lo que haya sin asumir una forma concreta.
            detalle = ""
            if isinstance(r, dict):
                detalle = " ".join(f"{k}={v}" for k, v in r.items()
                                   if isinstance(v, (int, float, str)))
            print(f"ok {detalle}")
            listos += 1
        except Exception as ex:  # noqa: BLE001 — se reporta y se sigue
            print(f"FALLO: {type(ex).__name__}: {ex}")
            fallaron.append(etiqueta(e))

    print(f"\nRecalculados {listos} de {len(objetivo)}.")
    if fallaron:
        # Los que fallaron quedan con el factor nuevo y el P&L viejo: hay que
        # decirlo fuerte, porque ese estado no se nota mirando un reporte.
        print(f"NO se pudo con: {', '.join(fallaron)}")
        print("Esos siguen con el factor nuevo escrito y el P&L viejo.")
    return 1 if fallaron else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
