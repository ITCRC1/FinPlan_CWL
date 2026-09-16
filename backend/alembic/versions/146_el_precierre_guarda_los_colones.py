# -*- coding: utf-8 -*-
"""El Pre-Cierre guarda el monto en colones, no solo el dólar.

Owner, 2026-09-15: *«qué tal si queremos ver pre-cierre en colones también… y
que una vez subido haya una parte donde yo pueda verlo en CRC o en USD»*.

El importador **siempre** calculó el colón —es de donde sale el dólar, vía
`a_dolares(mes_crc, tc)`— y lo descartaba antes de guardar. `PrecierreFila`
guardaba sólo las dos columnas en USD.

## Por qué se guarda en vez de reconstruirlo

`usd × tc` **no** devuelve el colón original. El dólar está redondeado, así que
cada fila se corre unos colones y el total no cuadra contra el mayor de
Integrity — que es justamente para lo que sirve mirarlo en colones.

## Las subidas viejas quedan en NULO

No hay de dónde sacarlo, y ponerle `usd × tc` sería un número que se parece al
del mayor sin serlo: el peor de los dos mundos. La pantalla dice que esa vuelta
no tiene colones guardados. El owner lo resuelve subiendo el mes otra vez —su
propia idea, 2026-09-15: *«yo puedo volver a subir el archivo en crc ya para
que se archive»*— y ahí queda exacto.

Seis decimales, igual que las columnas en USD: redondear antes de sumar
acumula deriva (ver la nota de `PrecierreFila.mes_usd`).

Revision ID: 146
Revises: 145
"""
import sqlalchemy as sa
from alembic import op

revision = "146"
down_revision = "145"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("precierre_filas",
                  sa.Column("mes_crc", sa.Numeric(18, 6), nullable=True))
    op.add_column("precierre_filas",
                  sa.Column("acumulado_crc", sa.Numeric(18, 6), nullable=True))
    op.add_column("precierre_posiciones",
                  sa.Column("mes_crc", sa.Numeric(18, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("precierre_posiciones", "mes_crc")
    op.drop_column("precierre_filas", "acumulado_crc")
    op.drop_column("precierre_filas", "mes_crc")
