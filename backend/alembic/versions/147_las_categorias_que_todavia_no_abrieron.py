# -*- coding: utf-8 -*-
"""Una categoría de habitación puede existir a partir de un año.

Owner, 2026-09-16, viendo la carga de estadísticas de agosto 2026: *«esto no
aplica todavía para el 2026»* · *«sí está para 2027 pero no para 2026»*, sobre
**Villas Deluxe** (2 unidades) y **Residencia** (1).

## Por qué no alcanzaba `active`

`active` es un sí/no sin fecha. Apagarlas arreglaba 2026 y las escondía también
de 2027, donde sí van a abrir — y el día que abrieran, alguien tenía que
acordarse de encenderlas. Con el año, el cambio ocurre solo.

## Qué estaban haciendo mientras tanto

Aparecían en la carga con sus NOCHES DISPONIBLES (62 y 31 en agosto) pero sin
sumar a las unidades: el cuadro decía 30 unidades y contaba 93 noches que no
existen. Eso infla el denominador de la ocupación y del RevPAR, así que los dos
salían más bajos de lo real — sin error, sin aviso, y en la dirección que nadie
sospecha.

Revision ID: 147
Revises: 146
"""
import sqlalchemy as sa
from alembic import op

revision = "147"
down_revision = "146"
branch_labels = None
depends_on = None

#: Las dos que el owner marcó. Se buscan por nombre porque el `code` canónico
#: todavía no está asignado para estas dos, y el nombre es lo que se ve en
#: pantalla — si no coincide, el UPDATE no toca nada y no rompe nada.
DESDE_2027 = ("Villas Deluxe", "Residencia")


def upgrade() -> None:
    op.add_column("room_type_configs",
                  sa.Column("vigente_desde_anio", sa.Integer(), nullable=True))
    op.execute(sa.text(
        "UPDATE room_type_configs SET vigente_desde_anio = 2027 "
        "WHERE name IN :nombres"
    ).bindparams(sa.bindparam("nombres", value=DESDE_2027, expanding=True)))


def downgrade() -> None:
    op.drop_column("room_type_configs", "vigente_desde_anio")
