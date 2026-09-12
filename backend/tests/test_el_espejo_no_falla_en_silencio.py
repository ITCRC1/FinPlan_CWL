# -*- coding: utf-8 -*-
"""El tab de Pre-Closing no puede mostrar plata vieja sin decirlo.

Pre-Closing no lee el borrador: lee el ESPEJO, un escenario que se escribe
aparte. Esa escritura puede fallar, y al fallar no rompia nada VISIBLE — la
subida respondia bien, el borrador quedaba con los numeros nuevos, y el tab
seguia con los viejos. El error viajaba en la respuesta y el frontend no leia
ese campo en ninguna parte.

Owner, 2026-09-11: «me da la impresion que a veces subo y los cambios no se
reflejan» · «necesito que cada vez que suba se aplique... sino no haga nada con
ese tab».

No se puede lograr que una escritura nunca falle. Estas pruebas clavan las dos
cosas que si se pueden: que la escritura se VERIFIQUE en vez de suponerse, y que
el desajuste se pueda CONSULTAR.
"""
import inspect

from app.api import precierre_api


def test_reflejar_verifica_lo_que_escribio():
    """Que no haya explotado no prueba que haya escrito."""
    src = inspect.getsource(precierre_api._reflejar)
    assert "EspejoNoCuadra" in src, (
        "_reflejar tiene que levantar su propia excepcion cuando el espejo no "
        "quedo: sin eso, el unico sintoma es un numero viejo en pantalla")
    assert "ActualEntry" in src and "_COL_MES" in src, (
        "la verificacion tiene que RELEER el espejo y comparar la plata, no "
        "confiar en que la llamada volvio sin error")


def test_la_excepcion_del_espejo_tiene_nombre_propio():
    """Para que la subida pueda distinguirla de un error cualquiera."""
    assert issubclass(precierre_api.EspejoNoCuadra, Exception)


def test_hay_forma_de_preguntar_si_el_tab_esta_al_dia():
    rutas = {r.path for r in precierre_api.router.routes}
    assert "/precierre/{anio}/{mes}/espejo/" in rutas, (
        "sin este endpoint la pantalla no tiene como saber que esta mostrando "
        "una subida anterior")


def test_el_endpoint_compara_plata_y_no_una_marca():
    """Un sello se puede quedar pegado aunque la escritura entre a medias."""
    src = inspect.getsource(precierre_api.espejo_al_dia)
    assert "al_dia" in src and "diferencia" in src
    assert 'Decimal("1.00")' in src, (
        "la tolerancia tiene que ser explicita: el redondeo a dos decimales de "
        "cada fila da centavos de diferencia y eso no es una falla")


def test_los_meses_se_leen_con_el_mismo_vocabulario_que_el_importador():
    """Si las dos listas se separan, la verificacion leeria OTRO mes y diria
    que no cuadra cuando cuadra — o al reves, que es peor."""
    from app.api.scenarios_api import _GL_MONTHS
    assert precierre_api._COL_MES == _GL_MONTHS
