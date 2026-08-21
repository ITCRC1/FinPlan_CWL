"""Cierra huecos de mapeo de planilla — conceptos 6xxx sin regla (plata que se perdía)

Hallazgos de la auditoría de trazabilidad:
  · 6004 (Incapacidades) existe en la planilla pero NO tenía regla en NINGÚN
    departamento → lo que se presupuestara ahí NO llegaba al P&L (DROP silencioso).
  · Departamentos sin ninguna cuenta 6xxx mapeada (ej. 0210 Utilities): la planilla
    presupuestada ahí desaparecía.

Regla: para cada departamento que ya tenga mapeada la cuenta 6000 (Salary & Wages),
se completan TODOS los conceptos de planilla faltantes apuntando a la MISMA línea
del reporte que usa ese departamento. Idempotente.

Revision ID: 071
Revises: 070
Create Date: 2026-08-07
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "071"
down_revision: Union[str, None] = "070"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Los 17 conceptos de la planilla (PayrollConceptEntry) + 6031 alias de "otros".
PAYROLL_ACCOUNTS = ["6000", "6001", "6002", "6003", "6004", "6010", "6020", "6021",
                    "6022", "6023", "6024", "6025", "6026", "6027", "6028", "6029",
                    "6030"]
REPORT_ID = "P&L_DETAIL_OWNERS"


def upgrade() -> None:
    conn = op.get_bind()
    # Departamento → línea destino de su planilla (se toma de la cuenta 6000).
    base = conn.execute(sa.text(
        "SELECT dept_code, source_department, report_line_code, report_line_name, "
        "       report_section, display_order "
        "FROM account_mapping "
        "WHERE report_id = :rid AND account_code = '6000' AND active_status = 'YES'"
    ), {"rid": REPORT_ID}).fetchall()

    added = 0
    for b in base:
        if not b.report_line_code:
            continue
        # Se filtra en Python para no depender del binding de arrays del driver.
        existing = {r.account_code for r in conn.execute(sa.text(
            "SELECT account_code FROM account_mapping "
            "WHERE report_id = :rid AND source_department = :dep"
        ), {"rid": REPORT_ID, "dep": b.source_department}).fetchall()
            if r.account_code in PAYROLL_ACCOUNTS}
        for acct in PAYROLL_ACCOUNTS:
            if acct in existing:
                continue
            conn.execute(sa.text(
                "INSERT INTO account_mapping "
                "(id, active_status, report_id, report_line_code, report_line_name, "
                " report_section, display_order, source_origin, source_department, "
                " dept_code, account_code, account_name_example, financial_nature, "
                " rollup_operator, notes) "
                "VALUES (:id,'YES',:rid,:lc,:ln,:sec,:ord,'PAYROLL',:dep,:dc,:acc,"
                "        :nm,'Expense','SUM','auto: hueco de planilla cerrado (mig 071)')"
            ), {"id": str(uuid.uuid4()), "rid": REPORT_ID, "lc": b.report_line_code,
                "ln": b.report_line_name, "sec": b.report_section,
                "ord": b.display_order, "dep": b.source_department,
                "dc": b.dept_code, "acc": acct, "nm": f"Payroll {acct}"})
            added += 1
    print(f"[071] reglas de planilla agregadas: {added}")


def downgrade() -> None:
    op.get_bind().execute(sa.text(
        "DELETE FROM account_mapping WHERE notes = "
        "'auto: hueco de planilla cerrado (mig 071)'"))
