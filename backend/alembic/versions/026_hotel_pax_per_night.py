"""Hotel pax_per_night (editable guests-per-occupied-night factor)

Revision ID: 026
Revises: 025
Create Date: 2026-06-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hotels",
        sa.Column("pax_per_night", sa.Numeric(6, 4), nullable=False, server_default="1.8"),
    )


def downgrade() -> None:
    op.drop_column("hotels", "pax_per_night")
