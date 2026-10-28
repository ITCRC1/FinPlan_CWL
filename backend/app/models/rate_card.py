from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class RateCard(Base):
    """Rack rate and net rate per room type per month for a scenario."""
    __tablename__ = "rate_cards"
    __table_args__ = (
        UniqueConstraint("scenario_id", "room_type_id", "month", name="uq_rate_card"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    hotel_id: Mapped[str] = mapped_column(String(10), nullable=False)
    room_type_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("room_type_configs.id"), nullable=False
    )
    month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    rack_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    net_rate: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    pax_per_room: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, default=Decimal("1.8000")
    )
    #: La neta la puso una persona: NO se recalcula como `rack x net factor`.
    #:
    #: Owner, 2026-10-27: las villas se venden a **$1,700 netos** — no hay rack
    #: del que derivarlos, y cargar 1,700 como rack le aplicaba el 20.30% del
    #: mes y presupuestaba $1,354.90. El numero se ve plausible; la plata no
    #: esta (mig 159).
    #:
    #: Lo respetan las tres rutas que resincronizan la neta: el guardado de
    #: Rack Rates, el Mixer de canales y el resync del «Push to the checkbook».
    #: Si se agrega una cuarta, tiene que preguntar por esta bandera.
    net_rate_manual: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
