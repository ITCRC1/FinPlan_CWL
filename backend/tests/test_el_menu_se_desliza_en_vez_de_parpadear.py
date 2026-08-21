# -*- coding: utf-8 -*-
"""El menú se desliza; no se apaga y se prende.

«Suavizar el movimiento» (owner, 2026-08-19, con una especificación y dos
prototipos).

**El defecto no era la animación: era la arquitectura.** Cada tab traía SU
propio panel. Moverse de una sección a otra desmontaba uno y montaba otro —
no hay nada que animar entre dos elementos que no coexisten, así que parpadea
por definición. Ninguna curva ni ningún `transition` lo arregla desde afuera.

Ahora el panel es UNO SOLO que persiste mientras haya sección abierta, así que
cambiar de sección mueve una caja que ya existe. Eso sí se puede deslizar.

Y el menú abría con CLICK, no con hover: no existía el gesto de recorrer la
barra. Por eso van también los tres tiempos de intención.
"""
import io
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


def _nav() -> str:
    return io.open(os.path.join(RAIZ, "components", "TopNav.tsx"),
                   encoding="utf-8").read()


def _css() -> str:
    return io.open(os.path.join(RAIZ, "app", "globals.css"),
                   encoding="utf-8").read()


def test_hay_UN_panel_y_no_uno_por_tab():
    """El invariante de fondo. Si el panel vuelve a vivir adentro del tab, el
    parpadeo vuelve con él y ninguna curva lo tapa."""
    src = _nav()
    assert src.count("createPortal(") == 1, (
        f"hay {src.count('createPortal(')} portales: el panel tiene que ser "
        f"UNO SOLO, montado por TopNav")
    assert "function Panel({ grupo, ancla," in src
    # El tab es solo el botón: no puede montar contenido de menú.
    tab = src[src.index("function Tab({"):src.index("function Panel({")]
    assert "createPortal" not in tab, "el tab volvió a montar su propio panel"


def test_el_panel_se_queda_montado_al_cambiar_de_seccion():
    """Se monta por «hay grupo abierto», no por «este grupo está abierto». Si
    dependiera del grupo, cambiar de sección lo desmontaría igual que antes."""
    src = _nav()
    assert "{grupoAbierto && ancla &&" in src, (
        "el panel volvió a depender de un grupo puntual para montarse")


def test_los_tres_tiempos_de_intencion():
    """No son gusto: cada uno arregla algo distinto.

    110 ms al abrir con el panel cerrado, para que pasar de camino no dispare
    un menú que nadie pidió. **0 ms si ya hay uno abierto** — acá es donde el
    movimiento se vuelve continuo. 220 ms de gracia al cerrar, porque entre el
    tab y el panel hay un hueco de píxeles y cruzarlo no puede cerrar el menú.
    """
    src = _nav()
    assert "const RETARDO_ABRIR = 110;" in src
    assert "const GRACIA_CERRAR = 220;" in src
    assert "openMenu ? 0 : RETARDO_ABRIR" in src, (
        "se perdió el 0 ms cuando ya hay un panel abierto, que es lo que hace "
        "que el movimiento se sienta continuo y no como abrir otro menú")


def test_el_menu_abre_con_el_mouse_y_no_solo_con_click():
    src = _nav()
    assert "onMouseEnter={onAbrir}" in src and "onMouseLeave={onCerrar}" in src
    assert "onFocus={onAbrir}" in src, (
        "sin foco, quien navega con teclado no puede abrir el panel")


def test_la_caja_se_mide_y_no_se_fija():
    """Con altura fija, secciones con distinta cantidad de opciones saltan —
    y Planning tiene 41 contra las 3 de Financials."""
    src = _nav()
    assert "new ResizeObserver(medir)" in src, "volvió una medida estática"
    assert "position: \"absolute\"" in src, (
        "el interior tiene que ir absoluto: si no, la caja toma su tamaño y "
        "medirlo para dárselo a la caja es circular")


def test_la_caja_no_anima_su_opacidad_al_moverse():
    """Animar la opacidad del contenedor al cambiar de sección reintroduce
    exactamente el parpadeo que esto viene a sacar. La opacidad solo se toca
    al abrir desde cero."""
    css = _css()
    bloque = re.search(r"\.nav-panel\s*\{[^}]*\}", css)
    assert bloque, "se fue la regla .nav-panel"
    trans = re.search(r"transition:([^;]*);", bloque.group(0))
    assert trans, "el panel dejó de tener transición: ya no se desliza"
    assert "opacity" not in trans.group(1), (
        "la caja volvió a animar su opacidad al moverse")
    for prop in ("left", "top", "width", "height"):
        assert prop in trans.group(1), f"la caja dejó de animar {prop}"


def test_se_respeta_quien_pidio_menos_movimiento():
    css = _css()
    i = css.find("prefers-reduced-motion")
    assert i > 0, "no se respeta `prefers-reduced-motion`"
    bloque = css[i:i + 400]
    assert ".nav-panel" in bloque, (
        "el panel nuevo quedó fuera de la regla de movimiento reducido")


# ── La otra mitad del gesto: la entrada de la pantalla ──────────────────────

def _transicion() -> str:
    return io.open(os.path.join(RAIZ, "components", "Transicion.tsx"),
                   encoding="utf-8").read()


def test_la_pantalla_se_anima_por_RUTA_y_no_por_direccion():
    """⚠️ La sutileza que rompe sin avisar.

    Desde el 19-ago el escenario viaja en la dirección (`?esc=`), y mover el
    selector la reescribe SIN cambiar de pantalla. Si esta animación dependiera
    de la dirección entera en vez del `pathname`, cambiar de escenario haría
    parpadear la tabla completa — un flash cada vez que alguien compara dos
    presupuestos, que es lo que más se hace en esta app.

    Nada fallaría: se vería «animado». Por eso queda vigilado.
    """
    src = _transicion()
    assert "const pathname = usePathname();" in src
    assert 'key={pathname}' in src
    assert "useSearchParams" not in src, (
        "la transición empezó a mirar la dirección entera: cambiar de escenario "
        "va a hacer parpadear la pantalla en cada selección")


def test_la_transicion_no_envuelve_a_la_barra():
    """El `key` REMONTA lo de adentro. Envolver al `TopNav` remontaría la barra
    en cada navegación — deshaciendo justo el panel que se acaba de arreglar."""
    p = os.path.join(RAIZ, "app", "layout.tsx")
    lay = io.open(p, encoding="utf-8").read()
    assert "<AuthGate><Transicion>{children}</Transicion></AuthGate>" in lay
    i, j = lay.index("<TopNav />"), lay.index("<Transicion>")
    assert i < j, "el TopNav quedó adentro de la transición"


def test_el_menu_no_precarga_cuarenta_pantallas_de_golpe():
    """Por omisión Next precarga cada enlace apenas entra en pantalla, y
    Planning abre CUARENTA de golpe: cuarenta pedidos por asomarse a un menú,
    de los que se usa uno. Se precarga al APUNTAR."""
    src = _nav()
    assert "prefetch={false}" in src, (
        "volvió la precarga al aparecer: abrir Planning dispara ~40 pedidos")
    assert "router.prefetch(item.href)" in src, (
        "se quitó la precarga al pasar el mouse, que es la que hace que el "
        "clic llegue con la pantalla ya en caché")
