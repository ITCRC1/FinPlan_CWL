"""Le faltaba al 0190 Mercadeo la regla de la 7685 (lavado de uniformes).

El reparto de lavanderia le carga uniformes a Mercadeo, pero el par
(0190, 7685) no tenia regla. El motor lo resolvia con el ultimo recurso
—cualquier regla que use la 7685— y ganaba la del 0110, asi que esos
$2,200.35 anuales terminaban en OPEX_ROOMS.

Los demas sub-departamentos del reparto (0122 Cocina, 0123 Restaurante, 0132
Spa, 0182 Finance, 0183 Purchasing, 0186 Security…) ya se arreglan solos
porque el motor ahora sube al departamento PADRE antes de rendirse. El 0190 no
tiene padre: es un departamento de primer nivel al que simplemente le faltaba
esta cuenta.

Revision ID: 078
Revises: 077
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None

REPORT_ID = "P&L_DETAIL_OWNERS"
DEPT = "0190"
CUENTA = "7685"


def upgrade() -> None:
    conn = op.get_bind()

    # Si alguien ya la creo a mano, no la duplicamos.
    ya = conn.execute(sa.text("""
        SELECT 1 FROM account_mapping
         WHERE report_id = :rid AND dept_code = :d AND account_code = :a
    """), {"rid": REPORT_ID, "d": DEPT, "a": CUENTA}).first()
    if ya:
        return

    # Copiamos los datos de cabecera de las reglas que el 0190 ya tiene, para
    # que la linea nueva quede identica a sus hermanas y no invente nombres.
    hermana = conn.execute(sa.text("""
        SELECT report_line_code, report_line_name, report_section, display_order,
               source_department
          FROM account_mapping
         WHERE report_id = :rid AND dept_code = :d AND active_status = 'YES'
         LIMIT 1
    """), {"rid": REPORT_ID, "d": DEPT}).first()
    if not hermana:
        return          # base sin el 0190: nada que enganchar

    conn.execute(sa.text("""
        INSERT INTO account_mapping
            (id, active_status, report_id, report_line_code, report_line_name,
             report_section, display_order, source_origin, source_department,
             account_code, account_name_example, financial_nature,
             rollup_operator, dept_code)
        VALUES
            (:id, 'YES', :rid, :lc, :ln, :sec, :ord, 'OpEx', :sd,
             :a, 'Uniform Laundry', 'Expense', 'SUM', :d)
    """), {
        "id": str(uuid.uuid4()), "rid": REPORT_ID,
        "lc": hermana[0], "ln": hermana[1], "sec": hermana[2], "ord": hermana[3],
        "sd": hermana[4], "a": CUENTA, "d": DEPT,
    })


def downgrade() -> None:
    op.get_bind().execute(sa.text("""
        DELETE FROM account_mapping
         WHERE report_id = :rid AND dept_code = :d AND account_code = :a
    """), {"rid": REPORT_ID, "d": DEPT, "a": CUENTA})
