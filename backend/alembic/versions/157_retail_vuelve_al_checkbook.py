# -*- coding: utf-8 -*-
"""Se deshace la 156: Retail vuelve a salir del Revenue Checkbook.

La 156 calculaba Retail = % x Rooms en el motor de drivers. Owner, 2026-10-23:
el Retail (y el resto de las lineas) se carga en el Revenue Checkbook, con su
propio "Retail % of Room net"; tener un segundo % en Total Revenue confundia.
La fuente correcta es poner el escenario en Checkbook, no otra formula.
"""
import sqlalchemy as sa
from alembic import op

revision = "157"
down_revision = "156"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("scenarios", "retail_pct")


def downgrade() -> None:
    op.add_column("scenarios", sa.Column(
        "retail_pct", sa.Numeric(6, 3), nullable=False, server_default="1.2"))
