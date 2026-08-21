# -*- coding: utf-8 -*-
"""Los canales comerciales y su comision — la tercera lista de canales.

Owner (2026-08-14), desde su app de Compensacion: 7 canales con su %.

Es OTRO EJE que el market code de Opera: cuatro describen POR DONDE entro la
reserva —eso Opera lo sabe— y tres describen QUIEN la trajo, que el PMS no
registra. Por eso viven aparte y no se derivan uno del otro.

Tenerlos en la misma base sirve para VERLOS JUNTOS, que es lo que el owner
pidio: las comisiones de esta tabla y las de `sales_channel_configs` describen el
mismo negocio y NO dicen lo mismo.

Revision ID: 109
"""
from alembic import op
import sqlalchemy as sa

revision = "109"
down_revision = "108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canales_comerciales",
        sa.Column("code", sa.String(30), primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False, server_default=""),
        sa.Column("comision_pct", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("entrada", sa.String(40), nullable=False, server_default=""),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    op.drop_table("canales_comerciales")
