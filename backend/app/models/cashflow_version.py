import uuid
from datetime import datetime
from sqlalchemy import String, Integer, JSON, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.hotel_actual import HOTEL_ID


class CashFlowVersion(Base):
    """Versión CONGELADA de un Cash Flow presentada a los dueños.

    Plana y sin conexión con el motor: se sube un Excel (formato del Cash Flow
    Budget: Section · Description · Ene..Dic · Full Year) y se guarda tal cual en
    `rows` (JSON). No se recalcula nunca. Sirve de archivo histórico de lo
    presentado (V1 Budget, V2 Forecast, …) para comparar contra el Current vivo.
    """
    __tablename__ = "cashflow_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(8), index=True, default=HOTEL_ID)
    name: Mapped[str] = mapped_column(String(160), default="")
    # 'frozen' = subida congelada (presentada); 'working' = copia editable del
    # Forecast que el usuario ajusta mes a mes (independiente del motor).
    kind: Mapped[str] = mapped_column(String(12), default="frozen")
    order_idx: Mapped[int] = mapped_column(Integer, default=0)
    # rows = [{"section": str, "label": str, "values": [12 floats], "full_year": float, "is_total": bool}]
    rows: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
