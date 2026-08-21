"""salary_allocation_config — salary_override (salario manual)

Revision ID: 065
Revises: 064
Create Date: 2026-06-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "065"
down_revision: Union[str, None] = "064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("salary_allocation_config",
                  sa.Column("salary_override", sa.JSON, nullable=True))


def downgrade() -> None:
    op.drop_column("salary_allocation_config", "salary_override")
