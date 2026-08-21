# -*- coding: utf-8 -*-
"""Modelo de datos del módulo Break-Even (punto de equilibrio).

Spec: `FINPLAN_BREAK_EVEN.md` §2. Cada decisión rara de acá está en el spec con
su motivo, y casi todas corresponden a un error que ya se cometió una vez.

## Lo que NO se negocia, y por qué

* **`pct_variable` es el único porcentaje que se guarda.** El fijo se deriva
  como `1 - pct_variable`. Guardar los dos permite que digan cosas distintas.
* **`dept_code` y `account` van vacíos, JAMÁS NULL.** El seed carga con
  `ON CONFLICT (property_id, dept_code, account, pl_line) DO NOTHING`, y en
  Postgres `NULL ≠ NULL`: con NULL, una segunda corrida duplicaría en silencio
  todas las filas `LINEA`.
* **El impuesto se excluye por la columna `excluded_from_be`**, no comparando
  texto contra `'INCOME TAX'`. Con texto, el día que alguien renombre la sección
  la exclusión deja de aplicar y el equilibrio de CWL salta $113k sin aviso.
* **Los departamentos son una TABLA, no un enum.** Hay 8 esperando activarse;
  como enum, cada propiedad nueva sería un release.
* **La llave es el `slug`, nunca el nombre.** Ocho nombres del origen traen
  doble espacio.

## Adaptación a FinPlan, y por qué

El spec habla de `property_id` como FK. En FinPlan la propiedad es `hotels.id`
(`'CWL'`), un `String(10)`, y **cada despliegue sirve una sola propiedad**
(`app.hotel_actual.HOTEL_ID`). Se respeta el modelo del spec —la columna existe y
todo se filtra por ella— porque es lo que permite que el día de mañana un
consolidado lea varias; pero el default sale de `HOTEL_ID`, así que hoy no hay
que pasarlo por todos lados.
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    String, Integer, Boolean, Numeric, DateTime, ForeignKey, JSON,
    UniqueConstraint, Index, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.hotel_actual import HOTEL_ID

#: Estados de `be_department.status`.
DEPT_ACTIVO = "active"
DEPT_PENDIENTE = "pending_classification"

#: Versiones de dato. NO hay default: ver `engine/break_even.py`.
DATA_VERSIONS = ("ACTUAL", "BUDGET", "FORECAST")


class BeDepartment(Base):
    """Catálogo de departamentos del break-even.

    Es una tabla y no una lista en el código a propósito (spec §2.1): CWL usa 14
    y hay 8 en `pending_classification` que otras propiedades van a necesitar.
    Activar uno tiene que ser un UPDATE, no un despliegue.
    """
    __tablename__ = "be_department"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    #: LA LLAVE. Estable, en minúscula y con guiones: `rooms`, `gift-shop`.
    #: Nunca el nombre — ocho nombres del origen traen doble espacio.
    slug: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(60), default="")
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    #: Si es `false`, no se le calcula % MC ni equilibrio propio: es un centro de
    #: costo no distribuido. La bandera vive acá y no en una lista del código
    #: para que la UI no tenga que saber cuáles son.
    generates_revenue: Mapped[bool] = mapped_column(Boolean, default=False)
    #: Códigos GL asociados, separados por coma: `'0110,0115,0116'`.
    dept_codes: Mapped[str] = mapped_column(String(60), default="")
    status: Mapped[str] = mapped_column(String(24), default=DEPT_ACTIVO)
    #: `NULL` = aplica a todas las propiedades. Es el gancho de multipropiedad.
    property_id: Mapped[str | None] = mapped_column(
        String(10), ForeignKey("hotels.id", ondelete="CASCADE"), nullable=True)

    def __repr__(self) -> str:
        return f"<BeDepartment {self.slug} [{self.status}]>"


class BeCostClassification(Base):
    """Una regla: qué porción de esta cuenta es variable. Es lo que el usuario edita.

    **No lleva monto**, y es deliberado (spec §8.1). En la v1 lo traía y sumaba
    $5.987.085 contra $4.198.042 reales, porque al expandir cada línea a sus
    cuentas GL hermanas el monto se repetía en cada fila. El monto es dato de
    PERIODO y vive en el P&L; la clasificación es atemporal.
    """
    __tablename__ = "be_cost_classification"
    __table_args__ = (
        # La llave del `ON CONFLICT` del seed. Funciona SOLO si `dept_code` y
        # `account` nunca son NULL — ver el docstring del módulo.
        UniqueConstraint("property_id", "dept_code", "account", "pl_line",
                         name="uq_be_classification"),
        # Resolución de respaldo: `(property_id, pl_line)` para las filas LINEA.
        Index("ix_be_class_pl_line", "property_id", "pl_line"),
        # La pantalla de configuración entra siempre por departamento.
        Index("ix_be_class_dept", "property_id", "be_department_id"),
        CheckConstraint("pct_variable >= 0 AND pct_variable <= 1",
                        name="ck_be_pct_variable"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("hotels.id", ondelete="CASCADE"),
        default=HOTEL_ID, index=True)
    be_department_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("be_department.id", ondelete="RESTRICT"), index=True)

    #: ⚠️ VACÍO, no NULL. Ver el docstring del módulo.
    dept_code: Mapped[str] = mapped_column(String(6), default="", server_default="")
    #: ⚠️ VACÍO, no NULL. Vacío en las filas `LINEA`.
    account: Mapped[str] = mapped_column(String(10), default="", server_default="")
    account_name: Mapped[str] = mapped_column(String(120), default="")
    #: La línea del reporte de FinPlan: `OPEX_ROOMS`, `COS_FB_FOOD`… Es el puente
    #: con el P&L, y por eso es NOT NULL.
    pl_line: Mapped[str] = mapped_column(String(40))
    section: Mapped[str] = mapped_column(String(40), default="")
    #: Sección del break-even: PAYROLL · COST OF SALES · OPERATING EXPENSES…
    be_section: Mapped[str] = mapped_column(String(40), default="")
    #: `Variable` | `Fixed Cost`. Referencia histórica: es de dónde salió la
    #: semilla, y lo que restaura el botón «Restablecer». No se usa en el cálculo.
    original_class: Mapped[str] = mapped_column(String(20), default="")

    #: EL ÚNICO EDITABLE. El fijo es `1 - pct_variable`, siempre derivado.
    pct_variable: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0"))

    #: `GL` (empata cuenta exacta) | `LINEA` (se resuelve por línea del P&L).
    #: La UI marca las `LINEA`: son asignaciones por sección, no cuentas reales.
    map_source: Mapped[str] = mapped_column(String(10), default="GL")

    #: El impuesto de renta. Sigue en la tabla para que el P&L cuadre, pero no
    #: entra al costo fijo: es función del resultado, no un costo.
    excluded_from_be: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false")

    #: De qué fila del Excel original salió la regla. Para auditar el origen.
    source_rows: Mapped[str] = mapped_column(String(120), default="")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def __repr__(self) -> str:
        clave = f"{self.dept_code}:{self.account}" if self.account else self.pl_line
        return f"<BeClass {clave} var={self.pct_variable}>"


class BeClassificationSnapshot(Base):
    """La foto de la clasificación al cerrar un periodo (spec §2.3).

    `pct_variable` no tiene dimensión de tiempo: sin esto, ajustar un porcentaje
    en noviembre **cambia retroactivamente** el punto de equilibrio de enero que
    ya se reportó. El reporte de un periodo cerrado se lee de acá, nunca de la
    tabla viva.

    En la Fase 1 la tabla existe y se escribe; leer desde ella es Fase 2 — es un
    gancho puesto a propósito, no una tabla muerta.
    """
    __tablename__ = "be_classification_snapshot"
    __table_args__ = (
        UniqueConstraint("property_id", "period", "data_version",
                         name="uq_be_snapshot"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id: Mapped[str] = mapped_column(
        String(10), ForeignKey("hotels.id", ondelete="CASCADE"),
        default=HOTEL_ID, index=True)
    #: `'2026-01'` para un mes, `'2026'` para el año.
    period: Mapped[str] = mapped_column(String(10))
    data_version: Mapped[str] = mapped_column(String(10))
    #: El juego COMPLETO de `pct_variable` al cierre, por clave de regla.
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    frozen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    frozen_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    def __repr__(self) -> str:
        return f"<BeSnapshot {self.period} {self.data_version}>"
