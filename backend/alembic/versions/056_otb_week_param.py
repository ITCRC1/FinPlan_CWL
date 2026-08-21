"""On The Books — parámetro % venta en propiedad por semana

Revision ID: 056
Revises: 055
Create Date: 2026-06-29
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "056"
down_revision: Union[str, None] = "055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "otb_week_params",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("week", sa.Integer, nullable=False, index=True),
        sa.Column("on_prop_pct", sa.Numeric(6, 4), server_default="0.126"),
        sa.UniqueConstraint("scenario_id", "week", name="uq_otbparam_scenario_week"),
    )


def downgrade() -> None:
    op.drop_table("otb_week_params")
