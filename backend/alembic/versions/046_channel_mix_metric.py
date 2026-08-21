"""Channel Mix por MÉTRICA (rooms/pax) — recrea la tabla con metric

Revision ID: 046
Revises: 045
Create Date: 2026-06-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "046"
down_revision: Union[str, None] = "045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # La tabla está vacía (sin datos cargados aún) → drop+recreate, igual que mig 043.
    op.drop_table("channel_mix_entries")
    op.create_table(
        "channel_mix_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("metric", sa.String(10), nullable=False, server_default="rooms"),
        sa.Column("value", sa.Numeric(14, 2), server_default="0"),
        sa.UniqueConstraint("scenario_id", "month", "channel", "metric",
                            name="uq_chmix_scenario_month_channel_metric"),
    )


def downgrade() -> None:
    op.drop_table("channel_mix_entries")
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
