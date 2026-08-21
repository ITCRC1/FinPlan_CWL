"""Sales channels per month — mix/commission can vary by month

Revision ID: 023
Revises: 022
Create Date: 2026-06-25

Adds sales_channel_configs.month (1-12). Existing rows default to month 1; the
API falls back to the channel's available row for months not yet set, so prior
(all-months) config keeps showing until the user edits a specific month.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sales_channel_configs",
        sa.Column("month", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("sales_channel_configs", "month")
