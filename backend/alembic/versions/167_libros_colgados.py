"""Mis libros: los Excels del owner en un solo lugar.

Owner, 2026-11-24: «quiero ir a un lugar solo y bajar mis proyectos, mis
creaciones, pero que no se rompa nada» y «no quiero llenarme de versiones».
Un libro por título; subir de nuevo lo reemplaza y guarda solo la versión
anterior. Ver `app/models/libro_colgado.py`.

Revision ID: 167
Revises: 166
"""
import sqlalchemy as sa
from alembic import op

revision = "167"
down_revision = "166"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "libros_colgados",
        sa.Column("id", sa.String(36), primary_key=True),
        # Sin default de columna: el hotel lo pone el modelo con HOTEL_ID (esta
        # migración corre en las cuatro propiedades).
        sa.Column("hotel_id", sa.String(10), nullable=False),
        sa.Column("titulo", sa.String(160), nullable=False),
        sa.Column("nombre_archivo", sa.String(200), nullable=False),
        sa.Column("contenido", sa.LargeBinary(), nullable=False),
        sa.Column("tamano", sa.Integer(), nullable=False),
        sa.Column("nota", sa.String(500), nullable=True),
        sa.Column("subido_por", sa.String(160), nullable=True),
        sa.Column("subido_el", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  nullable=False),
        sa.Column("anterior_nombre", sa.String(200), nullable=True),
        sa.Column("anterior_contenido", sa.LargeBinary(), nullable=True),
        sa.Column("anterior_tamano", sa.Integer(), nullable=True),
        sa.Column("anterior_subido_por", sa.String(160), nullable=True),
        sa.Column("anterior_subido_el", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("hotel_id", "titulo", name="uq_libro_titulo"),
    )


def downgrade():
    op.drop_table("libros_colgados")
