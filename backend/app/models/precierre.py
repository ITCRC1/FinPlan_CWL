# -*- coding: utf-8 -*-
"""El carril de espera del cierre mensual — los actuales antes de ser finales.

## Por qué existe

Hasta hoy el cierre entraba de una: se subía la plantilla y se escribía. La
revisión —¿aparecio una cuenta que USALI no contempla? ¿un departamento nuevo?
¿un gasto que nadie presupuestó?— pasaba por el ojo de una persona sobre un
Excel de 104 MB en Drive. Si nadie lo miraba, entraba igual y el P&L cuadraba
consigo mismo.

Un pre-cierre es ese mes **traducido y revisado, pero todavía no escrito**. Se
puede volver a él, mirarlo contra el Forecast y el Budget, y recién cuando
convence se pasa a Final.

## ⚠️ Un pre-cierre NO es un escenario

No lo lee ningún reporte, no aparece en las comparaciones y no alimenta el P&L.
Sólo se ve desde su propia pantalla. Si se filtrara a los reportes habría **dos
versiones del mismo mes conviviendo**, y la pregunta «¿cuál es el bueno?» no
tendría respuesta desde adentro del sistema.

## Y no abre una segunda puerta de escritura

«Pasar a Final» arma la plantilla de upload (`export/detail_excel`) y se la da
al importador que ya existe. Este repo ya se quemó con dos caminos al mismo
dato; el pre-cierre es una **antesala**, no un atajo.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (DateTime, ForeignKey, Integer, Numeric, String, Text,
                        UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

#: borrador → se está revisando · pasado_a_final → ya se escribió ·
#: descartado → se abandonó. Un mes puede tener varios descartados y un solo
#: borrador vivo.
ESTADOS = ("borrador", "pasado_a_final", "descartado")


class Precierre(Base):
    """Un mes traducido desde Integrity, esperando revisión."""
    __tablename__ = "precierre"
    __table_args__ = (
        # Un solo borrador vivo por mes. Los pasados y descartados no compiten:
        # son historia, y se conservan para poder decir con qué hallazgos
        # abiertos se cerró cada mes.
        UniqueConstraint("hotel_id", "anio", "mes", "estado",
                         name="uq_precierre_mes_estado"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)          # 1..12

    #: El tipo de cambio con el que se dolarizó. Se guarda porque es parte del
    #: resultado: el mismo archivo con otro TC da otro P&L, y sin esto no habría
    #: forma de reproducir lo que se revisó.
    tc: Mapped[Decimal] = mapped_column(Numeric(12, 4))

    archivo_nombre: Mapped[str] = mapped_column(String(255), default="")
    #: Del contenido, no del nombre. Es lo que permite decir «este es el mismo
    #: archivo que ya subiste» aunque lo hayan renombrado.
    checksum: Mapped[str] = mapped_column(String(64), default="", index=True)

    estado: Mapped[str] = mapped_column(String(16), default="borrador", index=True)
    subido_por: Mapped[str] = mapped_column(String(120), default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                server_default=func.now())

    #: Con cuántos hallazgos abiertos se pasó a Final. Ignorar uno es una
    #: decisión, y tiene que quedar escrita.
    hallazgos_abiertos: Mapped[int] = mapped_column(Integer, default=0)
    #: El detalle de esos hallazgos al momento de cerrar, en JSON. Un número
    #: solo no deja auditar nada.
    hallazgos: Mapped[str] = mapped_column(Text, default="")

    escenario_destino_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True)
    pasado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True),
                                                       nullable=True)
    pasado_por: Mapped[str] = mapped_column(String(120), default="")

    def __repr__(self) -> str:
        return f"<Precierre {self.hotel_id} {self.anio}-{self.mes:02d} {self.estado}>"


class PrecierreFila(Base):
    """Una fila del mayor de Integrity, ya traducida.

    Se guarda el resultado de la traducción y no el archivo crudo: el archivo se
    vuelve a leer igual, pero lo que se revisó fue esto. Si mañana cambia el
    puente de departamentos, el pre-cierre sigue diciendo lo que decía.
    """
    __tablename__ = "precierre_fila"

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    precierre_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("precierre.id", ondelete="CASCADE"), index=True)

    #: La fila del Excel de origen. Sin esto, un hallazgo no se puede ir a mirar.
    fila: Mapped[int] = mapped_column(Integer, default=0)
    cuenta: Mapped[str] = mapped_column(String(30), default="")
    cuenta_base: Mapped[int | None] = mapped_column(Integer, nullable=True)
    descripcion: Mapped[str] = mapped_column(String(200), default="")

    #: El departamento tal como viene de Integrity…
    depto: Mapped[str] = mapped_column(String(10), default="", index=True)
    #: …y a cuál de FinPlan se tradujo. Los dos sistemas NO comparten espacio de
    #: códigos: Integrity 0130 es el Restaurant Terra Kitchen y FinPlan 0130 es
    #: «Spa (gerencia)». Ver `seed_data/<HOTEL>/mapd_integrity.json`.
    destino_finplan: Mapped[str] = mapped_column(String(10), default="")
    #: El grupo del P&L, según el catálogo de FinPlan. Vacío es un estado válido:
    #: los departamentos que se abren POR CUENTA (280) no tienen grupo, y
    #: ponerles uno los rotularía mal.
    grupo: Mapped[str] = mapped_column(String(30), default="")
    categoria: Mapped[str] = mapped_column(String(20), default="")

    mes_usd: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    acumulado_usd: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))

    def __repr__(self) -> str:
        return f"<PrecierreFila {self.cuenta} ${self.mes_usd}>"
