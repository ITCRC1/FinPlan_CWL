# -*- coding: utf-8 -*-
"""Estadísticas con dimensiones: catálogo clase 9 + tabla de valores.

Hasta hoy «cuenta clase 9» eran tres códigos escritos a mano en un diccionario
de Python (9010/9020/9060) y cualquier otra 9xxx que llegara en un archivo se
descartaba en silencio absoluto. Y no había dónde ponerlas: `scenario_stats` son
cinco columnas fijas por escenario × mes, así que cada estadística nueva costaba
una migración y ~20 lugares que tocar.

El owner pidió (2026-08-14) cargarlas **por departamento y por posición**, más
canal, país y market code. Eso no cabe en columnas fijas.

Dos tablas:

* `stat_accounts` — el catálogo. Se siembra desde `seed_data/stats_catalog.json`
  en cada arranque. **No** sale de la tabla `accounts`: esa está vacía en
  producción (0 filas, verificado 2026-08-14), el catálogo contable de 9,292
  cuentas 9xxx que describe CLAUDE.md §18 nunca se importó.
* `statistical_entries` — los valores, con las dimensiones.

⚠️ Las dimensiones son `NOT NULL DEFAULT ''`, no nulables. En Postgres dos NULL
no son iguales, así que una restricción de unicidad con columnas nulables deja
pasar duplicados: el mismo dato entraría dos veces y el total saldría doble sin
que nada avise.

Nada se migra ni se mueve: las tres cuentas de hoy siguen escribiendo en
`scenario_stats` como siempre. Esta tabla nace vacía.

Revision ID: 106
"""
from alembic import op
import sqlalchemy as sa

revision = "106"
down_revision = "105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stat_accounts",
        sa.Column("code", sa.String(10), primary_key=True),
        sa.Column("grupo", sa.String(10), nullable=False, index=True),
        sa.Column("nombre_es", sa.String(200), nullable=False),
        sa.Column("nombre_en", sa.String(200), nullable=False, server_default=""),
        sa.Column("unidad", sa.String(16), nullable=False),
        sa.Column("dims", sa.String(120), nullable=False, server_default=""),
        sa.Column("agrega", sa.String(4), nullable=False, server_default="SUM"),
        sa.Column("dinero", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("amarra_con", sa.String(40), nullable=False, server_default=""),
        sa.Column("legado", sa.String(40), nullable=False, server_default=""),
        sa.Column("activa", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "statistical_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("scenario_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("account_code", sa.String(10),
                  sa.ForeignKey("stat_accounts.code"), nullable=False, index=True),
        sa.Column("month", sa.Integer(), nullable=False),
        # Dimensiones: cadena vacía, nunca NULL. Ver la advertencia de arriba.
        sa.Column("dept_code", sa.String(10), nullable=False, server_default=""),
        sa.Column("position_code", sa.String(24), nullable=False, server_default=""),
        sa.Column("room_type_code", sa.String(10), nullable=False, server_default=""),
        sa.Column("dim_type", sa.String(12), nullable=False, server_default=""),
        sa.Column("dim_code", sa.String(48), nullable=False, server_default=""),
        sa.Column("value", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("origen", sa.String(10), nullable=False, server_default="ARCHIVO"),
        sa.UniqueConstraint("scenario_id", "account_code", "month", "dept_code",
                            "position_code", "room_type_code", "dim_type", "dim_code",
                            name="uq_statistical_entry"),
    )
    op.create_index("ix_stat_entry_scen_acct", "statistical_entries",
                    ["scenario_id", "account_code"])
    op.create_index("ix_stat_entry_scen_mes", "statistical_entries",
                    ["scenario_id", "month"])
    op.create_index("ix_stat_entry_dept", "statistical_entries", ["dept_code"])
    op.create_index("ix_stat_entry_pos", "statistical_entries", ["position_code"])


def downgrade() -> None:
    op.drop_index("ix_stat_entry_pos", table_name="statistical_entries")
    op.drop_index("ix_stat_entry_dept", table_name="statistical_entries")
    op.drop_index("ix_stat_entry_scen_mes", table_name="statistical_entries")
    op.drop_index("ix_stat_entry_scen_acct", table_name="statistical_entries")
    op.drop_table("statistical_entries")
    op.drop_table("stat_accounts")
