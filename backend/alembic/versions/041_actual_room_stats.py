"""Actual room stats por tipo x mes (de Opera/PMS)

Revision ID: 041
Revises: 040
Create Date: 2026-06-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "041"
down_revision: Union[str, None] = "040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "actual_room_stats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("room_type_name", sa.String(120), nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("units", sa.Integer, server_default="0"),
        sa.Column("nights_available", sa.Numeric(12, 2), server_default="0"),
        sa.Column("nights_occupied", sa.Numeric(12, 2), server_default="0"),
        sa.Column("revenue", sa.Numeric(14, 2), server_default="0"),
        sa.Column("pax", sa.Numeric(12, 2), server_default="0"),
        sa.UniqueConstraint("scenario_id", "room_type_name", "month",
                            name="uq_roomstat_scenario_room_month"),
    )


def downgrade() -> None:
    op.drop_table("actual_room_stats")
