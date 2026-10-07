# -*- coding: utf-8 -*-
"""La subida ANTERIOR del mayor, para poder comparar contra la nueva.

Owner, 2026-10-07: *«voy a volver a subir el audit pero tengo un problema…
dijimos que solo guardamos una version por mes, pero hicimos cambios en esta
version, y cómo sé qué cambió con respecto a la primera. Tendrías que guardar 2
versiones para poder comparar el nuevo versus el anterior y ver si los cambios
quedaron»*.

## Por qué una tabla aparte y no una columna «vigente»

⚠️ Si `mayor_movimientos` pudiera tener dos versiones del mismo mes, **cualquier
consulta que olvide filtrar la vigente cuenta todo dos veces**. Es el modo de
falla más caro de este sistema: el total cuadra consigo mismo, no hay error, y la
plata está mal. Ya pasó con el `4999` contado dos veces y con las tres hojas del
Full Detail.

Con la anterior en su propia tabla, ese olvido es **imposible**:
`mayor_movimientos` sigue teniendo exactamente un mes por fila-mes, como desde
la migración 151, y nadie más que la comparación mira acá.

El costo es el espacio de una copia: medido, el año entero son 12 MB con el
archivo del owner y 23 MB con el *Full Detail*. Duplicarlo no mueve la aguja.

**Se guarda UNA anterior, no un historial.** La pregunta es «¿quedaron los
cambios que hice?», y eso se contesta con la de antes. Un historial completo
traería la pregunta de cuál era la buena, que es peor que no tenerlo.
"""
import sqlalchemy as sa
from alembic import op

revision = "152"
down_revision = "151"
branch_labels = None
depends_on = None

#: Las mismas columnas que `mayor_movimientos`, escritas a mano porque una
#: migración es una foto congelada y no puede depender de un modelo que mañana
#: cambie.
#:
#: ⚠️ Que las dos tablas no se separen lo vigila
#: `test_el_mayor_guardado.test_las_dos_tablas_tienen_las_MISMAS_columnas`: si
#: alguien le agrega una columna a una y no a la otra, la copia de la anterior
#: perdería ese dato en silencio.
COLS = [
    ("hotel_id", sa.String(10)), ("anio", sa.Integer), ("mes", sa.Integer),
    ("cuenta", sa.String(40)), ("seg1", sa.String(6)), ("seg2", sa.String(6)),
    ("seg3", sa.String(6)), ("asiento", sa.String(20)), ("linea", sa.String(10)),
    ("fecha", sa.String(20)), ("descripcion", sa.String(250)),
    ("desc_asiento", sa.String(250)), ("origen", sa.String(20)),
    ("referencia", sa.String(120)), ("num_doc", sa.String(40)),
    ("moneda", sa.String(10)), ("archivo", sa.String(255)), ("checksum", sa.String(64)),
    ("subido_por", sa.String(120)),
]
NUM = [("debito", sa.Numeric(18, 4)), ("credito", sa.Numeric(18, 4)),
       ("tc", sa.Numeric(12, 4))]


def upgrade() -> None:
    cols = [sa.Column("id", sa.String(36), primary_key=True)]
    for nombre, tipo in COLS:
        cols.append(sa.Column(nombre, tipo, nullable=False, server_default=""))
    for nombre, tipo in NUM:
        cols.append(sa.Column(nombre, tipo, nullable=False, server_default="0"))
    cols.append(sa.Column("subido_en", sa.DateTime(timezone=True)))
    # Cuándo dejó de ser la vigente. Es lo único que esta tabla tiene de más:
    # la pantalla dice «comparado contra la subida del …».
    cols.append(sa.Column("reemplazado_en", sa.DateTime(timezone=True)))
    op.create_table("mayor_movimientos_previos", *cols)
    op.create_index("ix_mayor_prev_mes", "mayor_movimientos_previos",
                    ["hotel_id", "anio", "mes"])
    op.create_index("ix_mayor_prev_mes_cuenta", "mayor_movimientos_previos",
                    ["hotel_id", "anio", "mes", "cuenta"])


def downgrade() -> None:
    op.drop_table("mayor_movimientos_previos")
