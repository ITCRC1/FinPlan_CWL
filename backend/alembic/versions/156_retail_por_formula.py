# -*- coding: utf-8 -*-
"""Retail (Gift Shop) por fórmula: % del ingreso de habitaciones, por escenario.

Owner, 2026-10-22: *«hay que quitar eso… debe leer desde las fórmulas»*. El
REV_RETAIL de los presupuestos era un monto fijo en `revenue_other`, cargado una
vez desde el Excel (1,2 % del Rooms del Budget 2026) y copiado a cada escenario
nuevo: el Budget 2027 seguía con el Retail de 2026 aunque su Rooms subiera.

Desde acá el motor calcula Retail = `retail_pct` % × Rooms del mes, en todos los
meses que calcula. Los meses reales de un forecast rodante y los escenarios
subidos no pasan por el motor, así que no cambian. Arranca en 1,2 (la tarifa de
`seed_data/CWL/driver_rates.json`) y se edita por escenario.
"""
import sqlalchemy as sa
from alembic import op

revision = "156"
down_revision = "155"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("scenarios", sa.Column(
        "retail_pct", sa.Numeric(6, 3), nullable=False, server_default="1.2"))


def downgrade() -> None:
    op.drop_column("scenarios", "retail_pct")
