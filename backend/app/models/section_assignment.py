import uuid
from typing import Optional
from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

# Secciones del presupuesto (espejan los módulos/tabs principales).
SECTIONS = ["master", "revenue", "costs", "payroll", "opex", "nonop"]
SECTION_LABELS = {
    "master": "Master data",
    "revenue": "Ingresos",
    "costs": "Costos de venta",
    "payroll": "Planilla",
    "opex": "OPEX",
    "nonop": "Gastos del propietario",
}
STATUSES = ["pending", "in_progress", "in_review", "approved"]


class SectionAssignment(Base):
    """Asignación + estado de una sección del presupuesto, por escenario (Fase 3)."""
    __tablename__ = "section_assignments"
    __table_args__ = (
        UniqueConstraint("scenario_id", "section", "ref", name="uq_section_assignment"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    section: Mapped[str] = mapped_column(String(20))
    ref: Mapped[str] = mapped_column(String(40), default="")   # depto/sub-item ("" = sección entera)
    assignee_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending")
    locked: Mapped[bool] = mapped_column(Boolean, default=False)

    def __repr__(self) -> str:
        return f"<SectionAssignment {self.section} {self.status}{' 🔒' if self.locked else ''}>"
