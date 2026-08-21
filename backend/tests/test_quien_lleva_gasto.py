# -*- coding: utf-8 -*-
"""
QUIÉN PUEDE RECIBIR UN GASTO EN EL CHECKBOOK.

`GET /departments/` **deriva** `lleva_gasto` en vez de enumerarlo, para que el
selector de Opex y Costos no sea una lista a mano que se queda vieja. La
derivación arrancó el 2026-08-14 como «no es hijo y tiene alguna regla de clase
5 o 7», y esa primera versión se equivocó en las dos direcciones:

* **Dejó adentro al `0162`** Laundry Revenue. Su única cuenta de clase 5 era la
  `5301`, y esa cuenta existe para recibir el costo de huéspedes que **escribe
  el motor** de repartos — no es un lugar donde alguien digite. Es el mismo
  criterio por el que la `4999` nunca contó, solo que la `4999` es clase 4 y
  quedaba afuera sola.

  ⚠️ **El `0162` volvió a entrar el 2026-08-16, y no por eso.** El owner mandó
  el costo de lavandería a ese departamento («en 0162 es COS») y con eso llegó
  la **`5603`**, que sí se digita. La derivación no se aflojó: cambió el mapeo.
  La prueba de abajo verifica que entre **por la `5603` y solo por ella**, para
  que la `5301` no se cuele de nuevo por la puerta que se abrió.

* **Sacó al `0115` Villas y al `0116` Residencias.** Cuelgan del `0110`, sí,
  pero no son FUNCIONES de Habitaciones como el Front Desk: son **sets de
  producto**, cada uno con sus 30 reglas de clase 5/7 propias y 180 filas de
  `opex_entries`. Y `rooms-sets` es un reporte de solo lectura, así que se
  quedaban sin ninguna pantalla donde cargarles gasto. Estaban en $0,00 —el
  owner todavía no cargó los porcentajes—, o sea que el agujero se destapaba
  justo el día que los cargara.

La propiedad, escrita entera: **acepta gasto el departamento que tiene reglas de
clase 5/7 propias que no son cuentas de reparto, y que no es un hijo FUNCIONAL**
— donde lo que distingue un set de una función es la bandera `room_set`, no el
parentesco solo.
"""
import json
import pathlib

import pytest

from app.api.audit_api import acepta_gasto_operativo, es_hijo_funcional
from app.engine.allocation_calculator import cuentas_de_reparto
from app.seed_department_catalog import build_rows
from app.seed_mapping import ARCHIVO


class _Depto:
    """Lo mínimo que mira la derivación, para no depender de la base."""

    def __init__(self, fila: dict):
        self.dept_code = fila["dept_code"]
        self.dept_name = fila["dept_name"]
        self.parent_dept_code = fila.get("parent_dept_code")
        self.room_set = bool(fila.get("room_set", False))


def _constante_de_migracion(archivo: str, nombre: str):
    """Lee una constante de una migración de alembic.

    El nombre del módulo empieza con dígitos, así que no se puede `import`. Se
    hace igual porque la alternativa es copiar la lista acá y que se quede
    vieja: `0115` y `0116` NO están en `build_rows` —el motor no los conoce,
    entraron al catálogo por la migración 085— y qué departamento es SET lo
    dice la 086. Leerlas es tener una sola fuente.
    """
    import importlib.util
    ruta = (pathlib.Path(__file__).resolve().parents[1]
            / "alembic" / "versions" / archivo)
    spec = importlib.util.spec_from_file_location(ruta.stem, ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, nombre)


#: Qué departamentos son SET de categorías de habitación (migración 086).
SETS = set(_constante_de_migracion("086_set_de_habitaciones.py", "SETS"))

#: Villas y Residencias entraron al catálogo por la 085, colgando del `0110`.
SETS_HIJOS = [{"dept_code": c, "dept_name": n, "parent_dept_code": "0110"}
              for c, n, _en in _constante_de_migracion(
                  "085_villas_residencias.py", "DEPTOS")]


@pytest.fixture(scope="module")
def deptos() -> list[_Depto]:
    filas = build_rows() + SETS_HIJOS
    return [_Depto({**f, "room_set": f["dept_code"] in SETS}) for f in filas]


def test_los_sets_siguen_viniendo_de_la_migracion_y_no_del_motor():
    """Si algún día `build_rows` empieza a emitir Villas y Residencias, hay que
    sacarlos de `SETS_HIJOS` acá — o quedarían duplicados y esta prueba estaría
    midiendo una lista que ya no es la del catálogo."""
    del_motor = {f["dept_code"] for f in build_rows()}
    repetidos = del_motor & {f["dept_code"] for f in SETS_HIJOS}
    assert not repetidos, (
        f"{sorted(repetidos)} ya salen de build_rows(): sacalos de SETS_HIJOS")
    assert SETS == {"0110", "0115", "0116"}, (
        f"cambió qué departamentos son SET ({sorted(SETS)}); revisá si el "
        "selector de gasto tiene que cambiar con ellos")


@pytest.fixture(scope="module")
def con_gasto_propio() -> set[str]:
    reglas = json.loads(pathlib.Path(ARCHIVO).read_text(encoding="utf-8"))["account_mapping"]
    de_reparto = cuentas_de_reparto()
    return {(m.get("dept_code") or "").strip() for m in reglas
            if m["active_status"] == "YES"
            and m["account_code"][:1] in ("5", "7")
            and m["account_code"] not in de_reparto}


