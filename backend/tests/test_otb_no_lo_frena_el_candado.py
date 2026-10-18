# -*- coding: utf-8 -*-
"""El candado del presupuesto no frena al On the Books.

**La regla (owner, 2026-08-18).** «El escenario es solo una referencia
comparativa, pero no tiene nada que ver con las subidas.»

Lo que entra por las rutas de OTB son las reservas que YA existen en Opera: un
hecho observado, no una cifra que alguien presupuestó. Enllavar un escenario
congela SUS números — y el candado se había quedado puesto por inercia sobre
las cinco rutas de OTB.

El síntoma que lo destapó: con el «Budget 2026 · Final» elegido (locked), subir
el XML moría con

    409 {"detail":"El escenario 'BUDGET Final 2026' está bloqueado
         (status=locked). Crea una nueva versión para editar."}

…cuando la subida no tocaba ni una cifra de ese presupuesto. La pantalla ni
siquiera avisaba: dejaba apretar el botón para que reventara contra la API.

⚠️ Esta prueba cuida las CINCO rutas. Volver a poner `candado` en cualquiera de
ellas rompe la regla del owner, no solo la de la que se tocó.
"""
import inspect

import pytest

from app.api import revenue_api

#: Las cinco rutas por las que entra el On the Books.
RUTAS_OTB = [
    "import_otb_xml",       # POST /import-otb-xml/  — el XML de Opera
    "put_otb_entry",        # PUT  /onthebooks-entry/ — carga manual por mes
    "put_daily_occ_entry",  # PUT  /daily-occ-entry/  — heatmap diario
    "put_otb_param",        # PUT  /otb-params/       — % de venta en propiedad
    "clear_otb",            # DEL  /otb/              — reset para volver a subir
]


@pytest.mark.parametrize("nombre", RUTAS_OTB)
def test_la_ruta_de_otb_no_pasa_por_el_candado(nombre):
    fn = getattr(revenue_api, nombre)
    src = inspect.getsource(fn)
    assert "await candado(" not in src, (
        f"`{nombre}` volvió a pasar por el candado del presupuesto. El On the "
        f"Books no es parte del presupuesto: enllavar congela las cifras del "
        f"escenario, no las reservas que ya existen en Opera.")


def test_el_candado_sigue_puesto_donde_SI_va():
    """El contrapeso: esto no es «sacar el candado», es sacarlo de donde no iba.

    Las rutas que escriben cifras del presupuesto tienen que seguir frenadas.
    Sin esta prueba, el arreglo de arriba se puede 'lograr' borrando `candado`
    del módulo entero.
    """
    modulo = inspect.getsource(revenue_api)
    assert modulo.count("await candado(db, scenario_id)") >= 6, (
        "quedaron menos candados de los esperados — se sacó de más")


# ── El candado GLOBAL, que es el que de verdad frenaba ─────────────────────
#
# ⚠️ Owner, 2026-10-17: *«REVISA ESTO POR MI»*, con el Budget 2026 elegido y
# este error en rojo:
#
#     API 409: Scenario "BUDGET Final 2026" is locked (status=locked).
#
# Las pruebas de arriba pasaban. Pasaban desde agosto. Y el XML seguia sin
# poder subirse.
#
# **Porque verificaban la creencia, no el comportamiento.** Comprobaban que
# ninguna ruta llamara a `candado()` —cierto— sin saber que el candado es una
# dependencia GLOBAL (`main.py`: `_guard`) que se dispara por el patron de la
# URL y el metodo. El comentario «SIN candado, a proposito» era sincero y
# falso al mismo tiempo, y la prueba lo confirmaba en vez de medirlo.
#
# Estas recorren el ROUTER de verdad.

from app.candado import (ESCRITURA, FUERA_DEL_PRESUPUESTO,   # noqa: E402
                         PERMITIDAS)


