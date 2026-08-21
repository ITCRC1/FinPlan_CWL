# -*- coding: utf-8 -*-
"""La API de Guillermo — permisos y puertas (`docs/GUILLERMO.md` §7 y §9.5).

Lo que se vigila acá es **quién puede qué**, y que ninguna puerta que da
permiso de escribir se abra por un typo.
"""
import inspect

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def cliente():
    return TestClient(app, raise_server_exceptions=False)


# ── El rol nuevo NO puede heredar los endpoints de admin ────────────────────

def test_el_rol_nuevo_NO_hereda_los_endpoints_de_administracion():
    """⚠️ **El defecto que esto evita.** `get_current_admin` compara contra
    «admin» a secas. Si al agregar `guillermo_approver` alguien hubiera
    relajado esa comparación a «cualquier rol de la lista», el aprobador de
    Guillermo habría ganado de golpe crear usuarios, editar orígenes y tocar
    integraciones — 12 endpoints que nadie le quiso dar.
    """
    from app.auth import get_current_admin

    fuente = inspect.getsource(get_current_admin)
    assert 'user.role != "admin"' in fuente, (
        "get_current_admin dejó de exigir exactamente «admin»")


def test_el_admin_TAMBIEN_puede_aprobar_excepciones():
    """⚠️ Si el único rol habilitado fuera `guillermo_approver`, el
    administrador quedaría afuera de la cola — y con él la única persona que
    puede crear ese rol. Un permiso que puede dejar a todos afuera no es un
    permiso, es una trampa."""
    from app.auth import get_guillermo_approver

    fuente = inspect.getsource(get_guillermo_approver)
    assert '"admin"' in fuente and '"guillermo_approver"' in fuente


def test_el_rol_entra_en_la_columna_y_no_necesito_migracion():
    from app.models.user import ROLES, User

    assert "guillermo_approver" in ROLES
    assert len("guillermo_approver") <= User.__table__.c.role.type.length


# ── Las puertas que dan permiso de escribir ─────────────────────────────────

def test_cambiar_la_config_exige_el_rol():
    """En la config vive `autonomy_level`, o sea el permiso de escribir en el
    modelo financiero. Leerla puede cualquiera; cambiarla no."""
    from app.api import guillermo_api

    leer = inspect.getsource(guillermo_api.leer_config)
    escribir = inspect.getsource(guillermo_api.guardar_config)
    assert "get_current_user" in leer
    assert "get_guillermo_approver" in escribir


def test_resolver_una_excepcion_exige_el_rol():
    from app.api import guillermo_api

    fuente = inspect.getsource(guillermo_api.resolver)
    assert "get_guillermo_approver" in fuente


def test_el_nivel_de_autonomia_NO_acepta_cualquier_texto():
    """⚠️ Un typo dejaría a Guillermo en un modo que no existe. Se valida
    contra la lista de niveles, no contra dos literales sueltos — así agregar
    un nivel no obliga a acordarse de tocar la validación."""
    from app.api import guillermo_api

    fuente = inspect.getsource(guillermo_api.guardar_config)
    assert "v not in NIVELES and v not in _ALIAS" in fuente


def test_UN_NIVEL_DESCONOCIDO_CAE_AL_MAS_BAJO():
    """⚠️ **La dirección del error importa.** Si una configuración mal escrita
    cayera al nivel más alto, un typo le daría permiso de escribir. Cae al más
    bajo: el error quita permisos, nunca los da."""
    from app.guillermo.core import nivel

    assert nivel("ASISTIDO!!").clave == "bajo"
    assert nivel(None).clave == "bajo"
    assert nivel("").clave == "bajo"


def test_los_nombres_del_spec_original_siguen_entrando():
    """`shadow` y `assisted` están guardados en la base de escenarios que ya
    corrieron. Romperlos dejaría a Guillermo en un nivel que no eligió nadie."""
    from app.guillermo.core import nivel

    assert nivel("shadow").clave == "bajo"
    assert nivel("assisted").clave == "medio"


def test_NINGUN_NIVEL_APLICA_UNA_PROPUESTA_DEL_MODELO():
    """⚠️ **La línea que no se cruza en ningún nivel**, incluido el más alto.

    Es la regla absoluta del §4: una propuesta del modelo nunca se aplica sola;
    lo único que se auto-aplica son reglas que un humano aprobó antes. Un nivel
    «alto» que la rompiera no sería más capaz — sería otro sistema, uno en el
    que ya no se puede confiar en el silencio.
    """
    from app.guillermo.core import NIVELES, puede

    for clave, n in NIVELES.items():
        assert n.aplica_propuestas_del_modelo is False, clave
        assert puede(clave, "aplica_propuestas_del_modelo") is False, clave
    # Y tampoco por inventarse un nivel nuevo.
    assert puede("inventado", "aplica_propuestas_del_modelo") is False


