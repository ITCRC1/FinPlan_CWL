"""Widen sales_channel_configs.channel to 40 (allow readable custom names)

Revision ID: 024
Revises: 023
Create Date: 2026-06-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sales_channel_configs", "channel",
        type_=sa.String(40), existing_type=sa.String(10), existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "sales_channel_configs", "channel",
        type_=sa.String(10), existing_type=sa.String(40), existing_nullable=False,
    )
