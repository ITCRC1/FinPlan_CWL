"""Cash Flow Budget — líneas de entrada (CapEx / Working Capital / Other) por escenario

Revision ID: 050
Revises: 049
Create Date: 2026-06-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "050"
down_revision: Union[str, None] = "049"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cashflow_budget_inputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("row_key", sa.String(24), nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("value", sa.Numeric(16, 2), server_default="0"),
        sa.UniqueConstraint("scenario_id", "row_key", "month", name="uq_cfb_scenario_row_month"),
    )


def downgrade() -> None:
    op.drop_table("cashflow_budget_inputs")
