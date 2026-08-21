# -*- coding: utf-8 -*-
"""`report_lines.estilo` — cómo se pinta cada fila en el archivo que va a SCP.

El owner mandó su archivo real y el export no lo replicaba: faltaban el bloque
de encabezado (`As of Date` / `Location` / `Month Ending` con las fechas), el
signo de dólar en los montos, los dos azules de subtotal y total, los bordes, la
fuente Helvetica 12 y la sangría de dos espacios por nivel.

El estilo se guarda POR FILA, leído del propio archivo del owner, porque no se
deriva de nada: la fila 49 lleva línea arriba sin ser subtotal, la 52 la lleva
doble, y `TOTAL DEPARTMENTAL PROFIT` se pinta como subtotal mientras `GROSS
OPERATING PROFIT` —el mismo tipo de línea— se pinta como total.

Que quede en la tabla y no en el exportador es la misma regla de siempre: si SCP
cambia el formato, se cambia el seed y no se toca una línea de código.

`{resalte: ''|subtotal|total, formato: money|pct|int, top, bottom,
  sangria_espacios}`. Vacío = fila normal, que es como quedan las que ya existen
hasta que el seed las llene en el próximo arranque.
"""
from alembic import op
import sqlalchemy as sa

revision = "124"
down_revision = "123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("report_lines",
                  sa.Column("estilo", sa.JSON, nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("report_lines", "estilo")
