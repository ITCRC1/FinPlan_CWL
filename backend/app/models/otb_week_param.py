import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class OtbWeekParam(Base):
    """Parámetros del On The Books por (hotel, corte) — parte del historial de
    cortes. Hoy guarda `on_prop_pct` = % del Rooms Revenue que se estima vender
    EN la propiedad (walk-in), ajuste positivo sobre el OTB de ese corte.

    ⚠️ La llave es el HOTEL, no el escenario — igual que `OnTheBooksEntry`.
    Ver la migración 126.
    """
    __tablename__ = "otb_week_params"
    __table_args__ = (
        UniqueConstraint("hotel_id", "week", name="uq_otbparam_hotel_week"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    #: Desde qué escenario se guardó. Rastro, no dueño.
    scenario_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="SET NULL"), index=True, nullable=True)
    week: Mapped[int] = mapped_column(Integer, index=True)  # 1..53
    on_prop_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.126"))
