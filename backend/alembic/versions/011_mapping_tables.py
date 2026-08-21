"""011 report line config and account mapping tables

Revision ID: 011
Revises: 010
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Report line config — one row per line in the P&L report layout
    op.create_table(
        "report_line_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_id", sa.String(50), nullable=False, index=True),
        sa.Column("display_order", sa.Integer, nullable=False),
        sa.Column("line_code", sa.String(60), nullable=False),
        sa.Column("section", sa.String(80), nullable=False),
        sa.Column("line_name", sa.String(150), nullable=False),
        # HEADER | MAPPED | CALCULATED | KPI
        sa.Column("line_type", sa.String(20), nullable=False),
        sa.Column("parent_line_code", sa.String(60), nullable=True),
        # e.g. "SUM(REV_*)" or "OPERATING_PROFIT - TOTAL_OVERHEAD_EXPENSES"
        sa.Column("calculation_logic", sa.String(250), nullable=True),
        sa.Column("format_hint", sa.String(30), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.UniqueConstraint("report_id", "line_code", name="uq_report_line_code"),
    )

    # Account mapping — maps GL (dept + account_code) to a report_line_code
    op.create_table(
        "account_mapping",
        sa.Column("id", sa.String(36), primary_key=True),
        # YES | REVIEW | NO
        sa.Column("active_status", sa.String(10), nullable=False, server_default="YES"),
        sa.Column("report_id", sa.String(50), nullable=False, index=True),
        sa.Column("report_line_code", sa.String(60), nullable=False, index=True),
        sa.Column("report_line_name", sa.String(150), nullable=True),
        sa.Column("report_section", sa.String(80), nullable=True),
        sa.Column("display_order", sa.Integer, nullable=True),
        # e.g. "Payroll", "Opex", "Revenue", "Food Cost"
        sa.Column("source_origin", sa.String(60), nullable=True),
        # e.g. "Departamento de Habitaciones"
        sa.Column("source_department", sa.String(100), nullable=True),
        sa.Column("account_code", sa.String(20), nullable=False),
        sa.Column("account_name_example", sa.String(200), nullable=True),
        # Revenue | Expense
        sa.Column("financial_nature", sa.String(20), nullable=False),
        # SUM | SUBTRACT
        sa.Column("rollup_operator", sa.String(10), nullable=False, server_default="SUM"),
        sa.Column("sign_rule", sa.String(250), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.UniqueConstraint(
            "report_id", "source_department", "account_code", "source_origin",
            name="uq_account_mapping",
        ),
    )
    op.create_index(
        "ix_account_mapping_dept_account",
        "account_mapping", ["source_department", "account_code"],
    )


def downgrade() -> None:
    op.drop_table("account_mapping")
    op.drop_table("report_line_config")
