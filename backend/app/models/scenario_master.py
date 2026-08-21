import uuid
from typing import Optional
from decimal import Decimal
from sqlalchemy import String, Numeric, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class ScenarioMaster(Base):
    """Master data **por escenario/año** que antes vivía a nivel hotel.

    Todo opcional: si una columna es NULL / vacía, el sistema cae al valor del
    hotel (= comportamiento actual, sin regresión). Permite que un año tenga, p.ej.,
    40 unidades y otro 29, o meses cerrados distintos.

    - `closed_months`: CSV "10,11" (meses que no opera) — fallback Hotel.closed_months
    - `pax_per_night`: factor pax/noche — fallback Hotel.pax_per_night
    - `units_json`: JSON {room_type_id: units} override por tipo — fallback RoomTypeConfig.units
    """
    __tablename__ = "scenario_master"
    __table_args__ = (
        UniqueConstraint("scenario_id", name="uq_scenario_master"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    closed_months: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    pax_per_night: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4), nullable=True)
    units_json: Mapped[str] = mapped_column(String(2000), default="")

    def __repr__(self) -> str:
        return f"<ScenarioMaster {self.scenario_id}>"
