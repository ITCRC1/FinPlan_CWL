"""Payroll checkbook schema — Phase 4

Revision ID: 003
Revises: 002
Create Date: 2026-06-20

Tables:
  payroll_positions      — one row per position × scenario
  payroll_concept_entries — 17 concepts per position × month
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payroll_positions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("dept_code", sa.String(10), nullable=False),
        sa.Column("dept_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("position_code", sa.String(10), nullable=False, server_default=""),
        sa.Column("position_name", sa.String(200), nullable=False),
        sa.Column("employee_name", sa.String(200), nullable=False, server_default="VACANTE"),
        sa.Column("employee_type", sa.String(20), nullable=False, server_default="1-Permanente"),
        sa.Column("class_code", sa.String(10), nullable=False, server_default="013"),
        sa.Column("category_code", sa.String(10), nullable=False, server_default="015"),
        sa.Column("salary_amount", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("salary_currency", sa.String(3), nullable=False, server_default="CRC"),
        sa.Column("fte_jan", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("fte_feb", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("fte_mar", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("fte_apr", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("fte_may", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("fte_jun", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("fte_jul", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("fte_aug", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("fte_sep", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("fte_oct", sa.Numeric(5, 4), nullable=False, server_default="0.0"),
        sa.Column("fte_nov", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
        sa.Column("fte_dec", sa.Numeric(5, 4), nullable=False, server_default="1.0"),
    )
    op.create_index("ix_payroll_positions_scenario_id", "payroll_positions", ["scenario_id"])
    op.create_index("ix_payroll_positions_dept_code", "payroll_positions", ["dept_code"])
    op.create_index("ix_payroll_positions_hotel_id", "payroll_positions", ["hotel_id"])

    op.create_table(
        "payroll_concept_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position_id", sa.String(36),
                  sa.ForeignKey("payroll_positions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dept_code", sa.String(10), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        # Group BASE
        sa.Column("c6000_sw", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6001_overtime", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6002_day_off", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6003_working_holiday", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6010_commissions", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6024_vacations_taken", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6027_incentive_bonus", sa.Numeric(14, 4), nullable=False, server_default="0"),
        # Automatic
        sa.Column("c6020_ccss", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6021_aguinaldo", sa.Numeric(14, 4), nullable=False, server_default="0"),
        # Manual benefits
        sa.Column("c6004_disabilities", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6022_occ_hazard", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6023_vacation_prov", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6025_cafeteria", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6026_severance", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6028_housing", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6029_transport", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("c6030_other", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "scenario_id", "position_id", "month",
            name="uq_payroll_concept_entry",
        ),
    )
    op.create_index("ix_payroll_concept_entries_scenario_id", "payroll_concept_entries", ["scenario_id"])
    op.create_index("ix_payroll_concept_entries_position_id", "payroll_concept_entries", ["position_id"])
    op.create_index("ix_payroll_concept_entries_dept_code", "payroll_concept_entries", ["dept_code"])


def downgrade() -> None:
    op.drop_table("payroll_concept_entries")
    op.drop_table("payroll_positions")
