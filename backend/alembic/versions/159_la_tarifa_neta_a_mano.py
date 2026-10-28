# -*- coding: utf-8 -*-
"""La tarifa NETA se puede fijar a mano, y deja de seguir la formula.

Owner, 2026-10-27, mirando el Net Rate de las villas: *«dame para yo poner esto
manual por ahora.. editable»*.

## Por que hace falta

El modelo del sistema es `net = rack x net factor`: se carga la tarifa
PUBLICADA y el mix de canales le descuenta la comision. Eso funciona para las
seis categorias de siempre.

Las villas no entran en ese molde. El owner negocia **$1,700 netos** — es lo que
entra, ya descontada la comision, y no hay un rack publicado del que derivarlo.
Al cargar 1,700 como rack, la pantalla le aplicaba el 20.30% del mes y
presupuestaba **$1,354.90**: $345 menos por noche, ~$73,000 menos en el ano
sobre 212 noches. Sin error, sin aviso, y en la direccion que nadie sospecha
porque el numero se ve plausible.

## La regla

`net_rate_manual = true` significa: **esta celda la puso una persona y no se
recalcula**. Las tres rutas que resincronizaban `net_rate = rack x factor` la
respetan a partir de ahora:

* el guardado masivo de Rack Rates,
* el cambio de mix en el Mixer de canales,
* y el resync previo al «Push to the checkbook».

Lo que NO cambia: el motor de ingresos sigue leyendo `net_rate` y nada mas. Una
celda manual entra al calculo igual que cualquier otra — la diferencia esta en
quien la escribe, no en como se usa.

⚠️ **Default `false` a proposito.** Las tarifas que ya existen siguen derivando
de la formula; ninguna se congela por esta migracion. Solo se vuelve manual la
que alguien edite en la pantalla de Net Rate.

Revision ID: 159
Revises: 158
"""
import sqlalchemy as sa
from alembic import op

revision = "159"
down_revision = "158"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rate_cards",
        sa.Column("net_rate_manual", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("rate_cards", "net_rate_manual")
