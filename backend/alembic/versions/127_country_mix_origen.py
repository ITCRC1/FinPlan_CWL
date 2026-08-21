# -*- coding: utf-8 -*-
"""De dónde vino cada mes del Country Mix, y cuándo.

**La regla (owner, 2026-08-18).** «Este archivo se sube una única vez para el
mes, y después se baja y se edita. Entonces un mismo mes no debería subirse más
de 2 veces.»

O sea: el XML de Opera escribe el mes UNA vez; la plantilla corregida lo
escribe una segunda. Un tercer paso del XML sobre ese mes **borraría la
corrección**, y hasta ahora lo hacía en silencio — `import_country_xml` hace
`delete` de los meses del archivo y vuelve a insertar, sin mirar qué había.

Sin saber de dónde vino cada mes no hay forma de distinguir «lo estás cargando
por primera vez» de «estás por pisar lo que corregiste a mano». Estas dos
columnas son lo que permite avisarlo:

- `origen`: `'xml'` (vino del importador) o `'manual'` (plantilla o grilla).
- `actualizado_en`: para poder decir *cuándo* se cargó, no solo que ya existe.

Las filas que ya estaban quedan como `'xml'`: es de donde vinieron.
"""
import sqlalchemy as sa
from alembic import op

revision = "127"
down_revision = "126"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("country_mix_entries", sa.Column(
        "origen", sa.String(10), nullable=False, server_default="xml"))
    op.add_column("country_mix_entries", sa.Column(
        "actualizado_en", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("country_mix_entries", "actualizado_en")
    op.drop_column("country_mix_entries", "origen")
