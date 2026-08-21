# -*- coding: utf-8 -*-
"""Los market codes de Opera y su canal.

Habia TRES listas de canales que no se hablaban: `SalesChannelConfig`
(TA/OTA/DIRECT, la que mueve plata), `CWL_CHANNELS` (el mix), y los KPI Groups
de Opera sobre 13 market codes (la realidad del PMS).

El owner mando su tabla y pidio ponerla debajo de Sales Channels, mas detallada:
o sea que el market code es el atomo y lo demas son agrupaciones suyas. Con esto
el modelo de comision pasa a ser un ROLLUP de esta tabla, y las estadisticas
ganan sus dos dimensiones —SEGMENT es el market code, CHANNEL es el canal—, que
era lo que las tenia bloqueadas.

Revision ID: 108
"""
from alembic import op
import sqlalchemy as sa

revision = "108"
down_revision = "107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_codes",
        sa.Column("code", sa.String(20), primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False, server_default=""),
        # Vacio es un estado VALIDO: "nadie lo ha decidido", no "no tiene".
        sa.Column("canal", sa.String(40), nullable=False, server_default="", index=True),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_table("market_codes")
