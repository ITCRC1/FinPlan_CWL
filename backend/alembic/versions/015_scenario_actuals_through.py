"""Rolling forecast cut: scenarios.actuals_through

Revision ID: 015
Revises: 014
Create Date: 2026-06-22

Adds actuals_through (1..12, 0=none) to scenarios. For a FORECAST, months
<= actuals_through are "closed" and the P&L reads from the linked ACTUAL
scenario; later months use the forecast's own checkbooks (rolling forecast).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("actuals_through", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("scenarios", "actuals_through")
