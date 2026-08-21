import json
import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

# Defaults = valores históricos hardcodeados en el motor (Costa Rica).
DEFAULT_CCSS_RATE = Decimal("0.26830")       # cargas sociales patronales sobre BASE
DEFAULT_AGUINALDO_DIVISOR = Decimal("12")    # aguinaldo = BASE / 12

ZERO = Decimal("0")
CEROS_12 = "[0,0,0,0,0,0,0,0,0,0,0,0]"
CALENDARIO_2027 = "[31,28,31,30,31,30,31,31,30,31,30,31]"


class PayrollParams(Base):
    """Parámetros de planilla **por escenario** (cambian por año en CR).

    Antes estaban hardcodeados en `payroll_calculator` (CCSS 26.83%, aguinaldo /12).
    Ahora cada escenario guarda los suyos; si no hay fila, el motor usa los defaults
    (= comportamiento anterior, sin regresión).
    """
    __tablename__ = "payroll_params"
    __table_args__ = (
        UniqueConstraint("scenario_id", name="uq_payroll_params"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    ccss_rate: Mapped[Decimal] = mapped_column(Numeric(7, 5), default=DEFAULT_CCSS_RATE)
    aguinaldo_divisor: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=DEFAULT_AGUINALDO_DIVISOR)

    # ── Drivers de los conceptos que en CR son regla, no digitación (mig 073) ──
    # Todos nacen en CERO: mientras no se llenen, el número no cambia.
    overtime_pct: Mapped[Decimal] = mapped_column(Numeric(7, 5), default=ZERO)          # 6001
    bonus_pct: Mapped[Decimal] = mapped_column(Numeric(7, 5), default=ZERO)             # 6027
    vacaciones_rate: Mapped[Decimal] = mapped_column(Numeric(7, 5), default=ZERO)       # 6023
    severance_annual_rate: Mapped[Decimal] = mapped_column(Numeric(7, 5), default=ZERO)  # 6026
    cafeteria_daily_crc: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=ZERO)   # 6025
    transport_monthly_crc: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=ZERO)  # 6029
    housing_monthly_crc: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=ZERO)   # 6028
    other_monthly_crc: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=ZERO)     # 6030
    # 6022 INS riesgos del trabajo: NO es parte del 26.83% de la CCSS, es una póliza
    # aparte. Se carga el monto del año y se reparte por FTE (mig 074).
    ins_annual_crc: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=ZERO)       # 6022
    # Calendarios por mes, guardados como lista JSON de 12 enteros.
    working_days: Mapped[str] = mapped_column(String(120), default=CEROS_12)
    holidays: Mapped[str] = mapped_column(String(120), default=CEROS_12)
    days_off: Mapped[str] = mapped_column(String(120), default=CEROS_12)   # 6002
    calendar_days: Mapped[str] = mapped_column(String(120), default=CALENDARIO_2027)

    # Marca de cambio: el recálculo compara contra scenarios.last_recalc_at
    # para avisar que el P&L quedó atrás. Sin esto no había CONTRA QUÉ
    # comparar y el usuario editaba sin saber que el reporte no lo reflejaba.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    def mes(self, campo: str, month: int) -> int:
        """Valor del calendario `campo` para el mes 1..12 (0 si está mal formado)."""
        try:
            v = json.loads(getattr(self, campo) or "[]")
            return int(v[month - 1]) if 1 <= month <= len(v) else 0
        except (ValueError, TypeError, IndexError):
            return 0

    def __repr__(self) -> str:
        return f"<PayrollParams ccss={self.ccss_rate} agu/{self.aguinaldo_divisor}>"
