import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class OnTheBooksEntry(Base):
    """On The Books (reservas confirmadas a la fecha) por mes — de Opera/PMS.

    Una fila por (hotel, week, year, month). El history_forecast del owner
    trae horizonte multi-año en el MISMO archivo (forecast hasta 5 años
    adelante del corte) — por eso `year` es columna propia, no se asume el
    año del escenario. Se compara contra el Budget para ver el pace/pickup y
    el GAP (lo que falta por vender). rooms_available se deriva (units
    totales × días del mes); ADR y occupancy se calculan.

    ⚠️ **La llave es el HOTEL, no el escenario.** «El escenario es solo una
    referencia comparativa, pero no tiene nada que ver con las subidas»
    (owner, 18-ago-2026): esto son las reservas que ya existen en Opera, un
    hecho de la propiedad. Cuando la llave era el escenario el dato quedaba
    partido —los cortes de junio en el Actual 2026 y el de agosto en el
    Budget 2027— e invisible desde cualquier otro. Ver la migración 126.
    """
    __tablename__ = "on_the_books_entries"
    __table_args__ = (
        UniqueConstraint("hotel_id", "week", "year", "month", name="uq_otb_hotel_week_year_month"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    #: Desde qué escenario se subió. RASTRO, no dueño: no entra en la llave y
    #: borrar el escenario no se lleva las reservas puestas.
    scenario_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="SET NULL"), index=True, nullable=True)
    week: Mapped[int] = mapped_column(Integer, index=True)  # 1..53 (snapshot semanal)
    year: Mapped[int] = mapped_column(Integer, index=True)  # año REAL de la fecha (del XML, no del escenario)
    month: Mapped[int] = mapped_column(Integer)          # 1..12
    total_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    rooms_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    rooms_occupied: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    guests: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
