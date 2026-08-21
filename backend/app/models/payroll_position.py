import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, Numeric, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

_FTE_ATTRS = [
    "fte_jan", "fte_feb", "fte_mar", "fte_apr", "fte_may", "fte_jun",
    "fte_jul", "fte_aug", "fte_sep", "fte_oct", "fte_nov", "fte_dec",
]


class PayrollPosition(Base):
    """
    Posición de planilla presupuestada por escenario.

    SW_mes = salary_amount × FTE_mes / TC_mes   (cuando salary_currency == 'CRC')
    SW_mes = salary_amount × FTE_mes             (cuando salary_currency == 'USD')
    Si FTE = 0.00 → SW = 0 → sin costo ese mes (posición planificada pero no ocupada).
    """
    __tablename__ = "payroll_positions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)

    # Identification
    dept_code: Mapped[str] = mapped_column(String(10), index=True)    # '0150'
    dept_name: Mapped[str] = mapped_column(String(100), default="")   # 'TOUR ACTIVITIES'
    position_code: Mapped[str] = mapped_column(String(10), default="") # '604'
    position_name: Mapped[str] = mapped_column(String(200))           # 'CAPITAN DE BARCO'
    employee_name: Mapped[str] = mapped_column(String(200), default="VACANTE")
    employee_type: Mapped[str] = mapped_column(String(20), default="1-Permanente")
    class_code: Mapped[str] = mapped_column(String(10), default="013")    # 013=Line, 012=Supervisor
    category_code: Mapped[str] = mapped_column(String(10), default="015") # 015=Local Perm, 010=Expat

    # Salary (full-time monthly)
    salary_amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    salary_currency: Mapped[str] = mapped_column(String(3), default="CRC")  # 'CRC' | 'USD'

    # FTE per month 0.00–1.00. October defaults to 0 for CWL 2026 but is not locked.
    fte_jan: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_feb: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_mar: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_apr: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_may: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_jun: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_jul: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_aug: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_sep: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_oct: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.0"))
    fte_nov: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_dec: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))

    # Marca de cambio: el recálculo compara contra scenarios.last_recalc_at
    # para avisar que el P&L quedó atrás. Sin esto no había CONTRA QUÉ
    # comparar y el usuario editaba sin saber que el reporte no lo reflejaba.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    def __repr__(self) -> str:
        return f"<PayrollPosition {self.dept_code}/{self.position_code} {self.position_name[:30]}>"


def get_fte(position: PayrollPosition, month: int) -> Decimal:
    """Return FTE for month 1-12."""
    return getattr(position, _FTE_ATTRS[month - 1])
