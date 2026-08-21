# -*- coding: utf-8 -*-
"""El provisionamiento se hace por departamento MADRE.

Owner, 2026-08-15: «los departamentos que se provisionan son los departamentos
madres, y cuando escogés una madre automáticamente adoptás todo el paquete… la
estructura 0110 conlleva implícito 0115 y 0116 como estructura primaria, y todos
los hijos, que ya lleva por default».

Antes la matriz listaba los 39 departamentos en fila plana, con cuatro casillas
independientes cada uno: se podía prender Ama de Llaves y apagar Front Desk
siendo los dos la misma Habitaciones, y nada avisaba.

Lo que estas pruebas cuidan son las tres trampas que hacen que esto NO sea
trivial:

1. **«Paquete» significa dos cosas distintas.** Para PROVISIONAR (visibilidad)
   manda `parent_dept_code` a secas y los sets de producto entran; para CALCULAR
   manda la bandera `room_set` y los sets quedan afuera, con checkbook de gasto
   propio. Unir los dos criterios acá no puede filtrarse al cálculo.
2. **La cadena sube recursiva** (`0132 → 0130 → 0140`): el paquete no se arma
   con un salto.
3. **Esto filtra VISIBILIDAD, nunca el cálculo.**
"""
import inspect
from types import SimpleNamespace

import pytest

from fastapi import HTTPException

from app.api import provisioning_api
from app.api.provisioning_api import (
    _cadena_de_padres, _expandir_al_paquete, _filas_por_madre, _madre_de, _paquetes,
)

# Lo que CWL tiene apagado hoy, 2026-08-16: cuatro casillas y nada más.
# `0156` Crowther Lab entero (no tiene hijos) y `0180` Administración SOLO en
# planilla —con sus cinco hijos prendidos—. La orden del owner al autorizar esto
# fue «no apagues nada de lo que ya hemos acordado».
APAGADO_HOY = {("0156", "COST"), ("0156", "OPEX"), ("0156", "PAYROLL"),
               ("0180", "PAYROLL")}


def _dept(code, padre=None, set_=False, rev=True):
    return SimpleNamespace(dept_code=code, dept_name=code, name_en="",
                           parent_dept_code=padre, room_set=set_,
                           is_revenue_dept=rev, is_allocation_source=False,
                           pl_kind="OPERATING", default_pl_group="ROOMS")


def _catalogo_real():
    """El catálogo de verdad, derivado de las mismas constantes que el seed."""
    from app.seed_department_catalog import build_rows
    filas = [SimpleNamespace(**r) for r in build_rows()]
    # Villas y Residencias entran por la migración 085, no por el seed: cuelgan
    # de 0110 y llevan la bandera de SET.
    for code, nombre in (("0115", "Villas"), ("0116", "Residencias")):
        filas.append(SimpleNamespace(
            dept_code=code, dept_name=nombre, name_en=nombre,
            parent_dept_code="0110", room_set=True, is_revenue_dept=False,
            is_allocation_source=False, pl_kind="OPERATING",
            default_pl_group="ROOMS"))
    for f in filas:
        if not hasattr(f, "room_set"):
            f.room_set = f.dept_code == "0110"
    return filas


# ── la cadena ─────────────────────────────────────────────────────────────────
def test_la_cadena_sube_recursiva():
    """`0132 → 0130 → 0140`. Con un solo salto, la planilla del Spa colgaría de
    `0130` —que a su vez es hijo— y `0140` mostraría un paquete incompleto."""
    padre_de = {"0140": "", "0130": "0140", "0132": "0130"}
    assert _cadena_de_padres("0132", padre_de) == ["0130", "0140"]
    assert _madre_de("0132", padre_de) == "0140"
    assert _madre_de("0140", padre_de) == "0140"


def test_la_cadena_corta_ante_un_ciclo():
    """Un padre mal capturado no puede colgar la pantalla."""
    padre_de = {"A": "B", "B": "A"}
    assert _cadena_de_padres("A", padre_de) == ["B"]
    assert _madre_de("A", padre_de) == "B"


def test_un_padre_que_no_existe_no_hace_desaparecer_al_hijo():
    """Ante la duda se muestra de más, nunca de menos: si el padre no está en el
    catálogo, el hijo se provisiona solo en vez de esfumarse de la matriz."""
    catalogo = [_dept("0110"), _dept("0999", padre="0000")]
    madre_de, paquete = _paquetes(catalogo)
    assert madre_de["0999"] == "0999"
    assert set(paquete) == {"0110", "0999"}


# ── el paquete ────────────────────────────────────────────────────────────────
def test_la_matriz_es_de_madres_y_no_de_39_sueltos():
    catalogo = _catalogo_real()
    madre_de, paquete = _paquetes(catalogo)
    assert len(catalogo) == 39, "el catálogo del grupo"
    hijos = [c for c, m in madre_de.items() if m != c]
    assert len(hijos) == 16, hijos
    assert len(paquete) == 23, sorted(paquete)


