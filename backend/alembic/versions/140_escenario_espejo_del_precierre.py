# -*- coding: utf-8 -*-
"""El borrador del Pre-Cierre se puede mirar en los 19 sub-tabs del P&L.

Owner, 2026-09-10: *«crea un tab que se llame Pre-Closing y jala del tab Monthly
P&L, jala todos los sub tabs pero hazlo facil, no quites ningun sub tab porque
sera objeto de analisis y revision rapida de cada uno de ellos con los datos que
se estan subiendo»* · *«debe leer la version mas reciente subida, porque seguro
se suban varias antes de llegar a final»*.

## Por qué una columna y no ocho endpoints

Los 19 sub-tabs del cierre se alimentan de OCHO cargadores distintos
—`_monthly_results`, `getAuditoria`, `getPLDetail`, `getGastoPorClase`,
`getCashflowBudget`, `getFbDetalle`, `getIngresoDetalle`, `correrConsulta`— y
cada uno consulta por `scenario_id` en sus propias tablas. No hay un punto
único donde interceptar.

Enseñarle a los ocho una fuente nueva son ocho reescrituras, y cada una es una
oportunidad de que el mismo mes dé un número distinto según el sub-tab que se
abra. Eso es peor que no tener la pantalla.

Así que el borrador se MATERIALIZA en un escenario, y los ocho cargadores lo
leen sin saber que es un pre-cierre. Cero endpoints tocados.

## El riesgo que esto abre, y cómo queda acotado

`models/precierre.py` advierte: *«si se filtrara a los reportes habría dos
versiones del mismo mes conviviendo, y la pregunta ¿cuál es el bueno? no
tendría respuesta desde adentro del sistema»*. La advertencia sigue vigente —
esta columna es la respuesta a esa pregunta:

* **`es_precierre = true` no aparece en ningún selector de escenario.**
  `/api/scenarios/` lo excluye salvo que se pida explícitamente. Pre-Closing lo
  pide; el resto de la app no sabe que existe.
* **Uno por hotel y año, sobreescrito en cada subida.** No uno por vuelta: si
  se sube cinco veces antes de Final, hay un solo espejo y muestra la quinta.
* **Nunca es el ACTUAL.** «Pasar a Final» sigue escribiendo el de siempre, por
  la puerta de siempre. El espejo no se promueve: se sobreescribe.

Aditiva y reversible.

Revision ID: 140
Revises: 139
"""
import sqlalchemy as sa
from alembic import op

revision = "140"
down_revision = "139"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `false` como server_default: los 20 escenarios que ya existen pasan a
    # «no es un espejo», que es exactamente lo que son. El día que esto se
    # despliega no cambia nada para nadie.
    op.add_column("scenarios",
                  sa.Column("es_precierre", sa.Boolean(), nullable=False,
                            server_default=sa.false()))


def downgrade() -> None:
    # ⚠️ Se BORRAN los espejos, no sólo la columna. Sin la bandera dejarían de
    # ser invisibles y aparecerían en cada selector como un ACTUAL más del
    # mismo año — que es precisamente la confusión que la columna evita.
    op.execute("DELETE FROM scenarios WHERE es_precierre")
    op.drop_column("scenarios", "es_precierre")
