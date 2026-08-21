# -*- coding: utf-8 -*-
"""Al gato se lo puede correr de lugar — pedido del owner, 2026-08-20.

*«A veces está detrás de cálculos y datos y hay que moverlo.»*

Con `position: fixed` y un solo lugar posible, la única salida era apagarlo — y
apagarlo pierde el aviso.

Esta prueba lee el componente del frontend, igual que
`test_todo_baja_a_excel`. No es elegante, pero es lo único que puede vigilar una
regla que vive en un `.tsx` desde una suite de Python — y acá hay cuatro cosas
que si se rompen, se rompen **en silencio**.
"""
import pathlib

import pytest

FRONT = pathlib.Path(__file__).resolve().parents[2] / "frontend"
GATO = FRONT / "components" / "Guillermo.tsx"
MUESTRA = FRONT / "app" / "admin" / "guillermo" / "page.tsx"


@pytest.fixture(scope="module")
def fuente() -> str:
    return GATO.read_text(encoding="utf-8")


def test_el_gato_se_arrastra(fuente):
    """Los tres eventos del arrastre, sobre el dibujo."""
    for evento in ("onPointerDown", "onPointerMove", "onPointerUp"):
        assert evento in fuente, evento
    # Y se cancela: soltar fuera de la ventana no puede dejarlo pegado al ratón.
    assert "onPointerCancel" in fuente


def test_la_posicion_se_RECUERDA(fuente):
    """⚠️ Si volviera a su rincón en cada recarga, moverlo no resolvería nada:
    habría que moverlo otra vez, y otra."""
    assert "localStorage.setItem(DONDE" in fuente
    assert "localStorage.getItem(DONDE)" in fuente


def test_el_contenedor_NO_SE_COME_LOS_CLICS(fuente):
    """⚠️ **El defecto que esto evita, y es justo el que reportó el owner.**

    El contenedor es una caja de 170×125 y casi todo es aire. Si tomara los
    eventos del ratón para poder arrastrarse, se comería los clics de la tabla
    que tiene debajo — o sea que arreglar «me tapa los datos» habría empeorado
    «no puedo tocar los datos». Los eventos van sobre las FIGURAS del SVG, que
    es donde está dibujado el gato; el SVG resuelve el impacto figura por
    figura y el aire deja pasar el clic.
    """
    contenedor = fuente.split("<svg")[0]
    assert 'pointerEvents: "none"' in contenedor, (
        "el contenedor del gato volvió a tomar eventos del ratón")
    # Y el dibujo sí los toma, si no no habría de dónde agarrarlo.
    assert 'pointerEvents: "auto"' in fuente


def test_un_CLIC_sigue_siendo_un_clic(fuente):
    """⚠️ El clic abre la pantalla de Guillermo y es lo que se hace todos los
    días. Sin umbral, un clic con la mano temblorosa movería al gato en vez de
    abrir la pantalla."""
    assert "UMBRAL" in fuente
    assert "a.movido" in fuente
    # El clic sólo se dispara si NO se movió.
    assert "alClic?.()" in fuente


def test_la_CAMINATA_no_pelea_con_la_posicion_elegida(fuente):
    """⚠️ Un gato que camina hacia su rincón de siempre después de que lo
    pusiste en otro lado es un gato que ignora lo que le pediste."""
    assert "if (pos) { setMs(0); return; }" in fuente


def test_NO_SE_PUEDE_PERDER_fuera_de_la_pantalla(fuente):
    """Arrastrado al borde, o con la ventana achicada después, un gato fuera de
    la pantalla no se recupera con nada."""
    assert "function dentro(" in fuente
    assert "window.innerWidth - ANCHO" in fuente
    assert "window.innerHeight - ALTO" in fuente
    # Y se vuelve a acomodar al cambiar el tamaño de la ventana.
    assert 'addEventListener("resize"' in fuente


def test_hay_forma_de_DEVOLVERLO_a_su_lugar(fuente):
    """La salida para quien lo arrastró sin querer y no sabe dónde lo dejó."""
    assert "onDoubleClick={devolver}" in fuente
    assert "localStorage.removeItem(DONDE)" in fuente


def test_que_se_ARRASTRA_se_DICE(fuente):
    """Una función que nadie descubre es una función que no existe — y el owner
    venía tapado por el gato sin saber que podía correrlo."""
    assert "Arrastralo para moverlo" in fuente
    assert "doble clic" in fuente


def test_el_TOOLTIP_va_adentro_del_SVG_y_no_en_el_contenedor(fuente):
    """⚠️ **Defecto que ya se cometió y se corrigió el mismo día.** El aviso
    estaba como `title` del contenedor — y el contenedor tiene
    `pointer-events: none` a propósito, así que el tooltip **no se mostraba
    nunca**. En SVG el tooltip es un elemento `<title>` adentro del dibujo, que
    es lo único que recibe el ratón.
    """
    assert "<title>" in fuente
    contenedor = fuente.split("<svg")[0]
    assert "title={" not in contenedor, (
        "el aviso volvió al contenedor, donde no se puede ver")


def test_el_arrastre_funciona_con_el_DEDO(fuente):
    """Sin `touch-action: none` el navegador interpreta el arrastre como scroll
    y el gato no se mueve en una pantalla táctil."""
    assert 'touchAction: "none"' in fuente


def test_el_gato_DE_MUESTRA_no_se_arrastra():
    """⚠️ **La trampa del `position: fixed`.** `Admin → Guillermo` monta el
    mismo componente en una caja para mostrar sus estados. Si ése leyera la
    posición guardada, se saldría de su caja y aparecería flotando sobre la
    pantalla: dos gatos a la vez, y uno mintiendo sobre dónde está el de verdad.
    """
    assert "arrastrable={false}" in MUESTRA.read_text(encoding="utf-8")
    assert "arrastrable = true" in GATO.read_text(encoding="utf-8"), (
        "el default cambió: el gato de verdad dejaría de arrastrarse")
