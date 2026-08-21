from sqlalchemy import String, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from app.db import Base


class Account(Base):
    __tablename__ = "accounts"

    # Código completo de 7 segmentos: '4000-0110-001-001-001-01-01'
    code_full: Mapped[str] = mapped_column(String(60), primary_key=True)

    # Segmentos individuales
    seg1: Mapped[str] = mapped_column(String(10), index=True)   # clase USALI (4000, 6000, etc.)
    seg2: Mapped[str] = mapped_column(String(10), index=True)   # departamento (0110, 0120, etc.)
    seg3: Mapped[str] = mapped_column(String(10))
    seg4: Mapped[str] = mapped_column(String(10))
    seg5: Mapped[str] = mapped_column(String(10))
    seg6: Mapped[str] = mapped_column(String(10))
    seg7: Mapped[str] = mapped_column(String(10))

    descripcion: Mapped[str] = mapped_column(String(300))
    tipo: Mapped[str] = mapped_column(String(1), index=True)    # 'I' | 'G' | 'T'
    estado: Mapped[str] = mapped_column(String(1))              # 'A' | 'I'
    acepta_mov: Mapped[bool] = mapped_column(Boolean, default=False)
    usa_cc: Mapped[bool] = mapped_column(Boolean, default=False)
    aplica_diferencial: Mapped[bool] = mapped_column(Boolean, default=False)
    link_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:
        return f"<Account {self.code_full} [{self.tipo}] {self.descripcion[:40]}>"
