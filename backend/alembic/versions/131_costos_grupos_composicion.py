# -*- coding: utf-8 -*-
"""La composición de cada concepto de costo, editable.

Estaba escrita en el código y el owner pidió que fuera editable (2026-08-19),
a propósito de Sustainability. Tenía razón, y no sólo por ese caso: la
composición es donde uno se equivoca, y donde cada propiedad difiere. Con la
tabla, corregirla es una fila; en el código, un despliegue.

**El caso que lo destapó.** La semilla del spec daba $92,12 por habitación
ocupada para el Sustainability Fee, y sólo cerraba sumando
`REV_SUSTAINABILITY` + `REV_MISC_OTHER`: en el libro de origen eran un mismo
cubo ($238.325,28, exacto). **Decisión del owner: van SEPARADOS.** Con eso
Sustainability queda en $54,38 por habitación ocupada y «Other / Misc» pasa a
ser un departamento propio, con $97.656 de contribución en cuatro meses.

⚠️ Eso hace que la semilla del §7 ya NO reproduzca — a propósito. La semilla
describía el libro de origen; la decisión del owner describe cómo quiere leerlo
de ahora en adelante.

Aditiva y reversible.
"""
import sqlalchemy as sa
from alembic import op

revision = "131"
down_revision = "130"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cfg_composicion_costos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        # ROOMS, FB, TOURS, TRANSPORTATION, SPA, RETAIL, SUSTAINABILITY…
        sa.Column("concepto", sa.String(32), nullable=False),
        # propio  = el costo completo del departamento (§4.1)
        # venta   = sólo el variable, el que va al Piso 1 marginal
        # ingreso = su revenue, para la contribución que la Golden Rate resta
        sa.Column("rol", sa.String(10), nullable=False),
        sa.Column("line_code", sa.String(40), nullable=False),
        sa.Column("activa", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("hotel_id", "concepto", "rol", "line_code",
                            name="uq_cfg_composicion_costos"),
    )


def downgrade() -> None:
    op.drop_table("cfg_composicion_costos")
