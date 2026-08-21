"""Cash Flow versions — snapshots planos presentados a dueños

Revision ID: 054
Revises: 053
Create Date: 2026-06-29
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "054"
down_revision: Union[str, None] = "053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cashflow_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(8), nullable=False, index=True, server_default="CWL"),
        sa.Column("name", sa.String(160), server_default=""),
        sa.Column("order_idx", sa.Integer, server_default="0"),
        sa.Column("rows", sa.JSON),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("cashflow_versions")
