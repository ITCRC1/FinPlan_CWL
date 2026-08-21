# -*- coding: utf-8 -*-
"""FTE real por departamento × mes (`actual_dept_fte`).

Un Actual/Forecast blend puede tener costo real (viene del GL, vía
`PayrollConceptEntry`) sin tener planilla cargada posición por posición —
`PayrollPosition` no existe para ese mes, así que el FTE calculado da 0
aunque el costo sea real y positivo. Esta tabla es la carga manual/Excel que
tapa ese hueco, mismo patrón que `actual_room_stat`: se sube o edita MES a
mes y reemplaza solo ese mes.

Cuando existe una fila acá para (scenario, dept, month), gana sobre el FTE
que saldría de sumar `PayrollPosition` — ver `_dept_fte_override` en
`app/api/payroll_api.py`.
"""
from alembic import op
import sqlalchemy as sa

revision = "121"
down_revision = "120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "actual_dept_fte",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dept_code", sa.String(10), nullable=False),
        sa.Column("dept_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("fte", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    op.create_index("ix_actual_dept_fte_scenario_id", "actual_dept_fte", ["scenario_id"])
    op.create_unique_constraint(
        "uq_deptfte_scenario_dept_month", "actual_dept_fte",
        ["scenario_id", "dept_code", "month"])


def downgrade() -> None:
    op.drop_table("actual_dept_fte")
