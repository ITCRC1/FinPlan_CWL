import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CashFlowBudgetDriver(Base):
    """Criterio (driver) de una partida del Cash Flow Budget por escenario.

    mode='manual'     → usa los valores manuales de CashFlowBudgetInput.
    mode='pct_sales'  → valor = pct × ventas brutas (Revenue) del mes.
    mode='days'       → días (DSO/DPO): valor = signo × Δbase × días/30
                        (A/R sobre ventas; A/P sobre costos). `pct` guarda los días.
    mode='lead_lag'   → valor = pct × ventas del mes (m − lag); lag>0 rezago,
                        lag<0 adelanto (lead). `pct` fracción, `lag` meses.
    """
    __tablename__ = "cashflow_budget_drivers"
    __table_args__ = (
        UniqueConstraint("scenario_id", "row_key", name="uq_cfd_scenario_row"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    row_key: Mapped[str] = mapped_column(String(24))
    mode: Mapped[str] = mapped_column(String(12), default="manual")   # manual|pct_sales|days|lead_lag
    pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))   # fracción o días
    lag: Mapped[int] = mapped_column(Integer, default=0)              # meses (solo lead_lag)
