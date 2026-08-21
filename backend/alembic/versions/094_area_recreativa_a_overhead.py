"""Área Recreativa pasa a overhead (decisión D4 del owner, 2026-08-11)

**Qué cambia.** El departamento `270 Área Recreativa` deja de ser un
departamento operativo y pasa a ser un **centro de costo dentro del overhead**,
como lo trata el Excel de Amarena (ahí entra al consolidado únicamente como una
línea de overhead, fila 76).

Concretamente:

* `OPEX_AREC` (Gastos Operativos, orden 45) → **`OH_AREC`** (Overhead, orden 78).
  Como los subtotales del reporte son sumas por prefijo
  —`TOTAL_OPERATING_EXPENSES = SUM(OPEX_*)`,
  `TOTAL_OVERHEAD_EXPENSES = SUM(OH_*)`—, renombrar la línea es lo que mueve la
  plata de un bloque al otro. Las reglas de `account_mapping` del depto 270 se
  reapuntan igual.
* `PROFIT_AREC` pasa de `REV_AREC - OPEX_AREC` a **`REV_AREC`** a secas: el costo
  ya no está en el bloque operativo. Es el mismo patrón que ya usa
  `PROFIT_SUSTAINABILITY = REV_SUSTAINABILITY`.
* `department_catalog.270.pl_kind`: `OPERATING` → `OVERHEAD`.

**Su ingreso SE QUEDA en INGRESOS TOTALES.** El Excel lo deja afuera, pero el
escaneo marcó ese punto para confirmar, no para copiar: «si el área genera
ingreso real, hoy se está perdiendo del estado de resultados»
(`docs/fase2/ESCANEO_03_FORMULAS.md` §5.12). Botar un ingreso del estado de
resultados es una pérdida silenciosa; dejarlo arriba no le hace daño a nadie.

**Cuánto se mueve el GOP: nada.** Medido contra producción antes de tocar:
`REV_AREC = $0` en los 12 escenarios y `OPEX_AREC = $41` solo en las cinco
versiones 2027 (Draft1..4 y Final). Con el ingreso adentro, el GOP es idéntico
por construcción —lo que sale de Utilidad Operativa entra a Overhead y se resta
igual—; los $41 solo cambian de renglón. Si el ingreso se hubiera sacado, el GOP
habría bajado exactamente `REV_AREC`, que hoy también es $0.

Revision ID: 094
Revises: 093
"""
from alembic import op
import sqlalchemy as sa

revision = "094"
down_revision = "093"
branch_labels = None
depends_on = None

REPORT_ID = "P&L_DETAIL_OWNERS"
NOMBRE = "Área Recreativa"
LOGICA_OH = "Nómina + Opex del depto 270. Centro de costo, no departamento operativo."
LOGICA_OH_ANTES = "SUM mapped accounts"


def upgrade() -> None:
    # 1. la línea del reporte cambia de bloque
    op.execute(sa.text(
        "UPDATE report_line_config SET line_code='OH_AREC', section='OVERHEAD EXPENSES', "
        "display_order=78, line_name=:n, calculation_logic=:l "
        "WHERE report_id=:r AND line_code='OPEX_AREC'"
    ).bindparams(n=NOMBRE, l=LOGICA_OH, r=REPORT_ID))

    # 2. la utilidad del depto ya no resta un costo que se fue al overhead
    op.execute(sa.text(
        "UPDATE report_line_config SET calculation_logic='REV_AREC', line_name=:n "
        "WHERE report_id=:r AND line_code='PROFIT_AREC'"
    ).bindparams(n=NOMBRE, r=REPORT_ID))

    # 3. las reglas de cuenta del depto 270 apuntan a la línea nueva
    op.execute(sa.text(
        "UPDATE account_mapping SET report_line_code='OH_AREC', "
        "report_section='OVERHEAD EXPENSES', display_order=78, report_line_name=:n "
        "WHERE report_id=:r AND report_line_code='OPEX_AREC'"
    ).bindparams(n=NOMBRE, r=REPORT_ID))

    # 4. el catálogo dice lo mismo que el motor
    op.execute(sa.text(
        "UPDATE department_catalog SET pl_kind='OVERHEAD' WHERE dept_code='270'"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "UPDATE report_line_config SET line_code='OPEX_AREC', section='OPERATING EXPENSES', "
        "display_order=45, calculation_logic=:l "
        "WHERE report_id=:r AND line_code='OH_AREC'"
    ).bindparams(l=LOGICA_OH_ANTES, r=REPORT_ID))
    op.execute(sa.text(
        "UPDATE report_line_config SET calculation_logic='REV_AREC - OPEX_AREC' "
        "WHERE report_id=:r AND line_code='PROFIT_AREC'"
    ).bindparams(r=REPORT_ID))
    op.execute(sa.text(
        "UPDATE account_mapping SET report_line_code='OPEX_AREC', "
        "report_section='OPERATING EXPENSES', display_order=45 "
        "WHERE report_id=:r AND report_line_code='OH_AREC'"
    ).bindparams(r=REPORT_ID))
    op.execute(sa.text(
        "UPDATE department_catalog SET pl_kind='OPERATING' WHERE dept_code='270'"
    ))
