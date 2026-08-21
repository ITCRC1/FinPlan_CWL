"""Hotel closed months (operating calendar) — CWL closes October

Revision ID: 021
Revises: 020
Create Date: 2026-06-25

Adds hotels.closed_months (comma-separated 1-based months the hotel does not
operate). Available room-nights for a closed month = 0, applied by formula
(nights = units × days, days = 0 if closed). Seeds CWL = '10' (October).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "hotels",
        sa.Column("closed_months", sa.String(40), nullable=False, server_default=""),
    )
    # CWL cierra octubre — marcar el dato existente en prod.
    op.execute("UPDATE hotels SET closed_months = '10' WHERE id = 'CWL'")


def downgrade() -> None:
    op.drop_column("hotels", "closed_months")
