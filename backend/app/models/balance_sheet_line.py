import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class BalanceSheetLine(Base):
    """Línea del Balance Sheet (bloque Summary) por escenario × año × mes.

    Cargado desde el Excel de contabilidad/Integrity vía
    balance_sheet_importer. Una fila por (scenario, year, month, order_idx);
    `order_idx` conserva el orden del estado. `indent`=jerarquía, `section`=
    ASSET/LIABILITY/EQUITY, `is_total`=subtotal/total. Montos en USD y CRC.
    """
    __tablename__ = "balance_sheet_lines"
    __table_args__ = (
        UniqueConstraint("scenario_id", "year", "month", "order_idx",
                         name="uq_bs_scenario_year_month_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer)       # 1..12
    order_idx: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(String(200), default="")
    indent: Mapped[int] = mapped_column(Integer, default=0)
    section: Mapped[str] = mapped_column(String(12), default="")   # ASSET|LIABILITY|EQUITY
    is_total: Mapped[bool] = mapped_column(Boolean, default=False)
    usd: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    crc: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
