import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class ScenarioStat(Base):
    """
    Room statistics (KPIs) per scenario × month, sourced from the upload Excel
    'Key Indicators' block (rows 3-8). Covers ALL scenarios — Actual, Budget and
    Forecast — so the P&L view can show Occupancy %, ADR and RevPAR uniformly.

    rooms_occupied / guests / occupancy_pct are stored as loaded. ADR is the
    Average Daily Room rate; RevPAR is derived on read as adr*occupied/available.
    """
    __tablename__ = "scenario_stats"
    __table_args__ = (
        UniqueConstraint("scenario_id", "month", name="uq_scenario_stat"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    month: Mapped[int] = mapped_column(Integer)  # 1-12
    rooms_available: Mapped[int] = mapped_column(Integer, default=0)
    rooms_occupied: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    guests: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    occupancy_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    adr: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))

    def __repr__(self) -> str:
        return f"<ScenarioStat m{self.month} occ={self.rooms_occupied} adr={self.adr}>"
