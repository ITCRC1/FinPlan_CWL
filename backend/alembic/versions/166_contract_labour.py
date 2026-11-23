"""Planilla: cuenta 6031 Contract Labour.

Owner, 2026-11-22: «necesito crear una cuenta que se llame Contract Labour que no
forme parte del cálculo de la CCSS y Aguinaldo pero que agrupe en Salaries». Debe
existir en todos los departamentos, y suele ir en dólares.

Una posición con el check «Contract Labour» (`payroll_positions.contract_labour`) manda su salario × FTE (÷ TC si es en colones) a
esta columna en vez de a 6000, y no genera cargas: ni CCSS, ni aguinaldo, ni
vacaciones, ni INS, ni beneficios por persona.

Solo agrega dos columnas: el check (nace en falso) y el concepto (nace en cero).

Revision ID: 166
Revises: 165
"""
import sqlalchemy as sa
from alembic import op

revision = "166"
down_revision = "165"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payroll_positions",
                  sa.Column("contract_labour", sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    op.add_column("payroll_concept_entries",
                  sa.Column("c6031_contract_labour", sa.Numeric(14, 4),
                            nullable=False, server_default="0"))


def downgrade():
    op.drop_column("payroll_positions", "contract_labour")
    op.drop_column("payroll_concept_entries", "c6031_contract_labour")
