"""Las tarifas del boton «Llenar desde drivers» se guardan por escenario.

Owner, 2026-11-09, sobre el recuadro «noches por estadia»: *«puse 2.80 de
estadia promedio porque hay gente que viene sola y hay gente que viene mas
dias... pero no vi que el calculo de revenue cambiara»*.

No cambiaba por tres razones, y la tercera era un defecto: **los nueve
recuadros de esa fila no se guardaban en ningun lado**. Eran estado del
navegador. Se escribia 2,80, se recargaba la pantalla y volvia a 3 — el valor
que viene del paquete, que ademas es un ENTERO (`int(base["nights"])`), asi que
un promedio de estadia con decimales no tenia donde vivir.

Un recuadro que olvida lo que uno escribio es peor que no tenerlo: invita a
poner un supuesto, lo usa una vez y despues lo pierde sin avisar.

Se guardan en `scenario_master`, que ya es la fila por escenario que lleva los
meses cerrados, el pax y las unidades. Una columna JSON y no nueve columnas,
porque la lista de perillas va a crecer —hoy mismo se le agrega el «% que no
consume»— y cada perilla nueva no deberia ser una migracion.

Revision ID: 161
Revises: 160
"""
import sqlalchemy as sa
from alembic import op

revision = "161"
down_revision = "160"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenario_master",
        sa.Column("driver_rates_json", sa.Text(), nullable=False,
                  server_default=""),
    )


def downgrade() -> None:
    op.drop_column("scenario_master", "driver_rates_json")
