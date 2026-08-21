# -*- coding: utf-8 -*-
"""Los canales de COMISIÓN: a dónde rueda cada sub-canal comercial.

Owner, 2026-08-17: *«inclusive se pueden crear más canales y sub-canales, pero
deben estar sincronizados para que ruede donde corresponde»*.

Eran una constante de tres —`("TA", "OTA", "DIRECT")`— repetida en cinco
lugares: el motor del mixer, `sales_channel_config`, las etiquetas de la API, el
importador y una pantalla del front. Con eso, **agregar un cuarto canal era
imposible sin tocar código en los cinco**, y olvidarse de uno lo dejaba
ignorando el nuevo en silencio.

Acá viven como tabla, y `canales_comerciales.rueda_a` los referencia con una FK
`ondelete="RESTRICT"`: **no se puede borrar un canal que tenga sub-canales
colgando**. Ese es el «sincronizados» del pedido — el borrado no puede dejar
huérfano un mix que después rodaría a cualquier lado.
"""
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CanalComision(Base):
    __tablename__ = "canales_comision"

    #: `TA`, `OTA`, `DIRECT`… y el que se agregue.
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), default="")
    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<CanalComision {self.code}>"
