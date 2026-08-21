"""Scenario master data (units / closed_months / pax_per_night por año)

Revision ID: 031
Revises: 030
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scenario_master",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "scenario_id", sa.String(36),
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("closed_months", sa.String(40), nullable=True),
        sa.Column("pax_per_night", sa.Numeric(6, 4), nullable=True),
        sa.Column("units_json", sa.String(2000), server_default=""),
        sa.UniqueConstraint("scenario_id", name="uq_scenario_master"),
    )


def downgrade() -> None:
    op.drop_table("scenario_master")
