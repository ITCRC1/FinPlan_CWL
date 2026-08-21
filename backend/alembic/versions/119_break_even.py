# -*- coding: utf-8 -*-
"""Módulo Break-Even: las tres tablas de la Fase 1.

Spec `FINPLAN_BREAK_EVEN.md` §2. Crea `be_department`, `be_cost_classification`
y `be_classification_snapshot`.

## Los detalles que parecen manías y no lo son

* **`dept_code` y `account` son NOT NULL con default `''`.** El seed carga con
  `ON CONFLICT (property_id, dept_code, account, pl_line) DO NOTHING`, y en
  Postgres `NULL ≠ NULL`: si las filas `LINEA` entraran con NULL, una segunda
  corrida del seed **duplicaría cada una en silencio** y el costo total del
  módulo se iría para arriba sin que nada fallara.
* **`excluded_from_be` es columna, no una comparación de texto.** El impuesto de
  renta se excluye por acá. Con `be_section = 'INCOME TAX'` bastaría que alguien
  renombre la sección para que el equilibrio de CWL salte de $3.996.427 a
  $4.109.443 sin aviso.
* **`CHECK (pct_variable BETWEEN 0 AND 1)`.** La validación del navegador no
  protege nada: un PATCH directo entra igual.
* **`ondelete='RESTRICT'` en el FK al departamento.** Borrar un departamento con
  reglas colgando dejaría huérfano el costo, y el módulo lo contaría como 100%
  fijo sin decir por qué.

`be_classification_snapshot` se crea en la Fase 1 aunque solo se lea en la 2: es
uno de los ganchos que el spec pide dejar puestos, y crear la tabla después
obligaría a inventar el histórico que no se guardó.
"""
from alembic import op
import sqlalchemy as sa

revision = "119"
down_revision = "118"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "be_department",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(40), nullable=False),
        sa.Column("name", sa.String(60), nullable=False, server_default=""),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("generates_revenue", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("dept_codes", sa.String(60), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
        sa.Column("property_id", sa.String(10),
                  sa.ForeignKey("hotels.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ux_be_department_slug", "be_department", ["slug"], unique=True)

    op.create_table(
        "be_cost_classification",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("property_id", sa.String(10),
                  sa.ForeignKey("hotels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("be_department_id", sa.String(36),
                  sa.ForeignKey("be_department.id", ondelete="RESTRICT"),
                  nullable=False),
        # ⚠️ NOT NULL con default '' — ver el docstring.
        sa.Column("dept_code", sa.String(6), nullable=False, server_default=""),
        sa.Column("account", sa.String(10), nullable=False, server_default=""),
        sa.Column("account_name", sa.String(120), nullable=False, server_default=""),
        sa.Column("pl_line", sa.String(40), nullable=False),
        sa.Column("section", sa.String(40), nullable=False, server_default=""),
        sa.Column("be_section", sa.String(40), nullable=False, server_default=""),
        sa.Column("original_class", sa.String(20), nullable=False, server_default=""),
        sa.Column("pct_variable", sa.Numeric(5, 4), nullable=False,
                  server_default="0"),
        sa.Column("map_source", sa.String(10), nullable=False, server_default="GL"),
        sa.Column("excluded_from_be", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("source_rows", sa.String(120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime, nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime, nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_by", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("pct_variable >= 0 AND pct_variable <= 1",
                           name="ck_be_pct_variable"),
        sa.UniqueConstraint("property_id", "dept_code", "account", "pl_line",
                            name="uq_be_classification"),
    )
    op.create_index("ix_be_class_pl_line", "be_cost_classification",
                    ["property_id", "pl_line"])
    op.create_index("ix_be_class_dept", "be_cost_classification",
                    ["property_id", "be_department_id"])

    op.create_table(
        "be_classification_snapshot",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("property_id", sa.String(10),
                  sa.ForeignKey("hotels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(10), nullable=False),
        sa.Column("data_version", sa.String(10), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("frozen_at", sa.DateTime, nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("frozen_by", sa.String(36),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("property_id", "period", "data_version",
                            name="uq_be_snapshot"),
    )
    op.create_index("ix_be_snapshot_prop", "be_classification_snapshot",
                    ["property_id"])


def downgrade() -> None:
    op.drop_table("be_classification_snapshot")
    op.drop_index("ix_be_class_dept", table_name="be_cost_classification")
    op.drop_index("ix_be_class_pl_line", table_name="be_cost_classification")
    op.drop_table("be_cost_classification")
    op.drop_index("ux_be_department_slug", table_name="be_department")
    op.drop_table("be_department")
