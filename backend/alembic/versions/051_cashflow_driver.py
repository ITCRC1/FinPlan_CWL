"""Cash Flow Budget — drivers (criterio % de ventas) por partida y escenario

Revision ID: 051
Revises: 050
Create Date: 2026-06-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "051"
down_revision: Union[str, None] = "050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cashflow_budget_drivers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("row_key", sa.String(24), nullable=False),
        sa.Column("mode", sa.String(12), server_default="manual"),
        sa.Column("pct", sa.Numeric(10, 6), server_default="0"),
        sa.UniqueConstraint("scenario_id", "row_key", name="uq_cfd_scenario_row"),
    )


def downgrade() -> None:
    op.drop_table("cashflow_budget_drivers")
