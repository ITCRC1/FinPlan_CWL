# -*- coding: utf-8 -*-
"""Estadísticas con dimensiones: una fila por cuenta × mes × apertura.

**Qué problema resuelve.** `scenario_stats` tiene **cinco columnas fijas** por
escenario × mes. Cada estadística nueva costaba una migración y ~20 lugares que
tocar; el precedente son los socios del Club Madresal — cuatro números por mes
que necesitaron tabla propia, modelo propio, API propia, router, dataset de
copia y prueba. Y el owner pidió (2026-08-14) subirlas **por departamento y por
posición**, más canal, país y market code. Eso no cabe en columnas fijas: cabe
en dimensiones.

**Las dimensiones vacías son cadena vacía, NUNCA NULL.** En Postgres dos NULL no
son iguales entre sí, así que una restricción de unicidad con columnas nulables
**deja pasar duplicados**: se cargaría el mismo dato dos veces y el total
saldría doble sin que nada avise. Es exactamente la familia de error que este
proyecto viene persiguiendo. Por eso todas las dimensiones tienen `default=""`
y `nullable=False`, y hay una prueba que lo vigila.

**Qué dimensión lleva cada cuenta lo decide el catálogo**, no quien carga: ver
`StatAccount.dims`. Una cuenta de kilos con un código de canal adentro es un
error de digitación, y la carga lo rechaza en vez de guardarlo.
"""
import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StatisticalEntry(Base):
    __tablename__ = "statistical_entries"
    __table_args__ = (
        # La llave completa incluye TODAS las dimensiones. Con cadena vacía en
        # vez de NULL, esta restricción de verdad impide el duplicado.
        UniqueConstraint(
            "scenario_id", "account_code", "month", "dept_code", "position_code",
            "room_type_code", "dim_type", "dim_code", name="uq_statistical_entry",
        ),
        Index("ix_stat_entry_scen_acct", "scenario_id", "account_code"),
        Index("ix_stat_entry_scen_mes", "scenario_id", "month"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    account_code: Mapped[str] = mapped_column(
        String(10), ForeignKey("stat_accounts.code"), index=True
    )
    month: Mapped[int] = mapped_column(Integer)   # 1-12

    # ── Dimensiones ───────────────────────────────────────────────────────────
    # Departamento y posición son de primera clase porque son la espina de todo
    # reporte de este sistema, y son las dos que el owner nombró.
    dept_code: Mapped[str] = mapped_column(String(10), default="", index=True)
    position_code: Mapped[str] = mapped_column(String(24), default="", index=True)

    # El tipo de habitación va por CÓDIGO FIJO (BL01, BI02…), no por nombre.
    # `actual_room_stats` lo ata por nombre y por eso renombrar un tipo le
    # desconecta el histórico; acá no se repite ese error.
    room_type_code: Mapped[str] = mapped_column(String(10), default="")

    # El resto de dimensiones —canal, país, segmento de mercado, punto de venta—
    # entran por este par en vez de una columna cada una. Cuál aplica lo declara
    # la cuenta en `StatAccount.dims`.
    dim_type: Mapped[str] = mapped_column(String(12), default="")
    dim_code: Mapped[str] = mapped_column(String(48), default="")

    value: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    # De dónde vino: 'GL' (detalle del mayor), 'ARCHIVO' (la carga de
    # estadísticas), 'MANUAL' (digitado en pantalla), 'MOTOR' (lo calculó el
    # sistema). Sirve para saber qué se puede pisar al recargar y qué no.
    origen: Mapped[str] = mapped_column(String(10), default="ARCHIVO")

    def __repr__(self) -> str:
        ap = "/".join(x for x in (self.dept_code, self.position_code,
                                  self.room_type_code, self.dim_code) if x)
        return f"<StatisticalEntry {self.account_code} m{self.month} {ap}={self.value}>"
