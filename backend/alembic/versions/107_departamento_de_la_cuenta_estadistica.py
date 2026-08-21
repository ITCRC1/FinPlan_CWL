# -*- coding: utf-8 -*-
"""En que departamentos vive cada cuenta estadistica.

Sin esto, una cuenta con dimension DEPT genera fila para los 38 departamentos y
el archivo de carga se llena de combinaciones imposibles: covers de
Mantenimiento, kilos de Ventas. El owner tendria que ignorar cientos de filas
que nunca van a tener dato — y una fila que siempre esta vacia entrena a no
mirar.

Revision ID: 107
"""
from alembic import op
import sqlalchemy as sa

revision = "107"
down_revision = "106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stat_accounts",
                  sa.Column("deptos", sa.String(200), nullable=False,
                            server_default=""))


def downgrade() -> None:
    op.drop_column("stat_accounts", "deptos")
