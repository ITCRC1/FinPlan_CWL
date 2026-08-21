import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.hotel_actual import HOTEL_ID


class CapitalProject(Base):
    """
    Detalle de proyectos de capital por área, mes a mes.

    Es el "qué se compra y cuándo" detrás de la línea de inversión de capital:
    el dueño arma la lista en Excel por área (Flota Marina, Lavandería, Cocina…)
    y cada renglón dice en qué mes se ejecuta. Hasta ahora esa lista vivía fuera
    del sistema y solo entraba el total.

    NO alimenta el P&L. La inversión de capital sigue saliendo de sus líneas
    (CAPITAL_RESERVE / LARGE_CAPEX en nonop_entries): esta tabla es el detalle
    que la explica y que la junta quiere ver abierto. Si mañana se quiere que
    mande, hay que decidirlo explícitamente — que el detalle empuje el P&L sin
    avisar sería peor que tenerlos separados, porque el total cambiaría al
    editar un renglón.

    `area` es texto libre a propósito: las áreas de esta lista no son los
    departamentos USALI (Flota Marina, Paneles Solares) y forzarlas al catálogo
    obligaría a inventar códigos que no existen.
    """
    __tablename__ = "capital_projects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True, default=HOTEL_ID)
    area: Mapped[str] = mapped_column(String(120), default="")
    name: Mapped[str] = mapped_column(String(250), default="")
    notes: Mapped[str] = mapped_column(String(300), default="")
    # Orden de captura. Sin esto la lista se reordena sola en cada guardado y el
    # dueño pierde el orden en que la armó.
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

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

        Lo encontro `test_meses_se_leen_igual` el 2026-08-14, buscando el hueco
        que rompio la descarga del Detalle: esta tabla guarda los doce meses en
        columnas y era la tercera sin la interfaz comun. Todavia ningun bucle la
        recorre junto a sus hermanas — se agrega antes de que alguno lo haga,
        porque el sintoma es un 500 sin detalle.

        Usa `MONTH_ATTRS`, que ya existia en este modulo: dos listas de meses en
        el mismo archivo se desincronizan y la segunda miente en silencio.
        """
        return getattr(self, MONTH_ATTRS[month - 1])

    def set_month(self, month: int, value: Decimal) -> None:
        setattr(self, MONTH_ATTRS[month - 1], value)

    def __repr__(self) -> str:
        return f"<CapitalProject {self.area}/{self.name}>"


MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"]
