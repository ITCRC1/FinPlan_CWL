"""
Seed del department_catalog — DERIVADO de las constantes de pl_engine para
garantizar que el catálogo == el motor (byte-por-byte). Cuando luego el motor
lea esta tabla en vez de sus constantes, el comportamiento no cambia.

Uso: `python -m app.seed_department_catalog` (upsert idempotente).
"""
import asyncio
from sqlalchemy import select

from app.db import get_session
from app.models.department_catalog import DepartmentCatalog
from app.engine.pl_engine import (
    OPERATING_DEPT_GROUPS, OVERHEAD_DEPT_GROUPS, GROUP_NAMES,
    OPERATING_GROUP_ORDER, OVERHEAD_GROUP_ORDER,
    CHECKBOOK_DEPT_CONSOLIDATION,
)

ALLOC_SOURCES = {"0220", "0161"}      # cafetería + lavandería gastos
COST_ONLY_GROUPS = {"CROWTHER"}        # operativo pero sin revenue

# Nombres canónicos por depto (de la BD de planilla normalizada + GROUP_NAMES)
DEPT_NAMES = {
    "0110": "Rooms / Habitaciones", "0111": "Front Desk", "0112": "Reservation",
    "0113": "Housekeeping", "0114": "Concierge",
    "0120": "Alimentos y Bebidas", "0121": "Private Bar",
    "0122": "Kitchen", "0123": "Restaurant",
    # Spa (mig 091): la madre lleva el gasto y los hijos la planilla. `0140`
    # recibe el OPEX, `0132` es la planilla y `0130` era para gerencia y hoy no
    # se usa — se marca para que nadie lo confunda con el que recibe los gastos.
    "0130": "Spa (gerencia)", "0132": "Spa (planilla)", "0140": "Departamento de Spa",
    # Tiendas (mig 091): son DOS locales distintos que se dejan abiertos a
    # propósito. El nombre «Tienda / Gift Shop» se leía como si fueran el mismo.
    "0150": "Tour Activities", "0151": "Tienda", "0165": "Gift Shop",
    "0152": "Transportation", "0161": "Laundry Operations", "0162": "Laundry Revenue",
    "0155": "Innoceana", "0156": "Crowther Lab",
    # 0181 = Gerencia, hijo de 0180 (owner, 2026-08-14). Acá decía «Management»
    # y el mapeo decía «Departamento de Beneficios Empleados»: dos verdades para
    # el mismo código. Manda la planilla, que es la que tiene gente — GERENTE
    # GENERAL y Gerencia Operaciones —, no beneficios a empleados (eso es la
    # Cafetería 0220, que ya se queda el alias «beneficios» acá abajo).
    "0180": "Administración", "0181": "Gerencia (Management)", "0182": "Finance",
    # 0184 = Recursos Humanos, hijo de 0180 (mig 092). Se llamaba
    # «Administración», igual que su padre.
    "0183": "Purchasing", "0184": "Recursos Humanos", "0186": "Security",
    "0190": "Sales and Marketing", "0191": "Sales & Marketing (remoto)",
    "0200": "Maintenance", "0230": "Information System",
    "0205": "Claro del Bosque (Huerta)", "0210": "Utilities",
    "0220": "Employee Dining (Cafetería)",
    "260": "Club Madresal", "270": "Área Recreativa", "280": "Miscelaneos",
    # 0250 = el departamento de los gastos de la propiedad (below-GOP, 8xxx).
    # Existía solo como texto en el mapeo y no tenía fila acá, así que la
    # plantilla y los tabs lo mostraban como un código pelado.
    "0250": "Gastos de la Propiedad",
}
DEPT_ALIASES = {
    # El alias 'spa' lo tenían 0130 y 0140 a la vez: una línea del GL que dijera
    # «spa» podía aterrizar en cualquiera de los dos. Queda solo en 0140, que es
    # el que recibe el gasto (mig 091). Igual con 'gift', que se lo quedaba 0151
    # siendo que el Gift Shop es 0165.
    "0110": ["habitaci"], "0120": ["a&b", "alimentos"], "0140": ["spa"],
    "0150": ["tours"], "0151": ["tienda"], "0165": ["gift", "gift shop"],
    "0152": ["transport"],
    "0155": ["innocean"], "0156": ["crowther", "crowler"], "0161": ["lavander"],
    "0180": ["administ"], "0190": ["ventas", "mercadeo", "marketing"],
    "0200": ["mantenim", "maintenance"], "0205": ["claro", "huerta"],
    "0210": ["utility", "utilit"], "0220": ["cafeter", "beneficios"],
    "0230": ["ti", "tecnolog"], "260": ["madresal"], "270": ["recreativa"],
    "280": ["miscel", "sostenib"],
    "0250": ["property", "propiedad"],   # mismos que gl_detail_importer
}


