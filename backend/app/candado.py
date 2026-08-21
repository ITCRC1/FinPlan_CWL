# -*- coding: utf-8 -*-
"""El candado del escenario, en UNA puerta.

Owner, 2026-08-20: *«si está enllavado nadie puede editar los checkbook»*.

## Lo que estaba pasando

Medido ese día contra el repo: **194 endpoints escriben y el candado se
verificaba en catorce**, casi todos en `scenarios_api`. Los que faltaban no eran
los raros:

| archivo | endpoints que escriben | chequeaban el candado |
|---|---|---|
| `revenue_api` | 36 | **0** |
| `payroll_api` | 17 | **0** |
| `opex_api` | 8 | **0** |
| `allocation_api` | 7 | **0** |
| `costs_api` | 6 | **0** |

O sea que enllavar frenaba los imports y el recálculo, **pero no impedía editar
planilla, opex, revenue ni costos**. El candado parecía protección y no lo era —
que es la forma más cara de no tenerla: alguien enllava, se queda tranquilo, y
el escenario se sigue moviendo.

## Por qué UNA dependencia y no 108 ediciones

Es el mismo mecanismo que cubrió las 23 puertas de subida en la Fase 0 de
Guillermo (`importers/registro_dep.py`): se engancha una vez, en el router, y
**una ruta nueva queda cubierta sin que nadie se acuerde de nada**. Insertar un
`if scenario.is_locked` en 108 endpoints son 108 ediciones que hay que repetir
cada vez que se agrega una — y la que se olvide no falla: deja escribir.

⚠️ **No es middleware.** Un middleware acá tendría que resolver el escenario
para toda petición, incluidas las de lectura; una dependencia falla de a una
ruta y la atrapan las pruebas. Misma razón que en el registro de subidas.

## Lo que SÍ se deja pasar, y por qué

**Cambiar el estado del escenario.** Si el candado bloqueara también el
interruptor que lo abre, enllavar sería irreversible desde la app: quedaría un
escenario que nadie puede desbloquear ni corregir. Es la única excepción, y por
eso está escrita acá y no repartida.

⚠️ **Esto es un candado, no un permiso.** Dice «este escenario no se toca», no
«vos no podés». Quién puede enllavar y desenllavar sigue siendo `PATCH
/scenarios/{id}/status/`, que **hoy no exige admin** — es el pendiente 14 y es
una decisión del owner. Con este candado puesto, ese pendiente pasa a importar
más: quien pueda desenllavar puede volver a escribir.
"""
from __future__ import annotations

from fastapi import Depends, Request

from app.db import get_db
from app.errores import ErrorApi
from app.models.scenario import Scenario

#: Los métodos que modifican. `GET` y `HEAD` nunca se frenan: un escenario
#: enllavado se sigue leyendo, y de hecho es lo que más se hace con él.
ESCRITURA = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Cómo se llama el escenario en la ruta. `scenario_id` cubre 108 de las 108
#: rutas de escritura que llevan uno; `target_id` es el DESTINO de una copia,
#: que es justo el caso peligroso —copiar encima de un escenario cerrado—.
LLAVES = ("scenario_id", "target_id")

#: La única excepción: el interruptor que abre el candado. Sin esto, enllavar
#: sería irreversible desde la app.
PERMITIDAS = ("/status/",)


async def candado_del_escenario(request: Request, db=Depends(get_db)) -> None:
    """409 si se intenta escribir sobre un escenario enllavado."""
    if request.method not in ESCRITURA:
        return

    ruta = request.scope.get("route")
    plantilla = getattr(ruta, "path", "") or request.url.path
    if any(plantilla.rstrip("/").endswith(p.rstrip("/")) for p in PERMITIDAS):
        return

    sid = next((request.path_params.get(k) for k in LLAVES
                if request.path_params.get(k)), None)
    if not sid:
        return

    sc = await db.get(Scenario, sid)
    # ⚠️ Un escenario que no existe **no se frena acá**: el endpoint tiene que
    # poder devolver su propio 404. Contestar 409 diría «está enllavado» de algo
    # que ni siquiera está.
    if sc is None or not sc.is_locked:
        return

    raise ErrorApi(409, "escenario.enllavado",
                   escenario=f"{sc.type} {sc.version} {sc.year}")
