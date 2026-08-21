import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, Boolean, JSON, UniqueConstraint, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

# Suggested default kilos distribution for CWL (approximate, user should adjust)
# Rooms = largest (bed linen, towels), F&B = second (tablecloths, kitchen uniforms)
DEFAULT_KILOS: dict[str, tuple[str, Decimal, bool]] = {
    "0110": ("Rooms / Housekeeping",        Decimal("2000"), True),
    "0120": ("F&B",                         Decimal("800"),  True),
    "0130": ("Spa",                         Decimal("400"),  True),
    "0150": ("Activities",                  Decimal("100"),  True),
    "0152": ("Transport",                   Decimal("50"),   True),
    "0155": ("Innoceana",                   Decimal("50"),   True),
    "0180": ("Administration",              Decimal("0"),    False),
    "0191": ("Sales & Marketing (remoto)",  Decimal("0"),    False),
    "0200": ("Maintenance",                 Decimal("50"),   True),
    "0220": ("Cafetería",                   Decimal("100"),  True),
    "0230": ("IT / Sistemas",               Decimal("0"),    False),
}


class LaundryAllocationConfig(Base):
    """
    Historical kilo weights per dept for laundry allocation.
    One row per dept per scenario. kilos_historicos = avg monthly kilos from that dept.
    participates=False means the dept doesn't use the laundry at all.
    """
    __tablename__ = "laundry_allocation_config"
    __table_args__ = (
        UniqueConstraint("scenario_id", "dept_code", name="uq_laundry_config"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    dept_code: Mapped[str] = mapped_column(String(10))
    dept_name: Mapped[str] = mapped_column(String(100), default="")
    # Promedio mensual (legacy / fallback). El reparto usa kilos_monthly por mes.
    kilos_historicos: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    # 12 valores (Ene..Dic). Si es None, se usa kilos_historicos para todos los meses.
    kilos_monthly: Mapped[list | None] = mapped_column(JSON, nullable=True)
    participates: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(String(200), default="")

    # Marca de cambio: el recálculo compara contra scenarios.last_recalc_at
    # para avisar que el P&L quedó atrás. Sin esto no había CONTRA QUÉ
    # comparar y el usuario editaba sin saber que el reporte no lo reflejaba.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    def kilos_for(self, month: int) -> Decimal:
        """Kilos de linen del mes (1-12). Cae a kilos_historicos si no hay mensual."""
        km = self.kilos_monthly
        if km and len(km) >= month and km[month - 1] is not None:
            return Decimal(str(km[month - 1]))
        return self.kilos_historicos or Decimal("0")

    def __repr__(self) -> str:
        return f"<LaundryConfig {self.dept_code} {self.kilos_historicos}kg>"
