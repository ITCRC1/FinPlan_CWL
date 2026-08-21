"""Package menu + experiences (cada experiencia elige componentes del menú)

Revision ID: 027
Revises: 026
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pkg_menu_components",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("rate_per_pax_night", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("is_commissionable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_pkg_menu_scenario", "pkg_menu_components", ["scenario_id"])
    op.create_table(
        "pkg_experiences",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("nights", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_pkg_exp_scenario", "pkg_experiences", ["scenario_id"])
    op.create_table(
        "pkg_experience_components",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("experience_id", sa.String(36), sa.ForeignKey("pkg_experiences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_id", sa.String(36), nullable=False),
    )
    op.create_index("ix_pkg_expcomp_exp", "pkg_experience_components", ["experience_id"])


def downgrade() -> None:
    op.drop_table("pkg_experience_components")
    op.drop_index("ix_pkg_exp_scenario", table_name="pkg_experiences")
    op.drop_table("pkg_experiences")
    op.drop_index("ix_pkg_menu_scenario", table_name="pkg_menu_components")
    op.drop_table("pkg_menu_components")
