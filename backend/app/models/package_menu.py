import uuid
from decimal import Decimal
from sqlalchemy import String, Numeric, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class PkgExperience(Base):
    """Una experiencia/paquete con nombre + noches/días (ej. Classic 3N/4D)."""
    __tablename__ = "pkg_experiences"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True)
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)
    name: Mapped[str] = mapped_column(String(120))
    nights: Mapped[int] = mapped_column(Integer, default=0)
    days: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # ¿Es la experiencia que alimenta el tab «Package Component Rack and Net
    # Rate»? Antes se buscaba la que tuviera «classic» EN EL NOMBRE: renombrarla
    # —o borrarla— hacía que ese tab pasara a mostrar otra sin avisar. Es una
    # marca explícita, así el nombre vuelve a ser solo una etiqueta.
    es_base: Mapped[bool] = mapped_column(Boolean, default=False)


class PkgExperienceItem(Base):
    """Una inclusión (fila) de una experiencia. Tabla informativa estilo Excel."""
    __tablename__ = "pkg_experience_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experience_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pkg_experiences.id", ondelete="CASCADE"), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    inclusion: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(30), default="")          # per pax/night, per pax/stay...
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)        # 0/1
    notes: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(20), default="")       # Basic / Add-On
    qty_mult_single: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("1"))
    qty_mult_double: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=Decimal("1"))
    info: Mapped[str] = mapped_column(String(120), default="")          # Base qty = pax*nights ...


# Inclusiones base del Classic Experience Package (tal cual el Excel del usuario)
_D = Decimal
CLASSIC_ITEMS = [
    {"inclusion": "Lodging", "unit": "per room/night", "unit_price": None, "enabled": True,
     "notes": "", "category": "", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": ""},
    {"inclusion": "Full Pension (Meals)", "unit": "per pax/night", "unit_price": _D("126"), "enabled": True,
     "notes": "", "category": "Basic", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax*nights"},
    {"inclusion": "Sustainability Fee", "unit": "per pax/night", "unit_price": _D("0"), "enabled": True,
     "notes": "Per pax per night", "category": "Basic", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax*nights"},
    {"inclusion": "Transport Sierpe/Drake <-> CWL", "unit": "per pax/stay", "unit_price": _D("150"), "enabled": True,
     "notes": "", "category": "Basic", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax"},
    {"inclusion": "Natural juices / coffee / tea", "unit": "per pax/day", "unit_price": _D("0"), "enabled": False,
     "notes": "Lunch & dinner", "category": "Add-On", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax"},
    {"inclusion": "Tour San Pedrillo", "unit": "per pax/stay", "unit_price": _D("168"), "enabled": True,
     "notes": "", "category": "Add-On", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax"},
    {"inclusion": "Tour a Cano", "unit": "per pax/stay", "unit_price": _D("174"), "enabled": True,
     "notes": "Add tour cost per pax", "category": "Add-On", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax"},
]

# VIP = las mismas inclusiones del Classic + extras VIP (enabled en blanco en el Excel → False)
VIP_EXTRA_ITEMS = [
    {"inclusion": "Cena Privada (setting especial y un menu especial)", "unit": "per pax/dinner",
     "unit_price": _D("50"), "enabled": False, "notes": "", "category": "",
     "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": ""},
    {"inclusion": "Claro del Bosque Experience", "unit": "per pax/excursion",
     "unit_price": _D("60"), "enabled": False, "notes": "", "category": "",
     "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": ""},
    {"inclusion": "Welcome gift (1 iman por habitacion????)", "unit": "per pax",
     "unit_price": _D("2"), "enabled": False, "notes": "", "category": "",
     "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": ""},
]
VIP_ITEMS = CLASSIC_ITEMS + VIP_EXTRA_ITEMS

# Grupo NH 2027 — Inclusions Master (3 Nights | Pre-Tax). Categoría nueva: Optional.
GRUPO_NH_ITEMS = [
    {"inclusion": "Full Pension (Meals)", "unit": "per pax/night", "unit_price": _D("126"), "enabled": True,
     "notes": "", "category": "Basic", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax*nights"},
    {"inclusion": "Sustainability Fee", "unit": "per pax/night", "unit_price": _D("0"), "enabled": True,
     "notes": "Per pax per night", "category": "Basic", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax*nights"},
    {"inclusion": "Transport Sierpe/Drake <-> CWL", "unit": "per pax/stay", "unit_price": _D("150"), "enabled": True,
     "notes": "", "category": "Basic", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax"},
    {"inclusion": "Natural juices / coffee / tea", "unit": "per pax/stay", "unit_price": _D("0"), "enabled": False,
     "notes": "Lunch & dinner", "category": "Add-On", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax"},
    {"inclusion": "Tour San Pedrillo", "unit": "per pax/stay", "unit_price": _D("168"), "enabled": True,
     "notes": "", "category": "Add-On", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax"},
    {"inclusion": "Preferred seating meals", "unit": "flat/group", "unit_price": _D("0"), "enabled": False,
     "notes": "", "category": "Add-On", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = 1"},
    {"inclusion": "Cooler for San Pedrillo", "unit": "per pax/stay", "unit_price": _D("0"), "enabled": False,
     "notes": "1 per pax", "category": "Add-On", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax"},
    {"inclusion": "Sundowner @ Inspiration Point", "unit": "flat/group", "unit_price": _D("0"), "enabled": False,
     "notes": "Drinks excluded", "category": "Add-On", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = 1"},
    {"inclusion": "Extra guide for PCN walks", "unit": "flat/group", "unit_price": _D("0"), "enabled": False,
     "notes": "", "category": "Add-On", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = 1"},
    {"inclusion": "Tour a Cano", "unit": "per pax/stay", "unit_price": _D("174"), "enabled": True,
     "notes": "Add tour cost per pax", "category": "Add-On", "qty_mult_single": _D("1"), "qty_mult_double": _D("1"), "info": "Base qty = pax"},
    {"inclusion": "Optional extra boat (Pargo arriba/abajo)", "unit": "flat/service", "unit_price": _D("0"), "enabled": False,
     "notes": "Taxes excluded", "category": "Optional", "qty_mult_single": _D("0"), "qty_mult_double": _D("0"), "info": "Base qty = 1; set mult=1 when used"},
]

CWL_DEFAULT_EXPERIENCES = [
    {"name": "Classic Experience Package", "nights": 3, "days": 4, "items": CLASSIC_ITEMS},
    {"name": "VIP Experience Package", "nights": 4, "days": 5, "items": VIP_ITEMS},
    {"name": "Grupo NH 2027 - Inclusions Master (Pre-Tax)", "nights": 3, "days": 4, "items": GRUPO_NH_ITEMS},
]
