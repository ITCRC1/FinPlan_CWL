"""Marcas de cambio para avisar que el P&L quedó atrás

El usuario edita un salario, un tipo de cambio o una regla de reparto, y el
reporte sigue mostrando lo de antes hasta que alguien aprieta Recalcular. Nada
lo decía. La auditoría del cash flow pidió ese aviso y no se pudo hacer: ninguna
tabla de origen guardaba CUÁNDO se modificó, así que no había contra qué
comparar.

Se agrega `updated_at` a las tablas cuyo cambio EXIGE recalcular, y
`last_recalc_at` al escenario. El aviso es la comparación de las dos.

Todo nullable y sin backfill a propósito: las filas viejas quedan en NULL, que
significa "no sé cuándo cambió". Rellenarlas con `now()` diría que todo se editó
hoy y dispararía el aviso en los 20 escenarios el primer día.

Revision ID: 083
Revises: 082
Create Date: 2026-08-10
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "083"
down_revision: Union[str, None] = "082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLAS = [
    "payroll_positions",
    "payroll_params",
    "exchange_rates",
    "salary_allocation_config",
    "cafeteria_allocation_config",
    "laundry_allocation_config",
]


def upgrade() -> None:
    for t in TABLAS:
        op.add_column(t, sa.Column("updated_at", sa.DateTime(), nullable=True))
    op.add_column("scenarios", sa.Column("last_recalc_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("scenarios", "last_recalc_at")
    for t in TABLAS:
        op.drop_column(t, "updated_at")
