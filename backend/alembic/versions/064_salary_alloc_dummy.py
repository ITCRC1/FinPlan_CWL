"""salary_allocation_config — dummy_monthly (ajuste manual por mes)

Revision ID: 064
Revises: 063
Create Date: 2026-06-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "064"
down_revision: Union[str, None] = "063"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("salary_allocation_config",
                  sa.Column("dummy_monthly", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("salary_allocation_config", "dummy_monthly")
