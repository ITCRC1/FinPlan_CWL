"""Cuentas estadisticas CALCULADAS: el set de FTE (9902-9905).

Owner, 2026-11-10: *«crea un set de estadisticas para FTE, busca en los rangos
que tenemos»* — despues de fijar la jornada en los dias del mes x 8 y de
guardarla en la 9979.

Las cuentas del set no se cargan: salen de las horas (9980-9986) divididas por
la base (9979). Hasta hoy toda cuenta del catalogo era un dato a llenar, asi
que la plantilla les habria abierto una fila a cada una por depto y posicion
—un lugar para escribir un numero que el sistema tiene que calcular, y que
el dia que no coincidiera dejaria dos FTE distintos para el mismo mes—.

`formula` vacia = se carga, como siempre. Con formula = se calcula: la
plantilla no la ofrece y una subida que la traiga se rechaza.

Revision ID: 162
Revises: 161
"""
import sqlalchemy as sa
from alembic import op

revision = "162"
down_revision = "161"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stat_accounts",
        sa.Column("formula", sa.String(80), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("stat_accounts", "formula")
