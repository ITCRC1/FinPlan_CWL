"""018 cost_entries monthly driver rates (per-month %)

Revision ID: 018
Revises: 017
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None

_MONTHS = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]


def upgrade() -> None:
    for m in _MONTHS:
        op.add_column("cost_entries",
                      sa.Column(f"rate_{m}", sa.Numeric(10, 6), nullable=True))


def downgrade() -> None:
    for m in _MONTHS:
        op.drop_column("cost_entries", f"rate_{m}")
