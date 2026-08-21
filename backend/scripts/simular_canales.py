# -*- coding: utf-8 -*-
"""Cuanto es en plata cada % del mix, A TARIFA RACK.

Owner (2026-08-14): «tiene que ser a tarifa rack». El mix se aplica sobre la
venta BRUTA y la comision se resta de ahi. Lo que esta en el P&L ya viene NETO,
asi que primero se devuelve a rack dividiendo por el factor vigente.

    python -m scripts.simular_canales "BUDGET Working 2027"
"""
import asyncio
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


def _ascii(t: str) -> str:
    """La consola de Windows es cp1252 y revienta con la raya larga de los
    nombres. Es cosmetico, pero un UnicodeEncodeError aborta el reporte entero."""
    return t.replace("—", "-").replace("–", "-")


async def main(nombre: str):
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from decimal import Decimal
    from sqlalchemy import select
    from app.db import get_session
    from app.models.scenario import Scenario
    from app.models.canal_comercial import CanalComercial
    from app.engine import mixer_canales as mixer
    from app.api.mixer_api import (_bases, _net_factor_vigente, LINEAS_COMISIONABLES)

    async with get_session() as s:
        escs = list((await s.execute(select(Scenario))).scalars())
        esc = next((e for e in escs
                    if f"{e.type} {e.version} {e.year}".lower() == nombre.lower()), None)
        if esc is None:
            print("No encontrado. Hay:")
            for e in escs:
                print("  ", f"{e.type} {e.version} {e.year}")
            return

        base = list((await s.execute(select(CanalComercial).where(
            CanalComercial.activo.is_(True)).order_by(CanalComercial.orden))).scalars())
        canales = mixer.resolver(base, [])
        nf_hoy, manda = await _net_factor_vigente(s, esc.id)
        bases = await _bases(s, esc.id)

    nf_nuevo = mixer.net_factor(mixer.derivar(canales))
    print(f"\n{esc.type} {esc.version} {esc.year}")
    print(f"factor vigente {float(nf_hoy):.4f} (sale de {manda})   "
          f"factor del mixer {float(nf_nuevo):.4f}\n")

    for etiqueta, clave in (("Solo habitaciones", "rooms"),
                            ("Venta comisionable", "comisionable"),
                            ("Total Revenue", "total")):
        neto = Decimal(str(bases[clave]))
        rack = neto / nf_hoy
        print(f"=== {etiqueta} ===")
        print(f"  neto en el P&L {float(neto):>14,.0f}")
        print(f"  venta rack     {float(rack):>14,.0f}   (neto / {float(nf_hoy):.4f})\n")
        print(f"  {'sub-canal':34} {'mix':>5} {'com':>5} "
              f"{'venta rack':>13} {'comision':>12} {'neto':>13}")
        tb = tc = Decimal(0)
        for c in canales:
            bruto = rack * c.mix_pct
            com = bruto * c.comision_pct
            tb += bruto
            tc += com
            print(f"  {_ascii(c.nombre)[:34]:34} {float(c.mix_pct):>4.0%} "
                  f"{float(c.comision_pct):>4.0%} {float(bruto):>13,.0f} "
                  f"{float(com):>12,.0f} {float(bruto - com):>13,.0f}")
        print(f"  {'TOTAL':34} {'':>5} {'':>5} {float(tb):>13,.0f} "
              f"{float(tc):>12,.0f} {float(tb - tc):>13,.0f}")
        print(f"  diferencia contra el neto de hoy: {float(tb - tc - neto):>+,.0f}\n")


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "BUDGET Working 2027"))
