# -*- coding: utf-8 -*-
"""Guillermo Fase 1 — configuración, manifiesto, latido y cola de excepciones.

Ver `docs/GUILLERMO.md`. Cuatro tablas nuevas, más **una columna** sobre
`mapeo_origen`.

⚠️ **La columna sobre `mapeo_origen` es la decisión 4 del owner.** El spec
original pedía una tabla `mapping_rules` aparte; `mapeo_origen` ya resuelve
«origen externo → cuenta interna», con precedencia por departamento, flag
`activo`, CRUD y pantalla. Lo único que le faltaba era la llave por TEXTO LIBRE
normalizado. Dos tablas de mapeo son dos pantallas donde el owner tiene que
acordarse de cuál mira — el mismo problema de las dos tablas de rack que se
arregló el día anterior.

La columna es `nullable`, sin default y sin backfill: las 0 filas que hoy
existen siguen resolviéndose por código de cuenta exactamente igual que antes.

⚠️ `guillermo_expected_reports` **nace vacía a propósito**: su contenido es la
decisión D-1 del owner y no se inventa. Un manifiesto inventado haría que
Guillermo reclamara archivos que nadie prometió.

Aditiva y reversible.
"""
import sqlalchemy as sa
from alembic import op

revision = "134"
down_revision = "133"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guillermo_config",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("clave", sa.String(40), nullable=False),
        sa.Column("valor", sa.String(120), nullable=False, server_default=""),
        sa.Column("descripcion", sa.String(200), nullable=False,
                  server_default=""),
        sa.UniqueConstraint("hotel_id", "clave", name="uq_guillermo_config"),
    )

    op.create_table(
        "guillermo_heartbeat",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("resultado", sa.String(20), nullable=False,
                  server_default="ok"),
        sa.Column("detalle", sa.Text, nullable=False, server_default=""),
        sa.Column("latido_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), index=True),
    )

    op.create_table(
        "guillermo_expected_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("report_id", sa.String(60), nullable=False),
        sa.Column("patron", sa.String(160), nullable=False, server_default=""),
        sa.Column("formato", sa.String(10), nullable=False, server_default=""),
        sa.Column("frecuencia", sa.String(12), nullable=False,
                  server_default="daily"),
        sa.Column("obligatorio", sa.Boolean, nullable=False,
                  server_default=sa.true()),
        sa.Column("tamano_min", sa.Integer, nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("notas", sa.String(200), nullable=False, server_default=""),
        sa.UniqueConstraint("hotel_id", "report_id", name="uq_expected_report"),
    )

    op.create_table(
        "guillermo_import_exceptions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("batch_id", sa.String(36),
                  sa.ForeignKey("import_batches.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("tipo", sa.String(30), nullable=False,
                  server_default="sin_mapeo"),
        sa.Column("linea", sa.Integer, nullable=False, server_default="0"),
        sa.Column("valor_crudo", sa.String(400), nullable=False,
                  server_default=""),
        sa.Column("valor_normalizado", sa.String(400), nullable=False,
                  server_default=""),
        sa.Column("destino_sugerido", sa.String(40), nullable=False,
                  server_default=""),
        sa.Column("confianza", sa.Numeric(4, 3), nullable=False,
                  server_default="0"),
        # ⚠️ El `rationale` es obligatorio por el principio rector: «puede
        # decidir, pero no puede esconder».
        sa.Column("rationale", sa.Text, nullable=False, server_default=""),
        sa.Column("estado", sa.String(16), nullable=False,
                  server_default="pending", index=True),
        sa.Column("resuelto_por", sa.String(120), nullable=False,
                  server_default=""),
        sa.Column("resuelto_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # ── La extensión de `mapeo_origen` (decisión 4 del owner) ────────────────
    #
    # Nullable, sin default y sin backfill: lo que hoy resuelve por código de
    # cuenta sigue resolviendo igual. La columna sólo habilita la llave nueva.
    op.add_column("mapeo_origen",
                  sa.Column("texto_origen", sa.String(200), nullable=True))
    op.create_index("ix_mapeo_origen_texto", "mapeo_origen",
                    ["hotel_id", "origen", "texto_origen"])


def downgrade() -> None:
    op.drop_index("ix_mapeo_origen_texto", table_name="mapeo_origen")
    op.drop_column("mapeo_origen", "texto_origen")
    op.drop_table("guillermo_import_exceptions")
    op.drop_table("guillermo_expected_reports")
    op.drop_table("guillermo_heartbeat")
    op.drop_table("guillermo_config")
