"""Allocation — restricción única incluye `account`

El modelo 3-vías de lavandería genera 2 filas por depto/mes (linen 7310 +
uniformes 7685). La restricción vieja (scenario, type, month, target_dept)
lo impedía y hacía fallar el recálculo. Se agrega `account` a la unique.

Revision ID: 058
Revises: 057
Create Date: 2026-06-29
"""
from typing import Sequence, Union
from alembic import op

revision: str = "058"
down_revision: Union[str, None] = "057"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_allocation_entry", "allocation_entries", type_="unique")
    op.create_unique_constraint(
        "uq_allocation_entry", "allocation_entries",
        ["scenario_id", "allocation_type", "month", "target_dept", "account"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_allocation_entry", "allocation_entries", type_="unique")
    op.create_unique_constraint(
        "uq_allocation_entry", "allocation_entries",
        ["scenario_id", "allocation_type", "month", "target_dept"],
    )
