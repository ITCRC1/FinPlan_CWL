# -*- coding: utf-8 -*-
"""La plantilla del Detalle no ofrece departamentos HIJOS para digitar.

**El defecto (owner, 2026-08-18, subiendo junio 2026).** «En Administración
0180 es el único que existe como departamento madre, todos los hijos se
consolidan acá; veo 0184 y este no debe estar. Tampoco spa, debe estar con la
madre y no solo como está ahorita 0130.»

La plantilla se contradecía con el motor: el catálogo ya declara 0184→0180,
0130→0140 y 0181→0180, y el P&L consolida por ahí — pero la plantilla ofrecía
una fila por cada hijo. Se digitaba en un lugar y el total aparecía en otro.

Se PLIEGA, no se descarta: lo que traiga el hijo se acumula en la fila de la
madre. Descartarlo perdería el dato al volver a subir el mes, porque el cierre
mensual reescribe ese mes entero.

**Y la lavandería son DOS departamentos con papeles distintos** — «0162 solo
ocupa Ingreso y Costo; el otro ocupa planilla, opex y las cuentas de
Allocation que dejan en 0 el departamento porque todo se distribuye».
"""
import collections
import json
import pathlib

ORDEN = (pathlib.Path(__file__).parent.parent / "app" / "seed_data"
         / "orden_plantilla.json")
MAPEO = (pathlib.Path(__file__).parent.parent / "app" / "seed_data"
         / "mapping_pl.json")

CLASE = {"4": "Revenue", "5": "Cost", "6": "Payroll", "7": "Opex", "8": "BelowGOP"}


def _clases_por_depto() -> dict:
    orden = json.loads(ORDEN.read_text(encoding="utf-8"))["orden"]
    out = collections.defaultdict(set)
    for f in orden:
        out[f["dept_code"]].add(CLASE.get(str(f["cuenta"])[0], "?"))
    return out


def test_el_ingreso_de_lavanderia_esta_en_el_0162():
    """0162 = Ingreso + Costo. Nada más."""
    clases = _clases_por_depto()
    assert clases["0162"] == {"Revenue", "Cost"}, clases["0162"]

    orden = json.loads(ORDEN.read_text(encoding="utf-8"))["orden"]
    en_0162 = {str(f["cuenta"]) for f in orden if f["dept_code"] == "0162"}
    assert {"4700", "4701", "4702"} <= en_0162


def test_la_operacion_de_lavanderia_no_ofrece_ingreso():
    """0161 = planilla + opex. Su única cuenta clase 4 es la 4900 de
    Distribución, que el sistema genera y la plantilla no ofrece para digitar."""
    orden = json.loads(ORDEN.read_text(encoding="utf-8"))["orden"]
    clase4 = {str(f["cuenta"]) for f in orden
              if f["dept_code"] == "0161" and str(f["cuenta"])[0] == "4"}
    assert clase4 == {"4900"}, clase4

    clases = _clases_por_depto()
    assert {"Payroll", "Opex"} <= clases["0161"]


def test_la_plantilla_pliega_los_hijos_en_su_madre():
    """El generador aplica `consolidate_dept` a TODA cuenta que entra.

    Sin esto reaparecen 0130, 0181 y 0184 como departamentos propios y se
    vuelve a poder digitar en un lugar que el P&L suma en otro.
    """
    import inspect

    from app.api import scenarios_api

    src = inspect.getsource(scenarios_api)
    i = src.index("def _add(dept, code, name, val_by_month):")
    cuerpo = src[i:i + 1400]
    assert "consolidate_dept(dept)" in cuerpo, \
        "`_add` tiene que plegar el departamento hijo en su madre"


def test_los_hijos_conocidos_tienen_madre():
    """Si alguien le saca el padre a uno de estos, vuelve a aparecer suelto en
    la plantilla — y su planilla se rutea por descarte."""
    from app.engine.pl_engine import consolidate_dept, reset_dept_catalog

    reset_dept_catalog()
    assert consolidate_dept("0184") == "0180"   # Recursos Humanos
    assert consolidate_dept("0181") == "0180"   # Gerencia / F&B Management
    assert consolidate_dept("0130") == "0140"   # Spa gerencia → Spa
    assert consolidate_dept("0132") == "0130"   # y la cadena sube
    # Los que NO son hijos se quedan donde están.
    for madre in ("0110", "0120", "0140", "0161", "0162", "0180", "0250"):
        assert consolidate_dept(madre) == madre, madre


