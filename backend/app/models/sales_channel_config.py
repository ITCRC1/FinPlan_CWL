from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

CHANNELS = ("TA", "OTA", "DIRECT")


class SalesChannelConfig(Base):
    """Channel mix and commission rates for a scenario, per month (1-12).

    Mix/commission can vary by month, so the net factor is month-specific.
    """
    __tablename__ = "sales_channel_configs"
    __table_args__ = (
        UniqueConstraint("scenario_id", "channel", "month", name="uq_channel_month"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    hotel_id: Mapped[str] = mapped_column(String(10), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)   # nombre/código del canal
    month: Mapped[int] = mapped_column(Integer, default=1)             # 1-12
    mix_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    commission_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)


# Default channel config from Budget2026_Revenue_CORCO.xlsx Key Indicators
CWL_DEFAULT_CHANNELS = [
    {"channel": "TA",     "mix_pct": Decimal("0.600000"), "commission_pct": Decimal("0.280000")},
    {"channel": "OTA",    "mix_pct": Decimal("0.050000"), "commission_pct": Decimal("0.200000")},
    {"channel": "DIRECT", "mix_pct": Decimal("0.350000"), "commission_pct": Decimal("0.000000")},
]


def compute_net_factor(channels: list[SalesChannelConfig],
                       month: int | None = None) -> Decimal:
    """Lo que le queda al hotel después de la comisión del canal.

    `Σ(mezcla × (1 − comisión)) / Σ(mezcla)` — un promedio **ponderado**.

    ⚠️ **La división es el arreglo, y no es cosmética.** Antes esto sumaba sin
    dividir, y los canales se guardan POR MES (`UNIQUE (escenario, canal, mes)`):
    con las 36 filas de un escenario devolvía **9,5640**, o sea doce veces el
    0,7970 real. Un factor mayor que 1 no es un factor: multiplicaría el ingreso
    de comida, tours y traslado por nueve.

    Medido en producción (2026-08-20): **ocho escenarios** —los presupuestos
    2028 a 2035— caían en ese camino, porque tienen 36 canales y cero tarifas.
    Hoy multiplican cero porque están vacíos, pero el camino se abre en cuanto
    alguien cargue tarifas netas dejando el rack en cero: ahí
    `_effective_net_factor` devuelve `None`, la ocupación sí acumula, y el 9,56
    entra a multiplicar de verdad.

    ⚠️ **Y por eso no alcanzaba con filtrar por mes.** El Budget 2026 Final
    tiene sus tres canales SÓLO en el mes 1: filtrar a secas le habría dado
    factor 0 de febrero a diciembre, o sea ingreso de paquetes en cero. Con la
    división ponderada el resultado es correcto **se filtre o no**, que es lo
    que hace al arreglo seguro.

    `month` afina cuando la mezcla varía mes a mes; si ese mes no tiene filas,
    cae al juego completo en vez de devolver cero.
    """
    filas = channels
    if month is not None:
        del_mes = [c for c in channels if c.month == month]
        if del_mes:
            filas = del_mes

    peso = sum((c.mix_pct for c in filas), Decimal("0"))
    if not peso:
        return Decimal("0")
    neto = sum((c.mix_pct * (Decimal("1") - c.commission_pct) for c in filas),
               Decimal("0"))
    return neto / peso
