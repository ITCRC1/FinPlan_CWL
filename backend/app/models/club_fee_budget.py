import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Qué conteo de socios multiplica el precio. Por defecto los que PAGAN: los
# condicionados, por definición, todavía no pagan cuota.
BASES = ("pagando", "total", "condicionados", "acuerdo_pago")


class ClubFeeBudget(Base):
    """Driver de la cuota del Club Madresal, por escenario × mes.

    **La forma del driver es la misma del Spa**: un dato operativo que ya se
    lleva (allá el capture rate, acá el conteo de socios) × un precio que se
    presupuesta = el ingreso. Se guarda el precio y el resultado se persiste en
    la línea `CLUB` del checkbook de ingresos, que es de donde el P&L lee.

        cuota del mes = socios(base) × precio     → línea CLUB (cuenta 4500)

    **`base` dice qué socios pagan.** Por defecto `pagando`, porque los
    condicionados —por definición— todavía no pagan cuota. Es configurable y no
    una constante en el código: quién paga es una regla del negocio del Club, no
    del software, y puede cambiar sin que nadie toque esto.

    **Las otras dos fuentes no tienen driver: se digitan.** El Club no vive solo
    de la cuota, y sus otros ingresos no son un «otros» anónimo — el catálogo los
    lleva con nombre y cuenta propia:

        actividad_usd   → línea CLUB_ACTIVIDAD  (cuenta 4501, «Actividad fin de año»)
        visitantes_usd  → línea CLUB_VISITANTES (cuenta 4502, «Visitantes»)

    Las tres caen en `REV_CLUB`, igual que Food + Beverage + Misc caen en
    `REV_FB`, así que separarlas no mueve el total. Se guardan aparte para que el
    presupuesto quede en el mismo vocabulario que la contabilidad —tres cuentas,
    tres nombres— en vez de una bola que hay que desarmar a mano.
    """
    __tablename__ = "club_fee_budgets"
    __table_args__ = (
        UniqueConstraint("scenario_id", "month", name="uq_club_fee_budget"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    month: Mapped[int] = mapped_column(Integer, nullable=False)       # 1-12

    price_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    actividad_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    visitantes_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    base: Mapped[str] = mapped_column(String(20), default="pagando")

    def __repr__(self) -> str:
        return f"<ClubFeeBudget m{self.month} ${self.price_usd} base={self.base}>"
