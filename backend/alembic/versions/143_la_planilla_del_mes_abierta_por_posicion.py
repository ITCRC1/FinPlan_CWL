# -*- coding: utf-8 -*-
"""La planilla del mes, abierta por POSICIÓN.

Owner, 2026-09-10: *«le metemos departamento, cuenta y posición — la posición
en las cuentas 6 es el tercer nivel»* · *«eso solo para actuales del mes»*.

En Integrity una cuenta de planilla es `6000-0111-501-013-015-00-00`: concepto,
departamento y **posición** (CLAUDE.md §12.1). El lector del Pre-Cierre guardaba
solo el nivel `concepto-departamento` y sumaba el resto sin conservar el código,
así que la planilla real únicamente se podía mirar por departamento: no había
forma de contestar «cuánto costaron los Room Attendants este mes».

El dato SIEMPRE estuvo en el archivo —244 filas en agosto 2026—; lo que faltaba
era guardarlo.

## Tabla aparte, no una fila más en `precierre_fila`

Todo lo que consume `precierre_fila` suma `mes_usd`. Meter ahí el subdetalle
duplicaría cada monto —el padre ya lo suma— y cada consulta tendría que
acordarse de filtrar. La que se olvidara no fallaría: daría un número más alto
y cuadraría consigo misma, que es el modo de falla caro de este sistema.

## Verificado antes de escribir la migración

Las 244 filas de posición de agosto 2026 suman US$227.497,60: **exactamente**
el total de planilla del nivel cuenta, al centavo. No es un total nuevo, es el
mismo abierto por quién lo cobra.

⚠️ Los borradores YA subidos no tienen este detalle: se llena al leer el
archivo. Hay que volver a subir el mes para verlo.

Revision ID: 143
Revises: 142
"""
import sqlalchemy as sa
from alembic import op

revision = "143"
down_revision = "142"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "precierre_posicion",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("precierre_id", sa.String(36),
                  sa.ForeignKey("precierre.id", ondelete="CASCADE"),
                  nullable=False),   # el índice se crea abajo, por nombre
        sa.Column("fila", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cuenta", sa.String(30), nullable=False, server_default=""),
        sa.Column("cuenta_base", sa.Integer(), nullable=True),
        sa.Column("posicion", sa.String(10), nullable=False, server_default=""),
        sa.Column("depto", sa.String(10), nullable=False, server_default=""),
        sa.Column("destino_finplan", sa.String(10), nullable=False, server_default=""),
        sa.Column("descripcion", sa.String(200), nullable=False, server_default=""),
        sa.Column("mes_usd", sa.Numeric(18, 6), nullable=False, server_default="0"),
    )
    # ⚠️ Los índices se crean ACÁ y no con `index=True` en la columna.
    #
    # Con las dos cosas, alembic emite el índice dos veces con el MISMO nombre
    # autogenerado (`ix_precierre_posicion_precierre_id`): la segunda falla,
    # la migración se cae, `alembic upgrade head` corta el arranque y la app
    # NO LEVANTA. Pasó el 2026-09-10: el backend quedó en 502 y la pantalla de
    # Pre-Cierre decía «Failed to fetch», que no se parece en nada a la causa.
    op.create_index("ix_precierre_posicion_precierre_id",
                    "precierre_posicion", ["precierre_id"])
    op.create_index("ix_precierre_posicion_posicion",
                    "precierre_posicion", ["posicion"])
    op.create_index("ix_precierre_posicion_depto",
                    "precierre_posicion", ["depto"])


def downgrade() -> None:
    op.drop_table("precierre_posicion")
