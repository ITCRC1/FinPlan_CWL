"""INS de riesgos del trabajo: un monto que se reparte por FTE.

El INS no es parte del 26.83% de la CCSS — es una poliza aparte que el INS factura
al patrono. La practica de la empresa es tomar el cargo que llega y repartirlo
entre todos los empleados, que es justo lo que hace este driver:

    6022 de cada posicion-mes = monto_anual x (FTE de esa posicion-mes / suma de
                                               todos los FTE-mes del ano)

Asi el reparto respeta el peso real de cada departamento, un mes con menos gente
recibe menos, y octubre (lodge cerrado, FTE 0) no recibe nada. La suma de las 6022
da exactamente el monto, con el redondeo puesto en la fila mas grande.

Nace en CERO: mientras no se llene, nada cambia.

Revision ID: 074
Revises: 073
"""
from alembic import op
import sqlalchemy as sa

revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payroll_params",
                  sa.Column("ins_annual_crc", sa.Numeric(16, 2),
                            nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("payroll_params", "ins_annual_crc")
