"""Cost entries schema — Phase 5 (Cost of Sales, Clase 5)

Revision ID: 005
Revises: 004
Create Date: 2026-06-20

Tables:
  cost_entries — one row per account (5xxx) × dept × scenario
                 with driver-based or manual monthly amounts (USD)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cost_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("dept_code", sa.String(10), nullable=False),
        sa.Column("account_code", sa.String(10), nullable=False),
        sa.Column("account_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("calc_mode", sa.String(10), nullable=False, server_default="MANUAL"),
        sa.Column("driver_type", sa.String(20), nullable=False, server_default=""),
        sa.Column("driver_pct_or_rate", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("revenue_line_ref", sa.String(20), nullable=False, server_default=""),
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
        sa.UniqueConstraint("scenario_id", "dept_code", "account_code", name="uq_cost_entry"),
    )
    op.create_index("ix_cost_entries_scenario_id", "cost_entries", ["scenario_id"])
    op.create_index("ix_cost_entries_hotel_id", "cost_entries", ["hotel_id"])
    op.create_index("ix_cost_entries_dept_code", "cost_entries", ["dept_code"])


def downgrade() -> None:
    op.drop_index("ix_cost_entries_dept_code", table_name="cost_entries")
    op.drop_index("ix_cost_entries_hotel_id", table_name="cost_entries")
    op.drop_index("ix_cost_entries_scenario_id", table_name="cost_entries")
    op.drop_table("cost_entries")
