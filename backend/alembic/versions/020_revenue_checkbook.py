"""Revenue checkbook: direct revenue amounts + scenario.revenue_source toggle

Revision ID: 020
Revises: 019
Create Date: 2026-06-25

- revenue_entries: one row per (line) × scenario, 12 USD month columns. The
  "checkbook" source of revenue (direct USD per P&L line) as an alternative to
  the driver engine (rate cards × occupancy × packages).
- scenarios.revenue_source: 'drivers' (default, current behavior) | 'checkbook'.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("revenue_source", sa.String(12), nullable=False, server_default="drivers"),
    )
    op.create_table(
        "revenue_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("line", sa.String(20), nullable=False),
        sa.Column("jan", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("feb", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("mar", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("apr", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("may", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("jun", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("jul", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("aug", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("sep", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("oct", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("nov", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("dec", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.UniqueConstraint("scenario_id", "line", name="uq_revenue_entry"),
    )
    op.create_index("ix_revenue_entries_scenario_id", "revenue_entries", ["scenario_id"])
    op.create_index("ix_revenue_entries_hotel_id", "revenue_entries", ["hotel_id"])


def downgrade() -> None:
    op.drop_index("ix_revenue_entries_hotel_id", table_name="revenue_entries")
    op.drop_index("ix_revenue_entries_scenario_id", table_name="revenue_entries")
    op.drop_table("revenue_entries")
    op.drop_column("scenarios", "revenue_source")
