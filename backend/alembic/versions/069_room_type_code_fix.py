"""Room type codes CWL — corrección: Treehouse=BI05, 5 Elements=BL06 (idempotente)

Revision ID: 069
Revises: 068
Create Date: 2026-08-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "069"
down_revision: Union[str, None] = "068"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # Códigos definitivos del owner para CWL (por sort_order, estable).
    conn.execute(sa.text("UPDATE room_type_configs SET code='BI05' WHERE hotel_id='CWL' AND sort_order=5"))
    conn.execute(sa.text("UPDATE room_type_configs SET code='BL06' WHERE hotel_id='CWL' AND sort_order=6"))


def downgrade() -> None:
    pass
