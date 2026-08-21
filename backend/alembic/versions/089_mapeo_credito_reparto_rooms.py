"""el crédito del reparto de Rooms necesita su propia regla de mapeo

Al repartir el costo de Rooms a Villas y Residencias, el asiento deja un crédito
único en la cuenta 4999 (Distribución) sobre el departamento 0110. Esa
combinación (0110, 4999) no tenía regla: el resolvedor caía al FALLBACK y usaba
la regla de la 4999 del depto 0220, que apunta a la línea de Cafetería.

Resultado: los $92,108 que Rooms entregaba salían restando de CAFETERÍA en vez
de restar de Rooms. El GOP no se movía —por eso el Control decía «$0 se pierde»—
pero el P&L por departamento quedaba mal por los dos lados: Rooms inflado y
Cafetería desinflado en el mismo monto.

Es exactamente la trampa de la migración 079, otra vez: un crédito de reparto
sin regla no da error, se va a la línea de otro y nadie lo nota mirando el
total.

La regla manda la 4999 de 0110 a OPEX_ROOMS, que es la MISMA línea a la que van
las otras 47 cuentas del departamento (planilla y opex juntos). Así el débito
que reciben los sets —que consolidan de vuelta en Rooms— y el crédito se anulan
sobre la misma línea, que es justo lo que tiene que pasar: el P&L no cambia.

Se agrega también para 0115 y 0116 aunque hoy nunca lleven crédito: si mañana un
set reparte a otro lado, el asiento ya tiene dónde caer.

Revision ID: 089
Revises: 088
"""
from alembic import op
import sqlalchemy as sa

revision = "089"
down_revision = "088"
branch_labels = None
depends_on = None

DEPTOS = [
    ("0110", "Departamento de Habitaciones"),
    ("0115", "Villas"),
    ("0116", "Residencias"),
]
CUENTA = "4999"
LINEA = "OPEX_ROOMS"


def upgrade() -> None:
    for code, nombre in DEPTOS:
        op.execute(sa.text("""
            INSERT INTO account_mapping
                (id, active_status, report_id, report_line_code, report_line_name,
                 report_section, display_order, source_origin, source_department,
                 account_code, account_name_example, financial_nature,
                 rollup_operator, sign_rule, notes, dept_code)
            SELECT gen_random_uuid()::text, 'YES', m.report_id, m.report_line_code,
                   m.report_line_name, m.report_section, m.display_order,
                   'Allocation', :nombre, :cuenta, 'Distribucion (credito del reparto)',
                   m.financial_nature, m.rollup_operator, m.sign_rule,
                   'Credito del reparto de Rooms a sus sets. Sin esta regla el monto '
                   'se va a la linea de Cafeteria (fallback de la 4999 del 0220).',
                   :code
            FROM account_mapping m
            WHERE m.dept_code = '0110' AND m.report_line_code = :linea
            LIMIT 1
        """).bindparams(code=code, nombre=nombre, cuenta=CUENTA, linea=LINEA))


def downgrade() -> None:
    op.execute(sa.text(
        "DELETE FROM account_mapping WHERE account_code = :c AND dept_code IN "
        "('0110','0115','0116')").bindparams(c=CUENTA))
