"""pl_manual_inputs — mgmt_fee_pct_3 server_default 0.03 -> 0

Kills the phantom 3% management fee: with a 0.03 server_default, any budget/
forecast with no manual inputs fabricated a 3%-of-revenue mgmt fee into Non
Allocated Expenses. Real below-GOP comes from the 8xxx accounts; the % driver is
opt-in. The table is empty today, so this only affects future inserts.

Revision ID: 066
Revises: 065
Create Date: 2026-06-30
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "066"
down_revision: Union[str, None] = "065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("pl_manual_inputs", "mgmt_fee_pct_3",
                    existing_type=sa.Numeric(8, 6), server_default="0")


def downgrade() -> None:
    op.alter_column("pl_manual_inputs", "mgmt_fee_pct_3",
                    existing_type=sa.Numeric(8, 6), server_default="0.03")
