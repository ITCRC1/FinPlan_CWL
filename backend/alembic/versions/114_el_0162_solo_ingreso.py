# -*- coding: utf-8 -*-
"""El `0162` Laundry Revenue es solo ingreso: fuera sus reglas de gasto.

Owner (2026-08-14), mirando el desplegable del checkbook de Opex: **«0162 no hace
nada acá, no tiene gastos»**.

Es la otra mitad de una decisión ya tomada: **el `0162` es el INGRESO de
lavandería y el `0161` es el que lleva el gasto y lo reparte**. El `0162`
arrastraba trece reglas de gasto —`5301` y doce cuentas 7xxx— que nunca
recibieron un colón en ningún escenario, y mientras existieran el selector lo
ofrecía como si tuviera dónde poner un gasto operativo.

## No mueve el P&L

Las trece dan **0,00 en todos los escenarios**. Lo único que el `0162` tiene son
sus ingresos (`4700`, `4701`, `4702`) y su planilla, que se quedan.

El gasto real de lavandería sigue donde estaba: el `0161` tiene sus veinte
cuentas propias hacia `OH_LAUNDRY` y `COH_LAUNDRY`, y desde ahí se reparte.

## Por qué esto saca al 0162 del selector

`GET /departments/` **deriva** `lleva_gasto` del mapeo: acepta gasto quien no es
hijo y tiene al menos una regla de clase 5 o 7. Sin estas trece, el `0162` deja
de calificar y desaparece del checkbook de Opex **solo**, sin lista a mano.

Queda declarado en `SIN_NUCLEO_A_PROPOSITO` de
`tests/test_departamentos_independientes.py`, igual que el `280`: no le faltan
las cuentas del núcleo, es que no le corresponden.

Revision ID: 114
Revises: 113
"""
from alembic import op
import sqlalchemy as sa

revision = "114"
down_revision = "113"
branch_labels = None
depends_on = None

FUERA = ["5301", "7105", "7110", "7150", "7175", "7185", "7380",
         "7400", "7665", "7670", "7675", "7680", "7685"]


def upgrade() -> None:
    op.execute(sa.text(
        "DELETE FROM account_mapping WHERE dept_code = '0162' "
        "AND account_code = ANY(:c)"
    ).bindparams(sa.bindparam("c", value=FUERA, type_=sa.ARRAY(sa.String))))
    # Las filas en blanco de la 5301: son las que hacían aparecer al 0162 en el
    # selector de Costos. Sin dato, no hay nada que preservar.
    op.execute(sa.text(
        "DELETE FROM cost_entries WHERE dept_code = '0162' "
        "AND account_code = '5301'"))


def downgrade() -> None:
    # La fuente de verdad es `mapping_pl.json`: volver el archivo atrás y
    # arrancar deja la base como estaba (ver la 097, la 112 y la 113).
    pass
