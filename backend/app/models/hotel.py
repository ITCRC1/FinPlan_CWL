from decimal import Decimal
from sqlalchemy import String, Integer, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


class Hotel(Base):
    __tablename__ = "hotels"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)   # 'CWL'
    name: Mapped[str] = mapped_column(String(100))
    short_name: Mapped[str] = mapped_column(String(20))
    rooms: Mapped[int] = mapped_column(Integer)                      # 30
    tc_usd_default: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("530.0000"))
    # Meses cerrados (no opera) — 1-based, separados por coma. CWL cierra octubre.
    # Las noches disponibles de un mes cerrado = 0 (lo aplica la fórmula que lee esto).
    closed_months: Mapped[str] = mapped_column(String(40), default="")
    # Pax por noche ocupada (factor para huéspedes). Editable.
    pax_per_night: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("1.8"))
    # Idioma con el que abre la app en esta propiedad. Se fija al provisionar.
    # El usuario puede pisarlo con su preferencia (users.locale). Ver app/i18n.py.
    default_locale: Mapped[str] = mapped_column(String(5), default="es", server_default="es")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def closed_months_list(self) -> list[int]:
        return [int(m) for m in self.closed_months.split(",") if m.strip().isdigit()]

    scenarios: Mapped[list["Scenario"]] = relationship("Scenario", back_populates="hotel")
    room_types: Mapped[list["RoomTypeConfig"]] = relationship("RoomTypeConfig", back_populates="hotel")

    def __repr__(self) -> str:
        return f"<Hotel {self.id} — {self.name}>"
