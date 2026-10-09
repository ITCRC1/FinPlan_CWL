# -*- coding: utf-8 -*-
"""El USALI, guardado para consultar y para revisar contra él.

Owner, 2026-10-08: *«yo quiero subir el pdf y que el documento viva en la app y
se use para análisis […] contra ese máximo detalle y USALI se saca para ver las
discrepancias»*.

Tres tablas nuevas, ninguna existente se toca. Ver `app/models/usali.py` para
qué guarda cada una y por qué la confianza viaja con el dato.

Medido sobre el libro del owner —USALI 11.ª edición, 391 páginas— antes de
decidir los tamaños: 1.946 filas de diccionario sobre 1.858 artículos, 347
cuentas distintas y 468 definiciones. El artículo más largo tiene 120
caracteres y la definición más larga unos 1.800, así que el texto va a `Text` y
los nombres a `String` holgado.

⚠️ **Esto NO se siembra.** El texto es de AHLA/HFTP y cada instalación sube el
suyo: un clon arranca con las tablas vacías, a propósito.
"""
import sqlalchemy as sa
from alembic import op

revision = "154"
down_revision = "153"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usali_documentos",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, server_default=""),
        sa.Column("archivo", sa.String(300), nullable=False, server_default=""),
        sa.Column("checksum", sa.String(64), nullable=False, server_default=""),
        sa.Column("paginas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("paginas_con_texto", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("items", sa.Integer, nullable=False, server_default="0"),
        sa.Column("items_confirmados", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("definiciones", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cruce", sa.Text, nullable=False, server_default=""),
        sa.Column("subido_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("subido_por", sa.String(120), nullable=False, server_default=""),
    )
    op.create_index("ix_usali_documentos_hotel_id", "usali_documentos", ["hotel_id"])
    op.create_index("ix_usali_documentos_checksum", "usali_documentos", ["checksum"])

    op.create_table(
        "usali_items",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, server_default=""),
        sa.Column("item", sa.String(400), nullable=False, server_default=""),
        sa.Column("item_norm", sa.String(400), nullable=False, server_default=""),
        sa.Column("schedule", sa.String(80), nullable=False, server_default=""),
        sa.Column("cuenta", sa.String(200), nullable=False, server_default=""),
        sa.Column("confianza", sa.String(12), nullable=False,
                  server_default="unico"),
        sa.Column("paginas", sa.String(60), nullable=False, server_default=""),
        sa.UniqueConstraint("hotel_id", "item_norm", "schedule", "cuenta",
                            name="uq_usali_item"),
    )
    op.create_index("ix_usali_items_hotel_id", "usali_items", ["hotel_id"])
    op.create_index("ix_usali_items_item_norm", "usali_items", ["item_norm"])
    op.create_index("ix_usali_items_schedule", "usali_items", ["schedule"])
    op.create_index("ix_usali_items_cuenta", "usali_items", ["cuenta"])

    op.create_table(
        "usali_definiciones",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, server_default=""),
        sa.Column("cuenta", sa.String(200), nullable=False, server_default=""),
        sa.Column("cuenta_norm", sa.String(200), nullable=False, server_default=""),
        sa.Column("texto", sa.Text, nullable=False, server_default=""),
        sa.Column("pagina", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("hotel_id", "cuenta_norm", "pagina",
                            name="uq_usali_definicion"),
    )
    op.create_index("ix_usali_definiciones_hotel_id", "usali_definiciones",
                    ["hotel_id"])
    op.create_index("ix_usali_definiciones_cuenta_norm", "usali_definiciones",
                    ["cuenta_norm"])


def downgrade() -> None:
    op.drop_table("usali_definiciones")
    op.drop_table("usali_items")
    op.drop_table("usali_documentos")
