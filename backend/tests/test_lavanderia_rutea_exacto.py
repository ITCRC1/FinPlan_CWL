# -*- coding: utf-8 -*-
"""
EL INGRESO DE LAVANDERÍA RUTEA POR REGLA EXACTA, NO POR DESCARTE.

El GL trae UN solo departamento «Lavandería» y `gl_detail_importer` asigna el
departamento POR NOMBRE: su tabla manda cualquier «lavander» al `0161`. Así que
el ingreso del servicio (4700/4701/4702) llega etiquetado `0161`, que en el
catálogo es *Laundry Operations* —overhead, `is_revenue_dept=False`— mientras las
reglas estaban escritas para el `0162` *Laundry Revenue*.

Resultado: caían al FALLBACK, que ignora el departamento y agarra la regla de
cualquiera que use esa cuenta. Aterrizaban bien de casualidad, porque esas
cuentas tenían una sola regla.

Las reglas se movieron al `0161`. **La línea destino no cambió** —sigue siendo
`REV_LAUNDRY`—; lo único que cambia es que ahora se resuelve por regla exacta.

Detalle que confirma que el `0161` era lo correcto: las tres reglas ya traían
`source_department='Departamento de Lavanderia'`, el MISMO string que las 39
reglas de gasto del `0161`. Y `mapping_loader` deriva el código de ese nombre,
o sea que una recarga masiva del mapeo ya calculaba `0161`: el `0162` del JSON
contradecía al importador y al cargador a la vez.
"""
import json
import pathlib

from app.engine import pl_engine

MAPEO = (pathlib.Path(pl_engine.__file__).parents[1]
         / "seed_data" / "mapping_pl.json")
INGRESO_LAVANDERIA = ("4700", "4701", "4702")


def _reglas() -> list[dict]:
    return json.loads(MAPEO.read_text(encoding="utf-8"))["account_mapping"]


def test_el_ingreso_de_lavanderia_siempre_va_a_su_linea():
    """Vive en `0161` y en `0162`, y en los dos va a `REV_LAUNDRY`.

    Antes esta prueba exigía que viviera SOLO en el `0161`. La norma del owner
    (2026-08-13) es que `0162` es el departamento de INGRESO de lavandería y
    `0161` el que lleva el gasto y desde ahí reparte a todos —al cierre del mes
    `0161` queda en cero—. Así que el ingreso tiene que resolver bien entrando
    por cualquiera de los dos.

    Lo que la prueba vigila no cambió: que estas tres cuentas no se pierdan ni
    se vayan a la línea de otro departamento.
    """
    reglas = [m for m in _reglas() if m["account_code"] in INGRESO_LAVANDERIA]
    por_dept = {}
    for m in reglas:
        por_dept.setdefault((m.get("dept_code") or ""), set()).add(m["account_code"])
        assert m["report_line_code"] == "REV_LAUNDRY", (m["account_code"], m.get("dept_code"))
    for dept in ("0161", "0162"):
        assert por_dept.get(dept) == set(INGRESO_LAVANDERIA), (dept, por_dept.get(dept))


def test_el_ingreso_de_lavanderia_rutea_exacto_por_los_dos_departamentos():
    resolve = pl_engine.construir_resolvedor(_reglas())
    for dept in ("0161", "0162"):
        for codigo in INGRESO_LAVANDERIA:
            regla, como = resolve(dept, codigo)
            assert como == "exact", (dept, codigo, como)
            assert regla["report_line_code"] == "REV_LAUNDRY", (dept, codigo)


def test_rutea_exacto_y_a_la_linea_de_siempre():
    """Lo que importa: misma línea, sin descarte."""
    resolve = pl_engine.construir_resolvedor(_reglas())
    for codigo in INGRESO_LAVANDERIA:
        regla, como = resolve("0161", codigo)
        assert como == "exact", (codigo, como)
        assert regla["report_line_code"] == "REV_LAUNDRY", codigo


def test_el_importador_sigue_mandando_lavanderia_al_0161():
    """Si alguien cambia la tabla del importador, el mapeo queda huérfano.

    Las dos piezas tienen que decir lo mismo: el importador etiqueta y el mapeo
    resuelve. Si se separan, el ingreso vuelve al FALLBACK sin que nada avise.
    """
    from app.importers.gl_detail_importer import dept_code_from_name
    assert dept_code_from_name("Departamento de Lavanderia") == "0161"
    assert dept_code_from_name("LAVANDERIA") == "0161"
