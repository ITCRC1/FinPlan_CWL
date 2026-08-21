"""Payroll params per scenario (CCSS rate, aguinaldo divisor — varían por año)

Revision ID: 030
Revises: 029
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payroll_params",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "scenario_id", sa.String(36),
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("ccss_rate", sa.Numeric(7, 5), server_default="0.26830"),
        sa.Column("aguinaldo_divisor", sa.Numeric(6, 3), server_default="12"),
        sa.UniqueConstraint("scenario_id", name="uq_payroll_params"),
    )


def downgrade() -> None:
    op.drop_table("payroll_params")
