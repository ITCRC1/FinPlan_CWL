# -*- coding: utf-8 -*-
"""El USALI, guardado para consultar.

Owner, 2026-10-08: *«yo quiero subir el pdf y que el documento viva en la app y
se use para análisis […] contra ese máximo detalle y USALI se saca para ver las
discrepancias»*.

Se guardan las dos partes del libro, que sirven para cosas distintas:

* **`usali_items`** — el diccionario de ingresos y gastos: qué artículo va en qué
  departamento y en qué cuenta. «Cots → Rooms / Operating Supplies». Son ~1.950
  filas sobre ~1.860 artículos: un mismo artículo puede tener más de un destino
  legítimo —«Apparel sales» va a F&B o a Spa según dónde se venda— y los dos se
  guardan.

* **`usali_definiciones`** — un párrafo por cuenta con lo que incluye y lo que
  no. Son ~470. Es lo que sirve para juzgar lo que el diccionario no cubre, que
  es casi todo lo raro.

## La confianza viaja con el dato

El libro trae el diccionario DOS VECES —ordenado por artículo y por
departamento/cuenta— y el importador cruza las dos. `confianza='confirmado'`
significa que los dos ordenamientos dicen lo mismo; `'unico'`, que solo uno lo
trae.

⚠️ **No se mezclan sin decir cuál es cuál.** El día que esto genere un hallazgo
que se le lleva a un gerente, el hallazgo tiene que poder decir de dónde salió.
Una regla que marca mal y no sabe explicarse se deja de mirar a la tercera vez.

## Derechos

El texto es de AHLA/HFTP y se guarda para uso interno de la propiedad que compró
el libro. No se reproduce en reportes que salgan a terceros, y al clonar a otra
propiedad **no viaja**: cada instalación sube el suyo.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class UsaliDocumento(Base):
    """Qué edición está cargada, de qué archivo y con qué resultado.

    Uno por instalación: subir otro reemplaza el anterior. Guardar el resultado
    de la lectura —cuántas entradas, cuántas confirmadas— es lo que permite
    saber, meses después, si el catálogo que está mandando salió bien.
    """
    __tablename__ = "usali_documentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    archivo: Mapped[str] = mapped_column(String(300))
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    paginas: Mapped[int] = mapped_column(Integer, default=0)
    paginas_con_texto: Mapped[int] = mapped_column(Integer, default=0)
    items: Mapped[int] = mapped_column(Integer, default=0)
    items_confirmados: Mapped[int] = mapped_column(Integer, default=0)
    definiciones: Mapped[int] = mapped_column(Integer, default=0)
    #: El cruce de los dos ordenamientos, como lo devolvió el importador.
    cruce: Mapped[str] = mapped_column(Text, default="")
    subido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())
    subido_por: Mapped[str] = mapped_column(String(120), default="")


class UsaliItem(Base):
    """Un artículo del diccionario: dónde dice el estándar que va."""
    __tablename__ = "usali_items"
    __table_args__ = (
        UniqueConstraint("hotel_id", "item_norm", "schedule", "cuenta",
                         name="uq_usali_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    #: El artículo tal como lo escribe el libro.
    item: Mapped[str] = mapped_column(String(400))
    #: El mismo, normalizado, que es por donde se busca y se aparea.
    item_norm: Mapped[str] = mapped_column(String(400), index=True)
    #: El departamento del USALI: Rooms, F&B, A&G, POM, Mult. Depts.…
    schedule: Mapped[str] = mapped_column(String(80), index=True)
    #: El nombre de cuenta: Operating Supplies, Linen, Contract Services…
    cuenta: Mapped[str] = mapped_column(String(200), index=True)
    confianza: Mapped[str] = mapped_column(String(12), default="unico")
    paginas: Mapped[str] = mapped_column(String(60), default="")


class UsaliDefinicion(Base):
    """Una cuenta con su definición, tal como la explica el libro."""
    __tablename__ = "usali_definiciones"
    __table_args__ = (
        UniqueConstraint("hotel_id", "cuenta_norm", "pagina",
                         name="uq_usali_definicion"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    cuenta: Mapped[str] = mapped_column(String(200))
    cuenta_norm: Mapped[str] = mapped_column(String(200), index=True)
    texto: Mapped[str] = mapped_column(Text)
    pagina: Mapped[int] = mapped_column(Integer, default=0)
