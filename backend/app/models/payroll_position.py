import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import Boolean, String, Numeric, Integer, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base

_FTE_ATTRS = [
    "fte_jan", "fte_feb", "fte_mar", "fte_apr", "fte_may", "fte_jun",
    "fte_jul", "fte_aug", "fte_sep", "fte_oct", "fte_nov", "fte_dec",
]


class PayrollPosition(Base):
    """
    Posición de planilla presupuestada por escenario.

    SW_mes = salary_amount × FTE_mes / TC_mes   (cuando salary_currency == 'CRC')
    SW_mes = salary_amount × FTE_mes             (cuando salary_currency == 'USD')
    Si FTE = 0.00 → SW = 0 → sin costo ese mes (posición planificada pero no ocupada).
    """
    __tablename__ = "payroll_positions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), index=True
    )
    hotel_id: Mapped[str] = mapped_column(String(10), index=True)

    # Identification
    dept_code: Mapped[str] = mapped_column(String(10), index=True)    # '0150'
    dept_name: Mapped[str] = mapped_column(String(100), default="")   # 'TOUR ACTIVITIES'
    position_code: Mapped[str] = mapped_column(String(10), default="") # '604'
    position_name: Mapped[str] = mapped_column(String(200))           # 'CAPITAN DE BARCO'
    employee_name: Mapped[str] = mapped_column(String(200), default="VACANTE")
    employee_type: Mapped[str] = mapped_column(String(20), default="1-Permanente")
    class_code: Mapped[str] = mapped_column(String(10), default="013")    # 013=Line, 012=Supervisor
    category_code: Mapped[str] = mapped_column(String(10), default="015") # 015=Local Perm, 010=Expat

    # Categoria (Operaciones | Administrativo | Gerencial) y SubCategoria
    # (On Property | Outside), como el archivo de RRHH. Vacío = la del depto
    # (`categoria_de` / `subcategoria_de`, al final de este archivo).
    categoria: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    subcategoria: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Contract Labour (owner, 2026-11-22): «cuando se crea la posición debe haber
    # un check donde se indique que es contract labour». Su salario va a 6031 y
    # no genera cargas (ver `es_contrato`).
    contract_labour: Mapped[bool] = mapped_column(Boolean, default=False,
                                                  server_default="false")

    # Salary (full-time monthly)
    salary_amount: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal("0"))
    salary_currency: Mapped[str] = mapped_column(String(3), default="CRC")  # 'CRC' | 'USD'

    # FTE per month 0.00–1.00. October defaults to 0 for CWL 2026 but is not locked.
    fte_jan: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_feb: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_mar: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_apr: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_may: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_jun: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_jul: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_aug: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_sep: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_oct: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("0.0"))
    fte_nov: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))
    fte_dec: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=Decimal("1.0"))

    # Marca de cambio: el recálculo compara contra scenarios.last_recalc_at
    # para avisar que el P&L quedó atrás. Sin esto no había CONTRA QUÉ
    # comparar y el usuario editaba sin saber que el reporte no lo reflejaba.
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True)

    def __repr__(self) -> str:
        return f"<PayrollPosition {self.dept_code}/{self.position_code} {self.position_name[:30]}>"


# ── Categoria y SubCategoria de cada posición ─────────────────────────────────
# Owner, 2026-11-22: «necesito categorizar cada posición o por departamento entre
# Operations and Non Operation» y, con el archivo de RRHH en la mano («revisa la
# columna C y D»), que queden LAS DOS tal cual ese archivo:
#   Categoria    → Operaciones | Administrativo | Gerencial
#   SubCategoria → On Property | Outside
# Vacío en la base = la del departamento (abajo). Se guarda solo la excepción, así
# una posición nueva —del botón, del Excel o de una copia— nace bien sola.
OPERACIONES, ADMINISTRATIVO, GERENCIAL = "Operaciones", "Administrativo", "Gerencial"
ON_PROPERTY, OUTSIDE = "On Property", "Outside"
CATEGORIAS = (OPERACIONES, ADMINISTRATIVO, GERENCIAL)
SUBCATEGORIAS = (ON_PROPERTY, OUTSIDE)

