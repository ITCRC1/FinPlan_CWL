"""Budget Big Picture — versiones guardadas (targets de crecimiento)

Revision ID: 060
Revises: 059
Create Date: 2026-06-29
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "060"
down_revision: Union[str, None] = "059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "big_picture_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), index=True, server_default="CWL"),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("base_scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("target_year", sa.Integer, server_default="2027"),
        sa.Column("growth", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("big_picture_versions")
