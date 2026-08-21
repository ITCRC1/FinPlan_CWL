"""007 allocation schema

Revision ID: 007
Revises: 006
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cafeteria_allocation_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("dept_code", sa.String(10), nullable=False),
        sa.Column("dept_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("participates", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notes", sa.String(200), nullable=False, server_default=""),
        sa.UniqueConstraint("scenario_id", "dept_code", name="uq_cafeteria_config"),
    )

    op.create_table(
        "laundry_allocation_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("dept_code", sa.String(10), nullable=False),
        sa.Column("dept_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("kilos_historicos", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("participates", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notes", sa.String(200), nullable=False, server_default=""),
        sa.UniqueConstraint("scenario_id", "dept_code", name="uq_laundry_config"),
    )

    op.create_table(
        "allocation_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("allocation_type", sa.String(20), nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("year", sa.Integer, nullable=False, server_default="2026"),
        sa.Column("source_dept", sa.String(10), nullable=False),
        sa.Column("target_dept", sa.String(10), nullable=False),
        sa.Column("amount_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("basis_value", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("basis_type", sa.String(10), nullable=False),
        sa.Column("calculated_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint(
            "scenario_id", "allocation_type", "month", "target_dept",
            name="uq_allocation_entry",
        ),
    )
    # NOTE: scenario_id already has index=True on the column above, which creates
    # ix_allocation_entries_scenario_id. Do NOT create it again here.


def downgrade() -> None:
    op.drop_table("allocation_entries")
    op.drop_table("laundry_allocation_config")
    op.drop_table("cafeteria_allocation_config")
