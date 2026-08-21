"""el ingreso del Club sale de un driver: socios × cuota

**El problema que resuelve.** El checkbook de ingresos **no tenía línea de
Club**: `REVENUE_LINES` iba de ROOMS a SUSTAINABILITY y `RevenueResult` no tenía
campo `club`. Por eso en los escenarios armados dentro de la app (el Budget 2027)
`REV_CLUB` daba **cero** — no porque faltara cargarlo, sino porque no había por
dónde. Esta migración abre esa puerta y le pone el driver.

**La forma es la misma del Spa**, que ya funciona así: un dato operativo que ya
se lleva (allá el capture rate, acá el conteo de socios) × un precio que se
presupuesta = el ingreso, que se persiste en la línea del checkbook de donde el
P&L lee.

    ingreso del mes = socios(base) × precio + otros

**`base` dice qué socios pagan** — por defecto los que están `pagando`, porque
los condicionados por definición todavía no pagan cuota. Es configurable y no
una constante en el código: quién paga es regla del negocio del Club y puede
cambiar sin que nadie toque esto.

**`otros_usd` es la puerta sin driver.** El Club no vive solo de la cuota: tiene
actividad de fin de año, visitantes y lo que aparezca. Sin esa puerta, todo
ingreso del Club tendría que caber en «socios × precio», que es falso.

Revision ID: 099
Revises: 098
"""
from alembic import op
import sqlalchemy as sa

revision = "099"
down_revision = "098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "club_fee_budgets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hotel_id", sa.String(length=10), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("price_usd", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("otros_usd", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("base", sa.String(length=20), nullable=False, server_default="pagando"),
        sa.UniqueConstraint("scenario_id", "month", name="uq_club_fee_budget"),
    )
    op.create_index("ix_club_fee_budgets_scenario_id", "club_fee_budgets", ["scenario_id"])
    op.create_index("ix_club_fee_budgets_hotel_id", "club_fee_budgets", ["hotel_id"])


def downgrade() -> None:
    op.drop_index("ix_club_fee_budgets_hotel_id", table_name="club_fee_budgets")
    op.drop_index("ix_club_fee_budgets_scenario_id", table_name="club_fee_budgets")
    op.drop_table("club_fee_budgets")
