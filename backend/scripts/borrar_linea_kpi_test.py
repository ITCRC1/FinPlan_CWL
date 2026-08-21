# -*- coding: utf-8 -*-
"""Borra la linea `KPI_TEST` que quedo viva en produccion.

Aparecio auditando el mapeo (2026-08-14): de las 120 lineas de
`report_line_config` de la base, UNA no esta en `seed_data/mapping_pl.json`. Se
llama «Test», es de tipo KPI y quedo de algun ensayo.

El seed es no destructivo a proposito —no borra lo que sobra—, asi que una linea
metida a mano se queda para siempre. Por eso hace falta borrarla explicitamente.

Verificado antes de borrar: 0 reglas de cuenta, 0 filas en `pl_lines` y 0 en
`actual_pl_lines` la referencian. Ademas el motor salta las lineas KPI antes de
evaluarlas (`pl_engine`: `if lt == "KPI": continue`), asi que nunca movio un
numero — lo que hacia era ocupar un renglon vacio en los reportes que listan
KPIs.

    python -m scripts.borrar_linea_kpi_test            # muestra que haria
    python -m scripts.borrar_linea_kpi_test --aplicar
"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts._prodenv import usar_produccion  # noqa: E402

usar_produccion()

from sqlalchemy import delete, func, select  # noqa: E402

from app.db import get_session  # noqa: E402
from app.models.actual_pl_line import ActualPLLine  # noqa: E402
from app.models.mapping import AccountMapping, ReportLineConfig  # noqa: E402
from app.models.pl_line import PLLine  # noqa: E402

CODIGO = "KPI_TEST"


async def main(aplicar: bool):
    async with get_session() as s:
        linea = (await s.execute(select(ReportLineConfig).where(
            ReportLineConfig.line_code == CODIGO))).scalars().first()
        if linea is None:
            print(f"  {CODIGO} no existe: nada que hacer")
            return

        # No se borra nada que tenga datos detras.
        usos = {}
        for modelo, campo, nombre in (
            (AccountMapping, AccountMapping.report_line_code, "reglas de cuenta"),
            (PLLine, PLLine.line_code, "pl_lines"),
            (ActualPLLine, ActualPLLine.line_code, "actual_pl_lines"),
        ):
            usos[nombre] = (await s.execute(
                select(func.count()).select_from(modelo)
                .where(campo == CODIGO))).scalar()

        print(f"  {CODIGO}: '{linea.line_name}' tipo={linea.line_type}")
        for k, v in usos.items():
            print(f"     {k}: {v}")
        if any(usos.values()):
            print("\n  NO se borra: tiene datos detras. Revisalos primero.")
            return
        if not aplicar:
            print("\n  (prueba en seco - corre con --aplicar)")
            return
        await s.execute(delete(ReportLineConfig).where(
            ReportLineConfig.line_code == CODIGO))
        await s.commit()
        print(f"\n  {CODIGO} borrada.")


if __name__ == "__main__":
    asyncio.run(main("--aplicar" in sys.argv))
