"""% por mes y por set para repartir el costo de Rooms

Cierra el costeo de Villas y Residencias: los departamentos ya existen (085),
están marcados como set (086) y tienen mapeo contable (087), pero no había
dónde guardar CUÁNTO se le mueve a cada uno.

Una fila por set destino con doce porcentajes. Rooms no lleva fila: es el
residuo. Se siembran las filas en 0 para todos los escenarios editables, así
que la pantalla abre con la tabla puesta y el reparto sigue sin mover un peso
hasta que alguien escriba un número.

Revision ID: 088
Revises: 087
"""
from alembic import op
import sqlalchemy as sa

revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None

SETS = ["0115", "0116"]
ORIGEN = "0110"


def upgrade() -> None:
    op.create_table(
        "rooms_allocation_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), index=True),
        sa.Column("hotel_id", sa.String(10), index=True, server_default="CWL"),
        sa.Column("dept_code", sa.String(10), nullable=False),
        sa.Column("source_dept", sa.String(10), server_default=ORIGEN),
        sa.Column("pct_monthly", sa.JSON(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("scenario_id", "dept_code", name="uq_rooms_alloc_cfg"),
    )

    ceros = "[0,0,0,0,0,0,0,0,0,0,0,0]"
    for code in SETS:
        op.execute(sa.text(f"""
            INSERT INTO rooms_allocation_config
                (id, scenario_id, hotel_id, dept_code, source_dept,
                 pct_monthly, active, updated_at)
            SELECT gen_random_uuid()::text, s.id, s.hotel_id, :code, :origen,
                   '{ceros}'::json, true, NOW()
            FROM scenarios s
            WHERE NOT EXISTS (
                SELECT 1 FROM rooms_allocation_config c
                WHERE c.scenario_id = s.id AND c.dept_code = :code)
        """).bindparams(code=code, origen=ORIGEN))


def downgrade() -> None:
    op.drop_table("rooms_allocation_config")
