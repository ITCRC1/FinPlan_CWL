# -*- coding: utf-8 -*-
"""
LOS KPI DE HABITACIONES, DERIVADOS AL LEER.

Ocupación %, ADR y RevPAR de un mes. Módulo PURO: no toca la base, no importa
modelos. Lo usan el P&L mensual y el de doce meses para no dar números
distintos del mismo mes.

## Qué problema resuelve

`scenario_stats.adr` es una columna GUARDADA. La escribe `_persist_room_stats`
(`engine/recalculate.py`) —y ahí la deriva bien, ingreso de habitaciones entre
noches ocupadas— **pero sólo cuando alguien aprieta Recalcular**. Entre que se
mueve una tarifa y que se recalcula, la pantalla muestra un ADR viejo al lado
del ingreso nuevo. Y no sale en cero: sale en un número creíble, que es peor
—un cero se lee como dato que falta; un ADR viejo se lee como dato.

Owner, 2026-09-05: *«necesito que derives el ADR y todos los kpi que dependen
de recalculo»*.

Acá se hace la MISMA cuenta que hace el recálculo, pero al leer. No es una
fórmula nueva: es la de `_persist_room_stats`, movida de la escritura a la
lectura.

## ⚠️ El numerador NO es la línea del P&L — es A4

El room revenue está abierto en tres cuentas (`docs/PENDIENTES.md` A4,
2026-08-12): `4000` Room Revenue, `4001` Cancellations, `4002` No Show. Las tres
consolidan en `REV_ROOMS`.

**Un no-show no ocupa habitación**, así que su ingreso no puede estar en el
numerador de una tarifa por habitación ocupada. El owner pidió que el ADR salga
SOLO de la 4000, y por eso en agosto se dejó de derivar de `REV_ROOMS`.

Por eso este módulo recibe `ingreso_habitaciones` de `RevenueResult.rooms` —el
ingreso de la tarifa, que **nunca pasó por las cuentas**— y jamás de una línea
del P&L. Derivar de `REV_ROOMS` inflaría el ADR solo, en silencio, apenas la
contabilidad empiece a postear en 4001/4002: el ADR no tiene contra qué cuadrar.
Lo vigilan `test_adr_sale_de_las_estadisticas_no_de_la_linea` y
`test_el_adr_agregado_pondera_por_noches_ocupadas` en `tests/test_pl_ytd.py`.

## Qué se deriva y qué se respeta

* **Las noches mandan desde `scenario_stats`** (decisión del 2026-08-17: salían
  de la tabla equivocada). Acá entran ya resueltas y no se tocan.
* **Ocupación %** se deriva siempre de esas dos noches. Estaban en la misma fila
  que la columna `occupancy_pct` y podían no coincidir con ella.
* **ADR** se deriva SÓLO si hay ingreso de habitaciones y noches ocupadas. Si
  falta cualquiera de los dos, queda el guardado: es el caso del ACTUAL, donde
  la estadística viene del PMS y el ingreso puro no existe sin abrir las
  cuentas. Owner, 2026-09-05: derivar sólo si hay ingreso; si no, no fabricar
  un cero.
* **RevPAR** = ADR × ocupación, no ingreso ÷ disponibles. Es para no romper la
  identidad `RevPAR = ADR × occ%`: con el ADR cayendo al guardado y el RevPAR
  derivado del ingreso, los tres números no cerrarían entre ellos.
"""
from decimal import Decimal


def _f(x) -> float:
    """A float, tolerando None, Decimal y str. Nunca revienta."""
    if x is None:
        return 0.0
    if isinstance(x, (float, int)):
        return float(x)
    if isinstance(x, Decimal):
        return float(x)
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def kpis_de_habitaciones(
    *,
    rooms_available,
    rooms_occupied,
    guests,
    ingreso_habitaciones=None,
    ingreso_total=None,
    adr_guardado=None,
    occupancy_guardada=None,
) -> dict:
    """Los seis KPI del mes, con el ADR derivado cuando se puede.

    `ingreso_habitaciones` es el ingreso PURO de la tarifa (`RevenueResult.rooms`),
    no la línea `REV_ROOMS` del P&L — ver el encabezado del módulo. Se pasa `None`
    cuando el escenario no lo calcula (ACTUAL, o cualquiera donde lo subido manda):
    ahí manda `adr_guardado`.

    Devuelve las mismas seis llaves que `_EMPTY_KPIS` en `api/pl_api.py`, para que
    quien consuma no tenga que saber por cuál camino salió el número.
    """
    disp = _f(rooms_available)
    ocup = _f(rooms_occupied)
    ingreso = _f(ingreso_habitaciones)

    # Ocupación: siempre de las noches. Las dos vienen de la misma fila, así que
    # la columna guardada sólo se usa si no hay disponibles con qué dividir.
    if disp:
        occupancy = ocup / disp
    else:
        occupancy = _f(occupancy_guardada)

    # ADR: derivar sólo con las dos patas. Sin ingreso —o sin noches ocupadas, que
    # dejarían la tarifa sin denominador— se respeta el guardado en vez de mostrar
    # un cero que se leería como dato.
    if ingreso and ocup:
        adr = ingreso / ocup
    else:
        adr = _f(adr_guardado)

    return {
        "rooms_available": rooms_available if isinstance(rooms_available, int) else int(disp),
        "rooms_occupied": ocup,
        "guests": _f(guests),
        "occupancy_pct": occupancy,
        "adr": adr,
        # ⚠️ RevPAR = ingreso TOTAL / disponibles (owner, 2026-09-08: «revpar
        # es total revenue per available room» · «total revenue by total rooms
        # available»).
        #
        # Era `ADR × ocupación`, y estaba puesto asi a proposito, «para
        # mantener la identidad aun cuando el ADR cayó al guardado». El owner
        # cambió la definición: mide cuánto rinde cada habitación disponible con
        # TODO lo que el hotel factura —spa, tours, A&B—, no sólo la noche.
        #
        # Sin `ingreso_total` NO se cae al ingreso de habitaciones: eso daría un
        # número con el nombre del nuevo y el valor del viejo, que es la peor de
        # las dos cosas. Se devuelve cero, y quien tenga el ingreso total lo
        # pasa — el P&L siempre lo tiene.
        "revpar": (_f(ingreso_total) / disp) if disp else 0.0,
    }
