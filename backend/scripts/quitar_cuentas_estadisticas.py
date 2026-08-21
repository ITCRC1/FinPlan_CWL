# -*- coding: utf-8 -*-
"""Saca de la base las cuentas estadísticas que ya no están en el catálogo.

**Por qué hace falta un script.** El seed es NO DESTRUCTIVO a propósito: inserta
lo que falta y actualiza lo que cambió, pero nunca borra. Es la regla correcta
—un hotel puede haber agregado cuentas propias y el seed corre en cada arranque,
así que borrar por ausencia le vaciaría el catálogo a alguien en un redeploy—
pero significa que quitar una cuenta del JSON no la quita de la base. El seed
solo la reporta como «sobra».

Este script cierra ese lazo, a mano y con confirmación.

**Se niega a borrar una cuenta que tenga datos detrás.** Si alguien ya cargó
estadísticas contra ella, borrarla se llevaría los valores por delante — y una
estadística que desaparece no se nota como se nota un descuadre de plata.

    python -m scripts.quitar_cuentas_estadisticas            # muestra qué haría
    python -m scripts.quitar_cuentas_estadisticas --aplicar  # lo hace
"""
import asyncio
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts._prodenv import usar_produccion  # noqa: E402

usar_produccion()

from sqlalchemy import delete, func, select  # noqa: E402

from app.db import get_session  # noqa: E402
from app.models.stat_account import StatAccount  # noqa: E402
from app.models.statistical_entry import StatisticalEntry  # noqa: E402
from app.seed_stats import leer_catalogo  # noqa: E402


async def main(aplicar: bool):
    del_catalogo = {str(c["code"]) for c in leer_catalogo()}

    async with get_session() as s:
        en_base = (await s.execute(select(StatAccount))).scalars().all()
        sobran = [a for a in en_base if a.code not in del_catalogo]

        if not sobran:
            print("Nada que quitar: la base y el catálogo dicen lo mismo "
                  f"({len(en_base)} cuentas).")
            return

        print(f"En la base hay {len(en_base)} cuentas; el catálogo tiene "
              f"{len(del_catalogo)}.")
        print(f"Sobran {len(sobran)}:\n")

        con_datos = []
        for a in sobran:
            n = (await s.execute(
                select(func.count()).select_from(StatisticalEntry)
                .where(StatisticalEntry.account_code == a.code))).scalar()
            marca = f"  <-- TIENE {n} VALORES CARGADOS" if n else ""
            print(f"  {a.code}  {a.nombre_es}{marca}")
            if n:
                con_datos.append((a.code, n))

        if con_datos:
            print("\nNO se borra nada: hay cuentas con datos detrás.")
            print("Borrarlas se llevaría los valores por delante, y una "
                  "estadística que desaparece no se nota como se nota un "
                  "descuadre de plata.")
            print("Decidí qué hacer con esos datos primero.")
            return

        if not aplicar:
            print("\n(prueba en seco — corré con --aplicar para hacerlo)")
            return

        await s.execute(delete(StatAccount).where(
            StatAccount.code.in_([a.code for a in sobran])))
        await s.commit()
        print(f"\nListo: {len(sobran)} cuentas quitadas.")


if __name__ == "__main__":
    asyncio.run(main("--aplicar" in sys.argv))
