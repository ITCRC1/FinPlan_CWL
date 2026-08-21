"""Non-operating (below-GOP) checkbook entries

Revision ID: 014
Revises: 013
Create Date: 2026-06-22

Tables:
  nonop_entries — one detail line per (account 8xxx, detail_code) × scenario × 12
                  months (USD). The "mini checkbook" of the owner / below-GOP
                  section (rent, insurance, capex, financial, depreciation…).
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nonop_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("report_line_code", sa.String(40), nullable=False),
        sa.Column("account_code", sa.String(10), nullable=False, server_default=""),
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
            "scenario_id", "report_line_code", "detail_code",
            name="uq_nonop_entry",
        ),
    )
    op.create_index("ix_nonop_entries_scenario_id", "nonop_entries", ["scenario_id"])
    op.create_index("ix_nonop_entries_hotel_id", "nonop_entries", ["hotel_id"])
    op.create_index("ix_nonop_entries_report_line_code", "nonop_entries", ["report_line_code"])


def downgrade() -> None:
    op.drop_index("ix_nonop_entries_report_line_code", table_name="nonop_entries")
    op.drop_index("ix_nonop_entries_hotel_id", table_name="nonop_entries")
    op.drop_index("ix_nonop_entries_scenario_id", table_name="nonop_entries")
    op.drop_table("nonop_entries")
