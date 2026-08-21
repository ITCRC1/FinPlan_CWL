# -*- coding: utf-8 -*-
"""Registro de importaciones — la identidad del archivo (Guillermo, Fase 0).

**El hueco que cierra** (medido el 2026-08-19): FinPlan tiene **26 endpoints de
subida** y **18 parsers**, y **ninguna forma de identidad de archivo**. Ni
checksum, ni nombre guardado, ni tamaño, ni tabla que diga «esto ya se subió».

**Subir el mismo archivo dos veces no se detecta.** Y como la respuesta HTTP es
efímera, tampoco queda traza de quién subió qué ni cuándo: si mañana un total
no cuadra, no hay forma de saber qué entró.

⚠️ **Lo que ya protegía, y por qué no alcanzaba.** El anti-duplicado de hoy es
por DOMINIO, no por archivo: `UNIQUE (scenario_id, dept_code, account_code,
outlet)` en `actual_entries`, más el `merge` acotado al período. Eso evita filas
duplicadas — pero **no distingue «subí el mismo archivo otra vez» de «subí el
archivo corregido»**, que es exactamente la diferencia que importa.

⚠️ **Es puramente aditivo.** Estas dos tablas sólo REGISTRAN. Ningún import
cambia de comportamiento por existir este módulo, salvo el 409 explícito del
reimport — que se puede pasar con un flag, igual que `confirmar_diferencias`.
"""
import uuid
from datetime import datetime

from sqlalchemy import (DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Los estados del §5.5. Terminales: failed, imported, reverted, shadowed.
ESTADOS = ("queued", "running", "failed", "validated", "pending_review",
           "imported", "shadowed", "reverted")

# `shadow` no escribe nada; `assisted` importa. Se congela en el batch para que
# leerlo dentro de un año diga bajo qué régimen entró, no el de hoy.
MODOS = ("shadow", "assisted")


class ImportBatch(Base):
    """Una corrida de importación. Una subida manual también es un batch."""
    __tablename__ = "import_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    # ⚠️ `hotel_id` de TEXTO, igual que las otras ~60 tablas. El spec original
    # pedía `property_id uuid FK → properties`; no existe tal tabla, y FinPlan
    # es **una instalación por hotel** (`app/hotel_actual.py`), no multi-tenant.
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    scenario_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="SET NULL"),
        nullable=True, index=True)

    # De dónde vino: manual (la pantalla), folder, correo, sftp, api.
    origen: Mapped[str] = mapped_column(String(20), default="manual")
    # Qué endpoint lo recibió. Sirve para saber qué puertas están cubiertas.
    endpoint: Mapped[str] = mapped_column(String(120), default="")
    estado: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    modo: Mapped[str] = mapped_column(String(12), default="assisted")

    lineas_total: Mapped[int] = mapped_column(Integer, default=0)
    lineas_auto: Mapped[int] = mapped_column(Integer, default=0)
    lineas_pendientes: Mapped[int] = mapped_column(Integer, default=0)

    # Quién lo disparó: el email del usuario, o `guillermo`.
    disparado_por: Mapped[str] = mapped_column(String(120), default="")
    detalle: Mapped[str] = mapped_column(Text, default="")

    iniciado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    terminado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)


class ImportFile(Base):
    """Un archivo dentro de un batch. **Acá vive la identidad.**"""
    __tablename__ = "import_files"
    __table_args__ = (
        # ⚠️ **El constraint que cierra el hueco.** El mismo archivo (mismo
        # contenido, mismo sha256) no entra dos veces al mismo escenario.
        #
        # Va con `scenario_id` y no solo con `hotel_id` a propósito: el MISMO
        # archivo puede legítimamente cargarse en dos escenarios distintos —un
        # Actual y un Forecast que lo espeja— y eso no es un duplicado.
        UniqueConstraint("hotel_id", "scenario_id", "checksum",
                         name="uq_import_file_checksum"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("import_batches.id", ondelete="CASCADE"),
        index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    scenario_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    nombre: Mapped[str] = mapped_column(String(255), default="")
    # sha256 del contenido. ⚠️ Del CONTENIDO, no del nombre: renombrar un
    # archivo no lo convierte en otro, y es la forma más común de reimportar
    # sin querer («actuales_julio (2).xlsx»).
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    tamano: Mapped[int] = mapped_column(Integer, default=0)

    # Qué reporte es, cuando se sepa (Fase 1). Vacío = todavía no se clasifica.
    report_id: Mapped[str] = mapped_column(String(60), default="")
    resultado: Mapped[str] = mapped_column(String(20), default="")
    mensaje: Mapped[str] = mapped_column(Text, default="")
    subido_por: Mapped[str] = mapped_column(String(120), default="")

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
