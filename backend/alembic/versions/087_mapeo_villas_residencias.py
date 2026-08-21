"""mapeo contable de Villas y Residencias — payroll y opex

Villas (0115) y Residencias (0116) nacieron sin NINGUNA fila en `account_mapping`.
Sin mapeo, una cuenta cargada en esos departamentos no da error: cae al fallback
del motor y aterriza en overhead **en silencio**. Es la trampa que ya nos mordió
antes (la planilla que se iba entera a OPEX_ROOMS, la 6004 sin mapear).

Se clonan las 48 filas de Rooms (0110) para cada set: 17 cuentas de planilla
(6000–6030), 30 de opex (7xxx) y 1 de revenue (4000). Apuntan a las MISMAS líneas
de reporte que Rooms —OPEX_ROOMS y REV_ROOMS— porque los sets son hijos y el
summary siempre consolida: el P&L no cambia, la apertura por set vive en la vista
de reporting.

Revision ID: 087
Revises: 086
"""
from alembic import op
import sqlalchemy as sa

revision = "087"
down_revision = "086"
branch_labels = None
depends_on = None

SETS = [("0115", "Villas"), ("0116", "Residencias")]
ORIGEN = "0110"


def upgrade() -> None:
    for code, nombre in SETS:
        op.execute(sa.text("""
            INSERT INTO account_mapping
                (id, active_status, report_id, report_line_code, report_line_name,
                 report_section, display_order, source_origin, source_department,
                 account_code, account_name_example, financial_nature,
                 rollup_operator, sign_rule, notes, dept_code)
            SELECT gen_random_uuid()::text, active_status, report_id,
                   report_line_code, report_line_name, report_section,
                   display_order, source_origin, :nombre, account_code,
                   account_name_example, financial_nature, rollup_operator,
                   sign_rule, notes, :code
            FROM account_mapping
            WHERE dept_code = :origen
              AND NOT EXISTS (
                  SELECT 1 FROM account_mapping m2
                  WHERE m2.dept_code = :code
                    AND m2.account_code = account_mapping.account_code
                    AND m2.report_line_code = account_mapping.report_line_code)
        """).bindparams(code=code, nombre=nombre, origen=ORIGEN))


def downgrade() -> None:
    for code, _ in SETS:
        op.execute(sa.text("DELETE FROM account_mapping WHERE dept_code = :c")
                   .bindparams(c=code))
