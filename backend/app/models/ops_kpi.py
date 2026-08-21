import uuid
from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class OpsKpiEntry(Base):
    """Fila de la tabla manual de Ops KPI (Operation Insight).

    Tabla libre por escenario: cada fila es un indicador operativo con su
    meta, valor actual, responsable y acción. Texto plano (no se calcula);
    el orden lo da `order_idx`. PUT reemplaza todas las filas del escenario.
    """
    __tablename__ = "ops_kpi_entries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    order_idx: Mapped[int] = mapped_column(Integer, default=0)
    kpi: Mapped[str] = mapped_column(String(200), default="")
    target: Mapped[str] = mapped_column(String(120), default="")
    actual: Mapped[str] = mapped_column(String(120), default="")
    owner: Mapped[str] = mapped_column(String(120), default="")
    action: Mapped[str] = mapped_column(String(400), default="")
