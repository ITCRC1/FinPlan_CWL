# -*- coding: utf-8 -*-
"""¿Lo que este driver guarde lo va a ver el P&L? — sí, y acá está el porqué.

## Lo que decía este archivo hasta 2026-08-15

Que **no siempre**. Los drivers de ingreso —el Spa con su capture rate, el Club
con su cuota— empujaban su resultado a una línea del **checkbook** de ingresos
(`RevenueEntry`), y esa tabla **solo se lee en modo `checkbook`**. Un escenario
en modo `drivers` arma el ingreso con tarifas y ocupación y ni consultaba esas
líneas: uno guardaba, la pantalla mostraba el ingreso, y el estado de resultados
seguía en cero **sin un solo error**. Se descubre semanas después, cuando no
cuadra un total. Al Club le costó $125.180 al año y lo dejó fuera de la
migración 116.

## Lo que pasa hoy

El owner lo cerró en una línea: «solo quiero que trabaje **estándar como todos
los departamentos**». Así que en vez de avisar del agujero, se tapó:
`app/api/_ingreso_de_driver.py` deposita el resultado de **todo** driver en las
dos fuentes —`RevenueEntry` para el modo checkbook y `RevenueOther` para el modo
drivers— y `calculate_revenue` lee las líneas planas de forma genérica, derivada
de `REVENUE_LINES`. Ningún departamento tiene que saber en qué modo está su
escenario.

## Por qué esto sigue existiendo

Porque la pregunta sigue siendo buena, y la respuesta tiene que salir de **un
solo lugar**. Si mañana aparece una tercera fuente de ingreso, o un modo nuevo,
acá se vuelve a poner `False` y las pantallas se enteran solas — que es
exactamente lo que no pasó la primera vez. `modo_ingresos` además se publica tal
cual: saber en qué modo está el escenario sigue siendo útil aunque ya no haya
nada que temer.

Uso:
    "llega_al_pl": llega_al_pl(scenario),
    "modo_ingresos": modo_ingresos(scenario),
"""


def modo_ingresos(scenario) -> str:
    """`checkbook` o `drivers`. El default histórico es `drivers`."""
    return getattr(scenario, "revenue_source", "drivers") or "drivers"


def llega_al_pl(scenario) -> bool:
    """True: el resultado de un driver llega al P&L en cualquiera de los modos.

    No depende del escenario a propósito — el parámetro se conserva porque la
    respuesta podría volver a depender de él, y las pantallas ya lo llaman así.
    """
    return True
