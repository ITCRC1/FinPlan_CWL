"""Reemplaza menu/links por items ricos de experiencia (tabla estilo Excel)

Revision ID: 028
Revises: 027
Create Date: 2026-06-26

Cada experiencia pasa a tener su propia tabla de inclusiones (unit, unit_price,
enabled, notes, category, qty mult single/double, info). Se elimina el menu
compartido y los links (no se habian usado todavia).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("pkg_experience_components")
    op.drop_table("pkg_menu_components")
    op.create_table(
        "pkg_experience_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("experience_id", sa.String(36), sa.ForeignKey("pkg_experiences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inclusion", sa.String(120), nullable=False),
        sa.Column("unit", sa.String(30), nullable=False, server_default=""),
        sa.Column("unit_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(200), nullable=False, server_default=""),
        sa.Column("category", sa.String(20), nullable=False, server_default=""),
        sa.Column("qty_mult_single", sa.Numeric(8, 4), nullable=False, server_default="1"),
        sa.Column("qty_mult_double", sa.Numeric(8, 4), nullable=False, server_default="1"),
        sa.Column("info", sa.String(120), nullable=False, server_default=""),
    )
    op.create_index("ix_pkg_items_exp", "pkg_experience_items", ["experience_id"])


def downgrade() -> None:
    op.drop_index("ix_pkg_items_exp", table_name="pkg_experience_items")
    op.drop_table("pkg_experience_items")
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
    op.create_table(
        "pkg_experience_components",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("experience_id", sa.String(36), sa.ForeignKey("pkg_experiences.id", ondelete="CASCADE"), nullable=False),
        sa.Column("component_id", sa.String(36), nullable=False),
    )
