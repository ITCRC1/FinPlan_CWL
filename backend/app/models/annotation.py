import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

KINDS = ("comment", "question")


class Annotation(Base):
    """Comentario o pregunta anclado a una sección/línea de un escenario (Fase 3).

    Sirve para dos cosas:
    - **comment** → explicación de variación (se agrega en la narrativa a dueños).
    - **question** → Q&A en contexto (abierta/resuelta).

    `ref` es texto libre (ej. la línea/depto: "Tours · Abril"). `month` 0 = general/anual,
    1-12 = mes puntual.
    """
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    section: Mapped[str] = mapped_column(String(20))     # master/revenue/costs/payroll/opex/nonop
    ref: Mapped[str] = mapped_column(String(120), default="")
    month: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(12), default="comment")
    body: Mapped[str] = mapped_column(String(2000))
    author_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Annotation {self.kind} {self.section}/{self.ref}>"
