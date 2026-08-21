# -*- coding: utf-8 -*-
"""Registro de importaciones — la identidad del archivo (Guillermo, Fase 0).

Ver `docs/GUILLERMO.md` §5.3. Decisión del owner 2026-08-19.

**El hueco:** FinPlan tiene 26 endpoints de subida y 18 parsers, y ninguna
forma de identidad de archivo — ni checksum, ni nombre guardado, ni tabla que
diga «esto ya se subió». **Subir el mismo archivo dos veces no se detecta**, y
como la respuesta HTTP es efímera tampoco queda traza de qué entró.

**Es puramente aditiva.** Dos tablas nuevas y nada más: ninguna tabla existente
se toca, ningún import cambia de comportamiento por esta migración. Lo único
que cambia es que ahora queda registrado — y que un reimport del mismo archivo
devuelve 409 con su motivo, igual que `confirmar_diferencias`.

⚠️ `hotel_id` es TEXTO, igual que las otras ~60 tablas. El spec original pedía
`property_id uuid FK → properties`: no existe tal tabla, y FinPlan es una
instalación por hotel, no multi-tenant. Ver `docs/GUILLERMO.md` §5.1.

Reversible: `downgrade` borra las dos tablas y no queda rastro en nada más.
"""
import sqlalchemy as sa
from alembic import op

revision = "133"
down_revision = "132"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        # ondelete SET NULL: borrar un escenario no puede borrar la traza de lo
        # que se importó — es justo cuando más falta hace.
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("origen", sa.String(20), nullable=False,
                  server_default="manual"),
        sa.Column("endpoint", sa.String(120), nullable=False, server_default=""),
        sa.Column("estado", sa.String(20), nullable=False,
                  server_default="queued", index=True),
        sa.Column("modo", sa.String(12), nullable=False,
                  server_default="assisted"),
        sa.Column("lineas_total", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lineas_auto", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lineas_pendientes", sa.Integer, nullable=False,
                  server_default="0"),
        sa.Column("disparado_por", sa.String(120), nullable=False,
                  server_default=""),
        sa.Column("detalle", sa.Text, nullable=False, server_default=""),
        sa.Column("iniciado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("terminado_en", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "import_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36),
                  sa.ForeignKey("import_batches.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("scenario_id", sa.String(36), nullable=True),
        sa.Column("nombre", sa.String(255), nullable=False, server_default=""),
        # sha256 del CONTENIDO, no del nombre: renombrar un archivo no lo
        # convierte en otro, y «actuales_julio (2).xlsx» es la forma más común
        # de reimportar sin querer.
        sa.Column("checksum", sa.String(64), nullable=False, index=True),
        sa.Column("tamano", sa.Integer, nullable=False, server_default="0"),
        sa.Column("report_id", sa.String(60), nullable=False, server_default=""),
        sa.Column("resultado", sa.String(20), nullable=False, server_default=""),
        sa.Column("mensaje", sa.Text, nullable=False, server_default=""),
        sa.Column("subido_por", sa.String(120), nullable=False,
                  server_default=""),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        # ⚠️ El constraint que cierra el hueco. Va con `scenario_id` y no solo
        # con `hotel_id` a propósito: el MISMO archivo puede cargarse
        # legítimamente en dos escenarios distintos, y eso no es un duplicado.
        sa.UniqueConstraint("hotel_id", "scenario_id", "checksum",
                            name="uq_import_file_checksum"),
    )


def downgrade() -> None:
    op.drop_table("import_files")
    op.drop_table("import_batches")
