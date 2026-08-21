import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class SpaBudget(Base):
    """Spa revenue driver per scenario per month (capture-rate model).

    El presupuesto de Spa se arma: Total Pax del mes × capture rate (% de pax
    que toma un tratamiento) = # de tratamientos; × precio promedio del
    tratamiento = ingreso de Spa. El pax sale de los drivers (noches ocupadas ×
    pax_per_night). Esta tabla guarda el capture rate por mes y el precio
    promedio; el ingreso calculado se persiste en la línea SPA del checkbook.
    """
    __tablename__ = "spa_budgets"
    __table_args__ = (
        UniqueConstraint("scenario_id", "month", name="uq_spa_budget"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    capture_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))  # fracción 0..1
    avg_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))   # USD/tratamiento

    def __repr__(self) -> str:
        return f"<SpaBudget m{self.month} cap={self.capture_pct} price={self.avg_price}>"
