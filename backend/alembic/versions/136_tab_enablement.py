# -*- coding: utf-8 -*-
"""Qué tabs y reportes ve cada propiedad.

Owner, 2026-08-20: «no todas las propiedades van a ver todos los reportes, ya
que son muchos para cada propiedad y se van a perder» · «así como los
departamentos se van a limitar, así se van a limitar los reportes y los tabs
principales» · «todo debe poderse esconder y habilitar».

Medido ese día: la barra tiene **13 tabs y 96 entradas**. Una propiedad nueva
abre con las 96, y encontrar el reporte que se usa es el problema.

Mismo patrón que `dept_enablement`: **tabla esparsa, default PRENDIDO**. El día
que esto se despliega **no cambia nada en ninguna propiedad** — sólo existen las
filas de lo que alguien apague a mano.

⚠️ Esto esconde de la barra; **no es un permiso**. La ruta sigue respondiendo y
el endpoint contesta lo mismo. Es navegación, no seguridad.

Aditiva y reversible.

Revision ID: 136
Revises: 135
"""
import sqlalchemy as sa
from alembic import op

revision = "136"
down_revision = "135"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tab_enablement",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("scope_kind", sa.String(8), nullable=False,
                  server_default="ITEM"),
        sa.Column("clave", sa.String(60), nullable=False),
        sa.Column("visible", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("actualizado_por", sa.String(120), server_default=""),
        sa.UniqueConstraint("hotel_id", "scope_kind", "clave",
                            name="uq_tab_enablement"),
    )
    op.create_index("ix_tab_enablement_hotel", "tab_enablement", ["hotel_id"])


def downgrade() -> None:
    op.drop_index("ix_tab_enablement_hotel", table_name="tab_enablement")
    op.drop_table("tab_enablement")
