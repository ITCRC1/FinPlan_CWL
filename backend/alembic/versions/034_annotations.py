"""Annotations — comentarios / Q&A (Fase 3)

Revision ID: 034
Revises: 033
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "annotations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "scenario_id", sa.String(36),
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True,
        ),
        sa.Column("section", sa.String(20), nullable=False),
        sa.Column("ref", sa.String(120), server_default=""),
        sa.Column("month", sa.Integer, server_default="0"),
        sa.Column("kind", sa.String(12), server_default="comment"),
        sa.Column("body", sa.String(2000), nullable=False),
        sa.Column("author_id", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved", sa.Boolean, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("annotations")
