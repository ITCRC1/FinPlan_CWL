"""department_catalog — universo canónico de departamentos (unifica las 3 fuentes)

Revision ID: 061
Revises: 060
Create Date: 2026-06-29
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "061"
down_revision: Union[str, None] = "060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "department_catalog",
        sa.Column("dept_code", sa.String(10), primary_key=True),
        sa.Column("dept_name", sa.String(100), server_default=""),
        sa.Column("name_en", sa.String(100), server_default=""),
        sa.Column("name_aliases", sa.JSON, nullable=True),
        sa.Column("usali_class", sa.Integer, nullable=True),
        sa.Column("default_pl_group", sa.String(30), server_default=""),
        sa.Column("pl_kind", sa.String(12), server_default="OPERATING"),
        sa.Column("is_revenue_dept", sa.Boolean, server_default=sa.false()),
        sa.Column("is_allocation_source", sa.Boolean, server_default=sa.false()),
        sa.Column("parent_dept_code", sa.String(10), nullable=True),
        sa.Column("display_order", sa.Integer, server_default="0"),
        sa.Column("active", sa.Boolean, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_table("department_catalog")
