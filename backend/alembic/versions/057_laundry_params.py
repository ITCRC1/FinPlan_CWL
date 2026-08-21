"""Lavandería — params de escenario (kilos uniformes/huéspedes + cuentas) y
columna account en allocation_entries.

Revision ID: 057
Revises: 056
Create Date: 2026-06-29
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "057"
down_revision: Union[str, None] = "056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "laundry_params",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("kilos_uniformes", sa.Numeric(10, 2), server_default="0"),
        sa.Column("kilos_huespedes", sa.Numeric(10, 2), server_default="0"),
        sa.Column("account_linen", sa.String(10), server_default="7310"),
        sa.Column("account_uniform", sa.String(10), server_default="7685"),
        sa.Column("account_servicios", sa.String(10), server_default="5301"),
        sa.UniqueConstraint("scenario_id", name="uq_laundry_params"),
    )
    op.add_column(
        "allocation_entries",
        sa.Column("account", sa.String(10), server_default=""),
    )


def downgrade() -> None:
    op.drop_column("allocation_entries", "account")
    op.drop_table("laundry_params")
