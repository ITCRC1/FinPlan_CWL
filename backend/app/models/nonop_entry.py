import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class NonOpEntry(Base):
    """
    One detail line of a BELOW-GOP (non-operating, owner) account (8xxx) per
    (account_code, detail_code) × scenario. Monthly amounts in USD.

    These are the "mini checkbooks" of the owner / below-GOP section: a P&L line
    like Properties Insurance is broken into a few named detail lines (Total
    Risk, Umbrella, Civil Liability, Others…) that sum to the line total.

    The P&L line is driven by `report_line_code`, NOT by account_code: several
    report lines share one GL account (Capital Reserve + Large Capex → 8020;
    Depreciation + Asset Loss → 8040), so the account→line mapping cannot tell
    them apart. The budget engine seeds these report lines directly from this
    table. account_code is kept for reference/export only. Below-GOP is
    property-level, so there is no dept_code.

    Management fees (revenue × %) and income tax (EBT × %) are NOT stored here —
    they are computed drivers, not entered detail.
    """
    __tablename__ = "nonop_entries"
    __table_args__ = (
        UniqueConstraint(
            "scenario_id", "report_line_code", "detail_code",
            name="uq_nonop_entry",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    report_line_code: Mapped[str] = mapped_column(String(40), index=True)  # 'PROPERTY_INSURANCE'
    account_code: Mapped[str] = mapped_column(String(10), default="")       # '8015' (reference)
    account_name: Mapped[str] = mapped_column(String(120), default="")
    detail_code: Mapped[str] = mapped_column(String(10), default="")
    detail_desc: Mapped[str] = mapped_column(String(200), default="")  # 'Seguro Umbrella'

    # Monthly amounts (USD)
    jan: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    feb: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    mar: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    apr: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    may: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    jun: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    jul: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    aug: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    sep: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    oct: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    nov: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    dec: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))

    def get_month(self, month: int) -> Decimal:
        return getattr(self, _MONTH_ATTRS[month - 1])

    def set_month(self, month: int, value: Decimal) -> None:
        setattr(self, _MONTH_ATTRS[month - 1], value)

    def __repr__(self) -> str:
        return f"<NonOpEntry {self.report_line_code}/{self.detail_code}>"


_MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec"]
