# -*- coding: utf-8 -*-
"""Módulo DEPOSIT LEDGER: el dinero de huéspedes que el hotel tiene en custodia.

El Deposit Ledger de Opera lista, a un corte, cada reserva futura con un
depósito ya cobrado: cuánto, de quién, para cuándo llega y desde cuándo está
ahí. Es plata que todavía no es ingreso — es un pasivo hasta que el huésped se
hospeda.

Como el pacing y el On the Books, esto es de la **propiedad**, no de un
escenario: son hechos observados en Opera.

⚠️ **Acá NO se reemplaza por id, a diferencia de `PacingReservation`.**
Cada subida se guarda entera, con su propia copia de las 165 reservas. Esa es
toda la razón de ser del módulo: el owner quiere comparar una subida contra
otra y ver **cuáles salieron y cuáles entraron**. Si cada archivo pisara al
anterior no quedaría contra qué comparar — el dato de ayer es justamente el que
dice qué cambió hoy. Un ledger son ~165 filas; cincuenta cortes son 8.250. No
hay nada que ahorrar aquí.

⚠️ **El monto viene NEGATIVO y así se guarda.** En Opera el depósito es un
crédito a favor del huésped: `TOTAL_PAID_AMT = -5019.76`. La pestaña que
muestra «el reporte tal como está en el XML» tiene que enseñar ese mismo signo.
Las de análisis trabajan con el valor absoluto, y el motor es el único que da
vuelta el signo (`app/engine/deposits.py`). Normalizar al guardar sería perder
la fidelidad al archivo, que es lo que se pidió primero.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class DepositLoad(Base):
    """Un corte del Deposit Ledger: un archivo subido, con sus totales."""

    __tablename__ = "deposit_loads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    #: Fecha del corte. Sale del archivo (el `LAST_DATE` más reciente) salvo que
    #: quien sube la escriba; ver `deposit_xml.corte_de`.
    as_of: Mapped[str] = mapped_column(String(10), index=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cuenta: Mapped[int] = mapped_column(Integer, default=0)
    #: Suma de `TOTAL_PAID_AMT` tal cual viene: negativa.
    total_amt: Mapped[float] = mapped_column(Numeric(16, 2), default=0)
    min_arrival: Mapped[str | None] = mapped_column(String(10), nullable=True)
    max_arrival: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nota: Mapped[str | None] = mapped_column(String(500), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class DepositEntry(Base):
    """Una reserva con depósito, dentro de un corte.

    Los nombres de campo siguen los del XML a propósito: quien abra la pestaña
    «Ledger» al lado del reporte de Opera tiene que poder aparear columna con
    columna sin traducir nada.
    """

    __tablename__ = "deposit_entries"
    __table_args__ = (
        UniqueConstraint("load_id", "resv_name_id", name="uq_deposit_load_resv"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    load_id: Mapped[str] = mapped_column(String(36), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)

    resv_name_id: Mapped[str] = mapped_column(String(40), index=True)
    confirmation_no: Mapped[str | None] = mapped_column(String(40), nullable=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sname: Mapped[str | None] = mapped_column(String(120), nullable=True)
    room: Mapped[str | None] = mapped_column(String(20), nullable=True)
    arrival: Mapped[str | None] = mapped_column(String(10), index=True)   # ISO
    departure: Mapped[str | None] = mapped_column(String(10), nullable=True)
    #: Fecha del último movimiento del depósito. Mide hace cuánto está la plata.
    last_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    resv_status: Mapped[str | None] = mapped_column(String(10), index=True)
    guarantee_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    #: Tal cual el XML: negativo.
    total_paid_amt: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    #: Noches de la estadía, calculadas de arrival/departure al importar.
    nights: Mapped[int] = mapped_column(Integer, default=0)