def _escribe_bajo_escenario():
    """Las rutas de escritura que cuelgan de un escenario, del router real."""
    from app.api.revenue_api import router
    for r in router.routes:
        ruta = getattr(r, "path", "")
        metodos = getattr(r, "methods", set()) or set()
        if (metodos & ESCRITURA) and "scenario_id" in ruta:
            yield ruta, sorted(metodos)[0]


def _la_deja_pasar(ruta: str) -> bool:
    return any(ruta.rstrip("/").endswith(x.rstrip("/")) for x in PERMITIDAS + FUERA_DEL_PRESUPUESTO)


def test_las_CINCO_rutas_de_otb_pasan_el_candado_global():
    """⚠️ Son cinco, y dos no llevan «otb» en la URL.

    `onthebooks-entry` y `daily-occ-entry` se quedan afuera facilisimo de una
    lista escrita a mano — me paso al escribir el arreglo. Por eso se buscan
    por el router.
    """
    otb = [(r, m) for r, m in _escribe_bajo_escenario()
           if any(x in r.lower() for x in ("otb", "onthebooks", "daily-occ"))]
    assert len(otb) == 5, f"se esperaban 5 rutas de OTB, hay {len(otb)}: {otb}"
    frenadas = [(m, r) for r, m in otb if not _la_deja_pasar(r)]
    assert not frenadas, (
        f"el candado global todavia frena estas rutas de OTB: {frenadas}. "
        "El On the Books son las reservas que YA existen en Opera: enllavar un "
        "escenario congela SUS cifras, no un hecho observado.")


def test_el_candado_global_sigue_frenando_el_PRESUPUESTO():
    """El contrapeso. Sin esto, el arreglo se puede «lograr» vaciando el
    candado: la lista de permitidas es una puerta, y una puerta abierta de mas
    no avisa."""
    otras = [r for r, _ in _escribe_bajo_escenario()
             if not any(x in r.lower()
                        for x in ("otb", "onthebooks", "daily-occ", "/status/"))]
    coladas = [r for r in otras if _la_deja_pasar(r)]
    assert not coladas, f"estas rutas de presupuesto quedaron sin candado: {coladas}"
    assert len(otras) >= 20, "hay muchas menos rutas frenadas de las esperadas"


def test_la_excepcion_es_por_RUTA_y_no_apaga_el_candado():
    """La puerta se abre nombrando rutas, no condiciones. Una condicion
    —«si el escenario es Budget», «si el usuario es admin»— es justo lo que
    convierte un candado en un permiso."""
    import inspect

    from app import candado as mod
    fuente = inspect.getsource(mod.candado_del_escenario)
    assert "PERMITIDAS" in fuente
    assert "sc is None or not sc.is_locked" in fuente
    # Y no hay excepciones por tipo de escenario ni por usuario.
    for sospechoso in ("BUDGET", "is_admin", "role", "rol =="):
        assert sospechoso not in fuente, sospechoso


def test_la_lista_que_NO_es_presupuesto_esta_SEPARADA_del_interruptor():
    """⚠️ Son dos preguntas distintas y tienen que vivir en dos listas.

    `PERMITIDAS` responde «que abre el candado»: una sola ruta, `/status/`, y
    esa lista NO crece — lo cuida `test_la_excepcion_esta_en_UN_lugar`.

    `FUERA_DEL_PRESUPUESTO` responde «que cuelga de un escenario sin ser suyo».
    Meter el OTB en la primera habria subido el contador de 1 a 6 y apagado esa
    prueba, que es justo la que impide que el candado se vuelva un colador.
    """
    from app import candado as mod

    assert len(mod.PERMITIDAS) == 1
    assert "/status/" in mod.PERMITIDAS
    assert len(mod.FUERA_DEL_PRESUPUESTO) == 5
    # Y ninguna ruta de presupuesto se coló en la segunda lista.
    for x in mod.FUERA_DEL_PRESUPUESTO:
        assert any(k in x for k in ("otb", "onthebooks", "daily-occ")), x
