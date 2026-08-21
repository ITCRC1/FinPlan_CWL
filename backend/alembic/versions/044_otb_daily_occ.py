"""OTB daily occupancy (rooms sold por día, heatmap)

Revision ID: 044
Revises: 043
Create Date: 2026-06-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "044"
down_revision: Union[str, None] = "043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "otb_daily_occ",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("week", sa.Integer, nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("day", sa.Integer, nullable=False),
        sa.Column("rooms_sold", sa.Numeric(8, 2), server_default="0"),
        sa.UniqueConstraint("scenario_id", "week", "month", "day", name="uq_dailyocc_sc_wk_mo_dy"),
    )


def downgrade() -> None:
    op.drop_table("otb_daily_occ")
