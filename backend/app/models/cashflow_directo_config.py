"""Config del Cash Flow Método Directo por escenario:
- `params`: overrides de los drivers del modelo (ver DIRECT_DEFAULTS): % tarjeta,
  IVA, retenciones, 70/30, honorarios %, meses de seguro, etc.
- `manual`: entradas manuales {row_key: [12]} — secciones Capital y Financiamiento
  (préstamos/intereses) y ajustes manuales por línea.

Portado de Luz de Mono, adaptado a la clave por `scenario_id` de CWL.
"""
from sqlalchemy import String, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CashFlowDirectoConfig(Base):
    __tablename__ = "cashflow_directo_config"

    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), primary_key=True)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    manual: Mapped[dict] = mapped_column(JSON, default=dict)