def test_los_sets_de_producto_entran_en_el_paquete_de_su_madre():
    """`0115` Villas y `0116` Residencias tienen padre pero NO son hijos
    funcionales. Para PROVISIONAR van adentro de `0110` igual: son su estructura
    primaria (owner)."""
    _, paquete = _paquetes(_catalogo_real())
    assert set(paquete["0110"]) == {"0110", "0111", "0112", "0113", "0114",
                                    "0115", "0116"}


def test_el_paquete_del_spa_junta_a_los_dos_hijos():
    _, paquete = _paquetes(_catalogo_real())
    assert set(paquete["0140"]) == {"0140", "0130", "0132"}
    assert "0130" not in paquete, "0130 es hijo: no lleva interruptor propio"


def test_administracion_arrastra_a_los_que_llevan_la_planilla():
    """El caso que hay que mirar antes de tocar nada: apagar `0180` en PAYROLL
    bajo esta regla se lleva puestos a los cinco que tienen la gente."""
    _, paquete = _paquetes(_catalogo_real())
    assert set(paquete["0180"]) == {"0180", "0181", "0182", "0183", "0184", "0186"}


def test_la_madre_va_primero_en_su_paquete():
    """Es la que lleva el interruptor y la que se manda al endpoint."""
    _, paquete = _paquetes(_catalogo_real())
    for madre, miembros in paquete.items():
        assert miembros[0] == madre, madre


def test_ningun_departamento_queda_afuera_de_algun_paquete():
    """39 departamentos repartidos en 23 paquetes, sin perder ni repetir a
    nadie: un departamento que no esté en ninguno desaparece de la pantalla."""
    catalogo = _catalogo_real()
    _, paquete = _paquetes(catalogo)
    todos = [c for miembros in paquete.values() for c in miembros]
    assert sorted(todos) == sorted(d.dept_code for d in catalogo)
    assert len(todos) == len(set(todos)), "alguien quedó en dos paquetes"


# ── el paquete de VISIBILIDAD no es el del CÁLCULO ────────────────────────────
def test_el_paquete_de_provisionar_usa_el_parentesco_a_secas():
    """Y por eso tiene 16 hijos donde el motor consolida 14: los dos de
    diferencia son los sets. Si acá se filtrara por `room_set`, Villas y
    Residencias quedarían con interruptor propio y la estructura primaria de
    Habitaciones se podría partir en dos."""
    src = inspect.getsource(_paquetes)
    assert "room_set" not in src, (
        "el paquete de provisionamiento se arma con parent_dept_code a secas")


def test_el_calculo_sigue_separando_los_sets():
    """La bandera manda donde tiene que mandar: el gasto operativo. Villas y
    Residencias NO son hijos funcionales y conservan checkbook propio —sacarlos
    por error ya costó una corrección."""
    from app.api.audit_api import es_hijo_funcional
    villas = _dept("0115", padre="0110", set_=True)
    front_desk = _dept("0111", padre="0110")
    assert not es_hijo_funcional(villas)
    assert es_hijo_funcional(front_desk)


def test_esto_no_toca_el_calculo():
    """La regla que hace seguro todo el provisionamiento: el motor no lee la
    matriz. Agrupar por madre no puede convertirse en un filtro de cálculo."""
    import pathlib
    motor = pathlib.Path(provisioning_api.__file__).parent.parent / "engine"
    ofensores = [p.name for p in motor.glob("*.py")
                 if "DeptEnablement" in p.read_text(encoding="utf-8")]
    assert not ofensores, ofensores


# ── el endpoint ───────────────────────────────────────────────────────────────
def test_guardar_expande_al_paquete_en_el_backend():
    """La expansión NO puede vivir solo en la pantalla: si la hiciera el
    navegador, cualquier otro cliente podría dejar un hijo prendido con su madre
    apagada, que es justo lo que esto cierra."""
    src = inspect.getsource(provisioning_api.guardar_matriz)
    assert "_expandir_al_paquete(body.rows, catalogo)" in src
    # y lo que se escribe son las casillas expandidas, no las que llegaron
    assert "for (dept_code, dimension), r in objetivo.items()" in src


def test_el_ingreso_no_aplica_a_los_sets():
    assert provisioning_api._aplica(_dept("0115", set_=True, rev=False), "REVENUE") is False
    assert provisioning_api._aplica(_dept("0115", set_=True, rev=False), "PAYROLL") is True


def test_expandir_una_madre_escribe_todo_el_paquete():
    """Apagar `0180` en planilla toca las seis filas de Administración."""
    fila = SimpleNamespace(dept_code="0180", dimension="PAYROLL",
                           enabled=False, notes="")
    objetivo = _expandir_al_paquete([fila], _catalogo_real())
    assert {c for c, _ in objetivo} == {"0180", "0181", "0182", "0183", "0184", "0186"}
    assert all(dim == "PAYROLL" for _, dim in objetivo)


