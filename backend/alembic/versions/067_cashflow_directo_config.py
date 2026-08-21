"""Cash Flow Método Directo — config (params/drivers + manual) por escenario

Revision ID: 067
Revises: 066
Create Date: 2026-07-01
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "067"
down_revision: Union[str, None] = "066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cashflow_directo_config",
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("params", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("manual", sa.JSON, nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_table("cashflow_directo_config")
