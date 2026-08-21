# -*- coding: utf-8 -*-
"""Costos para Negociación de Grupos — Fase 1: sólo la configuración.

Módulo nuevo (`COSTOS_GRUPOS.md`): calcula cuánto cuesta atender un grupo, en
dólares por unidad de servicio, para poder negociar sin destruir margen.

⚠️ **Esta migración crea CINCO tablas de configuración y NINGUNA de hechos**, y
esa es la decisión importante. El spec describe cuatro tablas `fact_*`
(`fact_pl_mensual`, `fact_overhead_mensual`, `fact_no_operativo`,
`fact_volumenes`). No se crean:

* El P&L mensual, el overhead y los no-operativos ya los produce el motor. Una
  copia en tabla es una segunda fuente del mismo número, y se separa en cuanto
  alguien recalcula el escenario — sin que nada falle.
* Los volúmenes ya tienen estructura: `stat_accounts` (39 cuentas clase 9),
  `statistical_entries` y `scenario_stats`.

Lo que sí faltaba es la configuración: el mapa de temporadas, los parámetros
del modelo, la clasificación escalonada, los escalones y la comisión por canal.

**Aditiva y reversible.** No toca una tabla existente ni mueve un número.
"""
import sqlalchemy as sa
from alembic import op

revision = "130"
down_revision = "129"
branch_labels = None
depends_on = None

TABLAS = ("cfg_canales_costos", "cfg_escalones_costos",
          "cfg_clasificacion_costos", "cfg_parametros_costos", "cfg_temporadas")


def upgrade() -> None:
    op.create_table(
        "cfg_temporadas",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("mes", sa.Integer, nullable=False),
        sa.Column("temporada", sa.String(8), nullable=False),
        sa.Column("dias", sa.Integer, nullable=False, server_default="0"),
        # El cierre anual vive acá, como DATO. Verificado en producción: es
        # octubre, pero no está en todos los escenarios — el Budget Working
        # 2027 lo tiene abierto y eso mueve el overhead por habitación de $216
        # a $198, un 9% en el piso.
        sa.Column("dias_abiertos", sa.Integer, nullable=False, server_default="0"),
        sa.UniqueConstraint("hotel_id", "mes", name="uq_cfg_temporada"),
    )
    op.create_table(
        "cfg_parametros_costos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("clave", sa.String(48), nullable=False),
        # Texto a propósito: conviven números, enteros y opciones (M2, B, SI).
        sa.Column("valor", sa.String(64), nullable=False),
        sa.UniqueConstraint("hotel_id", "clave", name="uq_cfg_parametro_costos"),
    )
    op.create_table(
        "cfg_clasificacion_costos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("dept_code", sa.String(10), nullable=False, server_default=""),
        sa.Column("linea_gasto", sa.String(120), nullable=False, server_default=""),
        sa.Column("pct_variable", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("pct_fijo", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("pct_escalonado", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("activa", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("hotel_id", "dept_code", "linea_gasto",
                            name="uq_cfg_clasificacion_costos"),
    )
    op.create_table(
        "cfg_escalones_costos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("dept_code", sa.String(10), nullable=False, server_default=""),
        sa.Column("driver", sa.String(32), nullable=False),
        sa.Column("umbral", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("costo_adicional", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("descripcion", sa.String(200), nullable=False, server_default=""),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "cfg_canales_costos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("canal", sa.String(48), nullable=False),
        sa.Column("dept_code", sa.String(10), nullable=False, server_default=""),
        sa.Column("comision_pct", sa.Numeric(6, 4), nullable=False, server_default="0"),
        sa.Column("aplica_a_grupos", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("hotel_id", "canal", "dept_code",
                            name="uq_cfg_canal_costos"),
    )


def downgrade() -> None:
    for t in TABLAS:
        op.drop_table(t)
