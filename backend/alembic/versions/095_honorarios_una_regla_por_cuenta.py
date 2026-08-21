"""honorarios de administración: dos líneas, una sola regla de cuenta

**La decisión (A3 del plan):** las DOS líneas se quedan abiertas. El 3% de
management fee y el 5% de royalties son conceptos distintos —el fee va a The
Costa Rica Collection, los royalties son otra cosa— aunque el GL los junte en la
cuenta `8005` y el Excel de Amarena los muestre en una sola línea.
`TOTAL_RENT_MGMT_FEES` las vuelve a sumar, así que el consolidado sale idéntico
en las dos lecturas y no se pierde detalle.

**El defecto que había.** La cuenta `8005` del departamento `0250` tenía DOS
reglas activas en `account_mapping`, una hacia cada línea. El resolvedor
(`construir_resolvedor`) hace `setdefault` sobre `(depto, cuenta)`: **gana la
fila que esté físicamente primero en la tabla**. Es decir, todo el monto de la
8005 aterrizaba entero en una de las dos líneas, y cuál dependía del orden de
inserción — que cambia cada vez que se recarga el mapeo desde el Excel.

**El arreglo.** Misma doctrina que la cuenta 8020 (migración 093): cuando una
cuenta del GL carga dos líneas del reporte, **una sola regla de cuenta** —la
línea por defecto— y la otra se alimenta a nivel línea (el porcentaje de
`pl_manual_inputs`, o el mini-checkbook `nonop_entries`). Acá la regla por
defecto es `MGMT_FEE_3`; la de `MGMT_FEE_5_ROYALTIES` queda **desactivada**, no
borrada, para que se vea que fue una decisión y no un olvido.

La regla de la 8005 del depto `260` (Club Madresal → MGMT_FEE_3) no se toca: es
otro departamento, no compite.

**Cuánto se mueve:** nada. En los escenarios importados el P&L se lee del
snapshot por línea; en los del checkbook el fee sale del porcentaje. La regla
desactivada solo elimina la ambigüedad para el día que un escenario se arme
desde el detalle de cuentas.

Revision ID: 095
Revises: 094
"""
from alembic import op
import sqlalchemy as sa

revision = "095"
down_revision = "094"
branch_labels = None
depends_on = None

REPORT_ID = "P&L_DETAIL_OWNERS"
NOTA = (
    "Desactivada a proposito: la cuenta 8005 carga MGMT_FEE_3 y "
    "MGMT_FEE_5_ROYALTIES, y el resolvedor solo admite una regla por "
    "(departamento, cuenta). La linea por defecto es MGMT_FEE_3; los royalties "
    "se alimentan a nivel linea (porcentaje o nonop_entries). Ver migracion 093."
)


def upgrade() -> None:
    op.execute(sa.text(
        "UPDATE account_mapping SET active_status='NO', notes=:n "
        "WHERE report_id=:r AND account_code='8005' "
        "  AND report_line_code='MGMT_FEE_5_ROYALTIES'"
    ).bindparams(n=NOTA, r=REPORT_ID))


def downgrade() -> None:
    op.execute(sa.text(
        "UPDATE account_mapping SET active_status='YES', notes=NULL "
        "WHERE report_id=:r AND account_code='8005' "
        "  AND report_line_code='MGMT_FEE_5_ROYALTIES'"
    ).bindparams(r=REPORT_ID))
