"""el Private Bar se cobra TODO con tarjeta — % propio, fuera del residual «otros»

El owner confirmó (2026-08-12) que el consumo del Private Bar se cobra entero
con tarjeta. Hasta ahora el `0121` no tenía porcentaje propio y su venta caía en
el residual «otros» de `engine/tax.py`, al **60%**.

Eso importaba más de lo que parece: esa venta antes se codificaba dentro de A&B,
que está al **70%**. O sea que sacar el Private Bar de F&B le había BAJADO el
porcentaje sin que nada avisara. No mueve el EBT ni el impuesto bruto — mueve la
retención acumulada, que es crédito contra el impuesto, así que sube el impuesto
neto a pagar. Y no se ve: el bar no es una fila del panorama fiscal, queda
absorbido dentro de «otros».

**La trampa al implementarlo**, por si alguien agrega la siguiente línea: `other`
es un RESIDUAL (`total − las nombradas`), no una línea. Toda línea que se saque a
porcentaje propio HAY que restarla del residual, o se cobra dos veces —una en su
línea y otra dentro de «otros»— y la retención sale inflada. Nada lo delata:
`card_revenue` no tiene contra qué cuadrar. Está hecho en `tax.py` y hay prueba.

El default es 1.00 y se rellena en las filas que ya existen. Como el `0121` está
en cero, ningún escenario cambia de número hoy.

Revision ID: 101
Revises: 100
"""
from alembic import op
import sqlalchemy as sa

revision = "101"
down_revision = "100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tax_params", sa.Column(
        "card_pct_private_bar", sa.Numeric(6, 4), nullable=False,
        server_default="1.00"))
    # Las filas que ya existían nacen con el criterio del owner, no con el 0.60
    # del cajón donde venían cayendo.
    op.execute("UPDATE tax_params SET card_pct_private_bar = 1.00")


def downgrade() -> None:
    op.drop_column("tax_params", "card_pct_private_bar")
