"""016 scenario source_mode (imported vs checkbook)

Revision ID: 016
Revises: 015
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("source_mode", sa.String(12), nullable=False, server_default="imported"),
    )


def downgrade() -> None:
    op.drop_column("scenarios", "source_mode")
