import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

# Los canales canónicos (Market Set / Channel Mix del PMS) NO viven acá.
#
# Eran la constante `CWL_CHANNELS` y `revenue_api` se las servía a cualquier
# propiedad: Amarena abría su Channel Mix con los cuatro canales de Corcovado.
# Ahora son la semilla `seed_data/<HOTEL_ID>/canales_mix.json`, y el endpoint le
# suma los canales que el escenario ya tenga guardados — ver
# `revenue_api._canales_del_mix`.


# Métricas del mix por canal. Cada una guarda su propio conteo → su propio mix %.
CHANNEL_METRICS = ["rooms", "pax"]


class ChannelMixEntry(Base):
    """Mix por canal de venta por mes (de PMS / Market Set).

    Una fila por (scenario, month, channel, metric). `value` = conteo del
    canal para esa métrica (room nights o pax); el mix % se calcula
    = value / total del mes/período (dentro de la misma métrica). Para el
    Budget se puede cargar el target como conteo o como % directo — ambos
    dan el mismo mix.
    """
    __tablename__ = "channel_mix_entries"
    __table_args__ = (
        UniqueConstraint("scenario_id", "month", "channel", "metric", name="uq_chmix_scenario_month_channel_metric"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    month: Mapped[int] = mapped_column(Integer)          # 1..12
    channel: Mapped[str] = mapped_column(String(40))     # canal canónico (seed_data/<HOTEL_ID>/canales_mix.json)
    metric: Mapped[str] = mapped_column(String(10), default="rooms")  # 'rooms' | 'pax'
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    #: De dónde vino: `'xml'` (importador de Opera) o `'manual'` (planificado a
    #: mano). El default es `manual` porque lo que ya existía se planificó así.
    origen: Mapped[str] = mapped_column(String(10), default="manual")
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChannelMixDetail(Base):
    """El ÁTOMO del mix por canal: noches y pax por MARKET CODE.

    Una fila por (escenario, mes, market code, métrica).

    **Por qué existe (owner, 2026-08-18).** «Me gustaría hacer varias capas: la
    general y también la detallada» · «necesito los pax y las noches por este
    detalle».

    El canal es una AGRUPACIÓN —Travel Agent son TA + TAFIT + TAGP juntos— así
    que mirando solo el canal no se ve que TAGP se caiga mientras TAFIT crece:
    el canal queda igual y el negocio cambió. Guardando el código, el canal se
    deriva con `market_codes` y el resumen **no puede discrepar del detalle**,
    porque sale de él.
    """
    __tablename__ = "channel_mix_detail"
    __table_args__ = (
        UniqueConstraint("scenario_id", "month", "market_code", "metric",
                         name="uq_chdet_scenario_month_code_metric"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    month: Mapped[int] = mapped_column(Integer)              # 1..12
    market_code: Mapped[str] = mapped_column(String(20))     # el código de Opera, crudo
    metric: Mapped[str] = mapped_column(String(10), default="rooms")
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    origen: Mapped[str] = mapped_column(String(10), default="xml")
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
