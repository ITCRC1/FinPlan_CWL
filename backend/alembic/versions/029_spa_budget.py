"""Spa budget (capture-rate model: pax × capture rate × avg treatment price)

Revision ID: 029
Revises: 028
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "spa_budgets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "scenario_id", sa.String(36),
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("capture_pct", sa.Numeric(8, 6), server_default="0"),
        sa.Column("avg_price", sa.Numeric(12, 2), server_default="0"),
        sa.UniqueConstraint("scenario_id", "month", name="uq_spa_budget"),
    )


def downgrade() -> None:
    op.drop_table("spa_budgets")
