# -*- coding: utf-8 -*-
"""Que escenarios usan de verdad el mix de canales, y cuales no.

El motor de revenue prefiere el factor EFECTIVO de las tarifas
(`net_rate / rack_rate`) sobre el que sale del mix de canales. O sea que en un
escenario con tarifas netas cargadas, aplicar el mixer escribe las filas y NO
mueve un solo numero. Esto lo mide en vez de suponerlo.

    python -m scripts.quien_usa_el_mix
"""
import asyncio
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


async def main():
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from decimal import Decimal
    from sqlalchemy import select
    from app.db import get_session
    from app.models.scenario import Scenario
    from app.models.rate_card import RateCard
    from app.models.sales_channel_config import SalesChannelConfig, compute_net_factor
    from app.engine.revenue_calculator import _effective_net_factor
    from app.engine import mixer_canales as mixer
    from app.models.canal_comercial import CanalComercial

    async with get_session() as s:
        base = list((await s.execute(select(CanalComercial).where(
            CanalComercial.activo.is_(True)).order_by(CanalComercial.orden))).scalars())
        nf_mixer = mixer.net_factor(mixer.derivar(mixer.resolver(base, [])))
        print(f"mix base cargado: {len(base)} canales, suma "
              f"{float(mixer.suma_del_mix(base)):.4f}, net factor {float(nf_mixer):.4f}\n")

        escs = list((await s.execute(select(Scenario).order_by(
            Scenario.year, Scenario.type, Scenario.version))).scalars())
        print(f"{'escenario':34} {'gobierna':9} {'manda':10} {'nf tarifas':>11} {'nf mix':>9}")
        print("-" * 78)
        for e in escs:
            aplica, motivo = mixer.gobierna(e)
            rcs = list((await s.execute(select(RateCard).where(
                RateCard.scenario_id == e.id))).scalars())
            chs = list((await s.execute(select(SalesChannelConfig).where(
                SalesChannelConfig.scenario_id == e.id))).scalars())
            enf = _effective_net_factor(rcs)
            # POR MES, igual que el motor: sumar las 36 filas daria 12 veces el
            # factor real. El motor filtra `[c for c in channels if c.month == m]`.
            m1 = min((c.month for c in chs), default=0)
            nf_ch = compute_net_factor([c for c in chs if c.month == m1]) if chs else None
            manda = "TARIFAS" if enf else ("mix" if chs else "-")
            print(f"{e.type + ' ' + e.version + ' ' + str(e.year):34} "
                  f"{'si' if aplica else 'no':9} {manda:10} "
                  f"{(f'{float(enf):.4f}' if enf else '-'):>11} "
                  f"{(f'{float(nf_ch):.4f}' if nf_ch is not None else '-'):>9}")


if __name__ == "__main__":
    asyncio.run(main())