def build_rows() -> list[dict]:
    """Deriva las filas del catálogo de las constantes de pl_engine."""
    rows: list[dict] = []
    order = 0
    for groups, kind, group_order in [
        (OPERATING_DEPT_GROUPS, "OPERATING", OPERATING_GROUP_ORDER),
        (OVERHEAD_DEPT_GROUPS, "OVERHEAD", OVERHEAD_GROUP_ORDER),
    ]:
        for g in group_order:
            for dept in groups.get(g, []):
                order += 1
                rows.append({
                    "dept_code": dept,
                    "dept_name": DEPT_NAMES.get(dept, GROUP_NAMES.get(g, g)),
                    "name_en": "",
                    "name_aliases": DEPT_ALIASES.get(dept),
                    "usali_class": None,
                    "default_pl_group": g,
                    "pl_kind": kind,
                    "is_revenue_dept": kind == "OPERATING" and g not in COST_ONLY_GROUPS,
                    "is_allocation_source": dept in ALLOC_SOURCES,
                    "parent_dept_code": CHECKBOOK_DEPT_CONSOLIDATION.get(dept),
                    "display_order": order,
                    "active": True,
                })
    # Depto de revenue NO-grupal (split por cuenta, no por grupo): Miscelaneos.
    order += 1
    rows.append({
        "dept_code": "280", "dept_name": DEPT_NAMES["280"],
        "name_en": "Miscellaneous Revenue", "name_aliases": DEPT_ALIASES["280"],
        "usali_class": 4, "default_pl_group": "", "pl_kind": "OPERATING",
        "is_revenue_dept": True, "is_allocation_source": False,
        "parent_dept_code": None, "display_order": order, "active": True,
    })
    # 0250 Property Expenses: SOLO gastos de la propiedad — below-GOP (8xxx).
    # «0250 no hay planilla, solo gastos de la propiedad» (owner, 2026-08-14).
    # Por eso NO lleva las cuentas del núcleo (planilla, cargas, cafetería,
    # suministros), y está declarado así en `SIN_NUCLEO_A_PROPOSITO` de
    # `test_departamentos_independientes.py`.
    #
    # `default_pl_group` va VACÍO a propósito, igual que el 280: sus cuentas
    # llegan a su línea por el mapeo de cuenta, no por grupo. `set_dept_catalog`
    # saltea los deptos sin grupo, así que `group_for_dept("0250")` sigue
    # devolviendo OTHER_OVERHEAD — exactamente lo mismo que devolvía cuando el
    # 0250 no estaba en el catálogo. Ponerle un grupo SÍ cambiaría el P&L.
    order += 1
    rows.append({
        "dept_code": "0250", "dept_name": DEPT_NAMES["0250"],
        "name_en": "Property Expenses", "name_aliases": DEPT_ALIASES["0250"],
        "usali_class": 8, "default_pl_group": "", "pl_kind": "OVERHEAD",
        "is_revenue_dept": False, "is_allocation_source": False,
        "parent_dept_code": None, "display_order": order, "active": True,
    })
    # 0205 Claro del Bosque (Huerta): overhead solo-gastos, sin grupo propio →
    # cae a OTHER_OVERHEAD (consistente con group_for_dept). Promovible a grupo
    # propio "Property/Grounds" si el owner lo decide.
    order += 1
    rows.append({
        "dept_code": "0205", "dept_name": DEPT_NAMES["0205"],
        "name_en": "Claro del Bosque (Garden)", "name_aliases": DEPT_ALIASES["0205"],
        "usali_class": 7, "default_pl_group": "OTHER_OVERHEAD", "pl_kind": "OVERHEAD",
        "is_revenue_dept": False, "is_allocation_source": False,
        "parent_dept_code": None, "display_order": order, "active": True,
    })
    return rows


async def seed() -> None:
    rows = build_rows()
    async with get_session() as session:
        existing = {
            r.dept_code for r in (await session.execute(select(DepartmentCatalog))).scalars()
        }
        added = updated = 0
        for d in rows:
            obj = await session.get(DepartmentCatalog, d["dept_code"])
            if obj is None:
                session.add(DepartmentCatalog(**d))
                added += 1
            else:
                for k, v in d.items():
                    setattr(obj, k, v)
                updated += 1
        await session.commit()
    print(f"department_catalog: +{added} nuevos, {updated} actualizados ({len(rows)} total)")


if __name__ == "__main__":
    asyncio.run(seed())
