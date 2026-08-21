"""Revenue account detail (GL 4xxx por cuenta x depto)

Revision ID: 038
Revises: 037
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "038"
down_revision: Union[str, None] = "037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_M = ["jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec"]


def upgrade() -> None:
    op.create_table(
        "revenue_account_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("hotel_id", sa.String(10), index=True),
        sa.Column("dept_code", sa.String(10), index=True),
        sa.Column("account_code", sa.String(10)),
        sa.Column("account_name", sa.String(120), server_default=""),
        *[sa.Column(m, sa.Numeric(14, 4), server_default="0") for m in _M],
        sa.UniqueConstraint("scenario_id", "dept_code", "account_code",
                            name="uq_revacct_scenario_dept_account"),
    )


def downgrade() -> None:
    op.drop_table("revenue_account_entries")
