"""Ops KPI (tabla manual de indicadores operativos por escenario)

Revision ID: 048
Revises: 047
Create Date: 2026-06-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "048"
down_revision: Union[str, None] = "047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ops_kpi_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("order_idx", sa.Integer, nullable=False, server_default="0"),
        sa.Column("kpi", sa.String(200), server_default=""),
        sa.Column("target", sa.String(120), server_default=""),
        sa.Column("actual", sa.String(120), server_default=""),
        sa.Column("owner", sa.String(120), server_default=""),
        sa.Column("action", sa.String(400), server_default=""),
    )


def downgrade() -> None:
    op.drop_table("ops_kpi_entries")