def test_expandir_saltea_a_quien_no_lleva_esa_dimension():
    """Habitaciones en INGRESO son cinco, no siete: Villas y Residencias no
    facturan, y una fila «REVENUE apagado» ahí sería una decisión inventada."""
    fila = SimpleNamespace(dept_code="0110", dimension="REVENUE",
                           enabled=False, notes="")
    objetivo = _expandir_al_paquete([fila], _catalogo_real())
    assert {c for c, _ in objetivo} == {"0110", "0111", "0112", "0113", "0114"}


def test_expandir_rechaza_un_hijo_suelto():
    fila = SimpleNamespace(dept_code="0113", dimension="OPEX",
                           enabled=False, notes="")
    with pytest.raises(HTTPException) as e:
        _expandir_al_paquete([fila], _catalogo_real())
    assert e.value.status_code == 422
    assert "0110" in e.value.detail


# ── lo que ya estaba apagado sigue apagado, y nada más ────────────────────────
def _matriz_de_hoy():
    return _filas_por_madre(_catalogo_real(), set(APAGADO_HOY), {})


def test_hoy_la_matriz_muestra_23_madres():
    filas, _ = _matriz_de_hoy()
    assert len(filas) == 23
    assert all(f["parent_dept_code"] == "" for f in filas), (
        "todas las filas son madres")


def test_las_cuatro_casillas_apagadas_de_hoy_siguen_apagadas():
    """La verificación que pidió el owner: se cambia la agrupación y NO se
    cambia el estado de nada."""
    filas, _ = _matriz_de_hoy()
    off = {(f["dept_code"], dim)
           for f in filas for dim, v in f["dims"].items()
           if v["aplica"] and not v["enabled"]}
    assert off == APAGADO_HOY


def test_no_se_apago_ni_una_casilla_de_mas():
    """El resto de la matriz queda intacto: 23 madres × 4 dimensiones, menos las
    que no aplican, menos las cuatro de siempre."""
    filas, _ = _matriz_de_hoy()
    prendidas = sum(1 for f in filas for v in f["dims"].values()
                    if v["aplica"] and v["enabled"])
    aplicables = sum(1 for f in filas for v in f["dims"].values() if v["aplica"])
    assert aplicables - prendidas == 4


def test_crowther_queda_apagado_limpio_porque_no_tiene_hijos():
    filas, _ = _matriz_de_hoy()
    f = next(x for x in filas if x["dept_code"] == "0156")
    assert len(f["paquete"]) == 1
    for dim in ("COST", "OPEX", "PAYROLL"):
        assert f["dims"][dim]["enabled"] is False
        assert f["dims"][dim]["mixto"] is False


def test_administracion_en_planilla_sale_MIXTA_y_no_se_toca():
    """▶️ La señal que el owner quiere ver. El estado de hoy —madre apagada,
    los cinco hijos que llevan la planilla prendidos— NO se puede representar
    con un interruptor por paquete. No se resuelve: se muestra.

    Resolverlo hacia «apagado» escondería la planilla de Gerencia, Finanzas,
    Compras, RRHH y Seguridad; hacia «prendido» borraría una decisión que
    alguien tomó. Las dos son cambios que nadie pidió."""
    filas, mixtos = _matriz_de_hoy()
    f = next(x for x in filas if x["dept_code"] == "0180")
    dim = f["dims"]["PAYROLL"]
    assert dim["mixto"] is True
    assert dim["apagados"] == ["0180"], "solo la madre está apagada"
    assert dim["miembros"] == 6
    assert mixtos == 1, "es el único caso en toda la matriz"


def test_la_matriz_no_escribe_nada():
    """Es un GET: describir el estado no puede cambiarlo."""
    src = inspect.getsource(_filas_por_madre)
    assert "db.add" not in src and "db.delete" not in src


def test_la_fila_ya_no_lleva_padre():
    """Todas las filas son madres; la llave queda vacía para no romper a quien
    la lea."""
    src = inspect.getsource(_filas_por_madre)
    assert '"parent_dept_code": ""' in src


def test_los_datos_del_paquete_se_suman():
    """La casilla habla por el paquete, así que el conteo que decide si esto es
    una limpieza o un error tiene que incluir a los hijos. Si mostrara solo los
    de la madre, apagar Administración en planilla se vería como si no hubiera
    nada detrás."""
    conteos = {"0181": {"PAYROLL": 7}, "0184": {"PAYROLL": 3},
               "0180": {"PAYROLL": 0}}
    filas, _ = _filas_por_madre(_catalogo_real(), set(), conteos)
    f = next(x for x in filas if x["dept_code"] == "0180")
    assert f["dims"]["PAYROLL"]["datos"] == 10
    assert f["datos_totales"] == 10


@pytest.mark.parametrize("dim", ["REVENUE", "PAYROLL", "OPEX", "COST"])
def test_las_cuatro_dimensiones_siguen_siendo_las_mismas(dim):
    """Agrupar por madre no agrega ni quita dimensiones."""
    assert dim in provisioning_api.DIMS_DEPT
    assert len(provisioning_api.DIMS_DEPT) == 4