def _acepta(deptos, con_gasto_propio) -> set[str]:
    return {d.dept_code for d in deptos if acepta_gasto_operativo(d, con_gasto_propio)}


@pytest.mark.parametrize("dept", sorted({"0115", "0116"}))
def test_un_set_de_habitaciones_lleva_gasto_propio(deptos, con_gasto_propio, dept):
    """Villas y Residencias: cuelgan del `0110` y NO son funciones suyas."""
    d = next(x for x in deptos if x.dept_code == dept)
    assert not es_hijo_funcional(d), (
        f"{dept} es un set de producto, no una función de Habitaciones: la "
        "bandera `room_set` es la que lo distingue del Front Desk")
    assert acepta_gasto_operativo(d, con_gasto_propio), (
        f"{dept} tiene reglas de gasto propias y `rooms-sets` es de solo "
        "lectura: sin el selector no hay dónde cargarle gasto")


@pytest.mark.parametrize("dept", ["0111", "0112", "0113", "0114", "0122", "0123",
                                  "0132", "0182", "0183", "0186", "0191"])
def test_un_hijo_funcional_no_lleva_gasto(deptos, con_gasto_propio, dept):
    """El gasto es del padre (owner, 2026-08-14)."""
    d = next(x for x in deptos if x.dept_code == dept)
    assert es_hijo_funcional(d), f"{dept} debería ser hijo funcional"
    assert not acepta_gasto_operativo(d, con_gasto_propio)


def test_el_0162_entra_por_la_5603_y_no_por_la_5301(deptos, con_gasto_propio):
    """El `0162` ENTRA al selector desde el 2026-08-16, y por una sola cuenta.

    ## Qué cambió, y por qué no es que la derivación se haya aflojado

    Hasta el 15-ago el `0162` tenía UNA sola cuenta de clase 5, la `5301`, y esa
    la **escribe el motor** de repartos (el costo de los kilos de huésped): no
    era un lugar donde alguien digitara, así que el departamento quedaba afuera.

    El 16-ago el owner mandó el costo de lavandería al `0162` —«así debe quedar
    el departamento 0162, debes mover el 0161 a 0162», «en 0162 es COS»— y con
    eso llegó la **`5603`**, que sí se digita: es una cuenta del mayor, no la
    escribe ningún motor, y sin ella no habría dónde presupuestar el costo de
    lavandería del 2027 (hoy los seis presupuestos la tienen en 0,00 — el agujero
    que se midió el mismo día).

    Owner, 2026-08-16: «0162 entra en el checkbook con la cuenta mencionada».

    **La derivación no se tocó.** Sigue diciendo lo mismo: entra el que tiene
    reglas de clase 5/7 propias que NO son cuentas de reparto. Lo que cambió es
    el mapeo. Por eso esta prueba verifica el MOTIVO y no solo el resultado: si
    el `0162` entrara de nuevo por la `5301` sería un defecto, no una decisión.
    """
    d = next(x for x in deptos if x.dept_code == "0162")
    assert acepta_gasto_operativo(d, con_gasto_propio)

    reparto = cuentas_de_reparto()
    propias = {r["account_code"] for r in json.loads(ARCHIVO.read_text("utf-8"))["account_mapping"]
               if r.get("dept_code") == "0162"
               and r["account_code"][:1] in ("5", "7")
               and r["account_code"] not in reparto}
    assert propias == {"5603"}, (
        "el 0162 tiene que entrar por la 5603 y solo por ella. Si aparecio otra "
        f"cuenta ({sorted(propias)}), revisa si de verdad se digita o la escribe "
        "un motor — es como se colo la 5301 la primera vez")


@pytest.mark.parametrize("dept", ["280", "0250"])
def test_los_que_no_tienen_gasto_operativo_siguen_afuera(deptos, con_gasto_propio, dept):
    """`280` es solo ingreso; el `0250` es clase 8 y tiene checkbook propio."""
    d = next(x for x in deptos if x.dept_code == dept)
    assert not acepta_gasto_operativo(d, con_gasto_propio)


def test_el_private_bar_y_los_independientes_siguen_adentro(deptos, con_gasto_propio):
    """Que la resta de cuentas de reparto no se lleve puesto a nadie: la `7310`
    y la `7685` también se digitan a mano, así que el criterio es «tiene alguna
    cuenta de gasto que NO sea de reparto», no «no tiene ninguna»."""
    adentro = _acepta(deptos, con_gasto_propio)
    for dept in ("0121", "0151", "0165", "0205", "0210", "0161", "0140", "0110"):
        assert dept in adentro, f"{dept} tiene gasto propio y se cayó del selector"


def test_la_lista_completa_del_selector(deptos, con_gasto_propio):
    """La foto entera, para que cualquier cambio de la derivación se vea acá y
    no en la pantalla del owner."""
    assert _acepta(deptos, con_gasto_propio) == {
        "0110", "0115", "0116", "0120", "0121", "0140", "0150", "0151", "0152",
        "0155", "0156", "0161", "0162", "0165", "0180", "0190", "0200", "0205",
        "0210", "0220", "0230", "260", "270",
    }
