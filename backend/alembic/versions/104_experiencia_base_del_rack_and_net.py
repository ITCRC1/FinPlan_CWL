# -*- coding: utf-8 -*-
"""Marca explícita de qué experiencia alimenta el Rack & Net Rate.

El tab «Package Component Rack and Net Rate» —el más importante de la pantalla,
según el owner— buscaba la experiencia cuyo NOMBRE contuviera «classic». Con eso,
renombrar el paquete o borrarlo hacía que el tab pasara a mostrar otra experiencia
en silencio, y las tarifas que se digitan ahí se guardaban contra la que quedara
primera.

Es el mismo error que el del código de las categorías de habitación: ligar por
nombre en vez de por una llave. Ahora hay una bandera explícita.

Las filas que ya existen se marcan acá mismo: la que diga «classic», o la primera
de cada escenario si ninguna lo dice.

Revision ID: 104
"""
from alembic import op
import sqlalchemy as sa

revision = "104"
down_revision = "103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("pkg_experiences",
                  sa.Column("es_base", sa.Boolean(), nullable=False,
                            server_default=sa.false()))
    # 1) la que se llama «classic» en cada escenario
    op.execute("""
        UPDATE pkg_experiences SET es_base = true
        WHERE id IN (
            SELECT DISTINCT ON (scenario_id) id
            FROM pkg_experiences
            WHERE LOWER(name) LIKE '%classic%'
            ORDER BY scenario_id, sort_order
        )
    """)
    # 2) los escenarios que no tienen ninguna «classic»: la primera
    op.execute("""
        UPDATE pkg_experiences SET es_base = true
        WHERE id IN (
            SELECT DISTINCT ON (scenario_id) id
            FROM pkg_experiences
            WHERE scenario_id NOT IN (
                SELECT scenario_id FROM pkg_experiences WHERE es_base = true
            )
            ORDER BY scenario_id, sort_order
        )
    """)


def downgrade() -> None:
    op.drop_column("pkg_experiences", "es_base")
