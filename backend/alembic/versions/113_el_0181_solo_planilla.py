# -*- coding: utf-8 -*-
"""El `0181` se queda en Administración y pierde el set de gastos entero.

## Cómo se llegó acá

La migración 112 dejó 15 reglas de gasto en el `0181` sin tocar, porque la `0180`
no tiene ninguna de las 15 y sacarlas las mandaba a Habitaciones y A&B por
descarte. Eran China, Cleaning Supplies, Dishwashing, Flatware, Glassware, Ice,
Kitchen Fuel, Kitchen Smallwares, Laundry, Linen, Paper and Plastics, Printing,
Utensils y los dos costos `5700`/`5701`.

El owner miró ese set y dijo primero que el `0181` era Management **de A&B** —y
tenía sentido: **13 de las 15 existen en el `0120`**, son cuentas de cocina—.
Después lo resolvió al revés, que es más simple y más limpio (2026-08-14):

    «0181 dije que era administración de F&B porque el set de gastos era de F&B.
    Ok, podemos dejarlo en administración pero **elimina todo el set de gastos**.»

Así que el departamento se queda donde está —hijo de la `0180`, con su planilla
en `OH_ADMIN`— y el set de gastos se va completo. Deja de haber una decisión
pendiente y deja de haber 15 cuentas de cocina colgando de Administración.

## Encaja con la regla general

Owner, el mismo día: «solo los departamentos padres pueden tener checkbook de
gastos, **ningún hijo puede tener gastos operativos** · los hijos integran a
nivel de planilla pero nada más». El `0181` es hijo: le corresponde planilla y
nada más. Después de esto **ningún hijo del sistema tiene reglas de gasto**.

## No mueve el P&L

Las 15 dan **0,00 en los 12 escenarios**. Y ninguna es del núcleo compartido, así
que no deja al `0181` perdiendo una cuenta que cualquier departamento usa — esas
ya las hereda de la `0180` desde la 112.

## El seed manda

La verdad vive en `app/seed_data/mapping_pl.json`, que es de donde el seed
re-afirma la tabla en cada arranque. Esta migración no decide nada: solo **borra
lo que el seed dejó de nombrar**, porque `seed_mapping` inserta y actualiza pero
no borra lo que sobra.

Revision ID: 113
Revises: 112
"""
from alembic import op
import sqlalchemy as sa

revision = "113"
down_revision = "112"
branch_labels = None
depends_on = None

FUERA = ["5700", "5701", "7060", "7065", "7140", "7195", "7235", "7275",
         "7295", "7300", "7310", "7350", "7460", "7490", "7695"]


def upgrade() -> None:
    op.execute(sa.text(
        "DELETE FROM account_mapping WHERE dept_code = '0181' "
        "AND account_code = ANY(:c)"
    ).bindparams(sa.bindparam("c", value=FUERA, type_=sa.ARRAY(sa.String))))


def downgrade() -> None:
    # No se reconstruyen: la fuente de verdad es `mapping_pl.json`. Volver el
    # archivo atrás y arrancar deja la base como estaba — escribirlas acá sería
    # una tercera copia de la misma decisión (ver la 097 y la 112).
    pass
