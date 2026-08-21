"""Cada linea del checkbook lleva su moneda.

El Budget 2026 se armo con TC 500 y hoy el TC es 450. Los costos se metieron en
dolares, pero muchos se pagan en COLONES: cafeteria, alimentos y bebidas. Con el
monto congelado en dolares, un movimiento del tipo de cambio desalinea el
presupuesto y nada lo avisa.

Ahora cada linea de OPEX y de Costos declara su moneda:

  currency = 'USD'  -> como siempre: los 12 meses son dolares y no se convierten.
  currency = 'CRC'  -> el dato MAESTRO son los colones (crc_jan..crc_dec) y el
                       dolar de cada mes se DERIVA con el TC DE ESE MES.

Se derivan y se guardan en las mismas columnas jan..dec de siempre, asi que todo
lo que lee el checkbook —P&L, allocations, reportes, exports, el tab de Control—
sigue viendo dolares y no cambia ni una linea. Sin eso, cada lugar que leyera un
monto tendria que acordarse de convertir, y el que se olvidara daria un numero
450 veces mas grande.

Mover el TC de un mes y recalcular re-expresa ese mes solo: es como el forecast
absorbe el impacto cambiario mes a mes.

Las lineas que ya existen quedan en USD: ningun numero cambia con esta migracion.

Revision ID: 077
Revises: 076
"""
from alembic import op
import sqlalchemy as sa

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]
TABLAS = ("opex_entries", "cost_entries")


def upgrade() -> None:
    for t in TABLAS:
        op.add_column(t, sa.Column("currency", sa.String(3),
                                   nullable=False, server_default="USD"))
        for m in MESES:
            op.add_column(t, sa.Column(f"crc_{m}", sa.Numeric(16, 2),
                                       nullable=False, server_default="0"))


def downgrade() -> None:
    for t in TABLAS:
        for m in MESES:
            op.drop_column(t, f"crc_{m}")
        op.drop_column(t, "currency")
