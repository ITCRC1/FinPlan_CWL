"""Balance Sheet (estado de situación financiera, bloque Summary) por escenario

Revision ID: 049
Revises: 048
Create Date: 2026-06-28
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "049"
down_revision: Union[str, None] = "048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "balance_sheet_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("year", sa.Integer, nullable=False, index=True),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("order_idx", sa.Integer, nullable=False, server_default="0"),
        sa.Column("label", sa.String(200), server_default=""),
        sa.Column("indent", sa.Integer, server_default="0"),
        sa.Column("section", sa.String(12), server_default=""),
        sa.Column("is_total", sa.Boolean, server_default=sa.false()),
        sa.Column("usd", sa.Numeric(16, 2), server_default="0"),
        sa.Column("crc", sa.Numeric(18, 2), server_default="0"),
        sa.UniqueConstraint("scenario_id", "year", "month", "order_idx",
                            name="uq_bs_scenario_year_month_order"),
    )


def downgrade() -> None:
    op.drop_table("balance_sheet_lines")
