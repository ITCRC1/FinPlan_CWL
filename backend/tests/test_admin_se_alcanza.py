# -*- coding: utf-8 -*-
"""El tab Admin tiene que ser alcanzable a cualquier ancho de pantalla.

«¿Por qué no tengo acceso a ADMIN?» (owner, 2026-08-19). No era permisos: su
rol ES admin, ninguna pantalla filtra por rol y las páginas responden 200.

Era que **no se veía.** Los tabs crecieron a doce y Admin quedó de último;
`.nav-scroll` scrollea de lado cuando no entran, con el scrollbar oculto a
propósito (`scrollbar-width: none`) y sin flecha ni sombra. En una pantalla que
no da para los doce, el tab cae fuera del borde derecho y NADA indica que está
ahí. El comentario del CSS todavía hablaba de «los 11 tabs».

Por eso Admin se renderiza aparte, fijo en el bloque de la derecha que nunca se
encoge. Estas pruebas existen para que un tab trece no lo vuelva a empujar
afuera.
"""
import io
import os
import re


def _nav() -> str:
    p = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                     "components", "TopNav.tsx")
    return io.open(p, encoding="utf-8").read()


def test_admin_no_se_renderiza_dentro_del_contenedor_que_scrollea():
    src = _nav()
    assert 'nav.filter(g => g.key !== "admin").map(' in src, (
        "Admin volvió a entrar a `.nav-scroll`: a doce tabs cae fuera del "
        "borde derecho y no hay scrollbar que lo delate")


def test_admin_se_renderiza_en_el_bloque_fijo_de_la_derecha():
    src = _nav()
    # El bloque de la derecha es el que declara `flexShrink: 0`.
    derecha = src.split("Lado derecho")[-1]
    assert "grupoAdmin" in derecha, (
        "el dropdown de Admin tiene que colgar del bloque que no se encoge")


def test_el_grupo_admin_sale_de_NAV_y_no_esta_duplicado():
    """Si se copiara el arreglo de items, agregar una pantalla de admin
    obligaría a acordarse de DOS lugares — y el segundo se olvida."""
    src = _nav()
    assert 'nav.find(g => g.key === "admin")' in src
    assert src.count('key: "admin",') == 1, (
        "el grupo Admin quedó definido dos veces")


def test_admin_sigue_teniendo_sus_pantallas():
    """Que sea alcanzable no sirve si el menú quedó vacío."""
    src = _nav()
    bloque = src.split('key: "admin",')[1].split("];")[0]
    for href in ("/admin/users", "/admin/apariencia", "/admin/mapping",
                 "/admin/control", "/admin/origenes", "/admin/import-actuals"):
        assert href in bloque, f"{href} desapareció del menú Admin"


def test_la_barra_sigue_ocultando_el_scrollbar():
    """La prueba de arriba solo vale mientras el scrollbar siga oculto: si
    algún día se muestra, el tab de más ya no sería invisible y esta historia
    cambia. Que falle acá para que alguien la relea."""
    p = os.path.join(os.path.dirname(__file__), "..", "..", "frontend",
                     "app", "globals.css")
    css = io.open(p, encoding="utf-8").read()
    bloque = re.search(r"\.nav-scroll\s*\{[^}]*\}", css)
    assert bloque and "scrollbar-width: none" in bloque.group(0), (
        "cambió el scrollbar de la barra: revisar si Admin todavía necesita "
        "ir fijo a la derecha")
