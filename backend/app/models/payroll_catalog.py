from sqlalchemy import String, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional
from app.db import Base


class PayrollAccount(Base):
    """
    Catálogo de cuentas de planilla (clase 6) con 7 niveles.
    Ejemplo: 6000-0111-500-011-015-00-00
             SW - FrontDesk - Manager - Directors - LocalPerm
    """
    __tablename__ = "payroll_accounts"

    code_full: Mapped[str] = mapped_column(String(60), primary_key=True)

    nivel1: Mapped[str] = mapped_column(String(10), index=True)   # 6000 → concepto (S&W, OT...)
    nivel2: Mapped[str] = mapped_column(String(10), index=True)   # 0111 → departamento
    nivel3: Mapped[str] = mapped_column(String(10))               # 500  → posición
    nivel4: Mapped[str] = mapped_column(String(10))               # 011  → clase empleado
    nivel5: Mapped[str] = mapped_column(String(10))               # 015  → categoría
    nivel6: Mapped[str] = mapped_column(String(10))
    nivel7: Mapped[str] = mapped_column(String(10))

    descripcion: Mapped[str] = mapped_column(String(300))
    tipo: Mapped[str] = mapped_column(String(1), default="G")
    acepta_mov: Mapped[bool] = mapped_column(Boolean, default=False)
    link_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Campos derivados para conveniencia
    concepto_nombre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    dept_nombre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    posicion_nombre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"<PayrollAccount {self.code_full} {self.descripcion[:40]}>"
