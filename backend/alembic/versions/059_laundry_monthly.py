"""Lavandería — kilos por mes (linen por depto, uniformes, huéspedes)

Para presupuesto los kilos varían por mes. Se agregan columnas JSON con
12 valores (Ene..Dic). Si son NULL, se usa el escalar mensual (legacy).

Revision ID: 059
Revises: 058
Create Date: 2026-06-29
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "059"
down_revision: Union[str, None] = "058"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("laundry_allocation_config", sa.Column("kilos_monthly", sa.JSON, nullable=True))
    op.add_column("laundry_params", sa.Column("uniformes_monthly", sa.JSON, nullable=True))
    op.add_column("laundry_params", sa.Column("huespedes_monthly", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("laundry_params", "huespedes_monthly")
    op.drop_column("laundry_params", "uniformes_monthly")
    op.drop_column("laundry_allocation_config", "kilos_monthly")
