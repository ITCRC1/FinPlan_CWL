# -*- coding: utf-8 -*-
"""Módulo PACING: fotos de Opera, reservas y la configuración del análisis.

Todo es de la **propiedad**, no de un escenario — igual que el On the Books
(ver `on_the_books.py`): son hechos observados en Opera. El escenario sólo entra
cuando se toma la meta desde un P&L (`/pacing/meta-from-scenario`), y ahí se
COPIA: borrar el escenario no deja al pacing sin meta.

⚠️ **Una foto = un corte.** El History & Forecast se guarda entero, un día por
llave dentro de `days` (JSON). Se guardan todas las fotos, no sólo la última:
el STLY exacto del año siguiente sale de la foto tomada hace un año, y la curva
de pacing se arma con la historia de cortes. Borrar fotos viejas es perder eso.

⚠️ **Las reservas se reemplazan por id.** Cada Reservations Entered On trae la
fila COMPLETA y actual de la reserva (estado, tarifa); la versión más reciente
manda. Una reserva que desaparece de un archivo nuevo NO se borra: el reporte
filtra por fecha de creación y un rango distinto no significa que no exista.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    String, Integer, Boolean, Numeric, DateTime, JSON, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

KINDS = ("rooms", "total")
ONSITE_MODOS = ("pct", "ratio")


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class PacingSnapshot(Base):
    """Un History & Forecast de Opera: Rooms Only o Total Revenue, a un corte."""
    __tablename__ = "pacing_snapshots"
    __table_args__ = (
        UniqueConstraint("hotel_id", "kind", "as_of", name="uq_pacing_snap_hotel_kind_asof"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    kind: Mapped[str] = mapped_column(String(10))            # rooms | total
    as_of: Mapped[str] = mapped_column(String(10), index=True)  # ISO: primer día Forecast
    date_from: Mapped[str] = mapped_column(String(10))
    date_to: Mapped[str] = mapped_column(String(10))
    has_forecast: Mapped[bool] = mapped_column(Boolean, default=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_revenue: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    #: `{fecha: [rn, rev, inv, ooo, comp, grp, arr, pax, hist]}` — el motor lo
    #: lee tal cual (`app.engine.pacing`).
    days: Mapped[dict] = mapped_column(JSON, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class PacingReservation(Base):
    """Una reserva de Reservations Entered On (sin pseudo-habitaciones PI)."""
    __tablename__ = "pacing_reservations"
    __table_args__ = (
        UniqueConstraint("hotel_id", "resv_id", name="uq_pacing_resv_hotel_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    resv_id: Mapped[str] = mapped_column(String(40))
    ins: Mapped[str] = mapped_column(String(10), index=True)   # fecha de creación
    arr: Mapped[str] = mapped_column(String(10), index=True)   # llegada
    nts: Mapped[int] = mapped_column(Integer, default=0)
    rms: Mapped[int] = mapped_column(Integer, default=1)
    amt: Mapped[float] = mapped_column(Numeric(14, 2), default=0)  # valor de la estadía
    st: Mapped[str] = mapped_column(String(2), default="A")    # A activa · X cancelada · N no show · P prospecto
    fl: Mapped[str | None] = mapped_column(String(4), nullable=True)   # COMP_HOUSE_YN
    ch: Mapped[str | None] = mapped_column(String(80), nullable=True)  # canal / agencia
    rate: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blk: Mapped[int] = mapped_column(Integer, default=0)
    room_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    guest: Mapped[str | None] = mapped_column(String(80), nullable=True)
    grupo: Mapped[str | None] = mapped_column(String(80), nullable=True)
    garantia: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pax: Mapped[int] = mapped_column(Integer, default=0)
    tarifa_noche: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    load_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class PacingResvLoad(Base):
    """Rastro de cada archivo de reservas subido."""
    __tablename__ = "pacing_resv_loads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cuenta: Mapped[int] = mapped_column(Integer, default=0)
    nuevas: Mapped[int] = mapped_column(Integer, default=0)
    actualizadas: Mapped[int] = mapped_column(Integer, default=0)
    descartadas_pi: Mapped[int] = mapped_column(Integer, default=0)
    min_ins: Mapped[str | None] = mapped_column(String(10), nullable=True)
    max_ins: Mapped[str | None] = mapped_column(String(10), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class PacingConfig(Base):
    """STLY de Revenue Management, metas por año y consumo en sitio."""
    __tablename__ = "pacing_config"

    hotel_id: Mapped[str] = mapped_column(String(10), primary_key=True)
    #: `{"years": {"2026": {"asOf", "rn":[12], "total":[12], "rooms":[12], "source"}}}`
    stly: Mapped[dict] = mapped_column(JSON, default=dict)
    #: `{"years": {"2026": {"rn":[12], "rooms":[12], "total":[12], "avail":[12], "source", "actualMonths"}}}`
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    onsite_mode: Mapped[str] = mapped_column(String(10), default="pct")
    onsite_pct: Mapped[float] = mapped_column(Numeric(6, 2), default=12)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
