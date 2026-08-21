import uuid
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Numeric, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

# Supported revenue line references for REVENUE_LINE driver
REVENUE_LINES = (
    "ROOMS", "FOOD", "BEVERAGE", "ACTIVITIES", "TRANSPORT",
    "INNOCEANA", "RETAIL", "SPA", "SUSTAINABILITY",
)

# Supported driver types
# FTE: monto por persona × la gente del mes. Para costos que se mueven con el
# headcount y no con el ingreso — la cafetería es el caso claro.
DRIVER_TYPES = ("REVENUE_LINE", "OCC_ROOMS", "GUESTS", "AVAIL_ROOMS", "KILOS",
                "FTE", "MANUAL")


class CostEntry(Base):
    """
    One cost line per account (5xxx) × dept × scenario.
    Monthly amounts are stored in jan..dec (USD).
    DRIVER lines are recalculated by recalculate_scenario(); MANUAL are preserved.
    """
    __tablename__ = "cost_entries"
    __table_args__ = (
        UniqueConstraint(
            "scenario_id", "dept_code", "account_code",
            name="uq_cost_entry",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    dept_code: Mapped[str] = mapped_column(String(10), index=True)
    account_code: Mapped[str] = mapped_column(String(10))   # '5101', '5150', etc.
    account_name: Mapped[str] = mapped_column(String(120), default="")

    # Calculation mode
    calc_mode: Mapped[str] = mapped_column(String(10), default="MANUAL")   # 'MANUAL'|'DRIVER'
    driver_type: Mapped[str] = mapped_column(String(20), default="")       # '' when MANUAL
    driver_pct_or_rate: Mapped[Decimal] = mapped_column(Numeric(10, 6), default=Decimal("0"))
    revenue_line_ref: Mapped[str] = mapped_column(String(20), default="")  # 'FOOD', 'ROOMS', etc.

    # Monthly amounts USD
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

    # Monthly driver rate/% (DRIVER mode). NULL = use driver_pct_or_rate (base).
    # Lets a cost vary by month (e.g. seasonal F&B cost %).
    rate_jan: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    rate_feb: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    rate_mar: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    rate_apr: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    rate_may: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    rate_jun: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    rate_jul: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    rate_aug: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    rate_sep: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    rate_oct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    rate_nov: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)
    rate_dec: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)

    # ── Moneda de la línea (mig 077) ──────────────────────────────────────────
    # 'USD' → los meses de arriba son el dato y no se convierten.
    # 'CRC' → el dato MAESTRO son los colones de abajo, y jan..dec se DERIVAN con
    #         el TC de cada mes. Todo lo que lee el checkbook sigue viendo dólares.
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    crc_jan: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc_feb: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc_mar: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc_apr: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc_may: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc_jun: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc_jul: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc_aug: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc_sep: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc_oct: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc_nov: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc_dec: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))

    @property
    def en_colones(self) -> bool:
        return (self.currency or "USD").upper() == "CRC"

    def get_crc(self, month: int) -> Decimal:
        return getattr(self, "crc_" + _MONTH_ATTRS[month - 1]) or Decimal("0")

    def set_crc(self, month: int, value: Decimal) -> None:
        setattr(self, "crc_" + _MONTH_ATTRS[month - 1], value)

    def derivar_usd(self, month: int, tc: Decimal) -> Decimal:
        """Dólares del mes a partir de los colones y el TC DE ESE MES.

        Una línea en dólares se devuelve tal cual: convertirla sería inventar un
        efecto cambiario que no existe.
        """
        if not self.en_colones:
            return self.get_month(month) or Decimal("0")
        if not tc or tc <= 0:
            return Decimal("0")
        return (self.get_crc(month) / tc).quantize(Decimal("0.0001"))

    def get_month(self, month: int) -> Decimal:
        """Return amount for month 1–12."""
        return getattr(self, _MONTH_ATTRS[month - 1])

    def set_month(self, month: int, value: Decimal) -> None:
        setattr(self, _MONTH_ATTRS[month - 1], value)

    def get_rate(self, month: int) -> Decimal:
        """Rate for month 1–12: the monthly rate if set, else the base rate."""
        r = getattr(self, _RATE_ATTRS[month - 1])
        return r if r is not None else self.driver_pct_or_rate

    def __repr__(self) -> str:
        return f"<CostEntry {self.dept_code}/{self.account_code}>"


_MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec"]
_RATE_ATTRS = [f"rate_{m}" for m in _MONTH_ATTRS]
