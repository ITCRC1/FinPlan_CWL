"""0184 pasa a ser RRHH, hijo de 0180, y se lleva la planilla de Administración

Administración es un departamento de GASTO y padre de los demás: 0181
Management, 0182 Finance, 0183 Purchasing, 0186 Security y ahora 0184. La
planilla vive en los hijos; 0180 no debería tener ninguna (owner, 2026-08-11).

Hoy tiene una: `0180-01 RRHH COORDINATOR-TRAINER (Outsourcing)`, en las seis
versiones del Budget 2027. Es exactamente la que corresponde a Recursos
Humanos, así que se muda a 0184 y su código pasa a `0184-01` — el código lleva
el departamento adentro y dejarlo como 0180-01 haría que el correlativo del
depto quedara mintiendo.

Tres cosas que hay que hacer en orden, porque cada una depende de la anterior:

1. **0184 cuelga de 0180.** Hoy NO tiene padre, y sin padre el motor no lo
   consolida: la planilla que se le mueva caería al fallback en vez de a
   OH_ADMIN. Los otros hijos (0182, 0183, 0186) tampoco tienen mapeo propio y
   funcionan bien justamente porque su padre los absorbe.
2. **Se clonan las 52 reglas de mapeo de 0180.** El camino del checkbook se
   resuelve por el padre, pero el de los ACTUALES mapea por departamento
   directo y ahí sí haría falta. Es la trampa que ya mordió dos veces (la 6004
   sin mapear, Villas sin mapeo).
3. **Se mueve la posición y sus 12 filas de conceptos.** `payroll_concept_entries`
   lleva su propio `dept_code`; sin actualizarlo, la planilla seguiría sumando
   en 0180 aunque la posición ya viviera en 0184.

**El P&L no se mueve:** 0184 consolida en 0180 y las dos rutas terminan en
OH_ADMIN.

Por último se apaga la dimensión PLANILLA de 0180 en la matriz de
provisionamiento, que es justo para lo que existe: el departamento deja de
ofrecerse como destino de planilla sin que nadie tenga que acordarse de la
regla.

**No se crea 0185.** El owner dijo «0185, seguro también», pero un departamento
que no existe no se inventa por si acaso: hay que decidir qué es antes de
abrirlo.

Revision ID: 092
Revises: 091
"""
from alembic import op
import sqlalchemy as sa

revision = "092"
down_revision = "091"
branch_labels = None
depends_on = None

PADRE = "0180"
RRHH = "0184"


def upgrade() -> None:
    # 1. 0184 = RRHH, hijo de Administración
    op.execute(sa.text(
        "UPDATE department_catalog SET dept_name = 'RRHH', name_en = 'Human Resources', "
        "parent_dept_code = :p WHERE dept_code = :c"
    ).bindparams(p=PADRE, c=RRHH))

    # 2. Mapeo contable propio (para el camino de los actuales, que no consolida)
    op.execute(sa.text("""
        INSERT INTO account_mapping
            (id, active_status, report_id, report_line_code, report_line_name,
             report_section, display_order, source_origin, source_department,
             account_code, account_name_example, financial_nature,
             rollup_operator, sign_rule, notes, dept_code)
        SELECT gen_random_uuid()::text, active_status, report_id, report_line_code,
               report_line_name, report_section, display_order, source_origin,
               'RRHH', account_code, account_name_example, financial_nature,
               rollup_operator, sign_rule, notes, :c
        FROM account_mapping
        WHERE dept_code = :p
          AND NOT EXISTS (
              SELECT 1 FROM account_mapping m2
              WHERE m2.dept_code = :c
                AND m2.account_code = account_mapping.account_code
                AND m2.report_line_code = account_mapping.report_line_code)
    """).bindparams(p=PADRE, c=RRHH))

    # 3. La planilla REAL de 0180 se muda a RRHH. Las filas sintéticas del GL
    #    (position_code = 'GL') se quedan: no son personas, traen el costo real
    #    del departamento y moverlas reescribiría los actuales.
    op.execute(sa.text("""
        UPDATE payroll_concept_entries SET dept_code = :c
        WHERE position_id IN (
            SELECT id FROM payroll_positions
            WHERE dept_code = :p AND position_code <> 'GL')
    """).bindparams(p=PADRE, c=RRHH))
    op.execute(sa.text("""
        UPDATE payroll_positions
           SET dept_code = :c,
               dept_name = 'RRHH',
               position_code = REPLACE(position_code, :p || '-', :c || '-')
         WHERE dept_code = :p AND position_code <> 'GL'
    """).bindparams(p=PADRE, c=RRHH))

    # 4. Administración deja de ofrecerse como destino de planilla
    op.execute(sa.text("""
        INSERT INTO dept_enablement
            (id, hotel_id, scope_kind, scope_key, dimension, enabled, notes, updated_at)
        SELECT gen_random_uuid()::text, h.id, 'DEPT', :p, 'PAYROLL', false,
               'Administracion es depto de gasto y padre de los demas: la planilla vive en los hijos.',
               NOW()
        FROM hotels h
        WHERE NOT EXISTS (
            SELECT 1 FROM dept_enablement d
            WHERE d.hotel_id = h.id AND d.scope_kind = 'DEPT'
              AND d.scope_key = :p AND d.dimension = 'PAYROLL')
    """).bindparams(p=PADRE))


def downgrade() -> None:
    op.execute(sa.text("""
        UPDATE payroll_concept_entries SET dept_code = :p
        WHERE position_id IN (
            SELECT id FROM payroll_positions
            WHERE dept_code = :c AND position_code <> 'GL')
    """).bindparams(p=PADRE, c=RRHH))
    op.execute(sa.text("""
        UPDATE payroll_positions
           SET dept_code = :p, dept_name = 'Administracion',
               position_code = REPLACE(position_code, :c || '-', :p || '-')
         WHERE dept_code = :c AND position_code <> 'GL'
    """).bindparams(p=PADRE, c=RRHH))
    op.execute(sa.text(
        "DELETE FROM account_mapping WHERE dept_code = :c").bindparams(c=RRHH))
    op.execute(sa.text(
        "DELETE FROM dept_enablement WHERE scope_key = :p AND dimension = 'PAYROLL'"
    ).bindparams(p=PADRE))
    op.execute(sa.text(
        "UPDATE department_catalog SET dept_name = 'Administracion', name_en = '', "
        "parent_dept_code = NULL WHERE dept_code = :c").bindparams(c=RRHH))
