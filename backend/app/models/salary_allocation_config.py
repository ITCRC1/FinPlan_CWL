import uuid
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, Boolean, JSON, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.hotel_actual import HOTEL_ID


class SalaryAllocationConfig(Base):
    """Regla de Salary Allocation: el salario de una posición de apoyo (depto
    fuente + position_code) se reasigna a fin de mes a las áreas que apoya.

    Una PORCIÓN (portion_pct) del salario de esa posición se reparte entre los
    `target_depts` proporcional al FTE de cada destino → DÉBITO a los destinos,
    CRÉDITO al depto fuente (netea $0). El gasto se reasigna, no se agrega.

    Se lleva UN renglón por destino: PROPERTY SUPPORT 0.34 FTE a tours 0150,
    0.33 a transporte 0152 y 0.33 a compras 0183, cada uno en su línea. Antes
    era un solo renglón con los tres destinos adentro y el reparto se hacía
    solo, proporcional al FTE de cada destino — imposible de auditar: el owner
    veía una línea y adentro un reparto que no eligió.

    Por eso ya NO hay llave única por (escenario, departamento, posición): esa
    llave era justamente la que obligaba a amontonar los destinos (mig 080). El
    endpoint que guarda borra y reinserta la lista completa, así que lo que
    queda en la base es siempre lo que el owner dejó en pantalla.
    """
    __tablename__ = "salary_allocation_config"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True, default=HOTEL_ID)
    source_dept: Mapped[str] = mapped_column(String(10))          # '0200' depto de apoyo (crédito)
    position_code: Mapped[str] = mapped_column(String(10))        # '598' PROPERTY HELPER
    position_name: Mapped[str] = mapped_column(String(200), default="")  # etiqueta legible
    portion_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("1"))  # % a reasignar
    cafeteria_pct: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0"))  # cafetería = % del salario
    salary_override: Mapped[list] = mapped_column(JSON, default=list)  # 12 valores: salario manual (si la planilla está en 0)
    dummy_monthly: Mapped[list] = mapped_column(JSON, default=list)  # 12 valores: ajuste manual ("dummy") por mes
    target_depts: Mapped[list] = mapped_column(JSON, default=list)  # ['0150','0152','0183'] destinos (débito)
    account: Mapped[str] = mapped_column(String(20), default="6000")  # cuenta de salario que se mueve
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Marca de cambio: el recálculo compara contra scenarios.last_recalc_at
    # para avisar que el P&L quedó atrás. Sin esto no había CONTRA QUÉ
    # comparar y el usuario editaba sin saber que el reporte no lo reflejaba.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    def __repr__(self) -> str:
        return f"<SalaryAlloc {self.source_dept}/{self.position_code} → {self.target_depts}>"
