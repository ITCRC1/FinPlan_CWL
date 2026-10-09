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

from sqlalchemy import (Boolean, DateTime, Integer, String, Text,
                        UniqueConstraint, func)
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
    renglones: Mapped[int] = mapped_column(Integer, default=0)
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


class UsaliRenglon(Base):
    """Un renglón aprobado del reporte de un departamento (un Schedule).

    Es la OTRA mitad del libro. El diccionario (`usali_items`) da ejemplos de
    artículos —«Cots → Rooms / Operating Supplies»—; el Schedule da el renglón
    del reporte: qué líneas lleva el estado de resultados de Rooms, de F&B, de
    A&G. Son ~400 en 14 schedules.

    ## Por qué es referencia y no alarma

    Se midió antes de construirlo, contra las 252 cuentas que usó setiembre
    2026. La regla «esta cuenta no es renglón aprobado de su schedule» dio UN
    hallazgo, y dudoso. El reparto real:

    * 130 (51.6%) son cuentas propias del hotel que el estándar nunca nombró;
    * 68 (27.0%) caen en departamentos donde el libro **no da lista** —el Spa y
      los minor departments son Schedule 3, que es una plantilla de formato—;
    * 52 (20.6%) sí son renglón aprobado de su schedule.

    Con ese reparto no se puede alarmar. Sirve para lo que el owner pidió el
    2026-10-08: *«cada cuenta tiene la descripción y va por departamento»* — al
    revisar una cuenta, ver qué dice el estándar que lleva ese departamento.

    ## `lista_aprobada` sale del libro, no de una lista a mano

    El texto declara la lista cerrada con una de dos frases —«approved as line
    items» o «does not provide for the addition or substitution»—. El Schedule 3
    no trae ninguna; dice «only the revenues and expenses […] that exist at an
    individual property». Leerlo del texto es lo que hace que otra edición del
    libro siga funcionando.
    """
    __tablename__ = "usali_renglones"
    __table_args__ = (
        UniqueConstraint("hotel_id", "numero", "renglon_norm",
                         name="uq_usali_renglon"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    #: El número del Schedule: 1 Rooms, 2 F&B, … 14 Payroll-Related.
    numero: Mapped[int] = mapped_column(Integer, index=True)
    #: Como lo titula el cuadro: ROOMS, HOUSE LAUNDRY, STAFF DINING…
    titulo: Mapped[str] = mapped_column(String(80))
    #: Como lo llama el diccionario: Rooms, Laundry, Staff Dining. Es la llave
    #: de apareo con `usali_items`.
    schedule: Mapped[str] = mapped_column(String(80), index=True)
    renglon: Mapped[str] = mapped_column(String(200))
    renglon_norm: Mapped[str] = mapped_column(String(200), index=True)
    #: En qué posición lo trae el cuadro: el reporte se arma en ese orden.
    orden: Mapped[int] = mapped_column(Integer, default=0)
    pagina: Mapped[int] = mapped_column(Integer, default=0)
    #: ¿El libro declara lista cerrada para este schedule? False en el 3.
    lista_aprobada: Mapped[bool] = mapped_column(Boolean, default=False)
