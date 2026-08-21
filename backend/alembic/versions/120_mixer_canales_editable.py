# -*- coding: utf-8 -*-
"""El mixer deja de ser una lista fija: se pueden crear y borrar canales.

Owner, 2026-08-17: *«tenés que dejarme crear más mix y borrar también, y que el
derivado lo tome… inclusive se pueden crear más canales y sub-canales, pero
deben estar sincronizados para que ruede donde corresponde»*.

## Las dos cosas que faltaban, y por qué la segunda es la que muerde

1. **No había cómo crear ni borrar.** `canales_comerciales` se llenaba solo por
   seed; la grilla era fija en siete.

2. **⚠️ El «rueda a» no era un dato: era un diccionario en el código.**

       ENTRADA_A_COMISION = {"Travel Agent": "TA", "OTA": "OTA",
                             "Direct Client": "DIRECT", "Website": "DIRECT",
                             "INHOUSE": "DIRECT", "": "DIRECT"}
       destino = ENTRADA_A_COMISION.get(c.entrada, "DIRECT")   # <- el default

   Ese `"DIRECT"` final es exactamente el «no rueda donde corresponde»: un
   sub-canal nuevo cuya `entrada` no estuviera en esa lista caía a DIRECT **en
   silencio**. Y DIRECT paga 9,27% de comisión contra el 30% de TA, así que el
   ingreso salía **de más**. No fallaba: facturaba mal.

Esta migración convierte las dos cosas en DATO:

* `canales_comerciales.rueda_a` — a qué canal de comisión va, editable.
* `canales_comision` — la tabla de destinos, para que TA/OTA/DIRECT dejen de ser
  una constante de tres y se pueda agregar un cuarto.

## No mueve un número

El backfill copia exactamente lo que hoy resuelve el diccionario, incluido el
default: los siete canales de CWL quedan con el mismo destino que ya tenían.
Verificado con la foto de ingreso de los tres presupuestos antes y después.

Revision ID: 120
Revises: 119
"""
from alembic import op
import sqlalchemy as sa

revision = "120"
down_revision = "119"
branch_labels = None
depends_on = None


#: El diccionario que vivía en `mixer_canales.ENTRADA_A_COMISION`, usado UNA vez
#: para el backfill y después nunca más: a partir de acá manda la columna.
_ENTRADA_A_COMISION = {
    "Travel Agent": "TA",
    "OTA": "OTA",
    "Direct Client": "DIRECT",
    "Website": "DIRECT",
    "INHOUSE": "DIRECT",
    "": "DIRECT",
}

_DESTINOS = [
    ("TA", "Travel Agency", 1),
    ("OTA", "OTAs", 2),
    ("DIRECT", "Direct", 3),
]


def upgrade() -> None:
    # ── La tabla de destinos ─────────────────────────────────────────────────
    op.create_table(
        "canales_comision",
        sa.Column("code", sa.String(30), primary_key=True),
        sa.Column("nombre", sa.String(120), nullable=False, server_default=""),
        sa.Column("orden", sa.Integer, nullable=False, server_default="0"),
        sa.Column("activo", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    for code, nombre, orden in _DESTINOS:
        op.execute(
            sa.text("INSERT INTO canales_comision (code, nombre, orden, activo) "
                    "VALUES (:c, :n, :o, true) ON CONFLICT (code) DO NOTHING")
            .bindparams(c=code, n=nombre, o=orden))

    # ── El destino, como columna ─────────────────────────────────────────────
    #
    # Arranca vacía y se rellena con lo que el diccionario resolvía, para que el
    # cambio sea invisible en los números. Después queda NOT NULL: un sub-canal
    # sin destino no puede existir — es justo el estado que hacía que rodara a
    # DIRECT sin que nadie lo decidiera.
    op.add_column("canales_comerciales",
                  sa.Column("rueda_a", sa.String(30), nullable=True))
    for entrada, destino in _ENTRADA_A_COMISION.items():
        op.execute(
            sa.text("UPDATE canales_comerciales SET rueda_a = :d "
                    "WHERE COALESCE(entrada, '') = :e AND rueda_a IS NULL")
            .bindparams(d=destino, e=entrada))
    # Cualquier `entrada` que el diccionario no contemplaba resolvía por el
    # default. Se escribe explícito para que se pueda VER y corregir.
    op.execute("UPDATE canales_comerciales SET rueda_a = 'DIRECT' WHERE rueda_a IS NULL")
    op.alter_column("canales_comerciales", "rueda_a", nullable=False)
    op.create_foreign_key("fk_canal_rueda_a", "canales_comerciales",
                          "canales_comision", ["rueda_a"], ["code"],
                          ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_canal_rueda_a", "canales_comerciales", type_="foreignkey")
    op.drop_column("canales_comerciales", "rueda_a")
    op.drop_table("canales_comision")
