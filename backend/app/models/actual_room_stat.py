import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class ActualRoomStat(Base):
    """Estadística REAL de habitaciones por tipo × mes (de Opera/PMS).

    Una fila por (scenario, room_type_name, month). Alimenta el reporte
    Room Stats con los ACTUALES (los budgets/forecasts salen de drivers).
    Se acumula mes a mes: cada mes se sube/upserta el mes cerrado.
    'Other Rooms Revenue' se guarda como un tipo más (solo revenue).
    """
    __tablename__ = "actual_room_stats"
    __table_args__ = (
        UniqueConstraint("scenario_id", "room_type_name", "month",
                         name="uq_roomstat_scenario_room_month"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    room_type_name: Mapped[str] = mapped_column(String(120))
    month: Mapped[int] = mapped_column(Integer)          # 1..12
    units: Mapped[int] = mapped_column(Integer, default=0)
    nights_available: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    nights_occupied: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    pax: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
