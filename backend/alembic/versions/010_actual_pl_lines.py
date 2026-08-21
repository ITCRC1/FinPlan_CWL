"""010 actual P&L lines (line-level actuals)

Revision ID: 010
Revises: 009
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "actual_pl_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("line_code", sa.String(40), nullable=False),
        sa.Column("amount_usd", sa.Numeric(16, 4), nullable=False, server_default="0"),
        sa.UniqueConstraint("scenario_id", "month", "line_code", name="uq_actual_pl_line"),
    )


def downgrade() -> None:
    op.drop_table("actual_pl_lines")
