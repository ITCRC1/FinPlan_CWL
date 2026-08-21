"""Lo que el allocation le mete a un departamento, para que el checkbook lo enseñe.

El problema que resuelve: el P&L suma DOS corrientes para un mismo par
(departamento, cuenta) — las líneas del checkbook y lo que le cae por
allocation— pero la pantalla del checkbook solo mostraba la primera. El 0110
enseña $25,295.87 en la 7310 y recibe $15,585.81 más por reparto; el 0162 no
enseñaba nada aunque carga $1,558.58 de costo de venta.

Estas filas NO son del checkbook: nadie las digitó y nadie las edita. Van
aparte, marcadas, para que el número de la pantalla y el del P&L cuenten la
misma historia. Convertirlas en líneas reales las contaría dos veces.
"""
from decimal import Decimal

from sqlalchemy import select

from app.models.allocation_entry import AllocationEntry
from app.models.department_catalog import DepartmentCatalog
from app.models.mapping import AccountMapping

ZERO = Decimal("0")
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]


async def _padres(session) -> dict[str, str]:
    """{departamento: su padre} según el catálogo. Solo los que tienen padre."""
    filas = (await session.execute(select(DepartmentCatalog))).scalars().all()
    return {d.dept_code: (d.parent_dept_code or "").strip()
            for d in filas if (d.parent_dept_code or "").strip()}


def agrupar_repartos(filas, nombres: dict[str, str] | None = None) -> list[dict]:
    """La parte pura: filas de AllocationEntry → líneas listas para la pantalla.

    Agrupa por (cuenta, destino, origen) y no por cuenta sola. Los tres importan:
    la cuenta dice qué gasto es, el destino distingue Cocina de Restaurante
    dentro del mismo A&B, y el origen dice si vino de cafetería o de lavandería.
    Colapsarlos escondería justo lo que el usuario necesita para ir a revisar.
    """
    nombres = nombres or {}
    acum: dict[tuple[str, str, str], dict] = {}
    for f in filas:
        clave = (
            getattr(f, "account", "") or "",
            getattr(f, "target_dept", "") or "",
            getattr(f, "source_dept", "") or "",
        )
        fila = acum.setdefault(clave, {
            "account_code": clave[0],
            "target_dept": clave[1],
            "source_dept": clave[2],
            "basis_type": getattr(f, "basis_type", "") or "",
            **{m: ZERO for m in MESES},
        })
        mi = (getattr(f, "month", 1) or 1) - 1
        if 0 <= mi < 12:
            fila[MESES[mi]] += (getattr(f, "amount_usd", ZERO) or ZERO)

    salida = []
    for (cuenta, _destino, _origen), fila in sorted(acum.items()):
        if all(fila[m] == ZERO for m in MESES):
            continue          # una cuenta que quedó en cero no es información
        salida.append({
            **{k: v for k, v in fila.items() if k not in MESES},
            "account_name": nombres.get(cuenta, ""),
            **{m: str(fila[m]) for m in MESES},
            "total": str(sum(fila[m] for m in MESES)),
            "editable": False,
        })
    return salida


async def lineas_del_allocation(
    session, scenario_id: str, dept_code: str, clases: str | tuple[str, ...] = "",
) -> list[dict]:
    """Filas de solo lectura, una por cuenta y origen, con sus 12 meses.

    Cada fila trae `source_dept`: de dónde salió la plata (0220 cafetería,
    0161 lavandería), que es lo que el usuario necesita para ir a revisar el
    reparto si un número le extraña.

    `clases` filtra por el primer dígito de la cuenta, porque cada pantalla
    muestra su clase y nada más:

        "7" → checkbook de OPEX     (linen 7310, uniformes 7685)
        "5" → checkbook de Costos   (servicios de lavandería 5301)
        "6" → planilla              (cafetería 6025, salarios 6000)

    Sin este filtro los repartos de planilla salían dentro del checkbook de
    OPEX, que es donde no van: la cuenta 6000 no es un gasto operativo y
    verla ahí hace dudar del cuadro entero. Vacío = todas, para quien quiera
    el panorama completo.
    """
    if isinstance(clases, str):
        clases = tuple(c for c in clases if c.strip())
    # El checkbook trabaja al nivel del departamento padre (0120 A&B), pero el
    # reparto cae en los hijos (0122 Cocina, 0123 Restaurante). Si buscáramos
    # solo el código exacto, el usuario abriría el 0120 y no vería nada aunque
    # el P&L le esté cargando la plata de cocina y restaurante.
    hijos = [d for d, padre in (await _padres(session)).items() if padre == dept_code]
    objetivos = [dept_code, *hijos]

    filas = (await session.execute(
        select(AllocationEntry).where(
            AllocationEntry.scenario_id == scenario_id,
            AllocationEntry.target_dept.in_(objetivos),
        )
    )).scalars().all()
    if clases:
        filas = [f for f in filas if (f.account or "")[:1] in clases]
    if not filas:
        return []

    # El nombre de la cuenta sale del mapeo, que es donde el usuario lo edita.
    codigos = {f.account for f in filas if f.account}
    nombres: dict[str, str] = {}
    if codigos:
        for m in (await session.execute(
            select(AccountMapping).where(
                AccountMapping.account_code.in_(codigos),
                AccountMapping.active_status == "YES",
            )
        )).scalars().all():
            if m.account_name_example and m.account_code not in nombres:
                nombres[m.account_code] = m.account_name_example

    return agrupar_repartos(filas, nombres)
