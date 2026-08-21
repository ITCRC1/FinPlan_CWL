"""matriz depto × dimensión por propiedad (provisionamiento)

Capa FINA del plan de provisionamiento (docs/PROVISIONING_MASTER_DATA_PLAN.md
§3): qué departamentos usa cada propiedad en Ingreso, Planilla, OPEX, Costos y
Gastos de propiedad.

La tabla nace VACÍA a propósito. El default es prendido, así que sin filas
todas las propiedades ven todo — exactamente como hoy. Las únicas filas que van
a existir son las de lo que alguien apague en el provisionamiento. Cutover de
riesgo cero: el día que se despliega, CWL no cambia en nada.

Revision ID: 090
Revises: 089
"""
from alembic import op
import sqlalchemy as sa

revision = "090"
down_revision = "089"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dept_enablement",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("scope_kind", sa.String(20), nullable=False, server_default="DEPT"),
        sa.Column("scope_key", sa.String(40), nullable=False),
        sa.Column("dimension", sa.String(12), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.String(300), server_default=""),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.String(120), server_default=""),
        sa.UniqueConstraint("hotel_id", "scope_kind", "scope_key", "dimension",
                            name="uq_dept_enablement"),
    )


def downgrade() -> None:
    op.drop_table("dept_enablement")
