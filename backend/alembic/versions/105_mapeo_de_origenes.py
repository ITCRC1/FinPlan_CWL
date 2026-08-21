# -*- coding: utf-8 -*-
"""Equivalencias cuenta-de-origen → cuenta de FinPlan.

Oxígen y Ojochal llevan la contabilidad en QuickBooks; Corcovado va a traer la
suya de un backoffice por API. El puente entre el código de cuenta de allá y el
catálogo USALI de acá tiene que ser DATO y no código: si fuera código, abrir cada
propiedad sería un desarrollo nuevo.

La tabla nace vacía. Sin filas no entra ningún monto por API — que es lo
correcto: mejor no importar nada que importar contra la cuenta equivocada.

Revision ID: 105
"""
from alembic import op
import sqlalchemy as sa

revision = "105"
down_revision = "104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mapeo_origen",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), sa.ForeignKey("hotels.id"), nullable=False, index=True),
        sa.Column("origen", sa.String(20), nullable=False, server_default="QUICKBOOKS"),
        sa.Column("cuenta_origen", sa.String(40), nullable=False),
        sa.Column("nombre_origen", sa.String(160), nullable=False, server_default=""),
        sa.Column("dept_origen", sa.String(40), nullable=False, server_default=""),
        sa.Column("account_code", sa.String(10), nullable=False),
        sa.Column("dept_code", sa.String(10), nullable=False, server_default=""),
        sa.Column("outlet", sa.String(40), nullable=False, server_default=""),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("nota", sa.String(200), nullable=False, server_default=""),
        sa.UniqueConstraint("hotel_id", "origen", "cuenta_origen", "dept_origen",
                            name="uq_mapeo_origen"),
    )
    op.create_index("ix_mapeo_origen_busqueda", "mapeo_origen",
                    ["hotel_id", "origen", "cuenta_origen"])


def downgrade() -> None:
    op.drop_index("ix_mapeo_origen_busqueda", table_name="mapeo_origen")
    op.drop_table("mapeo_origen")
