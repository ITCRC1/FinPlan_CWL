"""Room type — código fijo estable (RT01..) para ligar sistemas sin depender del nombre

Revision ID: 068
Revises: 067
Create Date: 2026-08-07
"""
from typing import Sequence, Union
from collections import defaultdict
from alembic import op
import sqlalchemy as sa

revision: str = "068"
down_revision: Union[str, None] = "067"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("room_type_configs",
                  sa.Column("code", sa.String(20), nullable=False, server_default=""))
    # Códigos FIJOS dados por el owner para CWL (en orden de sort_order). Cualquier
    # categoría extra (o de otro hotel) se numera SH## y desde CWL#7 sigue SH07…
    CWL_CODES = ["BL01", "BI02", "PO03", "RO04", "IS05", "AN06"]
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, hotel_id, sort_order FROM room_type_configs ORDER BY hotel_id, sort_order"
    )).fetchall()
    idx: dict = defaultdict(int)
    for r in rows:
        i = idx[r.hotel_id]
        idx[r.hotel_id] += 1
        if r.hotel_id == "CWL" and i < len(CWL_CODES):
            code = CWL_CODES[i]
        else:
            code = f"SH{i + 1:02d}"
        conn.execute(sa.text("UPDATE room_type_configs SET code=:c WHERE id=:id"),
                     {"c": code, "id": r.id})


def downgrade() -> None:
    op.drop_column("room_type_configs", "code")
