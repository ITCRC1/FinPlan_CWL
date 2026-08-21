import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class OtbDailyOcc(Base):
    """Ocupación DIARIA on-the-books (rooms sold por día) — de Opera (tblInputROO).

    Una fila por (hotel, week, year, month, day). `year` es el año REAL de
    la fecha (del XML) — el history_forecast del owner trae horizonte
    multi-año en el mismo archivo, así que no se puede asumir el año del
    escenario. OCC% = rooms_sold / inventario. Alimenta el heatmap diario.
    Snapshot por corte (igual que On the Books).

    ⚠️ La llave es el HOTEL, no el escenario — igual que `OnTheBooksEntry`.
    Ver la migración 126.
    """
    __tablename__ = "otb_daily_occ"
    __table_args__ = (
        UniqueConstraint("hotel_id", "week", "year", "month", "day", name="uq_dailyocc_hotel_wk_yr_mo_dy"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    #: Desde qué escenario se subió. Rastro, no dueño.
    scenario_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="SET NULL"), index=True, nullable=True)
    week: Mapped[int] = mapped_column(Integer, index=True)  # 1..53
    year: Mapped[int] = mapped_column(Integer, index=True)  # año REAL de la fecha
    month: Mapped[int] = mapped_column(Integer)             # 1..12
    day: Mapped[int] = mapped_column(Integer)               # 1..31
    rooms_sold: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=Decimal("0"))
