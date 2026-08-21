import uuid
from sqlalchemy import String, Boolean, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CashFlowWCParams(Base):
    """Parámetros del modelo de timing de Working Capital por escenario.

    Replica el modelo del usuario (mezcla de pago del revenue + timing,
    política A/P, aguinaldo, IVA). `params` guarda el dict de parámetros
    (ver WC_MODEL_DEFAULTS); cuando enabled=True, las 6 partidas WC se
    calculan con compute_wc_model en vez de su driver individual.
    """
    __tablename__ = "cashflow_wc_params"
    __table_args__ = (UniqueConstraint("scenario_id", name="uq_cfwc_scenario"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
