"""el outlet entra en la llave de actual_entries — previsión para A&B por outlet

El GL de A&B trae la MISMA cuenta cuatro veces, una por punto de venta:

    4110  Food1   Outlet 1   Ingreso Food   Departamento de A&B
    4110  Food    Outlet 2   Ingreso Food   Departamento de A&B
    4110  Food    Outlet 3   …
    4110  Food    Outlet 4   …

Son seis tipos de producto × cuatro outlets = 24 filas, y la contabilidad ya
codifica la dimensión. `actual_entries` no podía representarla: su llave única
era `(scenario_id, dept_code, account_code)`, así que las cuatro filas colisionan
en una sola. Y los escritores (`actuals_api`, `scenarios_api`) **asignan** el mes
en vez de acumularlo, o sea que sobrevive la última y **la plata de los otros
tres outlets desaparece sin dar error**.

Hoy no se ha roto porque los Outlets 2, 3 y 4 vienen en CERO (confirmado con el
owner el 2026-08-12) y el importador salta las filas sin monto. Esto es la
previsión para el día que se llenen — que es una decisión de contabilidad, no
del sistema.

**No cambia ningún número.** Todas las filas existentes quedan con `outlet = ''`,
y `('', cuenta, depto)` sigue siendo tan único como antes. Ningún reporte lee la
columna todavía.

Revision ID: 102
Revises: 101
"""
from alembic import op
import sqlalchemy as sa

revision = "102"
down_revision = "101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("actual_entries", sa.Column(
        "outlet", sa.String(40), nullable=False, server_default=""))
    # La llave pasa a incluir el outlet. Las filas de hoy tienen '' así que la
    # unicidad no cambia para ninguna.
    op.drop_constraint("uq_actual_entry", "actual_entries", type_="unique")
    op.create_unique_constraint(
        "uq_actual_entry", "actual_entries",
        ["scenario_id", "dept_code", "account_code", "outlet"])


def downgrade() -> None:
    op.drop_constraint("uq_actual_entry", "actual_entries", type_="unique")
    op.create_unique_constraint(
        "uq_actual_entry", "actual_entries",
        ["scenario_id", "dept_code", "account_code"])
    op.drop_column("actual_entries", "outlet")
