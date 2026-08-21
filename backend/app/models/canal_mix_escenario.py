# -*- coding: utf-8 -*-
"""La excepción: el mix de un escenario, y el de un mes dentro del escenario.

El mix base vive en `CanalComercial.mix_pct` y aplica a todo lo que nadie tocó —
es lo que hace que un escenario nuevo nazca con los parámetros correctos. Esta
tabla es para cuando ese base **no** es la verdad de un escenario concreto.

**`month = 0` es el valor anual del escenario.** 1..12 pisan un mes puntual.
La resolución cae en cascada:

    mes puntual  →  anual del escenario  →  base del canal

Se eligió así con el dato en la mano: en los 7 escenarios que hoy tienen canales
guardados, los 12 meses son idénticos. Pedir 7 canales × 12 meses serían 84
casillas para un dato que en la práctica no cambia. El caso normal se escribe una
vez; la excepción se declara.
"""
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

#: El `month` que significa «todo el año». No es un mes: es la ausencia de
#: excepción mensual.
ANUAL = 0


class CanalMixEscenario(Base):
    __tablename__ = "canal_mix_escenario"
    __table_args__ = (
        UniqueConstraint("scenario_id", "code", "month", name="uq_canal_mix_escenario"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    month: Mapped[int] = mapped_column(Integer, default=ANUAL)

    mix_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))
    comision_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), default=Decimal("0"))

    def __repr__(self) -> str:
        cuando = "anual" if self.month == ANUAL else f"mes {self.month}"
        return f"<CanalMixEscenario {self.code} {cuando} mix={float(self.mix_pct):.0%}>"
