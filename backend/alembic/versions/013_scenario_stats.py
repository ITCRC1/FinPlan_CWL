"""013 scenario stats (room KPIs per scenario × month)

Revision ID: 013
Revises: 012
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_stats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("rooms_available", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rooms_occupied", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("guests", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("occupancy_pct", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("adr", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.UniqueConstraint("scenario_id", "month", name="uq_scenario_stat"),
    )


def downgrade() -> None:
    op.drop_table("scenario_stats")
