"""CRÍTICO — backfill account_mapping.dept_code desde source_department

El motor del P&L (pl_engine.calculate_pl_from_mapping) rutea por `dept_code`.
El cargador del mapeo solo guardaba `source_department` (el NOMBRE), dejando
`dept_code` en NULL. Con dept_code NULL toda cuenta que mapee a distinta línea
según el departamento colapsa en la línea del PRIMER departamento:

    $1,000 de planilla en Rooms, A&B, Spa, Tours y Admin
      → ANTES: $5,000 en OPEX_ROOMS, overhead $0   (GOP deformado)
      → AHORA: $1,000 en cada línea, Admin a OH_ADMIN

Afecta a las 17 cuentas de planilla (6000-6030, mapeadas a 16 líneas) y al opex
compartido. Idempotente: solo llena las filas que están en NULL/vacío.

Revision ID: 070
Revises: 069
Create Date: 2026-08-07
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "070"
down_revision: Union[str, None] = "069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.importers.gl_detail_importer import dept_code_from_name

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT DISTINCT source_department FROM account_mapping "
        "WHERE source_department IS NOT NULL AND source_department <> ''"
    )).fetchall()
    resolved = skipped = 0
    for r in rows:
        name = (r.source_department or "").strip()
        code = dept_code_from_name(name)
        if not code:
            skipped += 1
            continue
        conn.execute(
            sa.text("UPDATE account_mapping SET dept_code = :c "
                    "WHERE source_department = :n AND (dept_code IS NULL OR dept_code = '')"),
            {"c": code, "n": r.source_department},
        )
        resolved += 1
    print(f"[070] departamentos resueltos: {resolved} · sin resolver (no son depto): {skipped}")


def downgrade() -> None:
    # No se revierte: dejar dept_code en NULL reintroduce el misruteo.
    pass
