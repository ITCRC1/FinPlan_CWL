"""salary_allocation_config — reasignación de salarios de deptos de apoyo

Revision ID: 062
Revises: 061
Create Date: 2026-06-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "062"
down_revision: Union[str, None] = "061"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "salary_allocation_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("hotel_id", sa.String(10), index=True, server_default="CWL"),
        sa.Column("source_dept", sa.String(10), nullable=False),
        sa.Column("position_code", sa.String(10), nullable=False),
        sa.Column("position_name", sa.String(200), server_default=""),
        sa.Column("portion_pct", sa.Numeric(6, 4), server_default="1"),
        sa.Column("target_depts", sa.JSON, nullable=True),
        sa.Column("account", sa.String(20), server_default="6000"),
        sa.Column("active", sa.Boolean, server_default=sa.true()),
        sa.UniqueConstraint("scenario_id", "source_dept", "position_code",
                            name="uq_salary_alloc_config"),
    )


def downgrade() -> None:
    op.drop_table("salary_allocation_config")
