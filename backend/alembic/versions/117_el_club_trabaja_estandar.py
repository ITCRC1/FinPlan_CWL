# -*- coding: utf-8 -*-
"""El Club deja de ser la excepción, y el `BUDGET Working 2027` pasa a `drivers`.

## La decisión

Owner, 2026-08-15: «No sé qué está pasando… **solo quiero que trabaje estándar
como todos los departamentos**». Con eso cierra la pregunta que la migración 116
dejó abierta: **el Club no obliga a su escenario a quedarse en `checkbook`; el
motor aprende a producir su ingreso en modo `drivers`.**

## Qué le faltaba al camino de `drivers`

Nada del Club en particular — le faltaba una **lista**. En modo `drivers` el
motor deriva Rooms/Food/Beverage/Activities/Transport/Sustainability de tarifas ×
ocupación, y las demás líneas las lee de `revenue_other`… pero con una cadena de
`if` escrita a mano con cinco líneas (Spa, Retail, F&B misc, Innoceana,
Lavandería). El Club no estaba en esa cadena, así que su driver escribía en el
**checkbook** (`revenue_entries`, la fuente del *otro* modo) y en modo `drivers`
el ingreso no existía: sin error, sin 4xx, sin nada en los logs.

Hoy la lista se **deriva** de las líneas canónicas (`OTHER_REVENUE_LINES`) y todo
driver deposita su resultado en las **dos** fuentes, vía
`app/api/_ingreso_de_driver.py`. El Spa tenía exactamente el mismo agujero y se
tapó con el mismo mecanismo.

## Qué mueve, medido antes de aplicar

**Un solo escenario: el `BUDGET Working 2027`.** Los otros diecinueve no tienen
líneas de Club ni cambian de modo, así que no se mueve un dólar en ellos.

    Ingresos   6.449.238 → 6.374.026    −75.212
       de los cuales:  −118.218 el mix (Room Revenue, Net Factor 0,8220 → 0,7970)
                       + 43.006 la ocupación (4.981,8 → 5.215,6 noches)

El checkbook del Working 2027 se congeló con **6** tipos de habitación y el
escenario hoy tiene **8**: por eso las noches suben al pasar a drivers, y con
ellas food, beverage, actividades, transporte y sustainability.

    REV_CLUB      125.180 → 125.180   (idéntico: 122.880 cuota + 1.500 + 800)
    PROFIT_CLUB  −228.471 → −228.471

**Si `REV_CLUB` diera cero, esta migración salió mal.** Ese era justo el número
que retenía al escenario en `checkbook`.

## Los dos pasos, y por qué en este orden

1. **Copiar** las tres líneas del Club de `revenue_entries` a `revenue_other`.
   Se copia el monto exacto que ya está en el checkbook —no se recalcula— para
   que el cambio de modo no traiga de regalo un recálculo que nadie pidió. Ese
   monto es el que el driver escribió (128 socios × $80 × 12 meses = 122.880,
   más 1.500 de actividad y 800 de visitantes en diciembre).
2. **Después** cambiar el modo. Al revés habría una versión del escenario, aunque
   fuera dentro de la misma transacción, con el modo nuevo y sin la fuente.

Solo `year >= 2027`. Los escenarios de 2026 y anteriores no se tocan.

Revision ID: 117
Revises: 116
"""
from alembic import op
import sqlalchemy as sa

revision = "117"
down_revision = "116"
branch_labels = None
depends_on = None

LINEAS_CLUB = "('CLUB', 'CLUB_ACTIVIDAD', 'CLUB_VISITANTES')"

#: Paso 1 — el monto del checkbook pasa a ser también monto del modo drivers.
#: `NOT EXISTS` para no duplicar si esto se corre dos veces; los meses en cero no
#: hacen falta (sin fila, el motor lee cero igual).
COPIAR = f"""
INSERT INTO revenue_other (id, scenario_id, hotel_id, line, month, amount_usd)
SELECT gen_random_uuid()::text, e.scenario_id, e.hotel_id, e.line, m.mes, m.monto
  FROM revenue_entries e
  JOIN scenarios s ON s.id = e.scenario_id
  CROSS JOIN LATERAL (VALUES
        (1, e.jan), (2, e.feb), (3, e.mar), (4, e.apr),
        (5, e.may), (6, e.jun), (7, e.jul), (8, e.aug),
        (9, e.sep), (10, e.oct), (11, e.nov), (12, e.dec)
  ) AS m(mes, monto)
 WHERE e.line IN {LINEAS_CLUB}
   AND s.year >= 2027
   AND m.monto <> 0
   AND NOT EXISTS (
        SELECT 1 FROM revenue_other o
         WHERE o.scenario_id = e.scenario_id
           AND o.line = e.line
           AND o.month = m.mes)
"""

#: Paso 2 — se cae la excepción de la 116: era el Club el que la sostenía, y el
#: Club ya trabaja estándar. Sin salvedades por versión: entran todos.
A_DRIVERS = """
UPDATE scenarios
   SET revenue_source = 'drivers'
 WHERE year >= 2027
   AND revenue_source = 'checkbook'
"""


def upgrade() -> None:
    op.execute(sa.text(COPIAR))
    op.execute(sa.text(A_DRIVERS))


def downgrade() -> None:
    # Vuelve el `Working 2027` a `checkbook` —los otros 2027 ya estaban en
    # `drivers` antes de esta migración, así que no se tocan— y se lleva la copia
    # que este paso creó. Las líneas del Club en `revenue_entries` quedan: son el
    # dato original, no una copia.
    op.execute(sa.text("""
        UPDATE scenarios
           SET revenue_source = 'checkbook'
         WHERE year = 2027
           AND lower(version) = 'working'
    """))
    op.execute(sa.text(f"""
        DELETE FROM revenue_other o
         USING scenarios s
         WHERE s.id = o.scenario_id
           AND s.year >= 2027
           AND o.line IN {LINEAS_CLUB}
    """))
