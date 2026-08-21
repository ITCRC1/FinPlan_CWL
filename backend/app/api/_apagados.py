# -*- coding: utf-8 -*-
"""Qué departamentos escondió el provisionamiento, en un solo lugar.

La matriz (`dept_enablement`) se llenaba desde su pantalla y **no la leía casi
nadie**: se guardaba la decisión y los departamentos seguían apareciendo en
todos los selectores. La capa que registra estaba hecha; la que aplica, no.

Dos reglas que valen para todo el que use esto:

**La tabla es esparsa y el default es PRENDIDO.** No tener fila significa
activo. Por eso se pregunta «quién está apagado» y no «quién está prendido»: una
propiedad recién creada no tiene ninguna fila y le funciona todo.

**Esto esconde, NO borra ni resta.** Un departamento apagado desaparece de las
pantallas de carga, pero si tiene datos cargados esos datos siguen sumando en el
P&L. Es a propósito: si esconder algo cambiara el estado de resultados, sería
una forma de mover números sin dejar rastro. La pantalla de provisionamiento
avisa cuánto dato hay detrás antes de dejar apagar.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dept_enablement import DeptEnablement


async def apagados_por_dimension(
    db: AsyncSession, hotel_id: str
) -> dict[str, list[str]]:
    """`{dimension: [dept_code, …]}` — solo lo que alguien apagó a mano."""
    out: dict[str, set[str]] = defaultdict(set)
    for r in (await db.execute(select(DeptEnablement).where(
            DeptEnablement.hotel_id == hotel_id,
            DeptEnablement.scope_kind == "DEPT",
            DeptEnablement.enabled.is_(False)))).scalars():
        out[r.dimension].add((r.scope_key or "").strip())
    return {dim: sorted(codigos) for dim, codigos in out.items()}


async def dept_apagado(
    db: AsyncSession, hotel_id: str, dept_code: str, dimension: str | None = None
) -> bool:
    """¿Este departamento está escondido?

    Sin `dimension`, contesta por el departamento entero: apagado en TODAS las
    que tenga fila. Con dimensión, contesta por esa sola. El tab del Club usa la
    primera forma —o el departamento existe en la propiedad o no— y las
    pantallas de carga la segunda.
    """
    q = select(DeptEnablement).where(
        DeptEnablement.hotel_id == hotel_id,
        DeptEnablement.scope_kind == "DEPT",
        DeptEnablement.scope_key == dept_code,
        DeptEnablement.enabled.is_(False),
    )
    if dimension:
        q = q.where(DeptEnablement.dimension == dimension)
    return (await db.execute(q)).scalars().first() is not None


# ─── Tabs y reportes (owner, 2026-08-20) ─────────────────────────────────────
#
# «No todas las propiedades van a ver todos los reportes, ya que son muchos para
# cada propiedad y se van a perder.»
#
# Vive en el MISMO archivo que los departamentos a propósito: «qué escondió el
# provisionamiento» tiene que poder contestarse en un solo lugar. Mismas dos
# reglas: tabla esparsa, default prendido.


async def tabs_apagados(db: AsyncSession, hotel_id: str) -> dict[str, list[str]]:
    """`{"TAB": [...], "ITEM": [...]}` — sólo lo que alguien apagó a mano."""
    from app.models.tab_enablement import TabEnablement

    fuera: dict[str, list[str]] = {"TAB": [], "ITEM": []}
    for r in (await db.execute(select(TabEnablement).where(
            TabEnablement.hotel_id == hotel_id))).scalars().all():
        fuera.setdefault(r.scope_kind, []).append(r.clave)
    return {k: sorted(v) for k, v in fuera.items()}
