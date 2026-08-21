"""019 pl_manual_inputs.capital_reserve_pct (reserve as % of revenue)

Revision ID: 019
Revises: 018
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pl_manual_inputs",
        sa.Column("capital_reserve_pct", sa.Numeric(8, 6), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("pl_manual_inputs", "capital_reserve_pct")
