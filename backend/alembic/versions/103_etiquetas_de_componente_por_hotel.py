# -*- coding: utf-8 -*-
"""Etiquetas de componente editables por propiedad.

El código del componente (FOOD, ACTIVITIES, TRANSPORT, SUSTAINABILITY) es lo que
usa el motor de revenue para armar el ingreso y rutearlo al P&L. La etiqueta era
un diccionario escrito en el código, igual para las cuatro propiedades.

Esta tabla guarda SOLO los rótulos que una propiedad decidió cambiar: si no hay
fila, se lee el texto por defecto. Así Corcovado no cambia de aspecto y un hotel
nuevo puede llamarle a las cosas como le sirva.

Revision ID: 103
"""
from alembic import op
import sqlalchemy as sa

revision = "103"
down_revision = "102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "component_labels",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), sa.ForeignKey("hotels.id"), nullable=False, index=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="PACKAGE"),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("label", sa.String(120), nullable=False, server_default=""),
        sa.UniqueConstraint("hotel_id", "kind", "code", name="uq_component_label"),
    )


def downgrade() -> None:
    op.drop_table("component_labels")