# Lo que dice el archivo de RRHH (payroll al 20/11/2026) para cada departamento,
# por mayoría. Los que no están acá son Operaciones / On Property. 0112 y 0184 no
# vienen en el archivo: son de oficina, como Finanzas.
DEFECTO_POR_DEPTO: dict[str, tuple[str, str]] = {
    "0181": (GERENCIAL, OUTSIDE),          # Management
    "0112": (ADMINISTRATIVO, OUTSIDE),     # Reservations
    "0182": (ADMINISTRATIVO, OUTSIDE),     # Finance
    "0183": (ADMINISTRATIVO, OUTSIDE),     # Purchasing
    "0184": (ADMINISTRATIVO, OUTSIDE),     # Human Resources
    "0190": (ADMINISTRATIVO, OUTSIDE),     # Sales & Marketing
    "0191": (ADMINISTRATIVO, OUTSIDE),
    "0230": (ADMINISTRATIVO, OUTSIDE),     # Information System
}


def _llano(valor) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(valor or "")).encode("ascii", "ignore").decode()
    return " ".join(t.lower().replace("-", " ").replace("_", " ").split())


def normalizar_categoria(valor) -> Optional[str]:
    """Lo escrito a mano → la Categoria canónica, o None si viene vacío o no se entiende."""
    t = _llano(valor)
    if t.startswith(("oper", "ops")):
        return OPERACIONES
    if t.startswith(("admin",)):
        return ADMINISTRATIVO
    if t.startswith(("geren", "manag")):
        return GERENCIAL
    return None


def normalizar_subcategoria(valor) -> Optional[str]:
    t = _llano(valor)
    if t.startswith(("on prop", "onprop", "on site", "dentro", "en propiedad", "propiedad")):
        return ON_PROPERTY
    if t.startswith(("outside", "out", "fuera", "remot", "off")):
        return OUTSIDE
    return None


def defecto_del_depto(dept_code) -> tuple[str, str]:
    return DEFECTO_POR_DEPTO.get(str(dept_code or "").strip(), (OPERACIONES, ON_PROPERTY))


def categoria_de(position) -> str:
    """La Categoria que vale: la fijada en la posición, o la de su depto."""
    return (normalizar_categoria(getattr(position, "categoria", None))
            or defecto_del_depto(getattr(position, "dept_code", ""))[0])


def subcategoria_de(position) -> str:
    return (normalizar_subcategoria(getattr(position, "subcategoria", None))
            or defecto_del_depto(getattr(position, "dept_code", ""))[1])


def para_guardar(dept_code, categoria, subcategoria) -> tuple[Optional[str], Optional[str]]:
    """Lo que se guarda: None donde coincide con el depto (así sigue a su depto).
    El Excel trae SIEMPRE las dos escritas —salen llenas para que el filtro sirva—,
    y guardarlas tal cual congelaría la regla del depto en cada posición."""
    dc, ds = defecto_del_depto(dept_code)
    c, s = normalizar_categoria(categoria), normalizar_subcategoria(subcategoria)
    return (None if c in (None, dc) else c), (None if s in (None, ds) else s)


# ── Contract Labour (6031) ───────────────────────────────────────────────────
# Owner, 2026-11-22. Una posición marcada «Contract Labour» (el check) va a la
# cuenta 6031 y no genera cargas sociales ni beneficios. Es su propio campo, no el
# Tipo: un contrato puede ser permanente o temporal igual que cualquiera.
def es_contrato(position) -> bool:
    # `is True` y no `bool(...)`: un objeto de prueba (MagicMock) devuelve un
    # atributo «verdadero» para cualquier nombre y pasaría por contratista.
    return getattr(position, "contract_labour", False) is True


def a_bool(valor) -> bool:
    """Lo que venga del Excel o del front → bool. «Sí», «x», «1», True…"""
    if isinstance(valor, bool):
        return valor
    t = str(valor or "").strip().lower()
    return t in {"si", "sí", "s", "x", "1", "true", "yes", "y", "✓", "✔"}


def get_fte(position: PayrollPosition, month: int) -> Decimal:
    """Return FTE for month 1-12."""
    return getattr(position, _FTE_ATTRS[month - 1])
