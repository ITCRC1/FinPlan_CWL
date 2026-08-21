"""Salary Allocation: una regla por DESTINO, no una por posicion.

La llave unica era (escenario, departamento, posicion), o sea que un puesto solo
podia tener UNA regla y por eso los destinos vivian amontonados en una lista,
repartiendose solos por el FTE de cada destino. El owner no puede auditar eso:
ve un solo renglon y adentro un reparto automatico que no eligio.

Con la llave abierta, un mismo puesto puede tener un renglon por destino —
guia de aventura 0.5 FTE a Compras y 0.5 FTE a Transporte— y cada linea dice
exactamente cuanto va a donde.

No se pone una llave nueva mas amplia porque el destino vive en una columna
JSON y no sirve de llave. Tampoco hace falta: el endpoint que guarda borra
todas las reglas del escenario y reinserta la lista completa, asi que lo que
queda es siempre lo que el owner dejo en pantalla.

Revision ID: 080
Revises: 079
"""
from alembic import op
import sqlalchemy as sa

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None

LLAVE = "uq_salary_alloc_config"


def upgrade() -> None:
    conn = op.get_bind()
    existe = conn.execute(sa.text("""
        SELECT 1 FROM pg_constraint
         WHERE conname = :n AND conrelid = 'salary_allocation_config'::regclass
    """), {"n": LLAVE}).first()
    if existe:
        op.drop_constraint(LLAVE, "salary_allocation_config", type_="unique")


def downgrade() -> None:
    # Solo se puede volver atras si ningun puesto quedo con mas de un renglon.
    conn = op.get_bind()
    choque = conn.execute(sa.text("""
        SELECT 1 FROM salary_allocation_config
         GROUP BY scenario_id, source_dept, position_code HAVING count(*) > 1 LIMIT 1
    """)).first()
    if choque:
        raise RuntimeError(
            "Hay puestos con varias reglas (una por destino). Consolidelos antes "
            "de revertir esta migracion, o la llave unica no se puede recrear."
        )
    op.create_unique_constraint(
        LLAVE, "salary_allocation_config",
        ["scenario_id", "source_dept", "position_code"],
    )
