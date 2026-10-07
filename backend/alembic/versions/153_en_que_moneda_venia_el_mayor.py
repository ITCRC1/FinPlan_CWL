# -*- coding: utf-8 -*-
"""En qué moneda venían los montos del mayor guardado.

Sin esto, el mayor guardado **no se puede volver a leer bien**. El encabezado del
archivo dice `Moneda: DOL` o `Moneda: COL` y de ahí depende si la columna de
montos son colones o dólares (ver `balance_comprobacion.Linea.monto_crc`). La
columna `moneda` que ya se guardaba es la de la TRANSACCIÓN y viene mezclada
—1.281 `DOL` y 3.497 `COL` en el mismo archivo—, así que no sirve para esto.

Hace falta ahora porque los hallazgos de la Auditoría dejan de recalcularse
sobre el archivo subido y pasan a recalcularse sobre el mayor guardado — owner,
2026-10-07: *«me gustaría que el análisis de diferencias una vez que se suba no
desaparezca… veo que todo desaparece una vez que uno sale y entra otra vez»*.

Sin la moneda del archivo, un mayor subido en dólares daría los montos
multiplicados por el tipo de cambio.

⚠️ Default `COL`, que es lo que el sistema asumía antes de mirar el encabezado.
Las filas que ya estén guardadas quedan con eso — y si el mes se subió en
dólares, hay que volver a subirlo. Es un mes, y la alternativa era adivinar.
"""
import sqlalchemy as sa
from alembic import op

revision = "153"
down_revision = "152"
branch_labels = None
depends_on = None

TABLAS = ("mayor_movimientos", "mayor_movimientos_previos")


def upgrade() -> None:
    for t in TABLAS:
        op.add_column(t, sa.Column("moneda_archivo", sa.String(10),
                                   nullable=False, server_default="COL"))


def downgrade() -> None:
    for t in TABLAS:
        op.drop_column(t, "moneda_archivo")
