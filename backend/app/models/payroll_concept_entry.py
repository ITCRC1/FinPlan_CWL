import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class PayrollConceptEntry(Base):
    """
    17 conceptos de planilla por posición × mes × escenario.

    Automáticos (recalculated on recalculate_scenario):
      c6000_sw       = salary × FTE / TC  (CRC) or salary × FTE (USD)
      c6020_ccss     = BASE × 26.83%
      c6021_aguinaldo = BASE / 12

    BASE = c6000 + c6001 + c6002 + c6003 + c6010 + c6024 + c6027

    Manuales: todos los demás (6001–6004, 6010, 6022–6030 excepto 6020/6021).
    Los manuales sobreviven el recálculo — nunca son sobreescritos.
    """
    __tablename__ = "payroll_concept_entries"
    __table_args__ = (
        UniqueConstraint(
            "scenario_id", "position_id", "month",
            name="uq_payroll_concept_entry",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    position_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payroll_positions.id", ondelete="CASCADE"), index=True
    )
    dept_code: Mapped[str] = mapped_column(String(10), index=True)
    month: Mapped[int] = mapped_column(Integer)   # 1–12
    year: Mapped[int] = mapped_column(Integer)

    # ── GRUPO BASE (7 conceptos) ────────────────────────────────────────────
    c6000_sw: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))          # AUTO
    c6001_overtime: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))    # manual
    c6002_day_off: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))     # manual
    c6003_working_holiday: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))  # manual
    c6010_commissions: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0")) # manual
    c6024_vacations_taken: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))  # manual
    c6027_incentive_bonus: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))  # manual

    # ── AUTOMÁTICOS (calculados desde BASE, no editables por el usuario) ────
    c6020_ccss: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))        # AUTO
    c6021_aguinaldo: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))   # AUTO

    # ── MANUALES (ingreso directo del usuario) ──────────────────────────────
    c6004_disabilities: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    c6022_occ_hazard: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    c6023_vacation_prov: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    c6025_cafeteria: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    c6026_severance: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    c6028_housing: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    c6029_transport: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    c6030_other: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))

    def __repr__(self) -> str:
        return f"<PayrollConceptEntry pos={self.position_id[:8]} m={self.month}>"
