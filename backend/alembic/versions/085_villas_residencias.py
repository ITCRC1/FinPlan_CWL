"""Villas y Residencias como departamentos hijos de Rooms

El owner quiere medir el costo de las villas y las residencias por separado, y
que el reparto exista A NIVEL DE GL —un asiento que redistribuye el gasto de un
departamento a otro— y no como un auxiliar por fuera.

Son HIJOS de Rooms (`parent_dept_code = '0110'`), así que consolidan dentro de
Rooms en el P&L: no aparece una línea nueva en el estado ni hay que tocar el
mapeo de reporte. Se miden aparte en los cuadros de costo y en el detalle.

El gasto sigue cayendo en 0110 desde el GL —no se recodifica ni un asiento de
historia— y de ahí se reparte a los hijos. Lo que le queda a 0110 después del
reparto ES «Rooms Standard».

También liga cada tipo de habitación con su departamento (`room_type_configs.
dept_code`): sin eso el reparto no tiene cómo saber qué noches son de Villas y
cuáles de Residencias. Vacío = el tipo se queda en 0110, que es el
comportamiento de hoy.

Revision ID: 085
Revises: 084
"""
from alembic import op
import sqlalchemy as sa

revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None

DEPTOS = [
    ("0115", "Villas", "Villas"),
    ("0116", "Residencias", "Residences"),
]


def upgrade() -> None:
    op.add_column("room_type_configs",
                  sa.Column("dept_code", sa.String(10), nullable=False,
                            server_default=""))
    for code, nombre, nombre_en in DEPTOS:
        op.execute(sa.text("""
            INSERT INTO department_catalog
                (dept_code, dept_name, name_en, default_pl_group, pl_kind,
                 is_revenue_dept, is_allocation_source, parent_dept_code,
                 display_order, active)
            VALUES
                (:c, :n, :ne, 'ROOMS', 'OPERATING', false, false, '0110', 0, true)
            ON CONFLICT (dept_code) DO NOTHING
        """).bindparams(c=code, n=nombre, ne=nombre_en))


def downgrade() -> None:
    for code, _, _ in DEPTOS:
        op.execute(sa.text("DELETE FROM department_catalog WHERE dept_code = :c")
                   .bindparams(c=code))
    op.drop_column("room_type_configs", "dept_code")
