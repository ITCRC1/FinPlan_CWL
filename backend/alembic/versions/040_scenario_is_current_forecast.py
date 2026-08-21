"""Scenario.is_current_forecast — marca el Forecast "Current" (target de uploads)

Revision ID: 040
Revises: 039
Create Date: 2026-06-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "040"
down_revision: Union[str, None] = "039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scenarios", sa.Column(
        "is_current_forecast", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("scenarios", "is_current_forecast")
