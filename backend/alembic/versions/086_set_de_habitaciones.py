"""marca qué departamentos son SET de categorías de habitación

Rooms (0110) ya tenía hijos —Front Desk, Reservation, Housekeeping, Concierge—
que son FUNCIONES del departamento, no conjuntos de producto: no se le puede
asignar una villa a Housekeeping. Filtrar por «hijo de Rooms» los traía a todos.

Se marca explícito cuáles son SET (Rooms, Villas, Residencias) en vez de
deducirlo de atributos que no lo dicen. Un set nuevo mañana es prender esta
bandera, no cambiar una consulta.

Revision ID: 086
Revises: 085
"""
from alembic import op
import sqlalchemy as sa

revision = "086"
down_revision = "085"
branch_labels = None
depends_on = None

SETS = ["0110", "0115", "0116"]


def upgrade() -> None:
    op.add_column("department_catalog",
                  sa.Column("room_set", sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    op.execute(sa.text(
        "UPDATE department_catalog SET room_set = true WHERE dept_code IN "
        "('0110', '0115', '0116')"))


def downgrade() -> None:
    op.drop_column("department_catalog", "room_set")
