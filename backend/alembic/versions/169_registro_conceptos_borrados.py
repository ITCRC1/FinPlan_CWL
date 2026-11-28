"""Planilla: registro de cada borrado de conceptos digitados.

Owner, 2026-11-27: las horas extra (6001) del Budget 2027 Working se perdieron sin
rastro. Cada borrado de conceptos (tasa en 0, reemplazo de planilla desde Excel,
posición borrada) deja una fila con quién, cuándo, cuenta y monto.

Revision ID: 169
Revises: 168
"""
import sqlalchemy as sa
from alembic import op

revision = "169"
down_revision = "168"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payroll_conceptos_borrados",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36), nullable=False, index=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, server_default="", index=True),
        sa.Column("cuando", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("quien", sa.String(160), nullable=False, server_default=""),
        sa.Column("origen", sa.String(40), nullable=False),
        sa.Column("cuenta", sa.String(8), nullable=False),
        sa.Column("concepto", sa.String(40), nullable=False),
        sa.Column("dept_code", sa.String(10), nullable=False, server_default=""),
        sa.Column("position_code", sa.String(40), nullable=False, server_default=""),
        sa.Column("meses", sa.Integer, nullable=False, server_default="0"),
        sa.Column("monto", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("detalle", sa.String(400), nullable=False, server_default=""),
    )


def downgrade():
    op.drop_table("payroll_conceptos_borrados")
