"""009 actual entries

Revision ID: 009
Revises: 008
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
           "jul", "aug", "sep", "oct", "nov", "dec"]


def upgrade() -> None:
    op.create_table(
        "actual_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, server_default=""),
        sa.Column("dept_code", sa.String(10), nullable=False, server_default=""),
        sa.Column("account_code", sa.String(10), nullable=False),
        sa.Column("account_name", sa.String(120), nullable=False, server_default=""),
        *[sa.Column(m, sa.Numeric(16, 4), nullable=False, server_default="0") for m in _MONTHS],
        sa.UniqueConstraint("scenario_id", "dept_code", "account_code", name="uq_actual_entry"),
    )


def downgrade() -> None:
    op.drop_table("actual_entries")
