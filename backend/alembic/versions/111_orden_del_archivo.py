# -*- coding: utf-8 -*-
"""El orden en que el owner subio cada fila.

Owner (2026-08-14): «debe quedar en el mismo orden, y que esten todas. mismo
orden.»

La plantilla del Detalle se ordenaba por grupo del P&L y clase — determinista y
estable entre descargas, pero NO el orden del archivo que el owner subio. La base
no guardaba esa informacion, asi que no habia forma de devolverla: cada vez que
comparaba la bajada contra su archivo historico tenia que cruzar dos listas.

`orden_archivo` es la fila del Excel de origen. NULL = esa fila no vino de un
archivo (o vino de antes de esta migracion): la exportacion cae al orden por
grupo, que es el de siempre. Por eso no hace falta backfill.

Revision ID: 111
"""
from alembic import op
import sqlalchemy as sa

revision = "111"
down_revision = "110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("actual_entries",
                  sa.Column("orden_archivo", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("actual_entries", "orden_archivo")
