"""Empuja el Room Revenue de los drivers a la línea ROOMS del checkbook.

**Por qué existe.** El ingreso de Rooms tiene dos fuentes que pueden separarse:
los drivers (tarifa × ocupación, abiertos POR CATEGORÍA de habitación) y la
línea `ROOMS` del checkbook, que es la única que ve el P&L cuando el escenario
tiene `revenue_source = 'checkbook'`. Cuando nace una categoría nueva —Villas,
Residencias— los drivers la facturan y la línea del checkbook se queda con las
viejas. La plata no se pierde: nunca llega.

Eso fue exactamente el caso del Budget 2027 Working: la línea traía
$3,560,260.57 —el Standard clavado al centavo— y los drivers $3,886,972.74.
Los $326,712.17 de diferencia eran Villas ($233,365.80) y Residencias
($93,346.32), que se crearon después de que esa línea se llenó.

**Qué toca.** SOLO la línea ROOMS. El botón «Llenar desde drivers» de la
pantalla reescribe ocho líneas (Food, Beverage, Tours, Transport, Retail,
Innoceana, Sustainability) con las tarifas que estén cargadas en la pantalla en
ese momento; acá eso no se toca, porque el descuadre es de Rooms y de nada más.

**Qué NO toca.** Escenarios enllavados: se niega. Un escenario cerrado es una
foto, y reescribirle el ingreso es reescribir historia.

Uso:
    python -m scripts.empujar_rooms_al_checkbook <scenario_id>            # ensayo
    python -m scripts.empujar_rooms_al_checkbook <scenario_id> --aplicar
    python -m scripts.empujar_rooms_al_checkbook <scenario_id> --prod --aplicar

Sin `--aplicar` no escribe nada: imprime el antes y el después y se va.
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal, ROUND_HALF_UP

# `--prod` tiene que resolverse ANTES de importar `app.*`: `app.db` arma el
# engine al importarse, y después ya no hay a dónde reapuntarlo.
if "--prod" in sys.argv:
    from scripts._prodenv import usar_produccion
    usar_produccion()

from sqlalchemy import select  # noqa: E402

from app.api.revenue_api import _load_revenue_data  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.engine.recalculate import recalculate_scenario  # noqa: E402
from app.engine.revenue_calculator import room_type_breakdown  # noqa: E402
from app.models.revenue_entry import RevenueEntry  # noqa: E402
from app.models.room_type_config import RoomTypeConfig  # noqa: E402
from app.models.scenario import Scenario  # noqa: E402

ETIQUETAS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
             "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
CENTAVO = Decimal("0.01")


def _centavos(v: Decimal) -> Decimal:
    return Decimal(v).quantize(CENTAVO, rounding=ROUND_HALF_UP)


async def room_revenue_por_mes(db, scenario: Scenario) -> tuple[
        list[Decimal], dict[str, Decimal]]:
    """Room Revenue de los drivers: total por mes y total por categoría.

    Suma TODAS las categorías activas del hotel, no una lista fija. Si mañana
    nace otra categoría, entra sola — que es justo lo que falló la vez pasada.
    """
    data = await _load_revenue_data(scenario.id, db)
    unidades = {t.id: t.units for t in data["room_types"]}

    rates_por_mes: dict[int, list] = {}
    for rc in data["rate_cards"]:
        rates_por_mes.setdefault(rc.month, []).append(rc)
    occ_por_mes: dict[int, list] = {}
    for ob in data["occupancies"]:
        occ_por_mes.setdefault(ob.month, []).append(ob)

    nombres = {c.id: c.name for c in (await db.execute(select(RoomTypeConfig).where(
        RoomTypeConfig.hotel_id == scenario.hotel_id,
        RoomTypeConfig.active == True,  # noqa: E712
    ))).scalars()}

    por_mes = [Decimal(0)] * 12
    por_categoria: dict[str, Decimal] = {}
    for m in range(1, 13):
        for r in room_type_breakdown(m, rates_por_mes.get(m, []),
                                     occ_por_mes.get(m, []), unidades):
            rev = Decimal(str(r.get("revenue") or 0))
            por_mes[m - 1] += rev
            etiqueta = nombres.get(r["room_type_id"], r["room_type_id"])
            por_categoria[etiqueta] = por_categoria.get(etiqueta, Decimal(0)) + rev
    return [_centavos(v) for v in por_mes], por_categoria


async def main(scenario_id: str, aplicar: bool) -> int:
    async with SessionLocal() as db:
        scenario = (await db.execute(
            select(Scenario).where(Scenario.id == scenario_id))).scalar_one_or_none()
        if scenario is None:
            print(f"No existe el escenario {scenario_id}")
            return 1

        etiqueta = f"{scenario.type} {scenario.version} {scenario.year}"
        print(f"Escenario: {etiqueta}  ({scenario.id})")
        print(f"  revenue_source = {getattr(scenario, 'revenue_source', '?')}"
              f"   enllavado = {getattr(scenario, 'is_locked', False)}")

        if getattr(scenario, "is_locked", False):
            print("\n✗ Está enllavado. No se toca: un escenario cerrado es una foto.")
            return 1

        if getattr(scenario, "revenue_source", "drivers") != "checkbook":
            print("\n· Este escenario lee los DRIVERS directamente, así que la "
                  "línea del checkbook no la ve el P&L. No hay nada que empujar.")
            return 0

        fila = (await db.execute(select(RevenueEntry).where(
            RevenueEntry.scenario_id == scenario_id,
            RevenueEntry.line == "ROOMS"))).scalar_one_or_none()
        if fila is None:
            fila = RevenueEntry(scenario_id=scenario_id,
                                hotel_id=scenario.hotel_id, line="ROOMS")
            db.add(fila)
            print("  (la línea ROOMS no existía — se crea)")

        antes = [_centavos(Decimal(str(fila.get_month(m) or 0))) for m in range(1, 13)]
        despues, por_categoria = await room_revenue_por_mes(db, scenario)

        print("\n  Room Revenue de los drivers, por categoría:")
        for nombre, monto in sorted(por_categoria.items()):
            print(f"    {nombre:<44} {float(monto):>14,.2f}")

        print(f"\n  {'':>5} {'ROOMS hoy':>15} {'drivers':>15} {'delta':>14}")
        for i in range(12):
            d = despues[i] - antes[i]
            marca = "  ←" if d else ""
            print(f"  {ETIQUETAS[i]:>5} {float(antes[i]):>15,.2f} "
                  f"{float(despues[i]):>15,.2f} {float(d):>14,.2f}{marca}")
        t_antes, t_despues = sum(antes), sum(despues)
        print(f"  {'TOTAL':>5} {float(t_antes):>15,.2f} {float(t_despues):>15,.2f} "
              f"{float(t_despues - t_antes):>14,.2f}")

        if t_despues == t_antes and antes == despues:
            print("\n✓ Ya están sincronizados. No hay nada que escribir.")
            return 0

        if not aplicar:
            print("\n· Ensayo. Para escribirlo, volvé a correrlo con --aplicar.")
            return 0

        for m in range(1, 13):
            fila.set_month(m, despues[m - 1])
        await db.commit()
        print(f"\n✓ Línea ROOMS actualizada: {float(t_despues):,.2f}")

        print("· Recalculando el P&L…")
        await recalculate_scenario(db, scenario_id)
        print("✓ P&L recalculado.")
        return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(args[0], "--aplicar" in sys.argv)))
