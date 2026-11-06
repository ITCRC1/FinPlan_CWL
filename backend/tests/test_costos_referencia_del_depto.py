# -*- coding: utf-8 -*-
"""El checkbook de costos enseña el ingreso DEL DEPARTAMENTO, no el del hotel.

Owner, 2026-11-05, parado en 0150 Tour Activities: *«acá debe estar el ingreso
del departamento en vista… y si cambio debe estar el otro»*.

La fila de referencia mostraba `total` —los $6,65 millones de todo CWL— en los
doce departamentos. Para sacar un % de costo de Tours eso no sirve: la cuenta
se hace contra los $948.613 de Tours.

Tres cosas que se pueden romper por separado y ninguna avisa:

1. que el mapa `DEPT_REV_REF` deje fuera un departamento que sí vende;
2. que mande a una línea que el backend no devuelve (sale en cero);
3. que el backend deje de mandar una línea que el mapa usa.
"""
import re

from tests._rutas import FRONT

PAGINA = FRONT / "app" / "costs" / "checkbook" / "page.tsx"
API = __import__("pathlib").Path(__file__).resolve().parents[1] / "app" / "api" / "costs_api.py"


def _mapa() -> dict[str, list[str]]:
    """`DEPT_REV_REF` leído del .tsx."""
    fuente = PAGINA.read_text(encoding="utf-8")
    m = re.search(r"const DEPT_REV_REF:[^=]*=\s*\{(.*?)\n\};", fuente, re.S)
    assert m, "no encontré DEPT_REV_REF en la pantalla"
    out = {}
    for dep, lineas in re.findall(r'"(\d+)":\s*\[([^\]]*)\]', m.group(1)):
        out[dep] = re.findall(r'"(\w+)"', lineas)
    return out


def _llaves_que_manda_el_backend() -> set[str]:
    """Las líneas dentro de `revenue_reference`, en minúscula como van."""
    fuente = API.read_text(encoding="utf-8")
    m = re.search(r'"revenue_reference":\s*\{(.*?)\n\s*\}\n', fuente, re.S)
    assert m, "no encontré revenue_reference en costs_api"
    return set(re.findall(r'^\s*"(\w+)":', m.group(1), re.M))


#: Departamentos que tienen costo pero NO venden: su costo va MANUAL y no hay
#: ingreso contra qué medirlo. Estar acá es una decisión, no un olvido.
SIN_INGRESO_PROPIO = {"0156", "0205", "0220", "0230", "270"}

#: Los que tienen líneas de costo en el Budget Working 2027 de CWL.
CON_COSTO = {"0120", "0150", "0152", "0155", "0156", "0162",
             "0165", "0205", "0220", "0230", "260", "270"}


def test_todo_departamento_que_vende_tiene_su_linea():
    mapa = _mapa()
    faltan = {d for d in CON_COSTO if d not in SIN_INGRESO_PROPIO} - set(mapa)
    assert not faltan, (
        f"estos departamentos tienen costo y venden, pero la pantalla no sabe "
        f"contra qué ingreso medirlo: {sorted(faltan)}")


def test_ninguna_linea_del_mapa_sale_en_cero_por_no_existir():
    """Apuntar a una línea que el backend no manda da $0 sin decir nada."""
    llaves = _llaves_que_manda_el_backend()
    malas = {(dep, linea) for dep, lineas in _mapa().items() for linea in lineas
             if linea.lower() not in llaves}
    assert not malas, (
        f"la pantalla pide líneas que `revenue_reference` no trae: {sorted(malas)}. "
        f"Las que manda hoy: {sorted(llaves)}")


def test_las_tres_lineas_que_faltaban_ya_se_mandan():
    """Lavandería, F&B Misc y el Club: el motor las calcula desde siempre y la
    respuesta no las incluía, así que su fila salía en cero."""
    llaves = _llaves_que_manda_el_backend()
    for linea in ("laundry", "fnb_misc", "club"):
        assert linea in llaves, f"`{linea}` volvió a faltar en revenue_reference"


def test_spa_apunta_a_0140_que_es_donde_vive_en_CWL():
    """El mapa tenía 0130 (Spa gerencia). El departamento con costo es 0140."""
    mapa = _mapa()
    assert mapa.get("0140") == ["SPA"], mapa.get("0140")


def test_ayb_enseña_sus_dos_lineas():
    """Comida y bebida se presupuestan aparte y sus costos también."""
    assert _mapa().get("0120") == ["FOOD", "BEVERAGE"]


def test_los_que_no_venden_se_quedan_fuera_a_proposito():
    mapa = _mapa()
    metidos = SIN_INGRESO_PROPIO & set(mapa)
    assert not metidos, (
        f"{sorted(metidos)} no venden nada: darles una línea de referencia "
        f"invita a sacar un % contra un ingreso que no es suyo")


def test_la_fila_del_total_del_hotel_sigue_estando():
    """Sirve para ver cuánto pesa el departamento. Se queda, más apagada."""
    fuente = PAGINA.read_text(encoding="utf-8")
    assert 'referenceTotal' in fuente
    assert '?.total ?? "0"' in fuente
