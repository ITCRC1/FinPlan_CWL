"""Channel Mix (mix por canal de venta por mes — Market Set vs Budget)

Revision ID: 045
Revises: 044
Create Date: 2026-06-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "045"
down_revision: Union[str, None] = "044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "channel_mix_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("value", sa.Numeric(14, 2), server_default="0"),
        sa.UniqueConstraint("scenario_id", "month", "channel", name="uq_chmix_scenario_month_channel"),
    )


def downgrade() -> None:
    op.drop_table("channel_mix_entries")
