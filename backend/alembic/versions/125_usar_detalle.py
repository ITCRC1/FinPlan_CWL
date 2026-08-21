# -*- coding: utf-8 -*-
"""`scenarios.usar_detalle` — forzar que el P&L lea el DETALLE del mayor.

El motor elige solo entre las dos fuentes de un ACTUAL importado: usa el
RESUMEN (`actual_pl_lines`) salvo que el DETALLE (`actual_entries`) dé los
mismos siete totales clave. Ese guardián existe por el Actual 2024, donde el
detalle traía $40.613 de gasto de más: usarlo habría cambiado un GOP ya
cerrado.

Pero en el Actual 2026 el incompleto es el RESUMEN. Medido contra producción
el 2026-08-18:

    DEPRECIATION          resumen 0,00   detalle 273.139,70
    EBITDA AFTER CAPITAL  resumen 0,00   detalle 738.293,06

y los dos números del detalle son EXACTAMENTE los que SCP espera. O sea el
guardián está protegiendo el número equivocado: descarta el detalle por no
coincidir con un resumen que no tiene esas líneas.

La salida NO es cambiar la regla para todos —el Actual 2024 necesita su
resumen— ni borrar el resumen del 2026. Es un interruptor POR ESCENARIO, que
alguien prende a propósito y se puede apagar.

Default `false`: nada cambia hasta que se prenda.
"""
from alembic import op
import sqlalchemy as sa

revision = "125"
down_revision = "124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenarios", sa.Column(
        "usar_detalle", sa.Boolean, nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("scenarios", "usar_detalle")
