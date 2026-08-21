import uuid
from sqlalchemy import String, Integer, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base


# Tipos de habitación de CWL — 30 unidades totales
CWL_ROOM_TYPES = [
    {"sort_order": 1, "name": "Corcovado Deluxe Villas, King bed",        "short_name": "Deluxe King",    "units": 6, "pax_min": 1, "pax_max": 2},
    {"sort_order": 2, "name": "Carate Deluxe Villa Double Beds",          "short_name": "Carate Double",  "units": 2, "pax_min": 2, "pax_max": 2},
    {"sort_order": 3, "name": "Agujas Villa 2 Queen Beds",                "short_name": "Agujas Queen",   "units": 4, "pax_min": 2, "pax_max": 4},
    {"sort_order": 4, "name": "Sirena Suites, Queen Bed (connecting)",    "short_name": "Sirena Suites",  "units": 8, "pax_min": 2, "pax_max": 4},
    {"sort_order": 5, "name": "Treehouse king bed",                       "short_name": "Treehouse",      "units": 5, "pax_min": 1, "pax_max": 2},
    {"sort_order": 6, "name": "5 Elements Treehouse king bed",            "short_name": "5 Elements",     "units": 5, "pax_min": 1, "pax_max": 2},
]


class RoomTypeConfig(Base):
    """
    Configuración de tipos de habitación por hotel.
    CWL: 6 tipos, 30 unidades totales.
    """
    __tablename__ = "room_type_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    hotel_id: Mapped[str] = mapped_column(String(10), ForeignKey("hotels.id"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer)
    # Código FIJO estable (RT01, RT02…) — liga todos los sistemas sin depender del
    # nombre. El nombre es solo etiqueta (cambia por hotel); el código NO cambia.
    code: Mapped[str] = mapped_column(String(20), default="")
    name: Mapped[str] = mapped_column(String(100))
    short_name: Mapped[str] = mapped_column(String(30))
    # Departamento al que pertenece este tipo. Vacío = se queda en Rooms (0110),
    # que es el comportamiento histórico. Se usa para repartir el costo de Rooms
    # entre sus hijos (Villas, Residencias) según las noches vendidas: sin este
    # vínculo el reparto no sabe qué noches son de cada uno.
    dept_code: Mapped[str] = mapped_column(String(10), default="")
    units: Mapped[int] = mapped_column(Integer)
    pax_min: Mapped[int] = mapped_column(Integer, default=1)
    pax_max: Mapped[int] = mapped_column(Integer, default=2)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    hotel: Mapped["Hotel"] = relationship("Hotel", back_populates="room_types")

    def __repr__(self) -> str:
        return f"<RoomType {self.short_name} ×{self.units}>"
