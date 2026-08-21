# -*- coding: utf-8 -*-
"""Los presupuestos 2027 dejan de leer montos digitados y pasan a `drivers`.

## La decisión

Owner, 2026-08-15: «hagamos que el mix y todos los cambios que se hicieron
apliquen para **2027 en adelante**» (`docs/DECISIONES_DEL_OWNER.md` punto 3).

Hasta hoy los seis presupuestos 2027 tenían `revenue_source = 'checkbook'`: el
ingreso eran montos en dólares digitados línea por línea. Con eso el motor de
revenue **ni se ejecuta** (`load_revenue_results` corta en la primera línea), así
que el mix de canales y el Net Factor no tocaban un solo número. Con `drivers`
el ingreso sale de **tarifas × ocupación**, y el mix lo maneja de verdad.

## Qué mueve, medido antes de aplicar

En los cinco que entran acá, **la venta a tarifa RACK no se mueve ni un dólar** y
**la ocupación tampoco**:

    noches ocupadas   4.981,8   (idéntico)   ·   pax 8.967 (idéntico)
    venta rack        $4.331.219             (idéntico)
    neta digitada     $3.560.261  → factor implícito 0,8220
    neta por drivers  $3.451.979  → factor implícito 0,7970

O sea: **el 100% del cambio es el Net Factor, y el Net Factor es el mix**. El
checkbook quedó congelado con el 0,8220 de antes del mixer; los drivers usan el
0,7970 de hoy. Nada viene de las tarifas ni de la ocupación.

Por escenario (los cinco dan lo mismo, son la misma carga):

    Ingresos      5.997.346 → 5.826.131    −171.215   (−2,9%)
    GOP           2.842.543 → 2.671.328    −171.215
    EBITDA        2.662.623 → 2.496.544    −166.078
    Utilidad neta 1.567.716 → 1.455.588    −112.128

La estimación vieja de −$181.000 quedó cerca pero no es el número: son
**−$171.215** por escenario, y estaba calculada como si el factor ya manejara el
ingreso — cosa que no hacía.

## Por qué el `BUDGET Working 2027` NO entra

Porque ahí el cambio **borraría plata que nadie decidió borrar**: sus
$125.180 de Club Madresal (`REV_CLUB`) se van a **cero**.

El driver del Club —socios × precio, más actividad de fin de año y visitantes—
guarda su resultado en las líneas `CLUB` / `CLUB_ACTIVIDAD` / `CLUB_VISITANTES`
del **checkbook de ingresos**, porque «es de ahí de donde el P&L lee»
(`club_stats_api.guardar_cuota`). Pero el camino de `drivers` no consulta
`RevenueEntry`: `calculate_revenue` no tiene ninguna fuente de Club. Es
exactamente el agujero que `app/api/_llega_al_pl.py` ya documenta y que
`test_club_membresias.py` cuida avisándole al usuario — el aviso existe, la
fuente no.

Es una decisión de producto, no un bug a tapar de paso: **¿el driver del Club
alimenta el P&L en modo `drivers`, o el Club obliga a ese escenario a quedarse en
`checkbook`?** Queda para el owner, con el número puesto: $125.180 al año, y el
`PROFIT_CLUB` pasa de −228.471 a −353.651 si se aplica sin resolverlo.

Los otros cinco no tienen el problema: no tienen líneas de Club cargadas.

## Los 2028–2035 ya estaban en `drivers`

Nacieron así (el default del modelo es `drivers`, y `ensure_working_budgets` crea
sin pasar el campo). Hoy están vacíos, así que nacen con el modelo nuevo sin que
haya que tocar nada. Esta migración igual los cubre por si alguno se creó
copiando de un `checkbook` — `_clone_scenario_data` copia el modo del origen a
propósito.

Revision ID: 116
Revises: 115
"""
from alembic import op
import sqlalchemy as sa

revision = "116"
down_revision = "115"
branch_labels = None
depends_on = None

#: 2027 en adelante pasa a drivers. La única excepción es el `Working 2027`,
#: por el Club (ver arriba). Se excluye por año Y versión, no por versión sola:
#: los `Working` de 2028 en adelante sí tienen que entrar cuando se llenen.
SQL = """
UPDATE scenarios
   SET revenue_source = 'drivers'
 WHERE year >= 2027
   AND revenue_source = 'checkbook'
   AND NOT (year = 2027 AND lower(version) = 'working')
"""


def upgrade() -> None:
    op.execute(sa.text(SQL))


def downgrade() -> None:
    # Solo los cinco de 2027 volvían de `checkbook`; los 2028+ nunca estuvieron
    # ahí, así que devolverlos sería inventarles un pasado.
    op.execute(sa.text("""
        UPDATE scenarios
           SET revenue_source = 'checkbook'
         WHERE year = 2027
           AND lower(version) <> 'working'
    """))
