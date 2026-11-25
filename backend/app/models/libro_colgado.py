"""Mis libros: los Excels del owner en un solo lugar.

Owner, 2026-11-24, con el Master File v13 abierto: *«solo quiero colgarlo ahí…
yo lo bajo y lo corro como siempre»*, *«tengo versiones por todos lados… quiero
ir a un lugar solo y bajar mis proyectos, mis creaciones, pero que no se rompa
nada»* y *«no quiero llenarme de versiones»*.

- El archivo se guarda byte por byte: no se abre ni se arma, así el Power Query
  llega intacto y se actualiza en Excel con la llave, como siempre.
- **Un libro por título.** Subir con el mismo título lo REEMPLAZA. Solo se
  guarda la versión inmediatamente anterior (`anterior_*`), una sola, para poder
  volver atrás si se subió algo mal. Nada más se acumula.
- El botón «Budget Package (todo en un libro)» baja el libro con el título
  `TITULO_BUDGET_PACKAGE`.

Owner, 2026-11-24: *«podemos crear sub tabs acá… y que pueda subir archivos
mensuales para Cierre, Budget o Forecast y otros, ya si no se mezclan»* y *«es
un mismo repositorio solo que organizado por estos sub tabs»*.

- La **carpeta** es solo para ordenar la vista. El repositorio sigue siendo uno:
  el título manda igual que antes, y por eso **un mismo título no puede estar
  dos veces aunque sea en carpetas distintas** — mover de carpeta no clona ni
  duplica nada, solo cambia en cuál tab se ve.
- Un libro se puede mover de carpeta cuando sea, sin volver a subirlo.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, deferred, mapped_column

from app.db import Base
from app.hotel_actual import HOTEL_ID

TITULO_BUDGET_PACKAGE = "Budget Package (todo en un libro)"

#: Las carpetas (los sub-tabs), en el orden en que se muestran. La clave es lo
#: que se guarda; el rótulo, lo que se lee en pantalla.
CARPETAS: dict[str, str] = {
    "CIERRE": "Cierre de mes",
    "BUDGET": "Budget",
    "FORECAST": "Forecast",
    "OTROS": "Otros",
}
#: Dónde cae un libro que no dice carpeta, y dónde quedaron los ya subidos.
CARPETA_POR_DEFECTO = "OTROS"
ORDEN_CARPETA = {c: i for i, c in enumerate(CARPETAS)}


class LibroColgado(Base):
    __tablename__ = "libros_colgados"
    __table_args__ = (UniqueConstraint("hotel_id", "titulo", name="uq_libro_titulo"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), default=lambda: HOTEL_ID)
    titulo: Mapped[str] = mapped_column(String(160))
    # Solo ordena la vista: NO entra en la llave única — ver el docstring.
    carpeta: Mapped[str] = mapped_column(String(16), default=CARPETA_POR_DEFECTO,
                                         server_default=CARPETA_POR_DEFECTO)
    nombre_archivo: Mapped[str] = mapped_column(String(200))
    # deferred: la lista no carga los megas de cada archivo; solo la descarga.
    contenido: Mapped[bytes] = deferred(mapped_column(LargeBinary))
    tamano: Mapped[int] = mapped_column(Integer)
    nota: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    subido_por: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    subido_el: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())
    # La versión anterior, una sola, para deshacer una subida equivocada.
    anterior_nombre: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    anterior_contenido: Mapped[Optional[bytes]] = deferred(
        mapped_column(LargeBinary, nullable=True))
    anterior_tamano: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    anterior_subido_por: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    anterior_subido_el: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True)
