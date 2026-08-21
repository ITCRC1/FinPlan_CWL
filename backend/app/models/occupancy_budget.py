from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class OccupancyBudget(Base):
    """Budgeted rooms occupied per room type per month for a scenario."""
    __tablename__ = "occupancy_budgets"
    __table_args__ = (
        UniqueConstraint("scenario_id", "room_type_id", "month", name="uq_occupancy_budget"),
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
    rooms_occupied: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    # % de ocupación (fuente de entrada). rooms_occupied se deriva = pct × noches
    # disponibles (unidades × días, 0 si mes cerrado).
    occupancy_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))
    # available_rooms = room_type.units × calendar_days_in_month
