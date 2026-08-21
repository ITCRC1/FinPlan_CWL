"""Occupancy as % per room type × month

Revision ID: 025
Revises: 024
Create Date: 2026-06-25

Adds occupancy_budgets.occupancy_pct. The Ocupación tab edits the %, and
rooms_occupied is derived = pct × available nights (units × days, 0 if closed).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "occupancy_budgets",
        sa.Column("occupancy_pct", sa.Numeric(8, 6), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("occupancy_budgets", "occupancy_pct")
