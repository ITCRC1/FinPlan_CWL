"""Reparto de beneficios: un mecanismo generico para cualquier cuenta 60xx.

Habia dos formas distintas de meter costo a una cuenta de beneficio y no se
hablaban entre si:

  - Allocations repartia el costo del depto 0220 (cafeteria) a la cuenta 6025 por
    FTE, a nivel DEPARTAMENTAL, dejando 0220 en cero.
  - El driver `cafeteria_daily_crc` (mig 073) escribia esa MISMA cuenta 6025 en la
    planilla, por POSICION. Con las dos encendidas la cafeteria se contaba dos veces.
  - Y el INS (mig 074) tenia su propio reparto por FTE, hecho aparte.

Ahora es una sola cosa configurable. Cada fila dice:

    cuenta   6022 INS · 6025 cafeteria · 6028 vivienda · 6029 transporte · 6030 otros...
    origen   MONTO  = un monto anual que da el usuario
             DEPTO  = el costo de un departamento (que queda en cero al repartirse)
    base     FTE (por peso de plaza) o HEADCOUNT (por cabeza)
    nivel    POSICION (entra a la planilla) o DEPTO (entra como allocation)

Con eso, el INS es {6022, MONTO, FTE, POSICION} y la cafeteria es
{6025, DEPTO 0220, FTE, DEPTO} — el comportamiento de hoy, pero declarado.

`cafeteria_daily_crc` deja de usarse: la cafeteria viene del reparto, no de un
per diem. La columna se conserva para no perder lo que alguien haya digitado.

Revision ID: 075
Revises: 074
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benefit_allocation_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), index=True),
        sa.Column("account", sa.String(10), nullable=False),        # 6022, 6025, 6028…
        sa.Column("label", sa.String(80), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(10), nullable=False, server_default="MONTO"),
        sa.Column("source_dept", sa.String(10), nullable=False, server_default=""),
        sa.Column("amount_crc", sa.Numeric(16, 2), nullable=False, server_default="0"),
        sa.Column("basis", sa.String(12), nullable=False, server_default="FTE"),
        sa.Column("level", sa.String(10), nullable=False, server_default="POSITION"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("scenario_id", "account", name="uq_benefit_alloc_cuenta"),
    )

    # El INS que ya se cargo por `ins_annual_crc` pasa a ser una fila del reparto,
    # para que haya un solo lugar donde mirar.
    con = op.get_bind()
    filas = con.execute(sa.text(
        "SELECT scenario_id, ins_annual_crc FROM payroll_params "
        "WHERE coalesce(ins_annual_crc,0) > 0")).fetchall()
    for sid, monto in filas:
        con.execute(sa.text(
            """INSERT INTO benefit_allocation_config
               (id, scenario_id, account, label, source_type, source_dept,
                amount_crc, basis, level, active)
               VALUES (:id, :sid, '6022', 'Riesgos del trabajo (INS)', 'MONTO', '',
                       :monto, 'FTE', 'POSITION', true)"""),
            {"id": str(uuid.uuid4()), "sid": sid, "monto": monto})


def downgrade() -> None:
    op.drop_table("benefit_allocation_config")
