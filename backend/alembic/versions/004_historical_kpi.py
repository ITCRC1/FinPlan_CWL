"""Historical KPIs schema — Phase 3 (2024/2025 actuals)

Revision ID: 004
Revises: 003
Create Date: 2026-06-20

Tables:
  historical_kpis — real room KPIs (2024/2025 actuals) per hotel × year × month
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "historical_kpis",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("room_type_id", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rooms_available", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rooms_occupied", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("guests", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("occupancy_pct", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("adr_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("revpar_usd", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("revenue_usd", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("source", sa.String(20), nullable=False, server_default="ACTUAL_IMPORT"),
        sa.UniqueConstraint("hotel_id", "year", "month", "room_type_id", name="uq_historical_kpi"),
    )
    op.create_index("ix_historical_kpis_hotel_id", "historical_kpis", ["hotel_id"])


def downgrade() -> None:
    op.drop_index("ix_historical_kpis_hotel_id", table_name="historical_kpis")
    op.drop_table("historical_kpis")
