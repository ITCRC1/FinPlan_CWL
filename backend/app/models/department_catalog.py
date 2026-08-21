from sqlalchemy import String, Integer, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class DepartmentCatalog(Base):
    """
    Canonical, GROUP-WIDE department universe — the single source of truth that
    replaces the 3 drifting sources today (pl_engine constants, gl_detail_importer
    name-map, frontend cwl-depts.ts).

    NO hotel_id: this is the shared universe for the whole hotel group. Which
    departments a given property uses is decided by the per-property enablement
    matrix (dept_enablement), NOT by forking this catalog. (See
    docs/PROVISIONING_MASTER_DATA_PLAN.md / MULTIPROPERTY_PLAN.md.)

    Seeded byte-for-byte from the (corrected) pl_engine constants so the future
    engine refactor — making pl_engine read this table instead of its module
    constants — is behavior-preserving.
    """
    __tablename__ = "department_catalog"

    dept_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    dept_name: Mapped[str] = mapped_column(String(100), default="")   # canonical display (ES)
    name_en: Mapped[str] = mapped_column(String(100), default="")
    # gl name keywords (absorbs gl_detail_importer.dept_code_from_name)
    name_aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    usali_class: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 4/6/7
    # P&L group key (== pl_engine GROUP keys: ROOMS/FB/SPA/.../AREC/ADMIN/...).
    # Empty for account-based revenue depts (e.g. 280 Miscelaneos splits by account).
    default_pl_group: Mapped[str] = mapped_column(String(30), default="")
    pl_kind: Mapped[str] = mapped_column(String(12), default="OPERATING")     # OPERATING | OVERHEAD
    is_revenue_dept: Mapped[bool] = mapped_column(Boolean, default=False)
    is_allocation_source: Mapped[bool] = mapped_column(Boolean, default=False)  # 0220, 0161
    # SET de categorías de habitación (Rooms, Villas, Residencias). Distingue los
    # conjuntos de PRODUCTO de los hijos que son FUNCIONES (Front Desk,
    # Housekeeping): a esos no se les asigna una categoría.
    room_set: Mapped[bool] = mapped_column(Boolean, default=False)
    # sub-dept consolidation parent (replaces CHECKBOOK_DEPT_CONSOLIDATION),
    # applied on the checkbook build path only, never to imported actuals.
    parent_dept_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<Dept {self.dept_code} {self.default_pl_group}/{self.pl_kind}>"
