# -*- coding: utf-8 -*-
"""Los renglones aprobados de cada Schedule del USALI.

La otra mitad del libro. El diccionario que cargó la 154 da EJEMPLOS de
artículos —«Cots → Rooms / Operating Supplies»—; los Schedules dan el RENGLÓN
del reporte: qué líneas lleva el estado de resultados de cada departamento.
Son ~400 en 14 schedules.

⚠️ **Es referencia, no alarma — y se midió antes de construirla.** Contra las
252 cuentas que usó setiembre 2026, la regla «esta cuenta no es renglón
aprobado de su schedule» dio UN hallazgo, y dudoso: 130 cuentas (51.6%) son
propias del hotel y el estándar nunca las nombró, y 68 (27.0%) caen en
departamentos donde el libro no da lista. Se guarda para contestar lo que el
owner pidió —*«cada cuenta tiene la descripción y va por departamento»*—, que
es ver, al revisar una cuenta, qué dice el estándar que lleva ese departamento.

Como la 154: **no se siembra**. El texto es de AHLA/HFTP y cada instalación
sube el suyo. Un clon arranca con la tabla vacía, a propósito.
"""
import sqlalchemy as sa
from alembic import op

revision = "155"
down_revision = "154"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usali_renglones",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, server_default=""),
        sa.Column("numero", sa.Integer, nullable=False, server_default="0"),
        sa.Column("titulo", sa.String(80), nullable=False, server_default=""),
        sa.Column("schedule", sa.String(80), nullable=False, server_default=""),
        sa.Column("renglon", sa.String(200), nullable=False, server_default=""),
        sa.Column("renglon_norm", sa.String(200), nullable=False,
                  server_default=""),
        sa.Column("orden", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pagina", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lista_aprobada", sa.Boolean, nullable=False,
                  server_default=sa.false()),
        sa.UniqueConstraint("hotel_id", "numero", "renglon_norm",
                            name="uq_usali_renglon"),
    )
    op.create_index("ix_usali_renglones_hotel_id", "usali_renglones",
                    ["hotel_id"])
    op.create_index("ix_usali_renglones_numero", "usali_renglones", ["numero"])
    op.create_index("ix_usali_renglones_schedule", "usali_renglones",
                    ["schedule"])
    op.create_index("ix_usali_renglones_renglon_norm", "usali_renglones",
                    ["renglon_norm"])
    # Cuantos renglones leyo la subida: igual que `items` y `definiciones`, es
    # lo que permite saber meses despues si la lectura salio bien.
    op.add_column("usali_documentos",
                  sa.Column("renglones", sa.Integer, nullable=False,
                            server_default="0"))


def downgrade() -> None:
    op.drop_column("usali_documentos", "renglones")
    op.drop_table("usali_renglones")
