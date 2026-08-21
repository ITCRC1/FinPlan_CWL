import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

SCENARIO_TYPES = ("ACTUAL", "BUDGET", "FORECAST")
SCENARIO_STATUSES = ("draft", "approved", "locked")


class ScenarioLockedError(Exception):
    """Se lanza cuando se intenta modificar un escenario bloqueado."""
    pass


class Scenario(Base):
    __tablename__ = "scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), ForeignKey("hotels.id"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(10))     # 'ACTUAL' | 'BUDGET' | 'FORECAST'
    version: Mapped[str] = mapped_column(String(30))  # 'v1', 'FINAL', 'MAY_REFORECAST'
    status: Mapped[str] = mapped_column(String(10), default="draft")
    # Rolling forecast cut: months 1..actuals_through are "closed" and read from
    # the linked ACTUAL scenario (same hotel+year); months after use this
    # scenario's own checkbooks. 0 = no actuals yet (pure forecast/budget).
    actuals_through: Mapped[int] = mapped_column(Integer, default=0)
    # Forecast "Current": el forecast vivo al que apuntan los uploads del bloque
    # Forecast (sin ambigüedad cuando hay varias versiones) y que auto-avanza el cut.
    # Solo uno por (hotel, año). Snapshots mensuales / reforecasts archivados = False.
    is_current_forecast: Mapped[bool] = mapped_column(Boolean, default=False)
    # P&L source: 'imported' = read the loaded snapshot (ActualEntry / ActualPLLine);
    # 'checkbook' = roll up the in-app checkbooks (build budget/forecast from scratch,
    # so "edit checkbook → account total → P&L" takes effect).
    source_mode: Mapped[str] = mapped_column(String(12), default="imported")
    # Fuerza que el P&L de un ACTUAL importado lea el DETALLE del mayor
    # (`actual_entries`) y no el RESUMEN (`actual_pl_lines`).
    #
    # Normalmente el motor decide solo: usa el resumen salvo que el detalle dé
    # los mismos siete totales clave. Eso protege al Actual 2024, donde el
    # detalle traía $40.613 de más. Pero cuando el que está incompleto es el
    # RESUMEN —Actual 2026: depreciación 0 en el resumen y 273.139,70 en el
    # detalle, que es lo que SCP espera— el guardián descarta el número bueno
    # por no coincidir con el malo.
    #
    # Se prende a propósito, por escenario, y se puede apagar.
    usar_detalle: Mapped[bool] = mapped_column(Boolean, default=False)
    # Revenue source: 'drivers' = derive from rate cards × occupancy × packages
    # (the revenue engine); 'checkbook' = read direct USD amounts from RevenueEntry
    # (KPIs come from ScenarioStat). Default keeps existing scenarios on drivers.
    revenue_source: Mapped[str] = mapped_column(String(12), default="drivers")
    source_file: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(100), default="")

    # Cuándo corrió el último recálculo. Se compara contra el updated_at de
    # planilla / tipos de cambio / configs de reparto para avisar que el P&L
    # quedó atrás respecto de lo que el usuario ya editó.
    last_recalc_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    hotel: Mapped["Hotel"] = relationship("Hotel", back_populates="scenarios")
    exchange_rates: Mapped[list["ExchangeRate"]] = relationship(
        "ExchangeRate", back_populates="scenario", cascade="all, delete-orphan"
    )

    @property
    def is_locked(self) -> bool:
        return self.status == "locked"

    def assert_editable(self) -> None:
        """Lanza ScenarioLockedError si el escenario está bloqueado."""
        if self.is_locked:
            raise ScenarioLockedError(
                f"El escenario '{self.type} {self.version} {self.year}' está bloqueado "
                f"(status=locked). Crea una nueva versión para editar."
            )

    def __repr__(self) -> str:
        return f"<Scenario {self.type} {self.version} {self.year} [{self.status}]>"
