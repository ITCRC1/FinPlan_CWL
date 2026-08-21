import uuid
from decimal import Decimal
from datetime import datetime
from sqlalchemy import String, Numeric, Integer, DateTime, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class AllocationEntry(Base):
    """
    Computed allocation result per month. Regenerated each time /calculate is called.
    source_dept = dept that incurred the cost (0220 Cafetería / 0161 Lavandería).
    target_dept = dept that receives the charge.
    amount_usd  = positive value (always a cost).
    The source_dept also gets one row with amount = -sum(all target amounts) to net to zero.
    """
    __tablename__ = "allocation_entries"
    __table_args__ = (
        # incluye `account`: en el modelo 3-vías de lavandería un mismo depto
        # puede recibir DOS cargos en el mismo mes (linen 7310 + uniformes 7685).
        # incluye `basis_type`: desde que Salary Allocation es 1 regla = 1 destino,
        # un depto puede ENTREGAR y RECIBIR en el mismo mes bajo la misma cuenta
        # (0150 acredita a sus guías y recibe parte de Property Support). Sin esto
        # el cargo y el crédito chocan y revientan el recálculo entero.
        UniqueConstraint(
            "scenario_id", "allocation_type", "month", "target_dept", "account",
            "basis_type", name="uq_allocation_entry",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    allocation_type: Mapped[str] = mapped_column(String(20))   # 'CAFETERIA' | 'LAUNDRY'
    month: Mapped[int] = mapped_column(Integer)                 # 1-12
    year: Mapped[int] = mapped_column(Integer, default=2026)
    source_dept: Mapped[str] = mapped_column(String(10))        # '0220' or '0161'
    target_dept: Mapped[str] = mapped_column(String(10))        # receiving dept
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4)) # positive charge
    basis_value: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    basis_type: Mapped[str] = mapped_column(String(10))         # 'FTE' | 'KILOS' | 'CREDIT'
    account: Mapped[str] = mapped_column(String(10), default="")  # 6025 / 7310 / 7685 / 4999
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<Allocation {self.allocation_type} m{self.month} "
            f"{self.source_dept}→{self.target_dept} ${self.amount_usd}>"
        )
