import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

# Métricas del mix por país (igual que channel mix). Cada una su propio mix %.
COUNTRY_METRICS = ["rooms", "pax"]


class CountryMixEntry(Base):
    """Mix por país / mercado de origen por mes (de PMS).

    Una fila por (scenario, month, country, metric). A diferencia del Channel
    Mix, la lista de países es DINÁMICA (la define el usuario al cargar).
    `value` = conteo (room nights o pax) de ese país en el mes; el mix % se
    calcula = value / total del período (dentro de la misma métrica).
    """
    __tablename__ = "country_mix_entries"
    __table_args__ = (
        UniqueConstraint("scenario_id", "month", "country", "metric",
                         name="uq_country_scenario_month_country_metric"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    month: Mapped[int] = mapped_column(Integer)          # 1..12
    country: Mapped[str] = mapped_column(String(60))     # nombre de país/mercado (libre)
    metric: Mapped[str] = mapped_column(String(10), default="rooms")  # 'rooms' | 'pax'
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    #: De dónde vino este mes: `'xml'` (importador de Opera) o `'manual'`
    #: (plantilla corregida o grilla en pantalla).
    #:
    #: ⚠️ Existe para poder avisar antes de pisar. La regla del owner es «el
    #: XML se sube UNA vez para el mes, y después se baja y se edita»: un
    #: segundo paso del importador sobre un mes ya corregido borraría la
    #: corrección, y sin esta columna lo haría en silencio.
    origen: Mapped[str] = mapped_column(String(10), default="xml")
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
