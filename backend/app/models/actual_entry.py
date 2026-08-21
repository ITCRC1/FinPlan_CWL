import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class ActualEntry(Base):
    """
    Real recorded amounts for an ACTUAL scenario — one row per
    (account_code × dept_code), 12 monthly USD columns. Totals only, no detail.

    Actuals do NOT use the budget checkbooks (revenue/payroll/cost/opex). The P&L
    engine reads ActualEntry directly when scenario.type == 'ACTUAL'.
    """
    __tablename__ = "actual_entries"
    __table_args__ = (
        # `outlet` entra en la llave. El GL de A&B trae la MISMA cuenta cuatro
        # veces, una por outlet (`4110 Food1 Outlet 1`, `4110 Food Outlet 2`…).
        # Sin el outlet acá, esas cuatro filas colisionan en una sola llave y el
        # escritor —que ASIGNA el mes, no lo acumula— deja viva solo la última:
        # la plata de los otros tres outlets desaparecería sin error.
        #
        # Hoy no pasa porque los Outlets 2-4 vienen en cero y el importador salta
        # las filas vacías. Esto es la previsión para el día que se llenen.
        UniqueConstraint(
            "scenario_id", "dept_code", "account_code", "outlet",
            name="uq_actual_entry",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True, default="")
    dept_code: Mapped[str] = mapped_column(String(10), index=True, default="")
    account_code: Mapped[str] = mapped_column(String(10))   # '4000', '6020', '8040', ...
    account_name: Mapped[str] = mapped_column(String(120), default="")
    # Punto de venta dentro del departamento, tal como lo rotula el GL
    # ('Outlet 1'…'Outlet 4'). Vacío = el departamento no se abre por outlet, que
    # es el caso de TODO menos A&B. No lo lee ningún reporte todavía: se guarda
    # para que el día que la contabilidad llene los outlets el dato entre con su
    # dimensión, sin re-importar y sin perder el arranque del histórico.
    outlet: Mapped[str] = mapped_column(String(40), default="", server_default="")

    jan: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    feb: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    mar: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    apr: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    may: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    jun: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    jul: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    aug: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    sep: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    oct: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    nov: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))
    dec: Mapped[Decimal] = mapped_column(Numeric(16, 4), default=Decimal("0"))

    _MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
                    "jul", "aug", "sep", "oct", "nov", "dec"]

    #: La fila del Excel del que vino, para devolver la plantilla EN EL ORDEN
    #: EN QUE SE SUBIO (owner, 2026-08-14). `None` = no vino de un archivo, o es
    #: anterior a la migracion 111: ahi la exportacion cae al orden por grupo del
    #: P&L, que es el de siempre.
    orden_archivo: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def get_month(self, month: int) -> Decimal:
        return getattr(self, self._MONTH_ATTRS[month - 1])

    def set_month(self, month: int, value: Decimal) -> None:
        setattr(self, self._MONTH_ATTRS[month - 1], value)

    def __repr__(self) -> str:
        return f"<ActualEntry {self.dept_code}/{self.account_code}>"
