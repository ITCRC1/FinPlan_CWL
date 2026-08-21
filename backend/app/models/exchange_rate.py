import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class ExchangeRate(Base):
    """
    Tipo de cambio CRC/USD por escenario × mes.

    Cada escenario tiene exactamente 12 filas (una por mes).
    El TC se aplica: amount_usd = amount_crc / tc_crc_usd
    530.00 significa 1 USD = ₡530

    Fallback: si no hay TC para un mes, usa el más reciente definido.
    Los Actuals NO usan esta tabla — sus valores ya vienen en USD.
    """
    __tablename__ = "exchange_rates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(String(36), ForeignKey("scenarios.id"), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    month: Mapped[int] = mapped_column(Integer)   # 1-12
    year: Mapped[int] = mapped_column(Integer)
    tc_crc_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    notes: Mapped[str] = mapped_column(String(200), default="")

    # Marca de cambio: el recálculo compara contra scenarios.last_recalc_at
    # para avisar que el P&L quedó atrás. Sin esto no había CONTRA QUÉ
    # comparar y el usuario editaba sin saber que el reporte no lo reflejaba.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    scenario: Mapped["Scenario"] = relationship("Scenario", back_populates="exchange_rates")

    def __repr__(self) -> str:
        return f"<ExchangeRate {self.year}-{self.month:02d} TC={self.tc_crc_usd}>"


def get_tc_for_month(exchange_rates: list[ExchangeRate], month: int) -> Decimal:
    """
    Retorna el TC para el mes dado.
    Fallback: si no hay TC exacto, usa el mes anterior más cercano disponible.
    Si no hay ninguno anterior, usa el primero disponible.
    """
    exact = next((r for r in exchange_rates if r.month == month), None)
    if exact:
        return exact.tc_crc_usd

    prior = sorted([r for r in exchange_rates if r.month < month], key=lambda r: r.month, reverse=True)
    if prior:
        return prior[0].tc_crc_usd

    available = sorted(exchange_rates, key=lambda r: r.month)
    if available:
        return available[0].tc_crc_usd

    raise ValueError("No hay tipos de cambio definidos para este escenario")
