"""012 add dept_code to account_mapping

Revision ID: 012
Revises: 011
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "account_mapping",
        sa.Column("dept_code", sa.String(10), nullable=True),
    )
    op.create_index(
        "ix_account_mapping_dept_code_acct",
        "account_mapping",
        ["dept_code", "account_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_account_mapping_dept_code_acct", table_name="account_mapping")
    op.drop_column("account_mapping", "dept_code")
