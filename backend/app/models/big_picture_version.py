import uuid
from datetime import datetime
from sqlalchemy import String, Integer, JSON, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.hotel_actual import HOTEL_ID


class BigPictureVersion(Base):
    """
    Una versión guardada del presupuesto 'Big Picture' (P&L top-down rápido):
    los % de crecimiento por línea/depto sobre una base (Forecast), para un año
    objetivo. NO construye el detalle — solo persiste los targets macro para
    poder retomar el ejercicio y compartirlo con el equipo.
    """
    __tablename__ = "big_picture_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True, default=HOTEL_ID)
    name: Mapped[str] = mapped_column(String(120))
    base_scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True
    )
    target_year: Mapped[int] = mapped_column(Integer, default=2027)
    growth: Mapped[dict | None] = mapped_column(JSON, nullable=True)   # {row_key: pct}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<BigPictureVersion {self.name} y{self.target_year}>"
