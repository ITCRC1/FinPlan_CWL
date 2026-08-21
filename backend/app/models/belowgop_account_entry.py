import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

#: Los doce meses, en orden. Es el mismo nombre y el mismo orden que usan
#: `OpexEntry` y `CostEntry`: quien recorra cualquiera de las tres tablas lo
#: hace igual.
_MESES = ("jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec")



class BelowGopAccountEntry(Base):
    """Detalle Below-GOP por cuenta × departamento × mes (Clase 8), del GL.

    Rent, Owners/Mgmt Fees, Insurance, Capital, Depreciación, Financieros, Income
    Tax. Análogo a OpexEntry/RevenueAccountEntry. Casi todo a nivel propiedad (0240).
    """
    __tablename__ = "belowgop_account_entries"
    __table_args__ = (
        UniqueConstraint("scenario_id", "dept_code", "account_code",
                         name="uq_belowgop_scenario_dept_account"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    dept_code: Mapped[str] = mapped_column(String(10), index=True)
    account_code: Mapped[str] = mapped_column(String(10))
    account_name: Mapped[str] = mapped_column(String(120), default="")
    jan: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    feb: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    mar: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    apr: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    may: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    jun: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    jul: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    aug: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    sep: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    oct: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    nov: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    dec: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))

    def get_month(self, month: int) -> Decimal:
        """El monto de ese mes (1..12).

        ⚠️ **Existe porque su ausencia rompía una descarga.** El endpoint que
        arma la plantilla de Detalle recorre las cuatro tablas del GL asumiendo
        que todas tienen `get_month` — lo tenían `OpexEntry` y `CostEntry`, y no
        estas dos. La descarga moría con `Internal Server Error` y el owner solo
        veía eso: ni qué tabla, ni qué versión.

        Un modelo que se recorre junto a otros tiene que responder igual que
        ellos, o el que los recorre necesita un caso especial por cada uno.
        """
        return getattr(self, _MESES[month - 1])

    def set_month(self, month: int, value: Decimal) -> None:
        setattr(self, _MESES[month - 1], value)
