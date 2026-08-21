# -*- coding: utf-8 -*-
"""Qué tabs y reportes ve CADA propiedad.

Owner, 2026-08-20: *«no todas las propiedades van a ver todos los reportes, ya
que son muchos para cada propiedad y se van a perder»* · *«así como los
departamentos se van a limitar, así se van a limitar los reportes y los tabs
principales»* · *«todo debe poderse esconder y habilitar»*.

Medido ese día: la barra tiene **13 tabs y 96 entradas**. Una propiedad nueva
abre con las 96.

**Es el mismo patrón que `dept_enablement`, a propósito.** Dos matrices de
provisionamiento con reglas distintas serían dos cosas que hay que aprender por
separado, y la de departamentos ya está probada:

* **La tabla es ESPARSA y el default es PRENDIDO.** No tener fila significa
  visible. Por eso se pregunta «qué está apagado» y no «qué está prendido»: el
  día que esto se despliega no cambia nada en ninguna propiedad, y una
  propiedad nueva ve todo.
* **Prender BORRA la fila** en vez de escribir `visible=true`, así la tabla
  contiene sólo lo que alguien apagó a mano.
* Y **un reporte nuevo nace VISIBLE**. Al revés —nacer oculto— sería peor: se
  construye algo, nadie lo ve, y nadie sabe que existe para poder prenderlo.

⚠️ **Esto ESCONDE de la barra; NO es un permiso.** La ruta sigue respondiendo:
quien escriba la URL entra igual, y el endpoint contesta lo mismo. Es
navegación, no seguridad — si hace falta impedir el acceso, eso son roles, no
esta tabla.

Y esa misma propiedad es la que hace seguro poder apagarlo **todo**, incluida la
pantalla que administra esto: aunque se esconda, se vuelve entrando a su URL.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

#: Qué se está apagando. `TAB` es un tab de primer nivel de la barra; `ITEM` es
#: una entrada de su menú (una pantalla o un reporte).
#:
#: ⚠️ Son dos niveles y no uno porque apagar un tab entero es una decisión
#: distinta de apagar un reporte suelto: «esta propiedad no hace Break-Even» no
#: es lo mismo que «esta propiedad no usa el reporte a la Junta».
SCOPE_KINDS = ["TAB", "ITEM"]


class TabEnablement(Base):
    """Una fila = algo que ESTA propiedad NO ve. Sin fila, se ve."""

    __tablename__ = "tab_enablement"
    __table_args__ = (
        UniqueConstraint("hotel_id", "scope_kind", "clave",
                         name="uq_tab_enablement"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    scope_kind: Mapped[str] = mapped_column(String(8), default="ITEM")
    #: La `key` de la barra (`reports`, `ownerReport`…).
    #:
    #: ⚠️ **El catálogo de lo que existe vive en la barra, no acá.** Copiarlo al
    #: backend sería una segunda lista que habría que acordarse de actualizar, y
    #: este proyecto ya pagó dos veces por una lista escrita a mano. Acá sólo se
    #: guarda lo apagado; una clave que ya no exista en la barra no rompe nada,
    #: simplemente no esconde nada.
    clave: Mapped[str] = mapped_column(String(60))
    #: Siempre `False`. La columna existe para poder leer una fila y entender
    #: qué significa sin ir al docstring.
    visible: Mapped[bool] = mapped_column(Boolean, default=False)

    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
    actualizado_por: Mapped[str] = mapped_column(String(120), default="")
