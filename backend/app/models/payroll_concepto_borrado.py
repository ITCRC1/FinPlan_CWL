"""Registro de cada borrado de conceptos de planilla (quién, cuándo, qué cuenta, cuánto).

Owner, 2026-11-27: las horas extra (6001) del Budget 2027 Working no estaban y nadie
sabía por qué. Los conceptos digitados (6001 horas extra, 6010 comisiones, 6024,
6026–6030…) se perdían sin dejar rastro al reemplazar la planilla desde Excel o al
poner una tasa en 0. Desde ahora cada borrado deja una fila aquí.

`scenario_id` no lleva llave foránea a propósito: si el escenario se borra, el
registro de lo que pasó con él se queda.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PayrollConceptoBorrado(Base):
    __tablename__ = "payroll_conceptos_borrados"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(String(36), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True, default="")
    cuando: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    quien: Mapped[str] = mapped_column(String(160), default="")
    #: parametro_en_cero · excel_sin_posicion · bulk_sin_posicion · codificacion_sin_posicion · posicion_borrada
    origen: Mapped[str] = mapped_column(String(40))
    cuenta: Mapped[str] = mapped_column(String(8))
    concepto: Mapped[str] = mapped_column(String(40))
    dept_code: Mapped[str] = mapped_column(String(10), default="")
    position_code: Mapped[str] = mapped_column(String(40), default="")
    meses: Mapped[int] = mapped_column(Integer, default=0)
    monto: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"))
    detalle: Mapped[str] = mapped_column(String(400), default="")
