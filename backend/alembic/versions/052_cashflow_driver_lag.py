"""Cash Flow Budget drivers — columna lag (modos días / lead_lag)

Revision ID: 052
Revises: 051
Create Date: 2026-06-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "052"
down_revision: Union[str, None] = "051"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cashflow_budget_drivers",
                  sa.Column("lag", sa.Integer, server_default="0"))


def downgrade() -> None:
    op.drop_column("cashflow_budget_drivers", "lag")
