"""El carril de espera del cierre: `precierre` y `precierre_fila`.

Un pre-cierre es el mes traducido desde Integrity, revisado, y todavia NO
escrito. Hasta hoy el cierre entraba de una y la revision pasaba por el ojo de
una persona sobre un Excel de 104 MB.

⚠️ NO es un escenario: ningun reporte lo lee. Si se filtrara habria dos
versiones del mismo mes conviviendo y la pregunta «cual es el bueno» no tendria
respuesta desde adentro del sistema.

Se agrega ademas `monto` a la cola de excepciones de Guillermo. Los hallazgos
del pre-cierre van a ESA cola y no a una nueva —dos colas de hallazgos son peor
que una: «una cola asi se aprende a ignorar»— pero sin el monto no hay forma de
saber si un hallazgo es ruido o si falta media operacion.

Revision ID: 138
Revises: 137
"""
from alembic import op
import sqlalchemy as sa

revision = "138"
down_revision = "137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "precierre",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("hotel_id", sa.String(10), nullable=False, index=True),
        sa.Column("anio", sa.Integer, nullable=False),
        sa.Column("mes", sa.Integer, nullable=False),
        # El TC es parte del RESULTADO: el mismo archivo con otro tipo de cambio
        # da otro P&L, y sin guardarlo no se podria reproducir lo que se reviso.
        sa.Column("tc", sa.Numeric(12, 4), nullable=False),
        sa.Column("archivo_nombre", sa.String(255), nullable=False, server_default=""),
        sa.Column("checksum", sa.String(64), nullable=False, server_default="", index=True),
        sa.Column("estado", sa.String(16), nullable=False, server_default="borrador",
                  index=True),
        sa.Column("subido_por", sa.String(120), nullable=False, server_default=""),
        sa.Column("creado_en", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("hallazgos_abiertos", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hallazgos", sa.Text, nullable=False, server_default=""),
        # Los hallazgos de los niveles 1 y 2, calculados AL SUBIR. Dependen de
        # cosas que el lector produce y que no se guardan —las filas sin cuenta,
        # el subdetalle, los departamentos sin puente—, asi que no se pueden
        # recalcular despues sin volver a leer el archivo. Los niveles 3 y 4 si
        # se recalculan en cada consulta: dependen de los auxiliares y de los
        # escenarios, que cambian.
        sa.Column("hallazgos_archivo", sa.Text, nullable=False, server_default=""),
        sa.Column("escenario_destino_id", sa.String(36),
                  sa.ForeignKey("scenarios.id", ondelete="SET NULL"), nullable=True),
        sa.Column("pasado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pasado_por", sa.String(120), nullable=False, server_default=""),
    )
    # ⚠️ Un solo BORRADOR vivo por mes — indice PARCIAL, no una unique de cuatro
    # columnas.
    #
    # El Integrity se sube muchas veces durante la revision: se corrige un error
    # de posteo y se vuelve a subir, hasta llegar al final acordado. Cada subida
    # descarta la anterior, asi que un mes acumula N descartados. Con una unique
    # sobre (hotel, anio, mes, estado) la TERCERA subida reventaba, porque ya
    # habria dos filas «descartado» del mismo mes.
    #
    # Los descartados y los pasados no compiten: son historia, y con ellos queda
    # la traza de cuantas vueltas llevo cerrar el mes.
    op.create_index("uq_precierre_borrador_vivo", "precierre",
                    ["hotel_id", "anio", "mes"], unique=True,
                    postgresql_where=sa.text("estado = 'borrador'"))
    op.create_table(
        "precierre_fila",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("precierre_id", sa.String(36),
                  sa.ForeignKey("precierre.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        # La fila del Excel de origen: sin esto un hallazgo no se puede ir a mirar.
        sa.Column("fila", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cuenta", sa.String(30), nullable=False, server_default=""),
        sa.Column("cuenta_base", sa.Integer, nullable=True),
        sa.Column("descripcion", sa.String(200), nullable=False, server_default=""),
        sa.Column("depto", sa.String(10), nullable=False, server_default="", index=True),
        # Los dos sistemas NO comparten espacio de codigos: Integrity 0130 es el
        # Restaurant Terra Kitchen y FinPlan 0130 es «Spa (gerencia)».
        sa.Column("destino_finplan", sa.String(10), nullable=False, server_default=""),
        # Vacio es un estado valido: los departamentos que se abren POR CUENTA
        # (280 Miscelaneos) no tienen grupo, y ponerles uno los rotularia mal.
        sa.Column("grupo", sa.String(30), nullable=False, server_default=""),
        sa.Column("categoria", sa.String(20), nullable=False, server_default=""),
        # SEIS decimales: el dolar sale de dividir colones entre el TC y casi
        # nunca es exacto. Con dos se redondeaban las 325 filas antes de sumar y
        # la utilidad neta de julio daba -94.182,93 en vez de -94.182,95.
        sa.Column("mes_usd", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("acumulado_usd", sa.Numeric(18, 6), nullable=False, server_default="0"),
    )
    # El monto del hallazgo, en la cola que ya existe.
    op.add_column("guillermo_import_exceptions",
                  sa.Column("monto", sa.Numeric(16, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("guillermo_import_exceptions", "monto")
    op.drop_index("uq_precierre_borrador_vivo", table_name="precierre")
    op.drop_table("precierre_fila")
    op.drop_table("precierre")
