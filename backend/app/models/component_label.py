# -*- coding: utf-8 -*-
"""Etiquetas de los componentes, editables POR PROPIEDAD.

**El pedido (owner, 2026-08-14):** «varias cosas no van a aplicar en otros
hoteles. Podría usar un rate para calcular en los otros, pero no tiene como
paquete. Dejame esta parte con el nombre editable para poder personalizar estos
componentes.»

Es la misma regla que los tipos de habitación, y por la misma razón:

    el CÓDIGO es fijo y liga · la ETIQUETA es tuya y se edita

`FOOD`, `ACTIVITIES`, `TRANSPORT` y `SUSTAINABILITY` son los códigos con los que
el motor de revenue arma el ingreso y lo rutea al P&L (`revenue_calculator.py`
los busca por nombre exacto). Cambiarlos movería plata de línea. La etiqueta, en
cambio, es solo lo que se lee en pantalla: en Corcovado «Transportation» es la
lancha desde Sierpe; en un hotel de ciudad puede ser «Traslado aeropuerto», o
apagarse dejándola en cero.

Por eso el `PUT` solo toca `label`. No hay endpoint para crear ni borrar
códigos: los cuatro son los que el motor sabe calcular.
"""
import uuid

from sqlalchemy import String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Familias de componentes. Hoy solo el paquete; el `kind` está para que sumar
# los canales de venta mañana no necesite otra tabla ni otra migración.
KIND_PACKAGE = "PACKAGE"

# Lo que se lee si la propiedad no editó nada. Son los textos que estaban
# escritos en `revenue_api._PKG_LABELS`, para que Corcovado no cambie de aspecto.
ETIQUETAS_POR_DEFECTO: dict[str, dict[str, str]] = {
    KIND_PACKAGE: {
        "FOOD": "Food (Desayuno + Almuerzo + Cena)",
        "BEVERAGE": "Beverage (ratio del Food)",
        "ACTIVITIES": "Activities (Tours)",
        "TRANSPORT": "Transportation",
        "SUSTAINABILITY": "Sustainability Fee",
    },
}


class ComponentLabel(Base):
    """Un rótulo propio para un código de componente, en una propiedad."""

    __tablename__ = "component_labels"
    __table_args__ = (
        UniqueConstraint("hotel_id", "kind", "code", name="uq_component_label"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), ForeignKey("hotels.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default=KIND_PACKAGE)
    # El código NO se edita: es la llave con la que calcula el motor.
    code: Mapped[str] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(120), default="")
