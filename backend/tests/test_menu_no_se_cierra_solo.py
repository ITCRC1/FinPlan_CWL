# -*- coding: utf-8 -*-
"""El menú de navegación no se puede cerrar solo.

«En planning no puedo darle click a los sub tabs, me saca y está como
inestable» (owner, 2026-08-12). Dos fallas encadenadas, las dos mías:

1. **El scroll del propio panel cerraba el panel.** El listener de scroll está
   en CAPTURA para enterarse del scroll de cualquier contenedor, y eso incluye
   el menú mismo. Planning tiene 41 opciones con `maxHeight: 78vh`: hay que
   rodar la rueda adentro para llegar a las de abajo, y al rodarla el menú se
   cerraba. Las últimas opciones eran inalcanzables.

2. **Cerrar estaba implementado como ALTERNAR.** Dos eventos de scroll seguidos
   alternaban dos veces —cerrar, abrir— antes de que React quitara el listener,
   y el menú parpadeaba.

Son de las que no salen en una prueba de humo: el menú abre bien, y el defecto
solo aparece cuando el usuario scrollea adentro. Por eso quedan vigiladas.

⚠️ **2026-08-19: la FORMA cambió, los invariantes no.** El panel dejó de ser
uno por tab y pasó a ser uno solo compartido (ver
`test_el_menu_se_desliza_en_vez_de_parpadear`). Con eso, el estado y los
listeners viven en `TopNav` en vez de en cada tab, así que estas pruebas miran
los nombres nuevos. Lo que NO cambió es qué tiene que seguir siendo cierto.
"""
import io
import os
import re


def _nav() -> str:
    p = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                     "components", "TopNav.tsx")
    return io.open(p, encoding="utf-8").read()


def test_el_scroll_dentro_del_panel_no_lo_cierra():
    src = _nav()
    assert "cajaPanel.current?.contains(e.target as Node)) return;" in src, (
        "el scroll del propio menú tiene que quedar exento, o las últimas "
        "opciones de Planning vuelven a ser inalcanzables")


def test_cerrar_y_alternar_son_cosas_distintas():
    """Un cierre que alterna no es un cierre: es un interruptor con otro
    nombre, y dos disparos lo dejan abierto."""
    src = _nav()
    assert "const cerrarYa = () => { limpiar(); setOpenMenu(null); };" in src, (
        "`cerrarYa` tiene que CERRAR, no alternar")
    # El alternar existe, y solo para el click en el tab.
    assert "if (openMenu === group.key) setOpenMenu(null);" in src


def test_nada_que_no_sea_el_tab_usa_el_alternar():
    """El click en el tab alterna. El click afuera, el scroll, el resize, la
    tecla Escape y elegir una opción CIERRAN. Si alguno alterna, vuelve el
    parpadeo."""
    src = _nav()
    for uso in ('window.addEventListener("resize", cerrarYa)',
                'window.addEventListener("scroll", alScrollear, true)',
                'document.addEventListener("mousedown", alClickear)',
                'onClick={onCerrar}'):          # elegir una opción del panel
        assert uso in src, f"debería cerrar, no alternar: {uso}"
    assert "onClick={onToggle}" in src, "el tab sí alterna"


def test_el_cierre_no_lee_un_valor_viejo_de_la_clausura():
    """El defecto original: `setOpenMenu(openMenu === …)` decide con el valor
    que la clausura capturó, y en el segundo disparo decide al revés.

    Hoy no hace falta la forma funcional porque **nadie LEE el estado para
    cerrar**: `cerrarYa` pone `null` y punto. Lo que se vigila es que no vuelva
    a aparecer una lectura de la clausura dentro de un `setOpenMenu`.
    """
    src = _nav()
    assert not re.search(r"setOpenMenu\(\s*openMenu\s*===", src), (
        "volvió una lectura de la clausura adentro de setOpenMenu")


def test_los_temporizadores_se_limpian():
    """Un `setTimeout` de apertura vivo después de desmontar la barra dispara
    un `setState` sobre un componente que ya no está."""
    src = _nav()
    assert "useEffect(() => limpiar, []);" in src, (
        "se fue la limpieza de los temporizadores al desmontar")
