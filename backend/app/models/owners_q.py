"""Tablas del tab `Reports` — el primer reporte que aloja es `Owners Q`.

`Reports` es un CONTENEDOR, no una pantalla. Por eso las cuatro tablas llevan
`report_key` en la llave: el próximo reporte se agrega sembrando filas, sin
tocar el motor ni migrar tablas. Y todas llevan `entidad`, porque el mismo
motor tiene que servir para Oxígen, Ojochal y Amarena cambiando únicamente el
Account Mapping y la tabla `capacidad`.

`Owners Q` es el nombre INTERNO. Lo que viaja a SCP se sigue titulando
`Statement of Income`: el nombre de acá adentro no sale en el entregable.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON, CheckConstraint, DateTime, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

LINE_TYPES = ("STAT", "HEADER", "DETAIL", "SUBTOTAL", "CALC")
NATURES = ("stat", "header", "revenue", "expense", "profit", "signed")


class ReportLine(Base):
    """Las 48 filas del reporte: código, etiqueta, sangría, tipo y naturaleza.

    NADA se codifica por fila en la vista ni en el motor (§3.5 del spec). Si
    SCP mueve una fila, se cambia acá y no se toca una línea de código.
    """
    __tablename__ = "report_lines"
    __table_args__ = (
        UniqueConstraint("report_key", "report_code", name="uq_report_line"),
        UniqueConstraint("report_key", "row_no", name="uq_report_line_row"),
        CheckConstraint(
            "line_type IN ('STAT','HEADER','DETAIL','SUBTOTAL','CALC')",
            name="ck_report_line_type"),
        CheckConstraint(
            "nature IN ('stat','header','revenue','expense','profit','signed')",
            name="ck_report_line_nature"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    report_key: Mapped[str] = mapped_column(String(40), index=True)
    #: Fila del Excel (9–56). Es la llave con la que SCP consolida: no es un
    #: orden cosmético, moverla desalinea su consolidación.
    row_no: Mapped[int] = mapped_column(Integer)
    report_code: Mapped[str] = mapped_column(String(60))
    #: Etiqueta EXACTA que ve SCP. Conserva los espacios finales (`ADR ($) `);
    #: no se le hace strip en ningún punto del circuito.
    label: Mapped[str] = mapped_column(String(150))
    #: 1 o 2. SCP lee el reporte por sangría, así que es dato, no estilo.
    indent: Mapped[int] = mapped_column(Integer, default=1)
    line_type: Mapped[str] = mapped_column(String(12))
    #: Gobierna la inversión de signo de la convención `favorable` (§6).
    nature: Mapped[str] = mapped_column(String(12))
    #: `Línea P&L` que suman las filas DETAIL. Lista, no string.
    lineas_pl: Mapped[list] = mapped_column(JSON, default=list)
    #: Operandos con signo de SUBTOTAL/CALC: [{"code": ..., "sign": 1|-1}].
    #: NO se parsea fórmula libre en tiempo de cálculo.
    operandos: Mapped[list] = mapped_column(JSON, default=list)
    #: La fórmula original en texto, solo para que un humano la lea.
    formula_nota: Mapped[str] = mapped_column(Text, default="")
    nota: Mapped[str] = mapped_column(Text, default="")

    #: Cómo se PINTA la fila en el Excel que recibe SCP, leído de su propio
    #: archivo: `{resalte, formato, top, bottom, sangria_espacios}`.
    #:
    #: Va acá y no en el exportador porque no se deriva de nada: la fila 49
    #: lleva línea arriba sin ser subtotal, la 52 la lleva doble, y
    #: `TOTAL DEPARTMENTAL PROFIT` se pinta como subtotal mientras `GOP` —del
    #: mismo tipo— se pinta como total. Es dato de la fila, igual que la
    #: sangría, y por la misma razón: el formato es parte de lo que SCP espera.
    estilo: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ReportLine f{self.row_no} {self.report_code}>"


class ReportLineMapping(Base):
    """`Línea P&L` → fila del reporte.

    El UNIQUE sobre (report_key, linea_pl) NO es decorativo: sin él una línea
    duplicada se suma en dos filas distintas y el reporte cuadra igual contra
    sí mismo, porque el subtotal de arriba la cuenta dos veces. Es un error
    que no se ve.
    """
    __tablename__ = "report_line_mapping"
    __table_args__ = (
        UniqueConstraint("report_key", "linea_pl", name="uq_report_line_mapping"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    report_key: Mapped[str] = mapped_column(String(40), index=True)
    linea_pl: Mapped[str] = mapped_column(String(60))
    report_code: Mapped[str] = mapped_column(String(60))
    nota: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ReportLineMapping {self.linea_pl}->{self.report_code}>"


class Capacidad(Base):
    """Habitaciones disponibles por entidad × año × mes.

    Vive en tabla y no como constante aunque hoy sea 30 fijo en todo 2025–2026:
    Villas (0115) y Residencias (0116) pueden moverlo, y el día que entre otra
    propiedad su capacidad es otra. `rooms_available = días del mes × esto`.

    ⚠️ El KPI interno del P&L usa 33 habitaciones (`scenario_stats`); SCP usa
    30. No son el mismo número y no se deben cruzar: 900 vs 990 en junio.
    """
    __tablename__ = "capacidad"
    __table_args__ = (
        UniqueConstraint("entidad", "anio", "mes", name="uq_capacidad"),
        CheckConstraint("habitaciones_disponibles > 0", name="ck_capacidad_positiva"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    entidad: Mapped[str] = mapped_column(String(20), index=True)
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    habitaciones_disponibles: Mapped[int] = mapped_column(Integer, default=30)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Capacidad {self.entidad} {self.anio}-{self.mes:02d} {self.habitaciones_disponibles}>"


class ReportSnapshot(Base):
    """Lo que se le MANDÓ a SCP, congelado.

    Enllavar un escenario no congela un reporte: todo reporte de FinPlan
    recomputa con el motor de hoy. Si el mapeo cambia —y D9 lo cambia— un
    período ya enviado devolvería números distintos al reejecutarse. Este
    snapshot es la única prueba de qué se mandó.

    Nunca se sobreescribe en silencio: si el recálculo en vivo difiere, el tab
    muestra "recalculado" con el delta por fila y el snapshot queda intacto.
    """
    __tablename__ = "report_snapshots"
    __table_args__ = (
        UniqueConstraint("report_key", "entidad", "anio", "mes", "version",
                         name="uq_report_snapshot"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True,
                                    default=lambda: str(uuid.uuid4()))
    report_key: Mapped[str] = mapped_column(String(40), index=True)
    entidad: Mapped[str] = mapped_column(String(20), index=True)
    anio: Mapped[int] = mapped_column(Integer)
    mes: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)

    enviado_el: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    #: `raw` o `favorable` — con cuál se generó lo que se envió.
    convencion: Mapped[str] = mapped_column(String(12), default="favorable")
    #: Período de vigencia del mapeo con el que se calculó, `YYYY-MM`.
    mapping_version: Mapped[str] = mapped_column(String(7), default="")
    #: Los 48×32 congelados: {report_code: {columna: valor|None}}.
    valores: Mapped[dict] = mapped_column(JSON, default=dict)
    nota: Mapped[str] = mapped_column(Text, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ReportSnapshot {self.report_key} {self.entidad} {self.anio}-{self.mes:02d} v{self.version}>"
