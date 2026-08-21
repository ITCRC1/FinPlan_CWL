# -*- coding: utf-8 -*-
"""El menú esconde lo que la persona no puede usar. No lo deshabilita.

El owner preguntó por qué no tenía acceso a Admin (2026-08-19). No era
permisos —su rol es admin— pero la pregunta destapó lo otro: las nueve cuentas
`collaborator` veían el menú Admin COMPLETO, `Users` incluido. Al entrar
reciben un 403, así que nunca fue un agujero de seguridad; era una pantalla
mostrando puertas que no abren, y de ahí salió la duda.

⚠️ **La marca `soloAdmin` tiene que corresponder con lo que el backend
BLOQUEA, y con la pantalla ENTERA.** Esconder de más saca acceso que hoy
existe; esconder de menos deja la puerta cerrada a la vista. Por eso las dos
listas de acá abajo se derivaron endpoint por endpoint, no del nombre del
grupo.
"""
import io
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..")


def _nav() -> str:
    p = os.path.join(RAIZ, "frontend", "components", "TopNav.tsx")
    return io.open(p, encoding="utf-8").read()


# Su PRIMERA llamada exige admin: sin el rol, la pantalla no muestra nada.
#   /admin/users     -> GET /auth/users     (auth_api, get_current_admin)
#   /admin/origenes  -> GET /origenes/      (origenes_api, get_current_admin)
SOLO_ADMIN = {"/admin/users", "/admin/origenes"}

# Cuelgan del menú Admin pero NO se esconden: un colaborador las usa.
#   provisioning  -> sus GET son abiertos, y la matriz la guarda cualquiera;
#                    solo tres PATCH (identidad, código, locale) piden admin
#   control · mapping · setup-cuenta · import-actuals · apariencia -> abiertas
NO_SE_ESCONDEN = {
    "/master-data/provisioning", "/admin/control", "/admin/mapping",
    "/master-data/setup-cuenta", "/admin/import-actuals", "/admin/apariencia",
}


def _marcadas() -> set:
    """Los `href` marcados con `soloAdmin: true` en el registro del menú."""
    src = _nav()
    return set(re.findall(r'href:\s*"([^"]+)"[^}]*soloAdmin:\s*true', src))


def test_se_esconde_exactamente_lo_que_el_backend_bloquea():
    assert _marcadas() == SOLO_ADMIN, (
        f"la marca `soloAdmin` dejó de coincidir con lo que el backend "
        f"bloquea.\n  marcadas: {sorted(_marcadas())}\n  esperadas: "
        f"{sorted(SOLO_ADMIN)}\nVerificar endpoint por endpoint antes de "
        f"cambiar esta lista: esconder de más SACA acceso que hoy existe.")


def test_no_se_esconde_lo_que_un_colaborador_si_usa():
    """El error caro del otro lado. `/master-data/provisioning` cuelga del menú
    Admin y suena a admin, pero sus lecturas son abiertas y la matriz la puede
    guardar cualquiera: esconderla les sacaría algo que hoy usan."""
    for href in NO_SE_ESCONDEN:
        assert href not in _marcadas(), (
            f"{href} se marcó como solo-admin, y no lo es: el backend deja "
            f"entrar a un colaborador. Esconderla le quita acceso.")


def test_el_filtro_se_aplica_ANTES_de_partir_el_menu():
    """El tab Admin se dibuja aparte, fijo a la derecha. Si saliera de la
    constante `NAV` en vez de la lista filtrada, el filtro no lo alcanzaría —
    y es justo el tab que tiene `Users`."""
    src = _nav()
    assert 'nav.find(g => g.key === "admin")' in src, (
        "el grupo Admin volvió a salir de `NAV` sin filtrar")
    assert 'nav.filter(g => g.key !== "admin").map(' in src, (
        "la fila de tabs volvió a recorrer `NAV` sin filtrar")


def test_mientras_no_se_sabe_el_rol_se_esconde():
    """`user` se lee DESPUÉS de montar (`localStorage` no existe en el render
    del servidor). El default seguro es esconder: al revés, todos verían por un
    instante lo que no pueden abrir — que es lo que esto viene a corregir."""
    src = _nav()
    assert 'const esAdmin = user?.role === "admin"' in src, (
        "cambió cómo se decide el rol; verificar que un `user` nulo NO cuente "
        "como admin")


def test_un_grupo_que_queda_vacio_no_se_dibuja():
    """Un tab que abre un panel vacío es peor que no tener el tab."""
    src = _nav()
    assert ".filter(g => g.href || g.items.some(i => i.href && !i.disabled))" in src, (
        "se fue el descarte de grupos vacíos: si alguna vez todas las entradas "
        "de un grupo son solo-admin, un colaborador vería un tab que no abre nada")
