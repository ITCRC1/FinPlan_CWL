"""Initial schema — Phase 1 + Phase 2

Revision ID: 001
Revises:
Create Date: 2026-06-20

Tablas:
  Phase 1: accounts, payroll_accounts
  Phase 2: hotels, scenarios, exchange_rates, room_type_configs
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Phase 1: accounts ──────────────────────────────────────────────────
    op.create_table(
        "accounts",
        sa.Column("code_full", sa.String(60), primary_key=True),
        sa.Column("seg1", sa.String(10), nullable=False),
        sa.Column("seg2", sa.String(10), nullable=False),
        sa.Column("seg3", sa.String(10), nullable=False),
        sa.Column("seg4", sa.String(10), nullable=False),
        sa.Column("seg5", sa.String(10), nullable=False),
        sa.Column("seg6", sa.String(10), nullable=False),
        sa.Column("seg7", sa.String(10), nullable=False),
        sa.Column("descripcion", sa.String(300), nullable=False),
        sa.Column("tipo", sa.String(1), nullable=False),
        sa.Column("estado", sa.String(1), nullable=False, server_default="A"),
        sa.Column("acepta_mov", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("usa_cc", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("aplica_diferencial", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("link_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_accounts_seg1", "accounts", ["seg1"])
    op.create_index("ix_accounts_seg2", "accounts", ["seg2"])
    op.create_index("ix_accounts_tipo", "accounts", ["tipo"])

    op.create_table(
        "payroll_accounts",
        sa.Column("code_full", sa.String(60), primary_key=True),
        sa.Column("nivel1", sa.String(10), nullable=False),
        sa.Column("nivel2", sa.String(10), nullable=False),
        sa.Column("nivel3", sa.String(10), nullable=False),
        sa.Column("nivel4", sa.String(10), nullable=False),
        sa.Column("nivel5", sa.String(10), nullable=False),
        sa.Column("nivel6", sa.String(10), nullable=False),
        sa.Column("nivel7", sa.String(10), nullable=False),
        sa.Column("descripcion", sa.String(300), nullable=False),
        sa.Column("tipo", sa.String(1), nullable=False, server_default="G"),
        sa.Column("acepta_mov", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("link_id", sa.Integer(), nullable=True),
        sa.Column("concepto_nombre", sa.String(100), nullable=True),
        sa.Column("dept_nombre", sa.String(100), nullable=True),
        sa.Column("posicion_nombre", sa.String(100), nullable=True),
    )
    op.create_index("ix_payroll_accounts_nivel1", "payroll_accounts", ["nivel1"])
    op.create_index("ix_payroll_accounts_nivel2", "payroll_accounts", ["nivel2"])

    # ── Phase 2: hotels ────────────────────────────────────────────────────
    op.create_table(
        "hotels",
        sa.Column("id", sa.String(10), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("short_name", sa.String(20), nullable=False),
        sa.Column("rooms", sa.Integer(), nullable=False),
        sa.Column("tc_usd_default", sa.Numeric(10, 4), nullable=False, server_default="530.0000"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(10), nullable=False),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column("source_file", sa.String(200), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by", sa.String(100), nullable=False, server_default=""),
    )
    op.create_index("ix_scenarios_hotel_id", "scenarios", ["hotel_id"])

    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), sa.ForeignKey("scenarios.id"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("tc_crc_usd", sa.Numeric(10, 4), nullable=False),
        sa.Column("notes", sa.String(200), nullable=False, server_default=""),
    )
    op.create_index("ix_exchange_rates_scenario_id", "exchange_rates", ["scenario_id"])

    op.create_table(
        "room_type_configs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), sa.ForeignKey("hotels.id"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("short_name", sa.String(30), nullable=False),
        sa.Column("units", sa.Integer(), nullable=False),
        sa.Column("pax_min", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pax_max", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.create_index("ix_room_type_configs_hotel_id", "room_type_configs", ["hotel_id"])


def downgrade() -> None:
    op.drop_table("room_type_configs")
    op.drop_table("exchange_rates")
    op.drop_table("scenarios")
    op.drop_table("hotels")
    op.drop_table("payroll_accounts")
    op.drop_table("accounts")
