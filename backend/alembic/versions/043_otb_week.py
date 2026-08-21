"""On The Books por SEMANA (snapshot semanal) — recrea la tabla con week

Revision ID: 043
Revises: 042
Create Date: 2026-06-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "043"
down_revision: Union[str, None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("on_the_books_entries")
    op.create_table(
        "on_the_books_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("week", sa.Integer, nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("total_revenue", sa.Numeric(14, 2), server_default="0"),
        sa.Column("rooms_revenue", sa.Numeric(14, 2), server_default="0"),
        sa.Column("rooms_occupied", sa.Numeric(12, 2), server_default="0"),
        sa.Column("guests", sa.Numeric(12, 2), server_default="0"),
        sa.UniqueConstraint("scenario_id", "week", "month", name="uq_otb_scenario_week_month"),
    )


def downgrade() -> None:
    op.drop_table("on_the_books_entries")
    op.create_table(
        "on_the_books_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("total_revenue", sa.Numeric(14, 2), server_default="0"),
        sa.Column("rooms_revenue", sa.Numeric(14, 2), server_default="0"),
        sa.Column("rooms_occupied", sa.Numeric(12, 2), server_default="0"),
        sa.Column("guests", sa.Numeric(12, 2), server_default="0"),
        sa.UniqueConstraint("scenario_id", "month", name="uq_otb_scenario_month"),
    )
