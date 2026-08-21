# -*- coding: utf-8 -*-
"""El nombre de cada departamento, del catálogo, en un solo lugar.

Los tres exportadores a Excel (OPEX, costos, planilla) tenían cada uno su propia
lista escrita a mano de unos 16 departamentos, mientras `department_catalog`
tiene 38. Todo lo que no estuviera en esa lista salía con el código repetido:
el owner abrió el Excel de OPEX y vio las pestañas **«260 260»** y **«270 270»**
al lado de «0230 IT».

Tres copias parciales de la misma verdad envejecen por separado — la del
exportador de OPEX ni siquiera coincidía con la de costos. Ahora el nombre lo
pasa quien exporta, sacado del catálogo, que ya es la fuente única para las
pantallas (`GET /departments/`).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.department_catalog import DepartmentCatalog


async def nombres_de_depto(db: AsyncSession) -> dict[str, str]:
    """`{dept_code: dept_name}` para rotular pestañas y encabezados."""
    return {
        d.dept_code: d.dept_name
        for d in (await db.execute(select(DepartmentCatalog))).scalars()
        if d.dept_code and d.dept_name
    }
