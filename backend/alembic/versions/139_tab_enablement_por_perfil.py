# -*- coding: utf-8 -*-
"""Esconder tabs y reportes **por perfil**, no sólo por propiedad.

Owner, 2026-08-26: *«revisemos el tema del perfil y permisos de vistas por
usuarios; para mí sería por perfil: editor, view, y con vistas limitadas por
perfil»*.

La matriz de la migración 136 contesta «qué NO ve esta propiedad». Faltaba la
otra mitad: dentro de la misma propiedad, un lector no tiene por qué ver las
pantallas de carga ni el provisionamiento.

## Por qué una columna y no una tabla nueva

Dos matrices con las mismas dos reglas —esparsa, default prendido— serían dos
cosas que aprender por separado y dos lugares donde preguntar «¿esto se ve?».
La pregunta es una sola: *qué está apagado para quien está mirando*.

## El centinela es "" y NO NULL, a propósito

En Postgres **dos NULL no chocan en un UNIQUE**: con `perfil` nullable, la misma
clave podría apagarse dos veces «para todos» y la tabla dejaría de tener una
fila por decisión. Con `""` la restricción sigue haciendo su trabajo.

Y como `""` es el default, **las filas que ya existen pasan a significar "para
todos", que es exactamente lo que significaban**. El día que esto se despliega
no cambia nada para nadie.

Aditiva y reversible.

Revision ID: 139
Revises: 138
"""
import sqlalchemy as sa
from alembic import op

# ⚠️ Es la 137 de Amarena, RENUMERADA a 139: esta instalacion ya tiene una
# 137 (grupos directos) y una 138 (Pre-Cierre) propias. Con dos revisiones
# "137" alembic tendria dos cabezas y el arranque —que hace `upgrade head`—
# no levantaria.
revision = "139"
down_revision = "138"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tab_enablement",
                  sa.Column("perfil", sa.String(20), nullable=False,
                            server_default=""))
    # La llave vieja no admite la misma clave apagada para dos perfiles.
    op.drop_constraint("uq_tab_enablement", "tab_enablement", type_="unique")
    op.create_unique_constraint(
        "uq_tab_enablement", "tab_enablement",
        ["hotel_id", "scope_kind", "clave", "perfil"])


def downgrade() -> None:
    # ⚠️ Volver atrás con filas por perfil dejaría duplicados que la llave vieja
    # no acepta. Se borran las de perfil — son decisiones de visualización, no
    # dato contable, y se vuelven a marcar en la pantalla.
    op.execute("DELETE FROM tab_enablement WHERE perfil <> ''")
    op.drop_constraint("uq_tab_enablement", "tab_enablement", type_="unique")
    op.create_unique_constraint(
        "uq_tab_enablement", "tab_enablement",
        ["hotel_id", "scope_kind", "clave"])
    op.drop_column("tab_enablement", "perfil")
