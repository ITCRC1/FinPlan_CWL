# -*- coding: utf-8 -*-
"""DOS CAMINOS DE CARGA, NO UN PARÁMETRO QUE HAY QUE TRADUCIR.

**El owner (2026-08-16):** «¿Por qué no hacemos **2 botones**, uno para los
históricos 12 meses y el otro mes a mes? Así queda todo bien configurado y
protegido.»

La razón importa para cómo está implementado: con dos caminos el owner elige la
**intención**, no un parámetro técnico. Hoy tenía que traducir «voy a cerrar
julio» a «alcance = mes», y esa traducción es donde se cuela el error — más
cuando el default es el que abarca todo.

  · **Carga histórica (12 meses)** — el ACTUAL 2024, el ACTUAL 2025, el BUDGET
    2026, y la carga inicial de cada propiedad nueva. Avisa fuerte si el
    escenario ya tiene meses.
  · **Cierre mensual (un mes)** — el año en curso. **Se niega a tocar los meses
    ya cerrados: no avisa, no puede.** Es el camino que se recorre todos los
    meses con cada hotel, donde un error se repite doce veces al año.

⚠️ **El límite vive en el BACKEND, no solo en la pantalla.** Una llamada directa
—curl, un script, otra pantalla— tiene que toparse con el mismo tope. Que el
usuario elija bien no puede ser la protección.

⚠️ **Y el recorte va ANTES de la verificación.** Si se recortara después, la
comparación bucket por bucket estaría midiendo un archivo y la base recibiendo
otro — un control que valida algo distinto de lo que se escribe.
"""
import inspect

import pytest

from app.api import scenarios_api


@pytest.fixture(scope="module")
def fuente() -> str:
    return inspect.getsource(scenarios_api.import_gl_detail)


def test_el_cierre_mensual_es_un_parametro_del_endpoint(fuente):
    """Si solo existiera en el front, un curl se lleva los meses cerrados."""
    assert "mes_de_cierre" in inspect.signature(scenarios_api.import_gl_detail).parameters


def test_el_recorte_pasa_antes_de_la_verificacion(fuente):
    """La verificación tiene que medir EXACTAMENTE lo que se va a escribir."""
    i_recorte = fuente.index("if mes_de_cierre is not None:")
    i_verif = fuente.index("verificaciones: dict[int, dict] = {}")
    assert i_recorte < i_verif, (
        "el recorte quedó después de la verificación: se valida un archivo y se "
        "escribe otro")


def test_el_recorte_pasa_antes_de_escribir(fuente):
    i_recorte = fuente.index("if mes_de_cierre is not None:")
    i_escribe = fuente.index("actual_uploads: list")
    assert i_recorte < i_escribe


def test_el_recorte_alcanza_a_las_cinco_clases(fuente):
    """Dejar una clase afuera pierde la mitad del punto: el gasto se recorta y
    el ingreso no, o al revés."""
    i = fuente.index("if mes_de_cierre is not None:")
    bloque = fuente[i:i + 1200]
    for clase in ("revenue", "opex", "costs", "belowgop", "payroll"):
        assert f'"{clase}"' in bloque, f"el recorte mensual no toca {clase}"


def test_el_recorte_alcanza_a_los_estadisticos_y_al_control(fuente):
    """Las estadísticas y el bloque de verificación viajan por mes igual que la
    plata. Si no se recortan, el cierre de julio sube la ocupación de todo el año."""
    i = fuente.index("if mes_de_cierre is not None:")
    bloque = fuente[i:i + 1200]
    assert '"stats"' in bloque
    assert '"verificacion"' in bloque


def test_la_respuesta_dice_que_camino_se_recorrio(fuente):
    """Sin esto, un cierre mensual y una carga histórica se ven iguales en la
    respuesta y no hay cómo auditar cuál fue."""
    assert '"mes_de_cierre": mes_de_cierre' in fuente
    assert '"meses_descartados": meses_descartados' in fuente


def test_el_default_sigue_siendo_el_ano_completo_sin_recorte(fuente):
    """`mes_de_cierre=None` = carga histórica: no recorta nada. El camino
    histórico tiene que seguir pudiendo subir los doce meses de un tirón —es
    cómo se carga una propiedad nueva, tres veces por hotel."""
    p = inspect.signature(scenarios_api.import_gl_detail).parameters["mes_de_cierre"]
    assert p.default.default is None


def test_el_alcance_del_mes_no_reintroduce_el_reemplazo_total(fuente):
    """`merge` sigue en True por defecto. El camino mensual NO pasa a `merge=False`:
    eso borraría y refabricaría el escenario entero, incluidas las contrapartidas
    de reparto que el archivo no puede traer (−$196.326,17 al año)."""
    p = inspect.signature(scenarios_api.import_gl_detail).parameters["merge"]
    assert p.default.default is True


# ── El estado que la pantalla necesita para separar los dos caminos ──────────

def test_hay_endpoint_de_meses_cerrados():
    """La pantalla tiene que poder decir «este escenario ya tiene 7 meses» ANTES
    de escribir, no después."""
    src = inspect.getsource(scenarios_api.meses_cerrados_del_escenario)
    for llave in ("meses_cerrados", "tiene_datos", "ultima_foto",
                  "meses_cerrados_sin_foto"):
        assert f'"{llave}"' in src


def test_hay_endpoint_de_divergencia():
    assert callable(scenarios_api.divergencia_del_escenario)
