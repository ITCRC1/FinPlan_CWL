"""Clear CWL closed_months — October computes by formula like every month

Revision ID: 022
Revises: 021
Create Date: 2026-06-25

Reversal of the operational assumption in 021: CWL does NOT leave October blank.
Every month's available nights = units × calendar days (October included). The
closed_months mechanism stays available, but defaults to empty.
"""
from typing import Sequence, Union
from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE hotels SET closed_months = '' WHERE id = 'CWL'")


def downgrade() -> None:
    op.execute("UPDATE hotels SET closed_months = '10' WHERE id = 'CWL'")
