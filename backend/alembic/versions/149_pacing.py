# -*- coding: utf-8 -*-
"""Módulo PACING: fotos de Opera, reservas, cargas y configuración.

Owner, 2026-09-30: *«un modulo que se llame PACING y ahi subo todos estos
archivos… ahí voy a hacer el presupuesto»*. Cuatro tablas nuevas, ninguna toca
nada existente. Ver `app/models/pacing.py`.
"""
import sqlalchemy as sa
from alembic import op

revision = "149"
down_revision = "148"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pacing_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("as_of", sa.String(10), nullable=False, index=True),
        sa.Column("date_from", sa.String(10), nullable=False),
        sa.Column("date_to", sa.String(10), nullable=False),
        sa.Column("has_forecast", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("file_name", sa.String(255)),
        sa.Column("total_revenue", sa.Numeric(16, 2), server_default="0"),
        sa.Column("days", sa.JSON, nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True)),
        sa.Column("uploaded_by", sa.String(255)),
        sa.UniqueConstraint("hotel_id", "kind", "as_of", name="uq_pacing_snap_hotel_kind_asof"),
    )
    op.create_table(
        "pacing_reservations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("resv_id", sa.String(40), nullable=False),
        sa.Column("ins", sa.String(10), nullable=False, index=True),
        sa.Column("arr", sa.String(10), nullable=False, index=True),
        sa.Column("nts", sa.Integer, server_default="0"),
        sa.Column("rms", sa.Integer, server_default="1"),
        sa.Column("amt", sa.Numeric(14, 2), server_default="0"),
        sa.Column("st", sa.String(2), server_default="A"),
        sa.Column("fl", sa.String(4)),
        sa.Column("ch", sa.String(80)),
        sa.Column("rate", sa.String(20)),
        sa.Column("blk", sa.Integer, server_default="0"),
        sa.Column("room_type", sa.String(20)),
        sa.Column("guest", sa.String(80)),
        sa.Column("grupo", sa.String(80)),
        sa.Column("garantia", sa.String(20)),
        sa.Column("pax", sa.Integer, server_default="0"),
        sa.Column("tarifa_noche", sa.Numeric(12, 2), server_default="0"),
        sa.Column("load_id", sa.String(36), index=True),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("hotel_id", "resv_id", name="uq_pacing_resv_hotel_id"),
    )
    op.create_table(
        "pacing_resv_loads",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("file_name", sa.String(255)),
        sa.Column("cuenta", sa.Integer, server_default="0"),
        sa.Column("nuevas", sa.Integer, server_default="0"),
        sa.Column("actualizadas", sa.Integer, server_default="0"),
        sa.Column("descartadas_pi", sa.Integer, server_default="0"),
        sa.Column("min_ins", sa.String(10)),
        sa.Column("max_ins", sa.String(10)),
        sa.Column("uploaded_at", sa.DateTime(timezone=True)),
        sa.Column("uploaded_by", sa.String(255)),
    )
    op.create_table(
        "pacing_config",
        sa.Column("hotel_id", sa.String(10), primary_key=True),
        sa.Column("stly", sa.JSON),
        sa.Column("meta", sa.JSON),
        sa.Column("onsite_mode", sa.String(10), server_default="pct"),
        sa.Column("onsite_pct", sa.Numeric(6, 2), server_default="12"),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.String(255)),
    )


def downgrade() -> None:
    op.drop_table("pacing_config")
    op.drop_table("pacing_resv_loads")
    op.drop_table("pacing_reservations")
    op.drop_table("pacing_snapshots")
