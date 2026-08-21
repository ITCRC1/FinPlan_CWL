# -*- coding: utf-8 -*-
"""
EL CATÁLOGO DE DEPARTAMENTOS SE EDITA, Y CON BARANDAS.

## Por qué existe (2026-08-16)

B6.4 decía «el motor embebe el catálogo: un clon no puede renombrar, agregar ni
quitar un departamento sin tocar código». Medido, **la mitad ya era falsa**:
`pl_engine.set_dept_catalog()` existe y `main.py` lo llama al arrancar, así que
el motor ya lee `department_catalog`. Lo que faltaba era la **puerta**: la tabla
solo se cambiaba por SQL o migración.

Owner, 2026-08-16: las cuatro propiedades usan **los mismos grupos** de P&L, y
*«es posible que algunos departamentos en Amarena quisiéramos renombrarlos, pero
quizás sea más fácil hacerlo después de clonar»*. O sea: **renombrar sobre una
propiedad que ya tiene datos** es el caso principal, no el borde.

Esto fija las barandas. Cada una es un modo de falla que este sistema YA tuvo:

* el **código no se edita** y **no se reutiliza** — la regla del código de
  categoría de habitación y del código de posición: el nombre es etiqueta, el
  código es la llave con la que se cruza la historia;
* **no se borra, se desactiva** — borrar libera el número y el correlativo lo
  vuelve a entregar;
* el **grupo tiene que existir en el motor** — uno inventado deja al
  departamento sin línea en el P&L, en silencio;
* la **cadena de padres no puede tener ciclos** — el padre decide dónde aterriza
  el gasto;
* **desactivar una madre con hijos activos** deja a los hijos sin destino.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def cliente(monkeypatch):
    """Cliente con una base en memoria: estas pruebas miden REGLAS, no datos."""
    from app.api import catalogo_departamentos_api as api

    catalogo: dict[str, object] = {}

    class _Dept:
        def __init__(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)
            for k, v in {"name_en": "", "name_aliases": None, "is_revenue_dept": False,
                         "is_allocation_source": False, "room_set": False,
                         "parent_dept_code": None, "display_order": 0,
                         "active": True, "default_pl_group": "", "pl_kind": "OPERATING",
                         }.items():
                if not hasattr(self, k):
                    setattr(self, k, v)

    class _DB:
        async def commit(self): pass
        def add(self, d): catalogo[d.dept_code] = d

    async def _todos(_db):
        return sorted(catalogo.values(), key=lambda d: d.dept_code)

    monkeypatch.setattr(api, "_todos", _todos)
    monkeypatch.setattr(api, "DepartmentCatalog", _Dept)

    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.dependency_overrides[api.get_db] = lambda: _DB()

    # Semilla mínima: una madre, un hijo y un grupo real del motor.
    grupo = sorted(api.grupos_conocidos())[0]
    catalogo["0180"] = _Dept(dept_code="0180", dept_name="Administración",
                             default_pl_group=grupo, pl_kind="OVERHEAD")
    catalogo["0181"] = _Dept(dept_code="0181", dept_name="Gerencia",
                             default_pl_group=grupo, pl_kind="OVERHEAD",
                             parent_dept_code="0180")
    c = TestClient(app)
    c.grupo = grupo          # type: ignore[attr-defined]
    c.catalogo = catalogo    # type: ignore[attr-defined]
    return c


def test_renombrar_no_toca_el_codigo_ni_los_alias(cliente):
    """El caso que pidió el owner: renombrar después de clonar.

    El nombre es etiqueta; el CÓDIGO es la llave con la que el mapeo, la planilla
    y los reportes se refieren al departamento. Y los alias son con lo que el
    importador reconoce la etiqueta del mayor: si renombrar los arrastrara, la
    próxima importación dejaría de reconocer esas filas **sin decirlo**.
    """
    cliente.catalogo["0180"].name_aliases = ["administ"]
    r = cliente.put("/api/department-catalog/0180/",
                    json={"dept_name": "Administración Amarena"})
    assert r.status_code == 200, r.text
    d = r.json()["departamento"]
    assert d["dept_name"] == "Administración Amarena"
    assert d["dept_code"] == "0180", "el código no se mueve"
    assert d["name_aliases"] == ["administ"], "renombrar NO toca los alias del GL"
    assert "no mueve ningún número" in r.json()["aviso"]


def test_el_codigo_no_se_puede_editar(cliente):
    """No está en el cuerpo aceptado: mandarlo se ignora, no renombra la llave."""
    r = cliente.put("/api/department-catalog/0180/",
                    json={"dept_code": "9999", "dept_name": "Otro"})
    assert r.status_code == 200, r.text
    assert r.json()["departamento"]["dept_code"] == "0180"
    assert "9999" not in cliente.catalogo


def test_un_codigo_no_se_reutiliza_ni_estando_inactivo(cliente):
    """Borrar libera el número y la historia vieja termina apuntando a otra cosa.
    Por eso no hay DELETE, y por eso el 409 mira también los inactivos."""
    cliente.catalogo["0180"].active = False
    r = cliente.post("/api/department-catalog/",
                     json={"dept_code": "0180", "dept_name": "Reciclado"})
    assert r.status_code == 409
    assert "no se reutiliza jamás" in r.json()["detail"]


def test_no_hay_forma_de_borrar(cliente):
    """La única salida es desactivar."""
    assert cliente.delete("/api/department-catalog/0180/").status_code in (404, 405)


def test_un_grupo_inventado_no_entra(cliente):
    """Dejaría al departamento sin línea en el P&L y no avisaría."""
    r = cliente.post("/api/department-catalog/",
                     json={"dept_code": "0999", "dept_name": "Nuevo",
                           "default_pl_group": "GRUPO_QUE_NO_EXISTE"})
    assert r.status_code == 422
    assert "no existe en el motor" in r.json()["detail"]


def test_el_grupo_vacio_si_es_valido(cliente):
    """El `280` Miscelaneos no tiene grupo a propósito: su ingreso llega a la
    línea por el mapeo de CUENTA, no por grupo."""
    r = cliente.post("/api/department-catalog/",
                     json={"dept_code": "0998", "dept_name": "Por cuenta",
                           "default_pl_group": ""})
    assert r.status_code == 200, r.text


def test_los_grupos_salen_del_motor_y_no_de_una_lista_a_mano(cliente):
    """Una lista escrita acá se queda vieja el día que el motor gane un grupo."""
    from app.api.catalogo_departamentos_api import grupos_conocidos
    from app.engine import pl_engine
    assert grupos_conocidos() == (set(pl_engine.OPERATING_DEPT_GROUPS)
                                  | set(pl_engine.OVERHEAD_DEPT_GROUPS))
    assert cliente.get("/api/department-catalog/").json()["grupos"]


def test_la_cadena_de_padres_no_admite_ciclos(cliente):
    """El padre decide dónde aterriza el gasto: un ciclo es un reporte que no
    cierra. `0181` ya cuelga de `0180`; colgar `0180` de `0181` lo cierra."""
    r = cliente.put("/api/department-catalog/0180/",
                    json={"parent_dept_code": "0181"})
    assert r.status_code == 422
    assert "ciclo" in r.json()["detail"]


def test_nadie_es_su_propio_padre(cliente):
    r = cliente.put("/api/department-catalog/0181/",
                    json={"parent_dept_code": "0181"})
    assert r.status_code == 422


def test_un_padre_que_no_existe_no_entra(cliente):
    r = cliente.post("/api/department-catalog/",
                     json={"dept_code": "0997", "dept_name": "Huérfano",
                           "parent_dept_code": "XXXX"})
    assert r.status_code == 422
    assert "no existe" in r.json()["detail"]


def test_no_se_desactiva_una_madre_con_hijos_activos(cliente):
    """«El gasto es del padre»: desactivar la madre deja al hijo sin destino."""
    r = cliente.put("/api/department-catalog/0180/", json={"active": False})
    assert r.status_code == 409
    assert "0181" in r.json()["detail"], "el aviso nombra al hijo, no dice solo 'tiene hijos'"


def test_se_desactiva_cuando_ya_no_tiene_hijos_activos(cliente):
    cliente.put("/api/department-catalog/0181/", json={"active": False})
    r = cliente.put("/api/department-catalog/0180/", json={"active": False})
    assert r.status_code == 200, r.text
    assert r.json()["departamento"]["active"] is False


def test_cambiar_de_grupo_avisa_que_el_motor_lo_toma_al_arrancar(cliente):
    """`set_dept_catalog` corre en el startup: un cambio de grupo no se ve en el
    P&L hasta el próximo despliegue. Decirlo es la diferencia entre «no funciona»
    y «todavía no».
    """
    r = cliente.put("/api/department-catalog/0181/",
                    json={"default_pl_group": cliente.grupo, "pl_kind": "OPERATING"})
    assert r.status_code == 200, r.text
    assert "próximo despliegue" in r.json()["aviso"]


def test_el_nombre_no_puede_quedar_vacio(cliente):
    assert cliente.put("/api/department-catalog/0180/",
                       json={"dept_name": "   "}).status_code == 422
