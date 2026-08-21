import uuid
from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class ActualDeptFte(Base):
    """FTE REAL por departamento × mes, para cuando no hay `PayrollPosition`
    cargada al detalle (un Actual que solo trae el costo total del GL, sin
    planilla posición por posición, tiene FTE=0 aunque el costo sea real).

    Mismo patrón que `ActualRoomStat`: se sube/edita mes a mes y reemplaza
    SOLO ese mes, el resto queda intacto. Si existe una fila acá para
    (scenario, dept, month), **gana** sobre el FTE que saldría de sumar
    `PayrollPosition` — es la única fuente cuando esa carga no existe.
    """
    __tablename__ = "actual_dept_fte"
    __table_args__ = (
        UniqueConstraint("scenario_id", "dept_code", "month",
                         name="uq_deptfte_scenario_dept_month"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    dept_code: Mapped[str] = mapped_column(String(10))
    dept_name: Mapped[str] = mapped_column(String(100), default="")
    month: Mapped[int] = mapped_column(Integer)          # 1..12
    fte: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
