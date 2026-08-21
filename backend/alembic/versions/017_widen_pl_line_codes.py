"""017 widen pl_lines.line_code/section (DB-driven mapping uses longer codes)

Revision ID: 017
Revises: 016
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("pl_lines", "line_code",
                    type_=sa.String(60), existing_type=sa.String(20))
    op.alter_column("pl_lines", "section",
                    type_=sa.String(60), existing_type=sa.String(20))


def downgrade() -> None:
    op.alter_column("pl_lines", "line_code",
                    type_=sa.String(20), existing_type=sa.String(60))
    op.alter_column("pl_lines", "section",
                    type_=sa.String(20), existing_type=sa.String(60))
