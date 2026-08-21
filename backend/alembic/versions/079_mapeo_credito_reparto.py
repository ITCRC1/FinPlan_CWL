"""La cuenta 4999 —el credito del reparto— necesita regla de mapeo.

Los repartos de cafeteria y lavanderia ahora si entran al P&L. Cada uno tiene
dos lados: el CARGO a los departamentos que consumen y el CREDITO al que
reparte, que es lo que deja al 0161 y al 0220 en cero.

El cargo ya tenia mapeo —son cuentas normales, 7310, 7685, 6025—. El credito
va a la 4999, que no tenia ninguna regla: se habria caido en el camino y el
gasto total del hotel habria subido por el monto repartido sin que nada lo
avisara.

  (0161, 4999) -> OH_LAUNDRY     alivia a lavanderia de lo que repartio
  (0220, 4999) -> OH_CAFETERIA   alivia a cafeteria de lo mismo

Con esto el reparto netea a cero en el P&L, igual que en el asiento contable:
lo unico que cambia es en que linea queda cada colon, no cuanto suma.

Revision ID: 079
Revises: 078
"""
import uuid

from alembic import op
import sqlalchemy as sa

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None

REPORT_ID = "P&L_DETAIL_OWNERS"
CUENTA = "4999"

# {departamento que reparte: linea del P&L que hay que aliviar}
CREDITOS = {
    "0161": "OH_LAUNDRY",
    "0220": "OH_CAFETERIA",
}


def upgrade() -> None:
    conn = op.get_bind()

    for dept, linea in CREDITOS.items():
        ya = conn.execute(sa.text("""
            SELECT 1 FROM account_mapping
             WHERE report_id = :rid AND dept_code = :d AND account_code = :a
        """), {"rid": REPORT_ID, "d": dept, "a": CUENTA}).first()
        if ya:
            continue

        # Nombre y seccion salen de la propia linea, para no inventarlos.
        cab = conn.execute(sa.text("""
            SELECT report_line_name, report_section, display_order, source_department
              FROM account_mapping
             WHERE report_id = :rid AND report_line_code = :lc AND active_status = 'YES'
             LIMIT 1
        """), {"rid": REPORT_ID, "lc": linea}).first()
        if not cab:
            continue      # base sin esa linea: nada que enganchar

        conn.execute(sa.text("""
            INSERT INTO account_mapping
                (id, active_status, report_id, report_line_code, report_line_name,
                 report_section, display_order, source_origin, source_department,
                 account_code, account_name_example, financial_nature,
                 rollup_operator, dept_code)
            VALUES
                (:id, 'YES', :rid, :lc, :ln, :sec, :ord, 'Allocation', :sd,
                 :a, 'Expense Distribution', 'Expense', 'SUM', :d)
        """), {
            "id": str(uuid.uuid4()), "rid": REPORT_ID, "lc": linea,
            "ln": cab[0], "sec": cab[1], "ord": cab[2], "sd": cab[3],
            "a": CUENTA, "d": dept,
        })


def downgrade() -> None:
    op.get_bind().execute(sa.text("""
        DELETE FROM account_mapping
         WHERE report_id = :rid AND account_code = :a AND dept_code IN ('0161', '0220')
    """), {"rid": REPORT_ID, "a": CUENTA})
