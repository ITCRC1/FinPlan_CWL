import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from sqlalchemy import String, Boolean, JSON, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.hotel_actual import HOTEL_ID

ZERO = Decimal("0")


class RoomsAllocationConfig(Base):
    """Cuánto del costo de Rooms se le mueve a cada SET, mes a mes.

    Una fila por set destino (0115 Villas, 0116 Residencias) con doce
    porcentajes. Rooms (0110) NO tiene fila: es el residuo — lo que no se
    asigna se queda ahí, y eso es «Rooms Standard». Si Rooms fuera un destino
    más habría que cuadrar que los tres sumen 100% en cada mes; siendo residuo
    no hay nada que cuadrar y no se puede perder plata por una casilla en
    blanco.

    Por MES y no un solo número al año porque la operación no es pareja: en
    temporada alta las villas se atienden distinto que en setiembre.

    El porcentaje se guarda como fracción (0.30 = 30%). La pantalla muestra
    treinta; la base guarda un tercio de uno. Mezclarlos es la forma clásica de
    repartir cien veces de más.
    """
    __tablename__ = "rooms_allocation_config"
    __table_args__ = (
        UniqueConstraint("scenario_id", "dept_code", name="uq_rooms_alloc_cfg"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True, default=HOTEL_ID)
    dept_code: Mapped[str] = mapped_column(String(10))          # '0115' | '0116'
    source_dept: Mapped[str] = mapped_column(String(10), default="0110")
    pct_monthly: Mapped[list] = mapped_column(JSON, default=list)  # 12 fracciones
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Marca de cambio: el recálculo la compara contra scenarios.last_recalc_at
    # para avisar que el P&L quedó atrás de lo que el usuario ya editó.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    def pct_for(self, month: int) -> Decimal:
        """El % del mes (1-12) como fracción. Una lista corta o vacía da 0 —
        un set sin configurar no recibe nada, que es lo mismo que hoy."""
        arr = self.pct_monthly or []
        i = month - 1
        if not self.active or not (0 <= i < len(arr)):
            return ZERO
        try:
            return Decimal(str(arr[i] or 0))
        except (TypeError, ValueError, InvalidOperation):
            # Un JSON con basura adentro no puede reventar el recálculo entero:
            # la transacción se revierte completa y el owner ve «no pasó nada».
            return ZERO

    def __repr__(self) -> str:
        return f"<RoomsAlloc {self.source_dept}→{self.dept_code}>"
