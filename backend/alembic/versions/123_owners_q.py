# -*- coding: utf-8 -*-
"""Tab `Reports` → `Owners Q`: el reporte mensual a SCP (POR/PAR).

Cuatro tablas nuevas (`report_lines`, `report_line_mapping`, `capacidad`,
`report_snapshots`) y dos columnas de VIGENCIA en `account_mapping`.

Por qué la vigencia. El reporte se alimenta del Account Mapping, y el mapeo
cambia: D9 saca la cuenta 7120 (Credit Card Commissions) de `OH_ADMIN` y la
manda a una línea propia porque SCP la exige separada. Sin vigencia, ese
cambio REESCRIBE LA HISTORIA: un período ya enviado a SCP devolvería números
distintos al reejecutarse, y encima seguiría cuadrando —la plata solo se mueve
entre dos filas del mismo subtotal—, así que nadie lo notaría.

`vigente_desde`/`vigente_hasta` son `YYYY-MM` inclusive, o NULL = sin límite.
Las 1.098 reglas de hoy quedan con las dos en NULL: vigentes siempre, que es
exactamente lo que eran hasta ahora. No es una migración de datos, es escribir
lo que ya estaba implícito.

⚠️ La restricción única de `account_mapping` pasa a incluir `vigente_desde`.
Sin eso, la regla vieja y la nueva de la 7120 (mismo depto, misma cuenta,
mismo origen) colisionan y la segunda no entra.
"""
from alembic import op
import sqlalchemy as sa

revision = "123"
down_revision = "122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Vigencia en el mapeo ─────────────────────────────────────────────────
    op.add_column("account_mapping", sa.Column("vigente_desde", sa.String(7), nullable=True))
    op.add_column("account_mapping", sa.Column("vigente_hasta", sa.String(7), nullable=True))
    op.drop_constraint("uq_account_mapping", "account_mapping", type_="unique")
    op.create_unique_constraint(
        "uq_account_mapping", "account_mapping",
        ["report_id", "source_department", "account_code", "source_origin", "vigente_desde"])

    # La unicidad de (depto, cuenta) solo vale ENTRE REGLAS ACTIVAS. Hoy la
    # cuenta 8005 del depto 250 existe dos veces: MGMT_FEE_3 (activa) y
    # MGMT_FEE_5_ROYALTIES (inactiva). El día que se active la segunda, la 8005
    # entraría dos veces a la fila 39. Índice PARCIAL, no restricción total.
    op.execute("""
        CREATE UNIQUE INDEX uq_mapping_activo_depto_cuenta
        ON account_mapping (report_id, dept_code, account_code,
                            COALESCE(vigente_desde, ''), COALESCE(vigente_hasta, ''))
        WHERE active_status = 'YES'
    """)

    # ── Las 48 filas del reporte ─────────────────────────────────────────────
    op.create_table(
        "report_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_key", sa.String(40), nullable=False),
        sa.Column("row_no", sa.Integer, nullable=False),
        sa.Column("report_code", sa.String(60), nullable=False),
        sa.Column("label", sa.String(150), nullable=False),
        sa.Column("indent", sa.Integer, nullable=False, server_default="1"),
        sa.Column("line_type", sa.String(12), nullable=False),
        sa.Column("nature", sa.String(12), nullable=False),
        sa.Column("lineas_pl", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("operandos", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("formula_nota", sa.Text, nullable=False, server_default=""),
        sa.Column("nota", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.CheckConstraint("line_type IN ('STAT','HEADER','DETAIL','SUBTOTAL','CALC')",
                           name="ck_report_line_type"),
        sa.CheckConstraint("nature IN ('stat','header','revenue','expense','profit','signed')",
                           name="ck_report_line_nature"),
    )
    op.create_index("ix_report_lines_report_key", "report_lines", ["report_key"])
    op.create_unique_constraint("uq_report_line", "report_lines", ["report_key", "report_code"])
    op.create_unique_constraint("uq_report_line_row", "report_lines", ["report_key", "row_no"])

    # ── `Línea P&L` → fila ───────────────────────────────────────────────────
    op.create_table(
        "report_line_mapping",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_key", sa.String(40), nullable=False),
        sa.Column("linea_pl", sa.String(60), nullable=False),
        sa.Column("report_code", sa.String(60), nullable=False),
        sa.Column("nota", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_report_line_mapping_report_key", "report_line_mapping", ["report_key"])
    # Sin esto una línea duplicada se suma dos veces sin avisar.
    op.create_unique_constraint("uq_report_line_mapping", "report_line_mapping",
                                ["report_key", "linea_pl"])

    # ── Capacidad ────────────────────────────────────────────────────────────
    op.create_table(
        "capacidad",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("entidad", sa.String(20), nullable=False),
        sa.Column("anio", sa.Integer, nullable=False),
        sa.Column("mes", sa.Integer, nullable=False),
        sa.Column("habitaciones_disponibles", sa.Integer, nullable=False, server_default="30"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.CheckConstraint("habitaciones_disponibles > 0", name="ck_capacidad_positiva"),
    )
    op.create_index("ix_capacidad_entidad", "capacidad", ["entidad"])
    op.create_unique_constraint("uq_capacidad", "capacidad", ["entidad", "anio", "mes"])

    # ── Lo enviado, congelado ────────────────────────────────────────────────
    op.create_table(
        "report_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("report_key", sa.String(40), nullable=False),
        sa.Column("entidad", sa.String(20), nullable=False),
        sa.Column("anio", sa.Integer, nullable=False),
        sa.Column("mes", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("enviado_el", sa.DateTime, nullable=True),
        sa.Column("convencion", sa.String(12), nullable=False, server_default="favorable"),
        sa.Column("mapping_version", sa.String(7), nullable=False, server_default=""),
        sa.Column("valores", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("nota", sa.Text, nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_report_snapshots_report_key", "report_snapshots", ["report_key"])
    op.create_index("ix_report_snapshots_entidad", "report_snapshots", ["entidad"])
    op.create_unique_constraint("uq_report_snapshot", "report_snapshots",
                                ["report_key", "entidad", "anio", "mes", "version"])


def downgrade() -> None:
    op.drop_table("report_snapshots")
    op.drop_table("capacidad")
    op.drop_table("report_line_mapping")
    op.drop_table("report_lines")
    op.execute("DROP INDEX IF EXISTS uq_mapping_activo_depto_cuenta")
    op.drop_constraint("uq_account_mapping", "account_mapping", type_="unique")
    op.create_unique_constraint(
        "uq_account_mapping", "account_mapping",
        ["report_id", "source_department", "account_code", "source_origin"])
    op.drop_column("account_mapping", "vigente_hasta")
    op.drop_column("account_mapping", "vigente_desde")
