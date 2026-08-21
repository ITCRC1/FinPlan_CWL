import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

# Las cinco dimensiones financieras en las que un departamento puede estar
# activo o no. Es un ENUM y no cinco booleanos en la fila del departamento
# porque las cinco NO comparten llave: planilla/opex/costo se llevan por
# `dept_code`, el ingreso por grupo de P&L, y los gastos de propiedad son
# líneas below-GOP que no tienen departamento. Agregar una sexta (CAPEX) es un
# valor más, no una migración de esquema.
DIMENSIONES = ["REVENUE", "PAYROLL", "OPEX", "COST", "PROPERTY"]

# Qué se está prendiendo o apagando: un departamento, una línea de ingreso o
# una línea de gastos de propiedad.
SCOPE_KINDS = ["DEPT", "REV_LINE", "BELOWGOP_LINE"]


class DeptEnablement(Base):
    """Qué departamentos usa CADA propiedad, por dimensión. Se fija en el
    provisionamiento: la propiedad arranca con el estándar completo y se
    DESMARCA lo que no aplica.

    La tabla es ESPARSA y el default es PRENDIDO: no tener fila significa
    «activo». Por eso el día que esto se despliega no cambia nada en ninguna
    propiedad — solo existen las filas de lo que alguien apagó a mano.

    ⚠️ **Esto filtra la VISIBILIDAD, nunca el cálculo.** Un departamento
    apagado desaparece de los selectores y de las pantallas de carga, pero si
    tiene datos cargados esos datos SIGUEN sumando en el P&L. Es a propósito:
    si apagar un departamento borrara plata del estado de resultados, esconder
    algo sería una forma de cambiar los números sin dejar rastro. La pantalla
    de provisionamiento avisa cuánto dato tiene cada casilla antes de dejar
    apagarla.

    El catálogo (`department_catalog`) NO se bifurca por hotel: el universo
    USALI es uno solo para el grupo. Lo que cambia entre propiedades es esta
    matriz.
    """
    __tablename__ = "dept_enablement"
    __table_args__ = (
        UniqueConstraint("hotel_id", "scope_kind", "scope_key", "dimension",
                         name="uq_dept_enablement"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    scope_kind: Mapped[str] = mapped_column(String(20), default="DEPT")
    scope_key: Mapped[str] = mapped_column(String(40))     # dept_code o line_code
    dimension: Mapped[str] = mapped_column(String(12))     # una de DIMENSIONES
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(120), default="")

    def __repr__(self) -> str:
        estado = "ON" if self.enabled else "OFF"
        return f"<DeptEnab {self.hotel_id} {self.scope_key}/{self.dimension} {estado}>"
