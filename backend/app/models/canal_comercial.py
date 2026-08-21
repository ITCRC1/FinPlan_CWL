# -*- coding: utf-8 -*-
"""Los canales comerciales y la comisión que paga cada uno.

**De dónde salen (owner, 2026-08-14).** De su app de Compensación: siete canales
con su % de comisión. Es la TERCERA lista de canales del sistema, y es la que
decide **quién cobra**.

⚠️ **Es otro eje que el market code de Opera**, y hay que decirlo antes de
intentar cruzarlos:

* «B2B», «Direct website», «Direct phone/email/social» y «OTA» describen **por
  dónde entró** la reserva. Eso Opera lo sabe.
* «Costa Rica Collection direct», «Direct groups» y «Executive personal direct»
  describen **quién la trajo**. Eso Opera NO lo sabe: una reserva con market code
  `DIR` puede haber entrado por teléfono, haberla traído la ejecutiva, o venir de
  CRC — y el código es el mismo.

Derivar el canal de compensación desde el market code sería **adivinar quién
vendió**, y eso pagaría comisiones equivocadas mientras el total sigue cuadrando.
Por eso viven en tablas separadas y el cruce, cuando exista, va a ser un dato que
alguien digita o que sale de un campo de agente del PMS — no una deducción.

**Lo que sí sirve tenerlos juntos** es ver el panorama: las comisiones de esta
tabla y las de `SalesChannelConfig` describen el mismo negocio y **no dicen lo
mismo**. Ver el endpoint del panorama en `api/canales_api.py`.
"""
from decimal import Decimal

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CanalComercial(Base):
    __tablename__ = "canales_comerciales"

    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), default="")

    #: La comisión que paga ese canal, como fracción (0.30 = 30%).
    comision_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))

    #: Qué parte del negocio entra por ese canal, como fracción (0.55 = 55%).
    #: Es el mix BASE: el que aplica cuando nadie dijo otra cosa, y el que hace
    #: que un escenario nuevo nazca bien. La excepción por escenario o por mes
    #: vive en `CanalMixEscenario`. La suma de todos tiene que dar 1.
    mix_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))

    #: Cómo entró la reserva: es lo único que Opera puede saber. Vacío = este
    #: canal describe QUIÉN la trajo, no por dónde entró.
    entrada: Mapped[str] = mapped_column(String(40), default="")

    #: **A qué canal de comisión rueda.** FK a `canales_comision`.
    #:
    #: ⚠️ Antes esto NO era un dato: se deducía de `entrada` con un diccionario
    #: de seis entradas en el código, y lo que no estaba en la lista caía a
    #: `DIRECT` **por default y en silencio**. Un sub-canal nuevo terminaba
    #: rodando a DIRECT —9,27% de comisión— cuando debía ir a TA —30%—, así que
    #: el ingreso salía de MÁS. No fallaba: facturaba mal.
    #:
    #: Como columna, el destino se elige, se ve en la grilla y se puede
    #: corregir. Y es NOT NULL: un sub-canal sin destino no existe.
    rueda_a: Mapped[str] = mapped_column(
        String(30), ForeignKey("canales_comision.code", ondelete="RESTRICT"),
        default="DIRECT")

    orden: Mapped[int] = mapped_column(Integer, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return (f"<CanalComercial {self.code} -> {self.rueda_a} "
                f"mix={float(self.mix_pct):.0%} com={float(self.comision_pct):.0%}>")
