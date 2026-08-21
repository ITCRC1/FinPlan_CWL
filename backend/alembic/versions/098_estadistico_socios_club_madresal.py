"""el conteo de socios del Club Madresal

**Qué es.** El Club vende **acceso a las instalaciones** del hotel. Detrás hay un
desarrollo inmobiliario que NO es parte de este P&L; lo que sí entra es la cuota
de acceso, que se cobra en el departamento `260` y ya vive en `REV_CLUB`. El
conteo de socios explica esa cuota —cuántos pagan, cuántos están condicionados—
pero **no es dinero**: va arriba con los KPIs de habitaciones, no en una línea
del estado de resultados. Es el hueco 2 de la Fase 2
(`docs/PLAN_FASES_1_Y_2.md` §2.6).

Cuatro conteos por mes, los mismos del Excel de Amarena (filas 11–14):
Total Membresías · Condicionados · Pagando · En acuerdo de pago.

**El total del año NO es la suma de los doce meses, es diciembre.** Son socios,
no ingresos: sumar 121 + 121 + 123… daría 1.500 socios donde hay 129. Junto con
la ocupación y el ADR son las únicas cuatro filas del archivo con semántica no
aditiva (`ESCANEO_03` §5.13).

**Y se va a ir.** El owner fue explícito: esto desaparece cuando el Club se
opere por fuera del hotel — es de Amarena. Por eso la visibilidad no se decide
con un `if` por hotel sino con la matriz de provisionamiento: se muestra si el
departamento `260` está habilitado en la propiedad. El día que salga, se
desmarca en Provisionamiento y se apaga solo, sin tocar código. Los datos
quedan: apagar esconde, nunca borra.

Revision ID: 098
Revises: 097
"""
from alembic import op
import sqlalchemy as sa

revision = "098"
down_revision = "097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "club_membership_stats",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("condicionados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pagando", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("acuerdo_pago", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("scenario_id", "month", name="uq_club_membership_stat"),
    )
    op.create_index("ix_club_membership_stats_scenario_id",
                    "club_membership_stats", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_club_membership_stats_scenario_id", table_name="club_membership_stats")
    op.drop_table("club_membership_stats")