def test_las_cuentas_de_distribucion_no_se_digitan():
    """4900/4901/4999 las escribe el motor de allocations. Ofrecerlas para
    escribir sería invitar a contar el reparto dos veces."""
    from app.importers.gl_detail_importer import es_contrapartida_de_allocation

    mp = json.loads(MAPEO.read_text(encoding="utf-8"))["account_mapping"]
    distribucion = [r for r in mp
                    if es_contrapartida_de_allocation(r["account_code"],
                                                      r.get("account_name_example"))]
    assert distribucion, "el mapeo tiene que seguir teniendo las de distribución"
    # La 4900 de lavandería es la que deja el departamento en cero.
    assert any(r["account_code"] == "4900" and r.get("dept_code") == "0161"
               for r in distribucion)


def test_un_departamento_listado_recibe_SOLO_sus_cuentas():
    """Owner (2026-08-18): «0210 Utilities solo tiene sus cuentas específicas.
    Hay basura, cuentas que no aplican para el departamento».

    Antes el filtro era por CLASE —«todas las de opex»— y a Utilities le
    entraban Training, Travel, Entertainment y Equipment Rental: 19 cuentas
    donde su lista tiene 8. Ahora el filtro es por CUENTA.
    """
    import inspect

    from app.api import scenarios_api

    src = inspect.getsource(scenarios_api)
    assert "cuentas_listadas = {(d, str(c)) for d, c in orden_canonico()}" in src
    assert "(m.dept_code, str(m.account_code)) not in cuentas_listadas" in src,         "el filtro tiene que ser por cuenta, no por clase"
    # Y el de clase ya no existe: si vuelve, vuelve la basura.
    assert "clases_del_depto" not in src


def test_utilities_tiene_pocas_cuentas_de_opex():
    """La lista del owner para 0210 es corta y específica: energía, agua,
    combustibles. Si esto crece de golpe, alguien volvió a abrir la puerta."""
    orden = json.loads(ORDEN.read_text(encoding="utf-8"))["orden"]
    opex_0210 = {str(f["cuenta"]) for f in orden
                 if f["dept_code"] == "0210" and str(f["cuenta"])[0] == "7"}
    assert len(opex_0210) <= 10, sorted(opex_0210)
    # Las que el owner señaló como basura NO están en su lista.
    basura = {"7110", "7150", "7175", "7185", "7380", "7400", "7665", "7670", "7675"}
    assert not (opex_0210 & basura), sorted(opex_0210 & basura)


def test_las_cuentas_de_distribucion_SI_se_muestran_en_su_departamento():
    """Owner (2026-08-18): «recuerda que laundry 0161 y cafetería 0220 deben
    quedar en 0 al final de mes». Necesita verlas para comprobar que netean.

    Es seguro: al SUBIR, el parser las salta y el reemplazo las protege. Lo que
    se escriba ahí se ignora; lo que ya estaba, sobrevive.
    """
    import inspect

    from app.api import scenarios_api

    src = inspect.getsource(scenarios_api)
    i = src.index("SI VAN cuando el owner las listo")
    bloque = src[i:i + 1200]
    assert "m.dept_code not in deptos_listados" in bloque,         "solo se ocultan en departamentos que el owner no listó"

    # Y siguen listadas en el archivo del owner, que es de donde salen.
    orden = json.loads(ORDEN.read_text(encoding="utf-8"))["orden"]
    assert ("0161", "4900") in {(f["dept_code"], str(f["cuenta"])) for f in orden}
    assert ("0220", "4901") in {(f["dept_code"], str(f["cuenta"])) for f in orden}


def test_el_parser_ignora_la_distribucion_al_subir():
    """La garantía de que mostrarlas no duplica el reparto."""
    import inspect

    from app.importers import gl_detail_importer

    src = inspect.getsource(gl_detail_importer)
    i = src.index("if es_contrapartida_de_allocation(code, acct_name):")
    assert "continue" in src[i:i + 120], "el parser tiene que saltarlas al leer"
