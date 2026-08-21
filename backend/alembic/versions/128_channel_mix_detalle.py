# -*- coding: utf-8 -*-
"""El Channel Mix, también al detalle: noches y pax por MARKET CODE.

**El pedido (owner, 2026-08-18).** «Me gustaría hacer varias capas: la general
y también la detallada» · «necesito los pax y las noches por este detalle».

El mix por canal ya existía (`channel_mix_entries`), pero el canal es una
AGRUPACIÓN: Travel Agent son TA + TAFIT + TAGP juntos. Mirando solo el canal no
hay forma de ver que, por ejemplo, TAGP se cayó y TAFIT creció — el canal queda
igual y el negocio cambió.

`channel_mix_detail` guarda el átomo: una fila por (escenario, mes, market code,
métrica). El canal se deriva de ahí con la tabla `market_codes`, así que el
resumen **no puede discrepar del detalle**: sale de él.

También suma `origen` y `actualizado_en` a `channel_mix_entries`, igual que en
Country Mix (mig. 127), para la misma regla del owner: el XML se sube una vez
por mes y después se corrige a mano — y una re-subida no puede pisar la
corrección en silencio.
"""
import sqlalchemy as sa
from alembic import op

revision = "128"
down_revision = "127"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "channel_mix_detail",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.Integer, nullable=False),
        sa.Column("market_code", sa.String(20), nullable=False),
        sa.Column("metric", sa.String(10), nullable=False, server_default="rooms"),
        sa.Column("value", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("origen", sa.String(10), nullable=False, server_default="xml"),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("scenario_id", "month", "market_code", "metric",
                            name="uq_chdet_scenario_month_code_metric"),
    )
    op.create_index("ix_channel_mix_detail_scenario_id", "channel_mix_detail", ["scenario_id"])

    # La misma protección que en Country Mix: saber de dónde vino cada mes.
    op.add_column("channel_mix_entries", sa.Column(
        "origen", sa.String(10), nullable=False, server_default="manual"))
    op.add_column("channel_mix_entries", sa.Column(
        "actualizado_en", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("channel_mix_entries", "actualizado_en")
    op.drop_column("channel_mix_entries", "origen")
    op.drop_index("ix_channel_mix_detail_scenario_id", "channel_mix_detail")
    op.drop_table("channel_mix_detail")
