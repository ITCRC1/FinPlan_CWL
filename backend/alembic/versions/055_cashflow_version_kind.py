"""Cash Flow versions — kind (frozen | working)

Revision ID: 055
Revises: 054
Create Date: 2026-06-29
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "055"
down_revision: Union[str, None] = "054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("cashflow_versions",
                  sa.Column("kind", sa.String(12), server_default="frozen", nullable=False))


def downgrade() -> None:
    op.drop_column("cashflow_versions", "kind")
