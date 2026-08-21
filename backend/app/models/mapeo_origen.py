# -*- coding: utf-8 -*-
"""Equivalencias entre las cuentas de un sistema de afuera y las de FinPlan.

**Por qué existe (owner, 2026-08-14).** Oxígen y Ojochal llevan la contabilidad
en QuickBooks; Corcovado va a traer la suya de un backoffice por API. O sea que
no hay UN origen: hay varios, y va a haber más.

Lo que cambia entre sistemas es el código de cuenta. Lo que NO cambia es el
catálogo USALI de este lado. Esta tabla es el puente, y es **dato**, no código:

    (propiedad, origen, cuenta de allá)  →  cuenta de acá + departamento + outlet

**Esa distinción es todo el punto.** Si el puente fuera código, abrir Oxígen
sería un desarrollo. Siendo dato, es cargar su mapeo desde una pantalla — y el
criterio que puso el owner se cumple: *conectar un hotel es variables + mapeo,
cero código*.

**`dept_origen` vacío = «cualquiera».** Algunos sistemas mandan el departamento
en la fila y otros no. Una regla con departamento gana sobre una sin él, para que
se pueda tener una regla general y excepciones sin duplicar el catálogo entero.
"""
import uuid

from sqlalchemy import String, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Orígenes conocidos. La lista vive acá y no en una tabla porque cada uno
# necesita además un adaptador en `app/origenes/`: agregar una fila no serviría
# de nada sin el código que sabe hablar con ese sistema.
ORIGEN_QUICKBOOKS = "QUICKBOOKS"
ORIGEN_BACKOFFICE = "BACKOFFICE"
ORIGEN_ARCHIVO = "ARCHIVO"

ORIGENES = (ORIGEN_QUICKBOOKS, ORIGEN_BACKOFFICE, ORIGEN_ARCHIVO)


class MapeoOrigen(Base):
    """Una equivalencia. Sin fila que la cubra, el monto NO entra — se reporta."""

    __tablename__ = "mapeo_origen"
    __table_args__ = (
        UniqueConstraint("hotel_id", "origen", "cuenta_origen", "dept_origen",
                         name="uq_mapeo_origen"),
        Index("ix_mapeo_origen_busqueda", "hotel_id", "origen", "cuenta_origen"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), ForeignKey("hotels.id"), index=True)
    origen: Mapped[str] = mapped_column(String(20), default=ORIGEN_QUICKBOOKS)

    # ── Lo que manda el sistema de afuera ────────────────────────────────
    cuenta_origen: Mapped[str] = mapped_column(String(40))
    nombre_origen: Mapped[str] = mapped_column(String(160), default="")
    # Vacío = la regla vale para cualquier departamento del origen.
    dept_origen: Mapped[str] = mapped_column(String(40), default="")

    # ── A dónde va acá ───────────────────────────────────────────────────
    account_code: Mapped[str] = mapped_column(String(10))
    dept_code: Mapped[str] = mapped_column(String(10), default="")
    outlet: Mapped[str] = mapped_column(String(40), default="")

    # Apagar una regla sin borrarla: el histórico de por qué se mapeó así vale.
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    nota: Mapped[str] = mapped_column(String(200), default="")
