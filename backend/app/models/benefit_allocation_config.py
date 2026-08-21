# -*- coding: utf-8 -*-
"""Reparto de beneficios: cómo se llena cada cuenta 60xx de beneficio.

Un solo mecanismo para lo que antes eran tres caminos distintos (el reparto de
cafetería en Allocations, el driver de per diem en la planilla y el reparto del
INS). Cada fila declara de dónde sale la plata, cómo se reparte y a qué nivel.

    cuenta   6022 INS · 6025 cafetería · 6028 vivienda · 6029 transporte · 6030 otros
    origen   MONTO = un monto anual en colones que da el usuario
             DEPTO = el costo de un departamento, que queda en cero al repartirse
    base     FTE = por peso de plaza · HEADCOUNT = por cabeza
    nivel    POSICION = entra a la planilla, fila por fila
             DEPTO    = entra como allocation, un renglón por departamento

Ejemplos reales de Corcovado:
    {6022, MONTO 8,600,000, FTE, POSICION}  — la póliza del INS repartida
    {6025, DEPTO 0220,      FTE, DEPTO}     — la cafetería, como funciona hoy
"""
import uuid
from decimal import Decimal

from sqlalchemy import String, Numeric, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

ORIGENES = ("MONTO", "DEPTO")
BASES = ("FTE", "HEADCOUNT")
NIVELES = ("POSITION", "DEPT")

# Cuentas de beneficio que se pueden repartir. NO se listan las que entran a la
# BASE de la CCSS (6001/6002/6003/6010/6024/6027): esas cotizan y no son un
# reparto de un pote, son salario.
CUENTAS_BENEFICIO = {
    "6004": "Incapacidades",
    "6022": "Riesgos del trabajo (INS)",
    "6023": "Provisión de vacaciones",
    "6025": "Cafetería",
    "6026": "Cesantía",
    "6028": "Vivienda",
    "6029": "Transporte",
    "6030": "Otros beneficios",
}


class BenefitAllocationConfig(Base):
    __tablename__ = "benefit_allocation_config"
    __table_args__ = (
        UniqueConstraint("scenario_id", "account", name="uq_benefit_alloc_cuenta"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    account: Mapped[str] = mapped_column(String(10))
    label: Mapped[str] = mapped_column(String(80), default="")
    source_type: Mapped[str] = mapped_column(String(10), default="MONTO")
    source_dept: Mapped[str] = mapped_column(String(10), default="")
    amount_crc: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0"))
    basis: Mapped[str] = mapped_column(String(12), default="FTE")
    level: Mapped[str] = mapped_column(String(10), default="POSITION")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def columna(self) -> str:
        """Nombre de la columna del concepto en PayrollConceptEntry."""
        sufijo = {
            "6004": "c6004_disabilities", "6022": "c6022_occ_hazard",
            "6023": "c6023_vacation_prov", "6025": "c6025_cafeteria",
            "6026": "c6026_severance", "6028": "c6028_housing",
            "6029": "c6029_transport", "6030": "c6030_other",
        }
        return sufijo.get(self.account, "")

    def __repr__(self) -> str:
        return (f"<BenefitAlloc {self.account} {self.source_type} "
                f"{self.basis} {self.level}>")
