from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class HistoricalKpi(Base):
    """
    Real historical room KPIs (Actual) per hotel × year × month.

    Includes 2024 and 2025 actuals. READ-ONLY reference data once imported —
    shown side-by-side with Budget/Forecast in the Key Indicators view.

    room_type_id = 0 means hotel total (the only granularity available in the
    source workbook; per-villa historicals are not tracked).
    """
    __tablename__ = "historical_kpis"
    __table_args__ = (
        UniqueConstraint("hotel_id", "year", "month", "room_type_id", name="uq_historical_kpi"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    hotel_id: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)      # 2024, 2025
    month: Mapped[int] = mapped_column(Integer, nullable=False)     # 1-12
    room_type_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 = hotel total

    rooms_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rooms_occupied: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    guests: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    occupancy_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0"))
    adr_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    revpar_usd: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=Decimal("0"))
    revenue_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=Decimal("0"))
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTUAL_IMPORT")

    def __repr__(self) -> str:
        return f"<HistoricalKpi {self.hotel_id} {self.year}-{self.month:02d} occ={self.rooms_occupied}>"
