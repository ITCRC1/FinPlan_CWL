import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

# ⚠️ `guillermo_approver` NO hereda los endpoints de admin: `get_current_admin`
# sigue comparando contra "admin" a secas. Aprobar excepciones de Guillermo usa
# su propia dependencia, `get_guillermo_approver`. Ver `docs/GUILLERMO.md` §7.
ROLES = ("admin", "collaborator", "guillermo_approver")


class User(Base):
    """Usuario de la app (Fase 0 — auth). role: admin (coordinador) | collaborator."""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="collaborator")
    # Preferencia de idioma. NULL = «usá el del hotel», que NO es lo mismo que
    # «elegí español»: sin esa distinción, cambiar el default de la propiedad no
    # le llegaría a nadie que ya tuviera un valor guardado. Ver app/i18n.py.
    locale: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # Paleta visual. Misma regla que `locale`: NULL = «usá el default», que no
    # es lo mismo que «elegí Lino». Pero a diferencia del idioma esto es de la
    # PERSONA y no del tenant: el idioma en que opera una propiedad no es
    # preferencia de nadie; el fondo que cansa la vista sí. Ver mig. 129.
    tema: Mapped[str | None] = mapped_column(String(16), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"
