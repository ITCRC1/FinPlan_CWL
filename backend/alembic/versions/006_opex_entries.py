"""OPEX entries schema — Phase 6 (Clase 7)

Revision ID: 006
Revises: 005
Create Date: 2026-06-20

Tables:
  opex_entries — one detail line per (dept, account, detail_code) × scenario × 12 months (USD)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "opex_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("dept_code", sa.String(10), nullable=False),
        sa.Column("account_code", sa.String(10), nullable=False),
        sa.Column("account_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("detail_code", sa.String(10), nullable=False, server_default=""),
        sa.Column("detail_desc", sa.String(200), nullable=False, server_default=""),
        sa.Column("jan", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("feb", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("mar", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("apr", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("may", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("jun", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("jul", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("aug", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("sep", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("oct", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("nov", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("dec", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "scenario_id", "dept_code", "account_code", "detail_code",
            name="uq_opex_entry",
        ),
    )
    op.create_index("ix_opex_entries_scenario_id", "opex_entries", ["scenario_id"])
    op.create_index("ix_opex_entries_hotel_id", "opex_entries", ["hotel_id"])
    op.create_index("ix_opex_entries_dept_code", "opex_entries", ["dept_code"])


def downgrade() -> None:
    op.drop_index("ix_opex_entries_dept_code", table_name="opex_entries")
    op.drop_index("ix_opex_entries_hotel_id", table_name="opex_entries")
    op.drop_index("ix_opex_entries_scenario_id", table_name="opex_entries")
    op.drop_table("opex_entries")
