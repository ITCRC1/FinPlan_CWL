import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class TaxParams(Base):
    """Parámetros del panorama fiscal por escenario.

    wh_rate: retención sobre cobros con tarjeta (2.5% CR).
    income_tax_rate: impuesto de renta sobre EBT (30%).
    card_pct_*: % de cada línea de ingreso que se cobra con tarjeta (base de la
    retención). 'other' aplica al resto del revenue.
    """
    __tablename__ = "tax_params"
    __table_args__ = (UniqueConstraint("scenario_id", name="uq_tax_params_scenario"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    wh_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.025"))
    income_tax_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.30"))
    card_pct_rooms: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.90"))
    card_pct_fb: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.70"))
    card_pct_spa: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.80"))
    card_pct_tours: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.75"))
    # Private Bar (depto 0121): el owner confirmó que se cobra TODO con tarjeta.
    # Sin línea propia caía en 'other' al 60%, y como su venta antes se codificaba
    # en A&B —que está al 70%— el split la habría bajado sin que nada avisara.
    card_pct_private_bar: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("1.00"))
    card_pct_other: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.60"))
