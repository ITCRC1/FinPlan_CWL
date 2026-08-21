"""Country Mix (mix por país/mercado por mes, rooms/pax — del PMS)

Revision ID: 047
Revises: 046
Create Date: 2026-06-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "047"
down_revision: Union[str, None] = "046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "country_mix_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("country", sa.String(60), nullable=False),
        sa.Column("metric", sa.String(10), nullable=False, server_default="rooms"),
        sa.Column("value", sa.Numeric(14, 2), server_default="0"),
        sa.UniqueConstraint("scenario_id", "month", "country", "metric",
                            name="uq_country_scenario_month_country_metric"),
    )


def downgrade() -> None:
    op.drop_table("country_mix_entries")
