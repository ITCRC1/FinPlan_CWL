# -*- coding: utf-8 -*-
"""El tarifario RACK de referencia para negociar grupos.

Decisión del owner (2026-08-19): «la realidad debe ser Forecast 2026», y
«tomá 2027 como válidos en una tabla de rack rates y yo los edito».

**Por qué una tabla propia y no `rate_cards` del escenario.** El Forecast
Working 2026 —la base del módulo— tiene CERO tarifas, cero ocupación y cero
paquetes: su ingreso viene del GL cargado, no del motor de drivers. Meterle un
tarifario lo dejaría con dos mecanismos de ingreso conviviendo. Pero la razón
de fondo es otra: el módulo entero se sostiene en que **ningún piso depende
del precio** (spec §1, validación 6). Si el rack viviera en el escenario,
editarlo movería el ingreso, el ingreso movería el costo unitario y el piso se
movería solo — la validación que existe para atrapar eso se caería sola.

Acá el precio entra sólo como TECHO de la negociación: `descuento_max =
1 − piso / rack`. Editar el rack mueve el descuento, nunca el piso.

**Por MES y no por temporada.** El rack tiene 7 valores distintos por
categoría y BAJA en temporada baja justo cuando el piso sube: en setiembre
Agujas vale $400 contra un piso de $1.012,56. Un promedio por temporada
taparía exactamente el mes que duele.

Aditiva y reversible.
"""
import sqlalchemy as sa
from alembic import op

revision = "132"
down_revision = "131"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cfg_tarifa_rack",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        # ⚠️ La llave es el CÓDIGO (BL01, BI02…), no el nombre: el código es
        # fijo por categoría y el nombre es una etiqueta renombrable.
        sa.Column("room_type_code", sa.String(20), nullable=False),
        sa.Column("mes", sa.Integer, nullable=False),
        sa.Column("rack", sa.Numeric(12, 4), nullable=False,
                  server_default="0"),
        sa.Column("neto", sa.Numeric(12, 4), nullable=False,
                  server_default="0"),
        sa.Column("pax", sa.Numeric(6, 2), nullable=False, server_default="0"),
        sa.UniqueConstraint("hotel_id", "room_type_code", "mes",
                            name="uq_cfg_tarifa_rack"),
    )


def downgrade() -> None:
    op.drop_table("cfg_tarifa_rack")
