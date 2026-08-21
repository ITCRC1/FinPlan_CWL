import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, JSON, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class LaundryParams(Base):
    """
    Scenario-level parameters for the 3-way laundry (0161) allocation.

    The total cost of dept 0161 (OPEX + payroll + CoS) is split by KILOS into:
      - Linen   (Σ kilos por área / total)   → account 7310, distributed by KILOS
      - Uniform (kilos_uniformes / total)     → account 7685, distributed by FTE
      - Guests  (kilos_huespedes / total)     → account 5301 (Cost of Sales),
                NOT spread by kilos — charged to 0162 as the COGS of the laundry
                service sold to guests.

    kilos_uniformes / kilos_huespedes are scenario-level monthly averages
    (applied to all 12 months), mirroring kilos_historicos per dept (linen).
    """
    __tablename__ = "laundry_params"
    __table_args__ = (
        UniqueConstraint("scenario_id", name="uq_laundry_params"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    # Promedio mensual (legacy / fallback). El reparto usa los *_monthly por mes.
    kilos_uniformes: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    kilos_huespedes: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    # 12 valores (Ene..Dic). Si es None, se usa el escalar para todos los meses.
    uniformes_monthly: Mapped[list | None] = mapped_column(JSON, nullable=True)
    huespedes_monthly: Mapped[list | None] = mapped_column(JSON, nullable=True)
    account_linen: Mapped[str] = mapped_column(String(10), default="7310")
    account_uniform: Mapped[str] = mapped_column(String(10), default="7685")
    account_servicios: Mapped[str] = mapped_column(String(10), default="5301")

    def uniformes_for(self, month: int) -> Decimal:
        m = self.uniformes_monthly
        if m and len(m) >= month and m[month - 1] is not None:
            return Decimal(str(m[month - 1]))
        return self.kilos_uniformes or Decimal("0")

    def huespedes_for(self, month: int) -> Decimal:
        m = self.huespedes_monthly
        if m and len(m) >= month and m[month - 1] is not None:
            return Decimal(str(m[month - 1]))
        return self.kilos_huespedes or Decimal("0")

    def __repr__(self) -> str:
        return (
            f"<LaundryParams uni={self.kilos_uniformes}kg "
            f"guest={self.kilos_huespedes}kg>"
        )
