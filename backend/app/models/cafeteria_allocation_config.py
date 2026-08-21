import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, UniqueConstraint, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

# Depts known to be REMOTE (not on-property) at CWL — excluded from cafetería by default
REMOTE_DEPTS = {"0191", "0192", "0200"}  # Sales, remote admin, owners


class CafeteriaAllocationConfig(Base):
    """
    Which depts participate in cafetería allocation (eat on-property).
    One row per dept per scenario. participates=False means the dept's FTE
    is excluded from the cafetería distribution denominator.
    """
    __tablename__ = "cafeteria_allocation_config"
    __table_args__ = (
        UniqueConstraint("scenario_id", "dept_code", name="uq_cafeteria_config"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    dept_code: Mapped[str] = mapped_column(String(10))
    dept_name: Mapped[str] = mapped_column(String(100), default="")
    participates: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(String(200), default="")

    # Marca de cambio: el recálculo compara contra scenarios.last_recalc_at
    # para avisar que el P&L quedó atrás. Sin esto no había CONTRA QUÉ
    # comparar y el usuario editaba sin saber que el reporte no lo reflejaba.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    def __repr__(self) -> str:
        flag = "✓" if self.participates else "✗"
        return f"<CafeteriaConfig {self.dept_code} {flag}>"
