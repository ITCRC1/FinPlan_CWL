import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class OpexEntry(Base):
    """
    One detail line of OPEX (Clase 7) per (dept_code, account_code, detail_code) × scenario.
    Monthly amounts in USD (imported from OPEXC_2026__*__BUDGET.xlsx or entered manually).
    """
    __tablename__ = "opex_entries"
    __table_args__ = (
        UniqueConstraint(
            "scenario_id", "dept_code", "account_code", "detail_code",
            name="uq_opex_entry",
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
    account_code: Mapped[str] = mapped_column(String(10))     # e.g. '7065'
    account_name: Mapped[str] = mapped_column(String(120), default="")
    detail_code: Mapped[str] = mapped_column(String(10), default="")   # e.g. '800'
    detail_desc: Mapped[str] = mapped_column(String(200), default="")

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
        return getattr(self, _MONTH_ATTRS[month - 1])

    def set_month(self, month: int, value: Decimal) -> None:
        setattr(self, _MONTH_ATTRS[month - 1], value)

    def __repr__(self) -> str:
        return f"<OpexEntry {self.dept_code}/{self.account_code}/{self.detail_code}>"


_MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec"]
