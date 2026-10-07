# -*- coding: utf-8 -*-
"""El movimiento del mayor, guardado, para poder bajar hasta el asiento.

Owner, 2026-10-06: *«me gustaría que quede guardado pero cada vez que se corra
se le caiga encima […] es solo para poder revisar detalladamente a nivel de
detalle»* · *«dale, máximo detalle y descripción del asiento»*.

Una tabla nueva, no toca ninguna existente. Ver `app/models/mayor_movimiento.py`
para por qué uno por mes, por qué se guarda el archivo entero y por qué esto no
entra a ningún total.

Medido antes de decidir: el año completo son 12 MB con el archivo de setiembre
del owner y 23 MB con el *Full Detail*. El espacio no era el problema.
"""
import sqlalchemy as sa
from alembic import op

revision = "151"
down_revision = "150"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mayor_movimientos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, server_default=""),
        sa.Column("anio", sa.Integer, nullable=False),
        sa.Column("mes", sa.Integer, nullable=False),
        sa.Column("cuenta", sa.String(40), nullable=False, server_default=""),
        sa.Column("seg1", sa.String(6), nullable=False, server_default=""),
        sa.Column("seg2", sa.String(6), nullable=False, server_default=""),
        sa.Column("seg3", sa.String(6), nullable=False, server_default=""),
        sa.Column("asiento", sa.String(20), nullable=False, server_default=""),
        sa.Column("linea", sa.String(10), nullable=False, server_default=""),
        sa.Column("fecha", sa.String(20), nullable=False, server_default=""),
        sa.Column("descripcion", sa.String(250), nullable=False, server_default=""),
        sa.Column("desc_asiento", sa.String(250), nullable=False, server_default=""),
        sa.Column("origen", sa.String(20), nullable=False, server_default=""),
        sa.Column("referencia", sa.String(120), nullable=False, server_default=""),
        sa.Column("num_doc", sa.String(40), nullable=False, server_default=""),
        sa.Column("debito", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("credito", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("tc", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("moneda", sa.String(10), nullable=False, server_default=""),
        sa.Column("archivo", sa.String(255), nullable=False, server_default=""),
        sa.Column("checksum", sa.String(64), nullable=False, server_default=""),
        sa.Column("subido_en", sa.DateTime(timezone=True)),
        sa.Column("subido_por", sa.String(120), nullable=False, server_default=""),
    )
    op.create_index("ix_mayor_movimientos_hotel_id", "mayor_movimientos", ["hotel_id"])
    op.create_index("ix_mayor_movimientos_asiento", "mayor_movimientos", ["asiento"])
    op.create_index("ix_mayor_movimientos_checksum", "mayor_movimientos", ["checksum"])
    # Los dos que sirven a las preguntas de verdad: «abrime esta cuenta de este
    # mes» y «todo lo de este departamento en este mes». Sin ellos cada apertura
    # barre las ~9.000 filas del mes.
    op.create_index("ix_mayor_mov_mes_cuenta", "mayor_movimientos",
                    ["hotel_id", "anio", "mes", "cuenta"])
    op.create_index("ix_mayor_mov_mes_depto", "mayor_movimientos",
                    ["hotel_id", "anio", "mes", "seg2"])


def downgrade() -> None:
    op.drop_table("mayor_movimientos")
