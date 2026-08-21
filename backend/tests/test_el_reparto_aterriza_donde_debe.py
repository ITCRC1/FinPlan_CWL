# -*- coding: utf-8 -*-
"""
LO QUE ESCRIBE EL MOTOR DE REPARTOS TAMBIÉN TIENE QUE TENER DÓNDE ATERRIZAR.

## Cómo se descubrió (auditoría del mapeo, 2026-08-14)

La migración **114** le sacó al `0162` Laundry Revenue sus trece reglas de gasto,
con esta justificación escrita en el commit:

    «El P&L no se mueve: las trece dan 0,00 en todos los escenarios.»

Y era verdad… medido sobre el **checkbook**. `opex_entries` y `cost_entries` no
tenían un solo colón en el `0162`. Lo que la medición no miró es
`allocation_entries`, porque esas filas **no las carga nadie: las escribe el
motor**. El reparto de lavandería manda el costo de los kilos de HUÉSPED —la
parte que se le vendió a un tercero— del `0161` al `0162`, en la cuenta `5301`,
para que el ingreso del servicio y su costo vivan en el mismo departamento y el
`0161` netee a cero (`calculate_laundry_distribution`, `guest_dept="0162"`).

Sin la regla, esos **$12.257,04** dejaron de resolver por `exact` y pasaron a
resolver por `FALLBACK`, que agarra la regla de la cuenta con departamento de
código MENOR: el `0140`, o sea **el Spa**. En los seis escenarios de checkbook
el costo se corrió de `COS_LAUNDRY` a `COS_SPA` —$6.604,12— y el GOP quedó
idéntico, que es exactamente cómo falla caro este sistema.

Es el mismo patrón que la nota de la `4999` en CLAUDE.md: **una cuenta sin filas
en el GL no es una cuenta sin plata, si el motor la escribe.**

## Por qué se cayó justo el `0162` y no otros veinticuatro

La verificación independiente contó **25 pares (departamento destino, cuenta) de
reparto sin regla exacta**. Veinticuatro son HIJOS, y esos están bien: heredan la
regla del padre por la cadena de `_cadena_de_padres`, que es el mecanismo
correcto — los repartos caen en sub-departamentos (`0122` Cocina, `0132` Spa)
que casi nunca tienen regla propia.

El `0162` era **el único sin padre**. Sin padre no hay de quién heredar, así que
la búsqueda siguió de largo hasta el `FALLBACK`, que no tiene nada que ver con
la herencia: agarra la regla de cualquier departamento que use esa cuenta.

Por eso lo que se exige acá es `exact` **o** `parent`, no `exact` a secas:
pedir regla propia marcaría 24 falsos positivos y taparía el que importa.

## Qué cuida esta prueba

Que ninguna cuenta de reparto caiga por descarte. Se recorre
`allocation_calculator.cuentas_de_reparto()` —que se arma del propio motor, así
que un reparto nuevo entra solo— con dos alcances distintos, porque los repartos
no eligen destino de la misma forma:

* **destino FIJO** (`4999` al departamento que reparte, `5301` al `0162`): el
  código dice a qué departamento va, así que se le exige regla propia o
  heredada del padre. Hoy los cuatro resuelven `exact`.
* **destino por FTE** (`6025` cafetería, `7685` uniformes): le pueden pegar a
  **cualquier** departamento que tenga gente, así que se exige regla para todos
  los que tienen planilla en el mapeo.

`7310` (lino) queda afuera a propósito: no le pega a cualquiera, va solo a los
departamentos a los que el owner les configura kilos, y eso es dato de cada
escenario. Ese lo cubre `scripts/auditoria_mapeo.py`, que lee las filas reales
de `allocation_entries` en producción.
"""
import json
import pathlib

import pytest

from app.engine import pl_engine
from app.engine.allocation_calculator import (
    ALLOCATION_ACCOUNT, CAFETERIA_ACCOUNT, cuentas_de_reparto)
from app.seed_department_catalog import build_rows
from app.seed_mapping import ARCHIVO

#: Cada motor de reparto acredita a SU departamento fuente en la `4999`. Están
#: en `recalculate.py` (`"0220"`, `"0161"`) y en la familia de Rooms (`"0110"`).
CREDITOS = {
    "0220": "cafetería",
    "0161": "lavandería",
    "0110": "Rooms → Villas/Residencias",
}

