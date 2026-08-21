from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models.revenue_entry import REVENUE_LINES

# Las líneas que el motor DERIVA: salen de tarifas × ocupación y de la
# configuración del paquete. No se digitan y no viven acá.
DERIVED_REVENUE_LINES = (
    "ROOMS", "FOOD", "BEVERAGE", "ACTIVITIES", "TRANSPORT", "SUSTAINABILITY",
)

# Todo lo demás es un **monto mensual**: o lo digita el usuario (Retail,
# Innoceana, Lavandería) o lo calcula un driver y lo deposita acá (el Spa con su
# capture rate, el Club con su cuota). Se deriva de las líneas canónicas a
# propósito: un departamento nuevo entra al modo `drivers` con solo aparecer en
# `REVENUE_LINES`, sin tocar el motor ni esta lista. Cuando era una lista escrita
# a mano, el Club quedó afuera y su ingreso se perdía en silencio.
OTHER_REVENUE_LINES = tuple(
    ln for ln in REVENUE_LINES if ln not in DERIVED_REVENUE_LINES
)


class RevenueOther(Base):
    """Monto mensual de una línea de ingreso que el motor no deriva.

    **Es la fuente de estas líneas en modo `drivers`.** El equivalente en modo
    `checkbook` es `RevenueEntry`. Son dos tablas distintas porque son dos
    caminos distintos: acá el ingreso derivado se calcula y solo los montos
    planos se guardan; allá se guarda todo, línea por línea.

    Un driver de ingreso (Spa, Club) escribe en **las dos**, vía
    `app/api/_ingreso_de_driver.py`, para que su resultado llegue al P&L sin
    depender del modo en que esté el escenario.
    """
    __tablename__ = "revenue_other"
    __table_args__ = (
        UniqueConstraint("scenario_id", "line", "month", name="uq_revenue_other"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    hotel_id: Mapped[str] = mapped_column(String(10), nullable=False)
    line: Mapped[str] = mapped_column(String(20), nullable=False)   # 'SPA'|'CLUB'|...
    month: Mapped[int] = mapped_column(Integer, nullable=False)      # 1-12
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
