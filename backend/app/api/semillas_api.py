# -*- coding: utf-8 -*-
"""Las semillas que pide el FRONTEND, servidas por propiedad.

**Por que existe.** Dos listas de arranque seguian escritas a mano dentro de
pantallas de Next.js, fuera del alcance de `seed_data/`:

* `DEFAULT_DRIVER_RATES` en Revenue -> Checkbook: las tarifas del paquete con
  que el boton «Llenar desde drivers» arma doce meses de ingreso.
* `TEMPLATE` en Allocations -> Salary: las nueve reasignaciones de puesto que
  propone el boton «Armar plantilla».

Las dos son producto de Corcovado —el traslado Sierpe/Drake, el tour a San
Pedrillo, el ROOM ATTENDANT del 0113— y las dos viajaban dentro del bundle: una
propiedad nueva abria esas pantallas con los datos de otro hotel y a un clic de
guardarlos. Es exactamente lo que `app/seed_data/__init__.py` describe, solo que
del lado del navegador, donde ninguna prueba del backend lo veia.

**Que devuelven.** `seeded: true` + los datos si la propiedad los tiene;
`seeded: false` con la lista vacia si no. Vacio NO es un error: es una propiedad
que todavia no cargo lo suyo, y la pantalla lo dice en vez de rellenarlo.

⚠️ **Son sugerencias, no dato guardado.** El dato guardado del paquete vive en
`package_configs` y `pkg_experience_items`; el de las reasignaciones, en
`salary_allocation_config`. Estas listas no se leen en ningun calculo del P&L.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.seed_data import semilla_cruda

router = APIRouter()


def _semilla(nombre: str, clave: str, vacio):
    d = semilla_cruda(nombre)
    if not d:
        return {"seeded": False, clave: vacio}
    return {"seeded": True, clave: d[clave], "nota": d.get("_nota", [])}


@router.get("/semillas/driver-rates/")
async def driver_rates():
    """Las tarifas del paquete con que el Checkbook llena desde drivers.

    ⚠️ NO son las del motor. El P&L calcula el paquete con `package_configs`
    (FOOD 108, ACTIVITIES 101, TRANSPORT 35, SUSTAINABILITY 28 por pax/noche) y
    estas salen del menu de Experiencias (126 / 342 y 150 por pax/estadia /
    30,97). Los dos numeros existen y no dicen lo mismo; cual manda es decision
    del owner. Hoy no cambia nada porque los 20 escenarios corren con
    `revenue_source = drivers`, o sea que el P&L no lee el checkbook.
    """
    return _semilla("driver_rates", "tarifas", {})


@router.get("/semillas/reasignaciones-salario/")
async def reasignaciones_salario():
    """Las reasignaciones de salario que propone la plantilla.

    Por PUESTO y no por codigo: los codigos de la planilla 2026 (508, 598,
    604...) cambiaron con el head count 2027 y las reglas quedaron apuntando al
    vacio sin que nada lo dijera. `legacy` es el codigo viejo, de respaldo.
    """
    return _semilla("reasignaciones_salario", "reasignaciones", [])
