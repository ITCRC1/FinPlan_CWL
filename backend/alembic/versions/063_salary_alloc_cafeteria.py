"""salary_allocation_config — cafeteria_pct (carga social)

Revision ID: 063
Revises: 062
Create Date: 2026-06-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "063"
down_revision: Union[str, None] = "062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("salary_allocation_config",
                  sa.Column("cafeteria_pct", sa.Numeric(6, 4), server_default="0"))


def downgrade() -> None:
    op.drop_column("salary_allocation_config", "cafeteria_pct")
