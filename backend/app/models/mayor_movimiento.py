# -*- coding: utf-8 -*-
"""El movimiento del mayor, guardado, para poder bajar hasta el asiento.

Owner, 2026-10-06: *«a mí me gustaría que quede guardado pero cada vez que se
corra se le caiga encima […] es solo para poder revisar detalladamente a nivel
de detalle»* · *«dale, máximo detalle y descripción del asiento»*.

## Qué cambia respecto de la Auditoría

Hasta hoy el Balance de Comprobación entraba, se revisaba y se iba: la Auditoría
del mayor es una lupa sobre un archivo y no guarda nada. Eso está bien para
buscar discrepancias, y no alcanza para **revisar**: para abrir el `7310-0110`
de setiembre y ver los nueve asientos que lo forman hay que tener los asientos.

## Uno por mes, y el que sube le cae encima

La llave de negocio es `(hotel, año, mes)`. Subir setiembre otra vez —porque
corrigieron un posteo— **reemplaza** lo que había: se borra el mes y se inserta
el archivo nuevo, en la misma transacción. Nunca hay dos versiones del mismo mes
y no hace falta acordarse de limpiar.

Subir octubre no toca setiembre: son meses distintos. El owner preguntó por el
espacio y está medido — el año entero son **12 MB** con su archivo de setiembre
y **23 MB** con el *Full Detail* completo. No hay nada que ahorrar.

## Se guarda TODO el archivo, no solo lo que se revisa

Las clases 4-8 son la mitad de las líneas, y recortar a eso habría ahorrado
~10 MB al año. No se recorta: el día que haga falta mirar un banco o una cuenta
por cobrar, el dato está y no hay que volver a subir nada. Diez megas no pagan
un «eso no lo guardamos».

⚠️ **Esto NO entra a ningún total.** No lo lee el P&L, no lo lee el Pre-Cierre,
no alimenta un escenario. Es el libro, para mirarlo. La plata del mes sigue
entrando por donde siempre — `integrity_final` → borrador → espejo → ACTUAL (ver
`el camino del pre-cierre`). Dos fuentes de plata es exactamente el problema que
este proyecto ya pagó varias veces.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MayorMovimiento(Base):
    __tablename__ = "mayor_movimientos"
    __table_args__ = (
        # El índice que sirve a la pregunta real: «abrime ESTA cuenta de ESTE
        # mes». Sin él, cada apertura es un barrido de las ~9.000 filas del mes.
        Index("ix_mayor_mov_mes_cuenta", "hotel_id", "anio", "mes", "cuenta"),
        # Y el de departamento, para «todo lo de Rooms en setiembre».
        Index("ix_mayor_mov_mes_depto", "hotel_id", "anio", "mes", "seg2"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True, default="")
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)          # 1..12

    # ── La cuenta, entera y en pedazos ───────────────────────────────────────
    #: `5420-0220-000-000-000-00-00`, tal cual la escribe Integrity.
    cuenta: Mapped[str] = mapped_column(String(40), default="")
    seg1: Mapped[str] = mapped_column(String(6), default="")    # clase: 5420
    seg2: Mapped[str] = mapped_column(String(6), default="")    # departamento
    #: El tercer nivel: en las 6 es el puesto, en las 7 el detalle del gasto.
    #: Es el MISMO eje que abren `Opex by Detail` y `Payroll by Position`.
    seg3: Mapped[str] = mapped_column(String(6), default="")

    # ── El asiento ───────────────────────────────────────────────────────────
    asiento: Mapped[str] = mapped_column(String(20), default="", index=True)
    linea: Mapped[str] = mapped_column(String(10), default="")
    #: Como viene en el archivo (`24/09/26`). Se guarda TEXTO a propósito: es un
    #: dato del libro, no una fecha que el sistema calcule, y parsearla acá sería
    #: inventar un formato que el archivo no promete.
    fecha: Mapped[str] = mapped_column(String(20), default="")
    #: La descripción de la LÍNEA (`PAYMENT CASH USD`).
    descripcion: Mapped[str] = mapped_column(String(250), default="")
    #: Y la del ASIENTO entero (`OPL - Ingresos Opera/Simphony 24/09/20`). Owner,
    #: 2026-10-06: *«máximo detalle y descripción del asiento»*. Son dos cosas
    #: distintas y las dos se guardan: la línea dice qué se compró, el asiento
    #: dice de dónde viene el movimiento.
    desc_asiento: Mapped[str] = mapped_column(String(250), default="")
    origen: Mapped[str] = mapped_column(String(20), default="")
    referencia: Mapped[str] = mapped_column(String(120), default="")
    num_doc: Mapped[str] = mapped_column(String(40), default="")

    # ── La plata ─────────────────────────────────────────────────────────────
    debito: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    credito: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    #: El TC del asiento y la moneda, como vienen. El mayor de CWL trae `DOL`.
    tc: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    moneda: Mapped[str] = mapped_column(String(10), default="")
    #: En qué moneda están los MONTOS de este archivo, del encabezado
    #: (`Moneda: DOL` / `Moneda: COL`).
    #:
    #: ⚠️ **Sin esto el mayor guardado no se puede volver a leer bien.** La
    #: columna `moneda` de arriba es la de la TRANSACCIÓN y viene mezclada; la
    #: que dice si los montos son colones o dólares es ésta. Un mayor subido en
    #: dólares, leído como colones, da los montos multiplicados por el TC.
    moneda_archivo: Mapped[str] = mapped_column(String(10), default="COL",
                                                server_default="COL")

    # ── De qué subida salió ──────────────────────────────────────────────────
    #: El nombre y el checksum viajan en la FILA y no en una tabla de subidas
    #: aparte: así «¿de qué archivo salió este asiento?» se contesta mirando el
    #: asiento. Y el anti-reimport NO aplica acá — volver a subir el mismo mes
    #: es justamente lo que se quiere.
    archivo: Mapped[str] = mapped_column(String(255), default="")
    checksum: Mapped[str] = mapped_column(String(64), default="", index=True)
    subido_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    subido_por: Mapped[str] = mapped_column(String(120), default="")


class MayorMovimientoPrevio(Base):
    """La subida ANTERIOR del mismo mes, sólo para comparar contra la nueva.

    Owner, 2026-10-07: *«hicimos cambios en esta versión… cómo sé qué cambió con
    respecto a la primera»*.

    ⚠️ **Vive en su propia tabla y no como una columna «vigente».** Si
    `mayor_movimientos` pudiera tener dos versiones del mismo mes, cualquier
    consulta que olvide filtrar la vigente contaría todo dos veces — el modo de
    falla más caro de este sistema, porque el total cuadra consigo mismo y no hay
    error. Acá ese olvido es imposible: `mayor_movimientos` sigue teniendo UNA
    versión por mes y nadie más que la comparación mira esta tabla.

    **Una anterior, no un historial.** La pregunta es «¿quedaron los cambios que
    hice?», y eso lo contesta la de antes. Guardar todas traería la pregunta de
    cuál era la buena, que es peor que no tenerlas.
    """
    __tablename__ = "mayor_movimientos_previos"
    __table_args__ = (
        Index("ix_mayor_prev_mes", "hotel_id", "anio", "mes"),
        Index("ix_mayor_prev_mes_cuenta", "hotel_id", "anio", "mes", "cuenta"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), default="")
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    cuenta: Mapped[str] = mapped_column(String(40), default="")
    seg1: Mapped[str] = mapped_column(String(6), default="")
    seg2: Mapped[str] = mapped_column(String(6), default="")
    seg3: Mapped[str] = mapped_column(String(6), default="")
    asiento: Mapped[str] = mapped_column(String(20), default="")
    linea: Mapped[str] = mapped_column(String(10), default="")
    fecha: Mapped[str] = mapped_column(String(20), default="")
    descripcion: Mapped[str] = mapped_column(String(250), default="")
    desc_asiento: Mapped[str] = mapped_column(String(250), default="")
    origen: Mapped[str] = mapped_column(String(20), default="")
    referencia: Mapped[str] = mapped_column(String(120), default="")
    num_doc: Mapped[str] = mapped_column(String(40), default="")
    debito: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    credito: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    tc: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    moneda: Mapped[str] = mapped_column(String(10), default="")
    moneda_archivo: Mapped[str] = mapped_column(String(10), default="COL",
                                                server_default="COL")
    archivo: Mapped[str] = mapped_column(String(255), default="")
    checksum: Mapped[str] = mapped_column(String(64), default="")
    subido_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    subido_por: Mapped[str] = mapped_column(String(120), default="")
    #: Cuándo dejó de ser la vigente. Es lo único que esta tabla tiene de más:
    #: la pantalla dice «comparado contra la subida del …».
    reemplazado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)


#: Las columnas que se copian de la vigente a la anterior. Se DERIVA del modelo
#: —no es una lista a mano— porque el día que `MayorMovimiento` crezca, la copia
#: tiene que crecer con él o la anterior pierde ese dato en silencio.
COLUMNAS_A_COPIAR = tuple(
    c for c in MayorMovimiento.__table__.columns.keys() if c != "id")
