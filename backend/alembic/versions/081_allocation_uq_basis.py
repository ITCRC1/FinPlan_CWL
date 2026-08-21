"""Allocation — la restricción única incluye `basis_type`

Desde que Salary Allocation es 1 regla = 1 destino (migración 080), un mismo
departamento puede ENTREGAR y RECIBIR costo en el mismo mes bajo la misma
cuenta 6000: Tours (0150) acredita el salario de sus guías y a la vez recibe
un pedazo de Property Support. La unique vieja
(scenario, type, month, target_dept, account) rechazaba la segunda fila, el
recálculo entero reventaba y la transacción se revertía dejando los repartos
viejos en pie sin avisar.

Agregar `basis_type` separa el cargo (FTE) del crédito (CREDIT). Las filas que
siguen compartiendo llave las consolida el motor antes de insertar
(`_consolidar_repartos` en engine/recalculate.py).

Revision ID: 081
Revises: 080
Create Date: 2026-08-10
"""
from typing import Sequence, Union
from alembic import op

revision: str = "081"
down_revision: Union[str, None] = "080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_allocation_entry", "allocation_entries", type_="unique")
    op.create_unique_constraint(
        "uq_allocation_entry", "allocation_entries",
        ["scenario_id", "allocation_type", "month", "target_dept", "account", "basis_type"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_allocation_entry", "allocation_entries", type_="unique")
    op.create_unique_constraint(
        "uq_allocation_entry", "allocation_entries",
        ["scenario_id", "allocation_type", "month", "target_dept", "account"],
    )
