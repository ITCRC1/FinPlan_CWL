"""Section assignments (colaboración — Fase 3)

Revision ID: 033
Revises: 032
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "section_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "scenario_id", sa.String(36),
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("section", sa.String(20), nullable=False),
        sa.Column("assignee_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(16), server_default="pending"),
        sa.Column("locked", sa.Boolean, server_default=sa.false()),
        sa.UniqueConstraint("scenario_id", "section", name="uq_section_assignment"),
    )


def downgrade() -> None:
    op.drop_table("section_assignments")
