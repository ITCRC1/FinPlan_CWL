"""Planilla: Categoria y SubCategoria de cada posición.

Owner, 2026-11-22: «necesito categorizar cada posición o por departamento entre
Operations and Non Operation… cuando yo bajo el Excel necesito tener la posibilidad
de filtrar por estos conceptos» · con el archivo de RRHH: «revisa la columna C y D»
→ las dos, tal cual: Categoria (Operaciones | Administrativo | Gerencial) y
SubCategoria (On Property | Outside).

Solo agrega dos columnas que nacen vacías. Vacía quiere decir «la del departamento»
(`categoria_de` / `subcategoria_de` en `app/models/payroll_position.py`), así que no
hay que llenar nada y no se toca ningún dato existente.

Revision ID: 165
Revises: 164
"""
import sqlalchemy as sa
from alembic import op

revision = "165"
down_revision = "164"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payroll_positions", sa.Column("categoria", sa.String(20), nullable=True))
    op.add_column("payroll_positions", sa.Column("subcategoria", sa.String(20), nullable=True))


def downgrade():
    op.drop_column("payroll_positions", "subcategoria")
    op.drop_column("payroll_positions", "categoria")