def test_lo_que_crece_entre_niveles_es_CUANDO_actua():
    """Bajo mira; medio importa y recalcula cuando se lo piden; alto además
    corre solo. Ninguno gana capacidad de DECIDIR sin humano."""
    from app.guillermo.core import NIVELES

    bajo, medio, alto = NIVELES["bajo"], NIVELES["medio"], NIVELES["alto"]
    assert not bajo.importa and not bajo.recalcula and not bajo.corre_solo
    assert medio.importa and medio.recalcula and not medio.corre_solo
    assert alto.importa and alto.recalcula and alto.corre_solo
    # Los tres encolan: avisar es lo mínimo, no un privilegio.
    assert bajo.encola and medio.encola and alto.encola


def test_un_escenario_enllavado_se_SALTEA_y_no_tumba_el_lote():
    """⚠️ Recalcular «todos» con uno enllavado adentro reventaría la corrida
    entera y no se recalcularía ninguno. El candado tiene que frenar ese
    escenario, no el lote — sobre todo cuando el owner viene de hacer treinta
    cambios."""
    from app.api import guillermo_api

    fuente = inspect.getsource(guillermo_api.recalcular)
    assert '"saltado"' in fuente
    assert 'sc.status == "locked"' in fuente


def test_un_escenario_que_falla_no_frena_a_los_demas():
    from app.api import guillermo_api

    fuente = inspect.getsource(guillermo_api.recalcular)
    assert "except Exception" in fuente
    assert '"falló"' in fuente
    assert "rollback" in fuente


def test_una_excepcion_ya_resuelta_no_se_resuelve_dos_veces():
    """Dos aprobaciones sobre la misma línea crearían dos reglas, y la traza de
    quién decidió qué diría cualquier cosa."""
    from app.api import guillermo_api

    fuente = inspect.getsource(guillermo_api.resolver)
    assert 'x.estado != "pending"' in fuente
    assert "409" in fuente


# ── El estado sale del backend ──────────────────────────────────────────────

def test_el_semaforo_lo_calcula_el_BACKEND_no_la_pantalla():
    """§10.2.7: el componente no infiere ni recuerda nada. Si la UI y la base
    discrepan, gana la base."""
    from app.api import guillermo_api

    fuente = inspect.getsource(guillermo_api.estado)
    assert "estado_visible(" in fuente and "latido_vencido(" in fuente


def test_el_estado_dice_si_FALTA_EL_MANIFIESTO():
    """⚠️ Un Guillermo que nunca reclama nada se ve igual que uno que no tiene
    nada que reclamar. Sin manifiesto no puede opinar, y eso hay que decirlo."""
    from app.api import guillermo_api

    fuente = inspect.getsource(guillermo_api.estado)
    assert "sin_manifiesto" in fuente


# ── Ninguna puerta de Guillermo escribe en el modelo financiero ─────────────

def test_LO_UNICO_QUE_ESCRIBE_ES_EL_BOTON_QUE_EL_OWNER_APRIETA():
    """⚠️ **Esta prueba pasaba por tecnicismo y decía una mentira.**

    Afirmaba que «ningún endpoint de Guillermo escribe en el modelo», y seguía
    en verde después de agregar `/recalcular/` —que sí escribe— porque buscaba
    nombres de clase que ese endpoint no menciona. Una prueba que pasa por el
    motivo equivocado es peor que una que falla: da permiso sin mirar.

    Lo que hay que vigilar no es «no escribe nunca», sino **que lo único que
    escriba sea lo que el owner disparó a mano**. `/recalcular/` existe porque
    él lo pidió así: «dame un botón para que corra cuando yo quiero, yo podría
    hacer unas 30 actualizaciones y no quiero que me pegue a cada rato».
    """
    from app.api import guillermo_api

    # El único que puede escribir en el modelo, y es un POST explícito.
    escribe = inspect.getsource(guillermo_api.recalcular)
    assert "recalculate_scenario" in escribe

    # Los demás sólo leen o tocan las tablas propias de Guillermo.
    for f in (guillermo_api.estado, guillermo_api.faltantes,
              guillermo_api.cuadre, guillermo_api.historial,
              guillermo_api.cola, guillermo_api.niveles,
              guillermo_api.recalculos):
        fuente = inspect.getsource(f)
        assert "recalculate_scenario" not in fuente, f.__name__
        assert "db.add(" not in fuente, f"{f.__name__} escribe"


def test_ninguna_ruta_de_guillermo_toca_las_tablas_del_modelo_directo():
    """La cola se resuelve acá; lo que se aplique se aplicará en el importador,
    con su propia traza."""
    from app.api import guillermo_api

    fuente = inspect.getsource(guillermo_api)
    for prohibido in ("OpexEntry", "CostEntry", "ActualEntry", "PayrollPosition",
                      "PLLine", "NonopEntry", "RevenueEntry"):
        assert prohibido not in fuente, (
            f"la API de Guillermo toca {prohibido}: eso va en el importador")


@pytest.mark.parametrize("ruta", [
    "/api/guillermo/estado/",
    "/api/guillermo/config/",
    "/api/guillermo/importaciones/",
    "/api/guillermo/excepciones/",
])
def test_las_rutas_existen_y_exigen_token(cliente, ruta):
    r = cliente.get(ruta)
    assert r.status_code != 500, r.text[:300]
    assert r.status_code in (401, 403)
