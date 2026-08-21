# -*- coding: utf-8 -*-
"""El setup de la cuenta tiene que decir la verdad, y decirla desde el motor.

**Por qué existe.** El owner (2026-08-16) pidió poder recorrer cuenta por cuenta
qué es, qué departamento, en qué línea del P&L cae, cómo llegó ahí y si se
alinea entre años — porque eso es lo que hace clonable una propiedad.

Una herramienta cuyo ÚNICO trabajo es decir la verdad falla de dos maneras, y
las dos ya salieron caras en este proyecto:

  1. **Se vuelve una segunda lista.** Si los rótulos, las clases o las líneas se
     escriben acá a mano, se desincronizan del mapeo y del catálogo. Así esta
     app llegó a mostrar 22 departamentos con 38 en la base.
  2. **Usa un resolvedor propio.** Una réplica «exacta» que se queda atrás hace
     que la vista jure una cosa mientras el P&L hace otra. El tab de Control ya
     tuvo una y hubo que sacarla (`pl_engine.construir_resolvedor`).

Y una tercera, específica de esta vista: los gastos del propietario
(`nonop_entries`) **no pasan por el mapeo** —siembran su línea directo—, así que
resolverlos con el mapeo los acusa de «por descarte» cuando están bien.
"""
import inspect

import pytest

from app.api import setup_cuenta_api as mod


def test_usa_el_resolvedor_del_motor_y_no_una_copia():
    """La línea la decide `pl_engine.construir_resolvedor`, el mismo del P&L."""
    fuente = inspect.getsource(mod.armar_setup)
    assert "construir_resolvedor" in fuente, (
        "El setup de la cuenta dejó de usar el resolvedor del motor. Una copia "
        "que se queda atrás hace que esta pantalla jure una cosa mientras el "
        "P&L hace otra — y esta pantalla existe justamente para decir la verdad."
    )
    # Y las piezas propias del ruteo no pueden reaparecer acá.
    for prohibido in ("lookup_exact", "lookup_by_acct", "_cadena_de_padres"):
        assert prohibido not in fuente, (
            f"Volvió una réplica del resolvedor ({prohibido}) dentro del setup "
            f"de la cuenta.")


def test_las_fuentes_son_las_mismas_del_tab_de_control():
    """De dónde sale la plata no se re-enumera: se reusa `audit_api._sources`.

    Es la única enumeración que ya contempla las dos vías (auxiliar y detalle
    GL), la planilla por concepto, los repartos y los gastos del propietario.
    Una segunda enumeración se olvida de una tabla y la vista reporta de menos
    sin dar error.
    """
    assert mod._sources is not None
    from app.api import audit_api
    assert mod._sources is audit_api._sources


def test_el_tipo_de_depto_sale_de_la_bandera_y_no_del_parentesco():
    """Madre / hijo funcional / set de producto — con el criterio de siempre."""
    from app.api import audit_api
    assert mod.es_hijo_funcional is audit_api.es_hijo_funcional

    class D:
        def __init__(self, padre, room_set):
            self.parent_dept_code, self.room_set = padre, room_set

    assert mod._tipo_de_depto(D("", False)) == "Madre"
    assert mod._tipo_de_depto(D("", True)) == "Madre"      # 0110 tiene la bandera
    assert mod._tipo_de_depto(D("0110", False)) == "Hijo funcional"   # 0113
    assert mod._tipo_de_depto(D("0110", True)) == "Set de producto"   # 0115 Villas
    assert mod._tipo_de_depto(None) == "Fuera del catálogo"


def test_las_cuatro_clases_del_owner_estan_y_se_llaman_como_el_las_llama():
    """«qué es ingreso, qué es costo, qué es gasto y qué es gastos de la
    propiedad». Son las clases USALI que el sistema ya distingue; lo único que
    hacía falta era mostrarlas juntas y con ESE nombre."""
    assert mod.CLASES["4"] == "Ingreso"
    assert mod.CLASES["5"] == "Costo"
    assert mod.CLASES["7"] == "Gasto"
    assert mod.CLASES["8"] == "Gasto de la propiedad"
    # La planilla es gasto, pero tiene auxiliar y cuentas propias: se muestra
    # aparte para poder filtrarla, no porque sea otra cosa.
    assert mod.CLASES["6"] == "Planilla"


