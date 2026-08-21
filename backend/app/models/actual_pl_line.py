import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class ActualPLLine(Base):
    """
    Line-level actuals for an ACTUAL scenario sourced from the macro P&L report
    (per P&L line, no account/dept detail). One row per scenario × month ×
    line_code. line_code matches app/engine/pl_engine line codes
    (REV_ROOMS, OPEXP_FB, GOP, NET_PROFIT, ...).

    This is INPUT data (source of truth for actuals), distinct from PLLine which
    is the COMPUTED P&L output for budget/forecast scenarios.
    """
    __tablename__ = "actual_pl_lines"
    __table_args__ = (
        UniqueConstraint("scenario_id", "month", "line_code", name="uq_actual_pl_line"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    month: Mapped[int] = mapped_column(Integer)
    line_code: Mapped[str] = mapped_column(String(40))
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))

    def __repr__(self) -> str:
        return f"<ActualPLLine {self.line_code} m{self.month} ${self.amount_usd}>"
