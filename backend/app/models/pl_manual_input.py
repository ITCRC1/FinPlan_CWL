import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class PLManualInput(Base):
    """
    Manual P&L inputs (CLAUDE.md §17.5) that do not come from the operating
    budget. One row per scenario × month. mgmt_fee / royalties amounts are
    NOT stored — they are computed as Total Revenue × the stored percentages.
    """
    __tablename__ = "pl_manual_inputs"
    __table_args__ = (
        UniqueConstraint("scenario_id", "month", name="uq_pl_manual_input"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    month: Mapped[int] = mapped_column(Integer)

    rent: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    mgmt_fee_pct_3: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))
    mgmt_fee_pct_5: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))
    properties_insurance: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    capital_reserve: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    capital_reserve_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))
    large_capex: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    bank_interest: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    depreciation: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    income_tax_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0.30"))

    def __repr__(self) -> str:
        return f"<PLManualInput scn={self.scenario_id} m{self.month}>"
