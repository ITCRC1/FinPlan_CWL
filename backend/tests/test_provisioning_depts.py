"""La matriz depto × dimensión del provisionamiento.

Lo que se protege es la regla que hace esto seguro: **filtra la visibilidad,
nunca el cálculo**. Un departamento apagado desaparece del selector, pero si
tiene datos esos datos siguen sumando en el P&L — porque si esconder algo
borrara plata del estado de resultados, sería una forma de cambiar los números
sin dejar rastro.
"""
import inspect

import pytest

from app.models.dept_enablement import DeptEnablement, DIMENSIONES, SCOPE_KINDS
from app.api import provisioning_api


# ── el modelo ─────────────────────────────────────────────────────────────────
def test_las_cinco_dimensiones():
    assert DIMENSIONES == ["REVENUE", "PAYROLL", "OPEX", "COST", "PROPERTY"]


def test_los_tres_alcances():
    assert SCOPE_KINDS == ["DEPT", "REV_LINE", "BELOWGOP_LINE"]


def test_el_default_es_prendido():
    """La tabla es esparsa: sin fila, el departamento está activo. Es lo que
    hace que desplegar esto no cambie nada en ninguna propiedad."""
    assert DeptEnablement.__table__.c.enabled.default.arg is True


def test_la_llave_unica_incluye_la_dimension():
    """Sin la dimensión en la llave, apagar OPEX apagaría también Planilla."""
    uq = [c for c in DeptEnablement.__table__.constraints
          if c.name == "uq_dept_enablement"]
    assert uq, "falta la unique"
    assert {c.name for c in uq[0].columns} == {
        "hotel_id", "scope_kind", "scope_key", "dimension"}


def test_la_matriz_es_por_hotel_y_el_catalogo_no():
    """El universo USALI es uno solo para el grupo: lo que cambia entre
    propiedades es la matriz, no un catálogo bifurcado por hotel."""
    from app.models.department_catalog import DepartmentCatalog
    assert "hotel_id" not in DepartmentCatalog.__table__.c
    assert "hotel_id" in DeptEnablement.__table__.c


# ── el ingreso solo aplica donde se factura ───────────────────────────────────
def test_el_ingreso_no_se_ofrece_en_un_depto_que_no_factura():
    assert provisioning_api.DIMS_DEPT == ["REVENUE", "PAYROLL", "OPEX", "COST"]
    assert set(provisioning_api.DIM_LABEL) >= set(DIMENSIONES)


# ── la regla de seguridad ─────────────────────────────────────────────────────
def test_el_motor_no_lee_la_matriz():
    """El gating vive en los selectores y en el provisionamiento. Si `engine/`
    llegara a leerlo, apagar un departamento cambiaría el P&L en silencio."""
    import pathlib
    motor = pathlib.Path(provisioning_api.__file__).parent.parent / "engine"
    ofensores = [p.name for p in motor.glob("*.py")
                 if "dept_enablement" in p.read_text(encoding="utf-8")
                 or "DeptEnablement" in p.read_text(encoding="utf-8")]
    assert not ofensores, (
        f"El motor no puede leer la habilitación: {ofensores}. Filtra la "
        f"visibilidad, nunca el cálculo.")


def test_apagar_con_datos_pide_confirmacion():
    """`force` existe y es opt-in: el default NO deja apagar algo con datos."""
    campos = provisioning_api.ToggleBody.model_fields
    assert "force" in campos
    assert campos["force"].default is False


def test_prender_borra_la_fila_en_vez_de_escribir_true():
    """Prender vuelve al default borrando el delta; si escribiera enabled=true
    la tabla dejaría de ser esparsa y una propiedad nueva ya no arrancaría
    completa."""
    src = inspect.getsource(provisioning_api.guardar_matriz)
    assert "db.delete(fila)" in src


def test_el_filtro_de_selectores_vive_en_un_solo_lugar():
    """Si la regla de resolución se copia en cada selector, una copia se queda
    atrás y dos pantallas muestran departamentos distintos."""
    from app.api.payroll_api import _esconder_apagados
    from app.api import opex_api, costs_api
    assert callable(_esconder_apagados)
    for mod in (opex_api, costs_api):
        src = inspect.getsource(mod)
        assert "_esconder_apagados" in src, mod.__name__


def test_sin_nada_apagado_el_filtro_no_toca_la_lista():
    """El caso normal: `depts_habilitados` devuelve None y quien llama se salta
    el filtro entero."""
    src = inspect.getsource(provisioning_api.depts_habilitados)
    assert "or None" in src