@pytest.mark.parametrize("modo,limpia", [
    ("exact", True),
    ("parent", True),          # un reparto que hereda del padre está BIEN
    ("dept-agnostic", True),
    ("siembra", True),         # los gastos del propietario no pasan por el mapeo
    ("FALLBACK", False),       # por descarte: aterriza en la línea de OTRO depto
    ("DROP", False),           # sin regla: la plata no llega al P&L
    ("siembra-rota", False),   # siembra una línea que no existe: se pierde
])
def test_que_cuenta_como_limpio(modo, limpia):
    assert mod.COMO[modo][1] is limpia


def test_los_gastos_del_propietario_no_se_resuelven_con_el_mapeo():
    """`nonop_entries` trae su `report_line_code` y viene SIN departamento.

    Pasarlo por el resolvedor lo devuelve como FALLBACK —porque encuentra una
    regla de otro departamento para esa cuenta— y la vista acusaría de sucio
    algo que está bien y por diseño. Medido en producción: la 8025 ($102.000) y
    la 8040 ($312.000) del Budget Working 2027 salían marcadas «por descarte».
    """
    fuente = inspect.getsource(mod.armar_setup)
    assert "seed_line" in fuente, (
        "El setup de la cuenta volvió a rutear los gastos del propietario por "
        "el mapeo. Van por su línea sembrada; lo único que hay que verificarles "
        "es que esa línea exista."
    )


def test_la_llave_incluye_la_linea_sembrada():
    """Una MISMA cuenta below-GOP alimenta dos líneas (la 8020 es Reserva de
    Capital y Capex Grande). Sin la línea en la llave, las dos colapsan en una
    fila que miente sobre las dos."""
    fuente = inspect.getsource(mod.armar_setup)
    assert "for dept, cuenta, sembrada in pares" in fuente


def test_la_alineacion_excluye_al_depto_que_no_existia():
    """La pregunta 5 se mide solo entre departamentos VIVOS en los dos años.

    Sin ese filtro la lista se llena de ruido que no es un problema de setup: el
    Club (260) y Claro del Bosque (0205) empiezan en 2027, Innoceana (0155)
    termina en 2026 — y con ellos TODA cuenta de planilla y de gasto «cambiaba
    de línea». Medido en producción: 31 cuentas señaladas contra 29 reales, y
    las 29 con celdas ilegibles.
    """
    fuente = inspect.getsource(mod.armar_setup)
    assert "deptos_activos" in fuente
    assert "el depto no estaba" in fuente


def test_el_nombre_de_cuenta_no_se_le_pide_al_dict_del_motor():
    """`load_active_account_mappings` arma el dict que el MOTOR necesita para
    rutear: cuenta, depto, línea. El nombre no está ahí, y pedírselo devuelve
    vacío en silencio — que fue exactamente lo que pasó la primera vez."""
    from app.engine import recalculate
    fuente = inspect.getsource(recalculate.load_active_account_mappings)
    assert "account_name_example" not in fuente
    propia = inspect.getsource(mod.armar_setup)
    assert "AccountMapping.account_name_example" in propia


def test_la_ruta_esta_montada():
    """Un router que nunca se monta da 404 en producción con las pruebas en
    verde. Ya pasó dos veces esta semana.

    Se mira el esquema publicado y no `app.routes`: FastAPI resuelve los routers
    incluidos de forma perezosa, así que `app.routes` está vacío al importar y
    la prueba pasaría —o fallaría— por el motivo equivocado.
    """
    from app.main import app
    rutas = set(app.openapi()["paths"])
    assert "/api/setup-cuenta/" in rutas
    assert "/api/setup-cuenta/excel/" in rutas


def test_la_ruta_RESPONDE_y_pide_token():
    """No alcanza con que la ruta EXISTA: hay que ejecutarla.

    Los dos modos de falla de esta semana fueron un router que nunca se montó
    (404 en producción con las pruebas en verde) y otro con una dependencia mal
    declarada que daba 500 al primer clic. Las dos se ven acá y ninguna se ve
    leyendo el código: 401 prueba que la ruta se resolvió Y que el guard corrió.
    """
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        assert c.get("/api/ruta-que-no-existe/").status_code == 404
        for ruta in ("/api/setup-cuenta/", "/api/setup-cuenta/excel/"):
            r = c.get(ruta)
            assert r.status_code == 401, (
                f"{ruta} devolvió {r.status_code}: {r.text[:200]}")
