"""008 P&L schema (pl_lines + pl_manual_inputs)

Revision ID: 008
Revises: 007
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pl_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("year", sa.Integer, nullable=False, server_default="2026"),
        sa.Column("line_code", sa.String(40), nullable=False),
        sa.Column("line_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("section", sa.String(20), nullable=False, server_default=""),
        sa.Column("dept_code", sa.String(20), nullable=False, server_default=""),
        sa.Column("amount_usd", sa.Numeric(16, 4), nullable=False, server_default="0"),
        sa.Column("is_calculated", sa.Boolean, nullable=False, server_default="true"),
        sa.UniqueConstraint("scenario_id", "month", "line_code", name="uq_pl_line"),
    )

    op.create_table(
        "pl_manual_inputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("rent", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("mgmt_fee_pct_3", sa.Numeric(8, 6), nullable=False, server_default="0.03"),
        sa.Column("mgmt_fee_pct_5", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("properties_insurance", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("capital_reserve", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("large_capex", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("bank_interest", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("depreciation", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("income_tax_rate", sa.Numeric(8, 6), nullable=False, server_default="0.30"),
        sa.UniqueConstraint("scenario_id", "month", name="uq_pl_manual_input"),
    )


def downgrade() -> None:
    op.drop_table("pl_manual_inputs")
    op.drop_table("pl_lines")
