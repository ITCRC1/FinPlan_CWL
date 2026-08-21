# -*- coding: utf-8 -*-
"""El mix de cada canal comercial, y su excepcion por escenario/mes.

Owner (2026-08-14): «hay que hacerle para todas las versiones, version forecast,
todas las versiones que tienen auxiliares... a partir de enero 2027 el forecast,
el budget, todo lo que se construye ahi como auxiliar tiene que dar con esos
parametros». Budget Final 2026 queda como esta: «ya es lo que es».

DOS TABLAS Y NO UNA, a proposito:

* `canales_comerciales.mix_pct` es el mix BASE — el que aplica cuando nadie dijo
  otra cosa. Es lo que hace que un escenario nuevo NAZCA bien.
* `canal_mix_escenario` es la EXCEPCION: un escenario que negocio distinto, o un
  mes puntual dentro de ese escenario.

Se midio antes de decidir la forma: en los 7 escenarios que tienen canales
guardados, los 12 meses son IDENTICOS. La variacion por mes ya existia en
`sales_channel_configs` y nadie la usaba. Obligar a llenar 7 canales x 12 meses
seria pedir 84 casillas para un dato que en la practica no cambia — asi que el
caso normal es anual (`month = 0`) y el mes es la excepcion que se declara.

Revision ID: 110
"""
from alembic import op
import sqlalchemy as sa

revision = "110"
down_revision = "109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "canales_comerciales",
        sa.Column("mix_pct", sa.Numeric(8, 6), nullable=False, server_default="0"),
    )
    op.create_table(
        "canal_mix_escenario",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        # 0 = el valor anual del escenario. 1..12 = ese mes en particular.
        sa.Column("month", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mix_pct", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.Column("comision_pct", sa.Numeric(8, 6), nullable=False, server_default="0"),
        sa.UniqueConstraint("scenario_id", "code", "month",
                            name="uq_canal_mix_escenario"),
    )
    op.create_index("ix_canal_mix_escenario_scenario", "canal_mix_escenario",
                    ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_canal_mix_escenario_scenario", table_name="canal_mix_escenario")
    op.drop_table("canal_mix_escenario")
    op.drop_column("canales_comerciales", "mix_pct")
