# -*- coding: utf-8 -*-
"""OTB multi-año: `year` propio en on_the_books_entries y otb_daily_occ.

El history_forecast del owner trae horizonte multi-año en el MISMO archivo
(forecast hasta 5 años adelante del corte, ej. corte 2026 con datos hasta
2030) — antes solo se guardaba mes/día, así que todos los años caían en el
mismo balde de 12 meses y se mezclaban entre sí. `year` es columna propia,
no se asume el año del escenario.

Backfill: las filas que ya existen no tienen fecha real guardada (se perdió
el año al no tener columna) — la única atribución razonable es el año del
escenario dueño, que es lo que YA se estaba asumiendo hasta ahora. No es una
pérdida de dato: es la misma atribución implícita que tenía el sistema,
ahora escrita explícitamente.
"""
from alembic import op
import sqlalchemy as sa

revision = "122"
down_revision = "121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("on_the_books_entries", sa.Column("year", sa.Integer, nullable=True))
    op.add_column("otb_daily_occ", sa.Column("year", sa.Integer, nullable=True))

    op.execute("""
        UPDATE on_the_books_entries e
        SET year = s.year
        FROM scenarios s
        WHERE e.scenario_id = s.id AND e.year IS NULL
    """)
    op.execute("""
        UPDATE otb_daily_occ d
        SET year = s.year
        FROM scenarios s
        WHERE d.scenario_id = s.id AND d.year IS NULL
    """)

    op.alter_column("on_the_books_entries", "year", nullable=False)
    op.alter_column("otb_daily_occ", "year", nullable=False)

    op.drop_constraint("uq_otb_scenario_week_month", "on_the_books_entries", type_="unique")
    op.create_unique_constraint(
        "uq_otb_scenario_week_year_month", "on_the_books_entries",
        ["scenario_id", "week", "year", "month"])

    op.drop_constraint("uq_dailyocc_sc_wk_mo_dy", "otb_daily_occ", type_="unique")
    op.create_unique_constraint(
        "uq_dailyocc_sc_wk_yr_mo_dy", "otb_daily_occ",
        ["scenario_id", "week", "year", "month", "day"])

    op.create_index("ix_otb_entries_year", "on_the_books_entries", ["year"])
    op.create_index("ix_otb_daily_year", "otb_daily_occ", ["year"])


def downgrade() -> None:
    op.drop_index("ix_otb_daily_year", table_name="otb_daily_occ")
    op.drop_index("ix_otb_entries_year", table_name="on_the_books_entries")
    op.drop_constraint("uq_dailyocc_sc_wk_yr_mo_dy", "otb_daily_occ", type_="unique")
    op.create_unique_constraint(
        "uq_dailyocc_sc_wk_mo_dy", "otb_daily_occ", ["scenario_id", "week", "month", "day"])
    op.drop_constraint("uq_otb_scenario_week_year_month", "on_the_books_entries", type_="unique")
    op.create_unique_constraint(
        "uq_otb_scenario_week_month", "on_the_books_entries", ["scenario_id", "week", "month"])
    op.drop_column("otb_daily_occ", "year")
    op.drop_column("on_the_books_entries", "year")
