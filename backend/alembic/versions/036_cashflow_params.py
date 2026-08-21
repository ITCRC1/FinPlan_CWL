"""Cash flow params (Fase D)

Revision ID: 036
Revises: 035
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cashflow_params",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("opening_cash", sa.Numeric(16, 2), server_default="0"),
        sa.Column("dso_days", sa.Integer, server_default="10"),
        sa.Column("dpo_days", sa.Integer, server_default="30"),
        sa.Column("distributions_annual", sa.Numeric(16, 2), server_default="0"),
        sa.UniqueConstraint("scenario_id", name="uq_cashflow_params_scenario"),
    )


def downgrade() -> None:
    op.drop_table("cashflow_params")
