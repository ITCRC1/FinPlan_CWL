"""Tax params (Fase D2)

Revision ID: 037
Revises: 036
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tax_params",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("wh_rate", sa.Numeric(6, 4), server_default="0.025"),
        sa.Column("income_tax_rate", sa.Numeric(6, 4), server_default="0.30"),
        sa.Column("card_pct_rooms", sa.Numeric(6, 4), server_default="0.90"),
        sa.Column("card_pct_fb", sa.Numeric(6, 4), server_default="0.70"),
        sa.Column("card_pct_spa", sa.Numeric(6, 4), server_default="0.80"),
        sa.Column("card_pct_tours", sa.Numeric(6, 4), server_default="0.75"),
        sa.Column("card_pct_other", sa.Numeric(6, 4), server_default="0.60"),
        sa.UniqueConstraint("scenario_id", name="uq_tax_params_scenario"),
    )


def downgrade() -> None:
    op.drop_table("tax_params")
