import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CashFlowParams(Base):
    """Supuestos del flujo de caja proyectado (método indirecto) por escenario.

    opening_cash: saldo de caja al 1 de enero (USD).
    dso_days: días de cobro (A/R). dpo_days: días de pago (A/P).
    distributions_annual: distribuciones a dueños en el año (USD, se reparten
    en diciembre por defecto). Todo editable; defaults razonables.

    Los campos `anchor_*` cuentan DE DÓNDE salió la caja inicial. El valor solo
    no dice nada: $702,799.20 puede ser el cierre del Forecast 2026, el del
    Budget 2027 o algo escrito a mano, y meses después nadie se acuerda. Se
    guardan también el nombre y el momento porque el escenario fuente puede
    cambiar o desaparecer, y entonces el número quedaría huérfano justo cuando
    alguien pregunte de dónde salió.
    """
    __tablename__ = "cashflow_params"
    __table_args__ = (UniqueConstraint("scenario_id", name="uq_cashflow_params_scenario"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    opening_cash: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    dso_days: Mapped[int] = mapped_column(Integer, default=10)
    dpo_days: Mapped[int] = mapped_column(Integer, default=30)
    distributions_annual: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))

    # De dónde salió opening_cash. Nulos = se escribió a mano (o viene de antes
    # de que existiera el anclaje).
    anchor_scenario_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    anchor_label: Mapped[str | None] = mapped_column(String(120), nullable=True)
    anchored_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