#: Destinos que el CÓDIGO fija, no la configuración de un escenario.
#: `(departamento, cuenta) -> quién lo escribe`.
DESTINOS_FIJOS = {
    **{(d, ALLOCATION_ACCOUNT): f"el crédito de {q}" for d, q in CREDITOS.items()},
    # `calculate_laundry_distribution(guest_dept="0162", acct_servicios="5301")`
    ("0162", "5301"): "el costo de huéspedes de lavandería",
}

#: Reparto que se distribuye por FTE: le puede pegar a cualquier departamento
#: que tenga planilla, así que todos necesitan regla.
POR_FTE = (CAFETERIA_ACCOUNT, "7685")

#: Va solo a quien tenga kilos configurados — dato de escenario, no estructura.
#: Lo mide `scripts/auditoria_mapeo.py` contra producción.
POR_KILOS = ("7310",)


@pytest.fixture(scope="module")
def reglas() -> list[dict]:
    return [m for m in json.loads(pathlib.Path(ARCHIVO).read_text(encoding="utf-8"))
            ["account_mapping"] if m["active_status"] == "YES"]


@pytest.fixture(scope="module")
def resolve(reglas):
    pl_engine.set_dept_catalog(build_rows())
    return pl_engine.construir_resolvedor(reglas)


@pytest.mark.parametrize("par", sorted(DESTINOS_FIJOS))
def test_los_destinos_fijos_del_reparto_tienen_regla_exacta(resolve, par):
    """El código dice a qué departamento va, así que tiene que resolver por
    regla propia o heredada del padre — nunca prestada de otro departamento.
    Hoy los cuatro resuelven `exact`."""
    dept, cuenta = par
    regla, modo = resolve(dept, cuenta)
    assert modo in ("exact", "parent"), (
        f"{DESTINOS_FIJOS[par]} ({dept}/{cuenta}) resuelve por {modo} → "
        f"{regla['report_line_code'] if regla else 'NADA'}. El motor escribe esa "
        "fila igual, así que la plata aterriza en la línea de otro departamento "
        "con el GOP cuadrando — nada avisa.")


@pytest.mark.parametrize("cuenta", POR_FTE)
def test_el_reparto_por_fte_tiene_donde_caer_en_todo_departamento_con_planilla(
        resolve, reglas, cuenta):
    """Cafetería y uniformes se reparten por FTE, así que le pegan a cualquier
    departamento que tenga gente. El que no tenga regla se lo come otro."""
    con_planilla = sorted({(m.get("dept_code") or "").strip() for m in reglas
                           if m["account_code"].startswith("6")} - {""})
    fugas = []
    for dept in con_planilla:
        regla, modo = resolve(dept, cuenta)
        if modo not in ("exact", "parent"):
            fugas.append(f"{dept}/{cuenta} → "
                         f"{regla['report_line_code'] if regla else 'NADA'} ({modo})")
    assert not fugas, (
        f"estos departamentos tienen planilla, así que el reparto de la {cuenta} "
        "les puede llegar, y no tienen dónde ponerlo:\n  " + "\n  ".join(fugas))


def test_toda_cuenta_de_reparto_esta_clasificada(resolve):
    """Si mañana aparece un reparto con una cuenta nueva, esta prueba avisa: hay
    que decidir si su destino es fijo, por FTE o por configuración, no dejarla
    sin mirar. `cuentas_de_reparto()` se arma sola del motor."""
    clasificadas = {c for _d, c in DESTINOS_FIJOS} | set(POR_FTE) | set(POR_KILOS)
    # La `6000` de la reasignación de salarios va a departamentos que ya tienen
    # planilla por definición (se les mueve un salario), así que la cubre la
    # prueba de FTE por el mismo camino: todos tienen regla de 6xxx.
    clasificadas.add("6000")
    sin_clasificar = cuentas_de_reparto() - clasificadas
    assert not sin_clasificar, (
        f"el motor de repartos escribe en {sorted(sin_clasificar)} y esta prueba "
        "no sabe con qué alcance exigirle regla. Clasificala arriba.")
