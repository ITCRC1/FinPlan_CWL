import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

# Canonical revenue lines (match RevenueResult fields / revenue_line_dict keys).
# Order here is the display order in the checkbook screen.
REVENUE_LINES = (
    "ROOMS", "FOOD", "BEVERAGE", "FNB_MISC", "SPA", "ACTIVITIES",
    "TRANSPORT", "RETAIL", "INNOCEANA", "LAUNDRY", "SUSTAINABILITY",
    "CLUB", "CLUB_ACTIVIDAD", "CLUB_VISITANTES",
)

# line code -> human label shown in the UI
REVENUE_LINE_LABELS = {
    "ROOMS": "Room Revenue",
    "FOOD": "Food",
    "BEVERAGE": "Beverage",
    "FNB_MISC": "F&B Misceláneo",
    "SPA": "Spa",
    "ACTIVITIES": "Tours",
    "TRANSPORT": "Transportation",
    "RETAIL": "Retail",
    "INNOCEANA": "Innoceana",
    "LAUNDRY": "Laundry",
    "SUSTAINABILITY": "Sustainability Fee & Misc. Revenue",
    # Las tres fuentes de ingreso del Club Madresal. Los nombres NO son
    # invención: son los de `account_mapping` (depto 260) y hay una prueba que
    # falla si se separan del catálogo.
    "CLUB": "Ingreso Madresal Club",
    "CLUB_ACTIVIDAD": "Actividad fin de año",
    "CLUB_VISITANTES": "Visitantes",
}

# Línea del checkbook → cuenta contable con la que va amarrada.
#
# Solo se declara donde la línea ES una cuenta. `ROOMS` o `FOOD` agregan varias,
# así que no llevan código: poner uno sería mentir.
#
# **Ojo con leer el código solo:** 4500/4501/4502 los comparten Club Madresal,
# INNOCEANA y Claro Huerta, cada uno con su nombre y su destino en el P&L. Lo
# que identifica la línea es el par (departamento, cuenta) — por eso acá va el
# departamento también, y por eso una hoja que solo mire el número termina
# mostrando «Ingreso Innoceana #3» donde va «Visitantes».
REVENUE_LINE_ACCOUNT: dict[str, tuple[str, str]] = {   # línea → (depto, cuenta)
    "CLUB": ("260", "4500"),
    "CLUB_ACTIVIDAD": ("260", "4501"),
    "CLUB_VISITANTES": ("260", "4502"),
}


class RevenueEntry(Base):
    """
    Direct revenue amount per line × scenario, 12 USD columns.

    This is the "checkbook" source for revenue: instead of deriving revenue from
    rate cards × occupancy × packages (the driver engine), the user types the USD
    amount per P&L revenue line per month. When scenario.revenue_source ==
    'checkbook', these amounts feed the P&L directly (KPIs come from ScenarioStat).
    """
    __tablename__ = "revenue_entries"
    __table_args__ = (
        UniqueConstraint("scenario_id", "line", name="uq_revenue_entry"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    line: Mapped[str] = mapped_column(String(20))   # one of REVENUE_LINES

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
        return getattr(self, _MONTH_ATTRS[month - 1])

    def set_month(self, month: int, value: Decimal) -> None:
        setattr(self, _MONTH_ATTRS[month - 1], value)

    def __repr__(self) -> str:
        return f"<RevenueEntry {self.line}>"


_MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
                "jul", "aug", "sep", "oct", "nov", "dec"]
