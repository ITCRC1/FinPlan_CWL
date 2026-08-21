"""Revenue engine schema — Phase 3

Revision ID: 002
Revises: 001
Create Date: 2026-06-20

Tables:
  sales_channel_configs  — channel mix & commissions per scenario
  rate_cards             — rack + net rates per room type × month
  occupancy_budgets      — rooms occupied per room type × month
  package_configs        — package component rates per scenario
  revenue_other          — flat monthly amounts for Spa, Retail, etc.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sales_channel_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("mix_pct", sa.Numeric(8, 6), nullable=False),
        sa.Column("commission_pct", sa.Numeric(8, 6), nullable=False),
    )
    op.create_index("ix_scc_scenario_id", "sales_channel_configs", ["scenario_id"])

    op.create_table(
        "rate_cards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("room_type_id", sa.String(36),
                  sa.ForeignKey("room_type_configs.id"), nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("rack_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("net_rate", sa.Numeric(12, 4), nullable=False),
        sa.Column("pax_per_room", sa.Numeric(6, 4), nullable=False, server_default="1.8000"),
        sa.UniqueConstraint("scenario_id", "room_type_id", "month", name="uq_rate_card"),
    )
    op.create_index("ix_rate_cards_scenario_id", "rate_cards", ["scenario_id"])

    op.create_table(
        "occupancy_budgets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("room_type_id", sa.String(36),
                  sa.ForeignKey("room_type_configs.id"), nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("rooms_occupied", sa.Numeric(10, 4), nullable=False),
        sa.UniqueConstraint("scenario_id", "room_type_id", "month", name="uq_occupancy_budget"),
    )
    op.create_index("ix_occ_budgets_scenario_id", "occupancy_budgets", ["scenario_id"])

    op.create_table(
        "package_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("component", sa.String(20), nullable=False),
        sa.Column("rate_per_pax_night", sa.Numeric(10, 4), nullable=False),
        sa.Column("is_commissionable", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("bev_food_ratio", sa.Numeric(8, 6), nullable=True),
        sa.UniqueConstraint("scenario_id", "component", name="uq_package_config"),
    )
    op.create_index("ix_package_configs_scenario_id", "package_configs", ["scenario_id"])

    op.create_table(
        "revenue_other",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("line", sa.String(20), nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("amount_usd", sa.Numeric(14, 4), nullable=False),
        sa.UniqueConstraint("scenario_id", "line", "month", name="uq_revenue_other"),
    )
    op.create_index("ix_revenue_other_scenario_id", "revenue_other", ["scenario_id"])


def downgrade() -> None:
    op.drop_table("revenue_other")
    op.drop_table("package_configs")
    op.drop_table("occupancy_budgets")
    op.drop_table("rate_cards")
    op.drop_table("sales_channel_configs")
