"""Cash Flow Budget — parámetros del modelo de timing de Working Capital

Revision ID: 053
Revises: 052
Create Date: 2026-06-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "053"
down_revision: Union[str, None] = "052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cashflow_wc_params",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("enabled", sa.Boolean, server_default=sa.false()),
        sa.Column("params", sa.JSON),
        sa.UniqueConstraint("scenario_id", name="uq_cfwc_scenario"),
    )


def downgrade() -> None:
    op.drop_table("cashflow_wc_params")
