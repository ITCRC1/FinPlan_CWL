"""6002 Dia libre pasa a ser automatico, con la misma forma que los feriados.

    6002 = S&W / dias del mes x dias libres del mes

Es la misma mecanica de 6003 Feriados laborados, con su propio calendario: se
declara cuantos dias libres se pagan en cada mes y el motor los prorratea sobre el
salario. Entra a la BASE, asi que cotiza CCSS y aguinaldo — por eso se calcula
antes que ellas.

Nace en CERO como los demas drivers: con el calendario vacio el concepto sigue
siendo manual y se respeta lo que el owner haya subido por Excel.

Revision ID: 076
Revises: 075
"""
from alembic import op
import sqlalchemy as sa

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None

CEROS = "[0,0,0,0,0,0,0,0,0,0,0,0]"


def upgrade() -> None:
    op.add_column("payroll_params",
                  sa.Column("days_off", sa.String(120),
                            nullable=False, server_default=CEROS))


def downgrade() -> None:
    op.drop_column("payroll_params", "days_off")
