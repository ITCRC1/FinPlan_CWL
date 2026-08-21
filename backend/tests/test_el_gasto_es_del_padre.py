# -*- coding: utf-8 -*-
"""
EL GASTO ES DEL PADRE; EL HIJO SOLO LLEVA PLANILLA.

Owner, 2026-08-14, mirando el checkbook de Opex:

    «los grandes departamentos en Opex son muy claros, solo los departamentos
    padres pueden tener checkbook de gastos, ningún hijo puede tener gastos
    operativos» · «los hijos integran a nivel de planilla pero nada más»

Es la regla USALI, y hasta ese día el sistema no la sostenía: el `0181` cargaba
quince cuentas de cocina (China, Dishwashing, Flatware, Glassware, Ice, Kitchen
Fuel, Kitchen Smallwares, Linen, Utensils…) que la `0180` no tiene. Trece de las
quince existen en el `0120` A&B — por eso el owner llegó a pensar que el `0181`
era Management de A&B. Lo resolvió al revés: el departamento se queda en
Administración y **el set de gastos se va entero** (migración 113).

## Por qué una prueba y no un comentario

Una regla de mapeo de gasto en un hijo no da error. Si el padre tiene esa cuenta,
el hijo la resuelve por herencia y aterriza en la misma línea; si NO la tiene,
cae por descarte en otro departamento —casi siempre Habitaciones— y **el GOP
cuadra igual**. O sea: agregar una regla de gasto a un hijo es gratis de hacer,
invisible de detectar y caro de encontrar después.

Quién es hijo sale de `CHECKBOOK_DEPT_CONSOLIDATION`, el mismo mapa que usa el
motor. Si mañana alguien cuelga un departamento nuevo, esta prueba lo cubre sola.
"""
import json
import pathlib

import pytest

from app.engine import pl_engine
from app.seed_mapping import ARCHIVO

# Clases de gasto: 5xxx costo de ventas, 7xxx gastos operativos. La planilla
# (6xxx) y las contrapartidas de reparto (49xx) SÍ le corresponden al hijo.
CLASES_DE_GASTO = ("5", "7")


@pytest.fixture(scope="module")
def reglas() -> list[dict]:
    return json.loads(pathlib.Path(ARCHIVO).read_text(encoding="utf-8"))["account_mapping"]


def test_ningun_hijo_lleva_reglas_de_gasto(reglas):
    hijos = set(pl_engine.CHECKBOOK_DEPT_CONSOLIDATION)
    assert hijos, "el mapa de consolidación está vacío: la prueba no mide nada"

    sobran: dict[str, list[str]] = {}
    for r in reglas:
        dept = (r.get("dept_code") or "").strip()
        cuenta = (r.get("account_code") or "").strip()
        if dept in hijos and cuenta[:1] in CLASES_DE_GASTO:
            sobran.setdefault(dept, []).append(cuenta)

    assert not sobran, (
        "estos departamentos HIJOS llevan reglas de gasto. Si el padre tiene la "
        "cuenta, el hijo la hereda y no cambia nada; si no la tiene, el gasto "
        "cae por descarte en otro departamento y el GOP cuadra igual:\n  "
        + "\n  ".join(f"{d} ({pl_engine.CHECKBOOK_DEPT_CONSOLIDATION[d]} es su "
                      f"padre): {sorted(c)}" for d, c in sorted(sobran.items())))


def test_los_hijos_si_llevan_planilla(reglas):
    """El complemento: la regla saca el gasto, no vacía al departamento. Sin
    esto, «ningún hijo lleva reglas» pasaría borrándolos enteros — y la planilla
    del hijo caería por descarte, que es lo que se está evitando."""
    hijos = set(pl_engine.CHECKBOOK_DEPT_CONSOLIDATION)
    con_planilla = {(r.get("dept_code") or "").strip() for r in reglas
                    if (r.get("account_code") or "").startswith("6")}
    # No todos los hijos tienen planilla propia (varios la heredan del padre),
    # pero los que la declaran tienen que seguir teniéndola.
    esperados = {"0181", "0184"}
    faltan = sorted(esperados - con_planilla)
    assert not faltan, (
        f"estos hijos se quedaron sin reglas de planilla: {faltan}. "
        "El hijo lleva planilla — es el gasto lo que es del padre.")
    assert esperados <= hijos, "cambió el mapa de padres: revisar esta prueba"
