import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CashFlowBudgetInput(Base):
    """Línea de entrada del Cash Flow Budget (CapEx / Working Capital / Other)
    por escenario × row_key × mes. Las líneas Operating Performance NO se
    guardan (se jalan del P&L); Beginning Cash sale de CashFlowParams.opening_cash.
    """
    __tablename__ = "cashflow_budget_inputs"
    __table_args__ = (
        UniqueConstraint("scenario_id", "row_key", "month", name="uq_cfb_scenario_row_month"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    row_key: Mapped[str] = mapped_column(String(24))
    month: Mapped[int] = mapped_column(Integer)          # 1..12
    value: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
