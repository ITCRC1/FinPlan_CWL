# -*- coding: utf-8 -*-
"""Un tab con raíz propia tiene que abrir por la URL.

**El defecto, reportado por el owner (2026-08-19, con la captura):** el tab
`Cost` estaba en la barra, sus dos sub-pantallas respondían 200, y entrar al
tab daba **404**. `app/cost/` tenía `pisos/page.tsx` y `simulador/page.tsx`
pero no `page.tsx`, así que `/cost` no existía.

⚠️ **No vale la regla «todo grupo necesita raíz».** `/reports` lo comparten
Board, Cash Flow y Reportes; `/pl` lo comparten dos. Un segmento compartido no
es la raíz de nadie, y mandarlo a un sub-tab elegido a dedo sería peor que el
404: llevaría al usuario a otro tab.

El invariante que sí se sostiene: **si un primer segmento lo usa UN solo grupo,
ese segmento es su raíz** —la URL que la gente escribe y que un enlace externo
comparte— y tiene que resolver. Hoy son cuatro: `/operation-insight`,
`/marketing-insight`, `/break-e` y `/cost`.
"""
import io
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


def _grupos() -> dict[str, list[str]]:
    """{key del grupo: [hrefs de sus items]} leído de la barra."""
    s = io.open(os.path.join(RAIZ, "components", "TopNav.tsx"),
                encoding="utf-8").read()
    fuera = {}
    for key, cuerpo in re.findall(
            r'key:\s*"(\w+)",\s*\n\s*items:\s*\[(.*?)\n\s*\],', s, re.S):
        fuera[key] = re.findall(r'href:\s*"([^"]+)"', cuerpo)
    return fuera


def _raices_propias() -> dict[str, str]:
    """{segmento: grupo} de los segmentos que usa un solo grupo."""
    grupos = _grupos()
    de_quien: dict[str, set] = {}
    for key, hrefs in grupos.items():
        for h in hrefs:
            partes = [p for p in h.split("/") if p]
            if len(partes) >= 2:                 # /seg/sub — hay raíz posible
                de_quien.setdefault(partes[0], set()).add(key)
    # sólo los que un grupo usa EN EXCLUSIVA, y para TODOS sus items anidados
    fuera = {}
    for seg, duenos in de_quien.items():
        if len(duenos) != 1:
            continue
        dueno = next(iter(duenos))
        anidados = [h for h in grupos[dueno] if len([p for p in h.split("/") if p]) >= 2]
        if all(h.split("/")[1] == seg for h in anidados):
            fuera[seg] = dueno
    return fuera


def test_todo_tab_con_raiz_propia_abre_por_la_url():
    """⚠️ El 404 del tab Cost. La barra lo mostraba y la URL no existía —
    y las dos sub-pantallas respondían perfecto, que es lo que hace que
    cueste encontrarlo."""
    faltan = []
    for seg, grupo in sorted(_raices_propias().items()):
        if not os.path.exists(os.path.join(RAIZ, "app", seg, "page.tsx")):
            faltan.append(f"/{seg} (tab «{grupo}»)")
    assert not faltan, (
        "estos tabs tienen raíz propia y NO abren por la URL —dan 404 con el "
        f"tab visible en la barra: {faltan}. Falta `app/<seg>/page.tsx`, aunque "
        "sea un redirect al sub-tab por defecto")


def test_la_raiz_de_un_tab_RESUELVE_no_necesariamente_redirige():
    """El invariante es que no sea un callejón sin salida, no que redirija.

    ⚠️ Antes esta prueba exigía un `router.replace`, y se cayó el día que
    `/cost` pasó de ser un redirect a tener contenido propio (el SUMMARY COST
    del spec §5). Exigir el MECANISMO en vez del RESULTADO hace que mejorar la
    pantalla rompa la prueba — y eso enseña a borrar pruebas.

    Vale cualquiera de las dos: contenido propio, o redirect a algo que existe.
    """
    for seg in sorted(_raices_propias()):
        p = os.path.join(RAIZ, "app", seg, "page.tsx")
        assert os.path.exists(p), f"falta la raíz de /{seg}"
        txt = io.open(p, encoding="utf-8").read()
        m = re.search(r'router\.replace\("([^"]+)"\)', txt)
        if m:                                  # es un redirect: el destino existe
            destino = m.group(1).strip("/")
            assert os.path.exists(os.path.join(RAIZ, "app", destino, "page.tsx")), (
                f"/{seg} redirige a /{destino}, que no existe: el 404 sólo "
                f"cambió de lugar")
        else:                                  # tiene contenido: que sea una pantalla
            assert "export default function" in txt, (
                f"/{seg} ni redirige ni exporta una pantalla")


def test_la_raiz_redirige_sin_dejar_el_404_en_el_historial():
    """`replace`, no `push`: con `push`, el botón «atrás» devuelve a la raíz
    que redirige de nuevo, y el usuario queda encerrado."""
    for seg in _raices_propias():
        p = os.path.join(RAIZ, "app", seg, "page.tsx")
        if not os.path.exists(p):
            continue
        txt = io.open(p, encoding="utf-8").read()
        if "router.replace" in txt or "router.push" in txt:
            assert "router.push" not in txt, (
                f"/{seg} usa router.push: el botón «atrás» vuelve a la raíz y "
                f"redirige otra vez")


def test_todo_href_del_menu_apunta_a_una_pantalla_que_existe():
    """⚠️ La red más ancha: un enlace del menú a una pantalla no construida se
    ve exactamente igual que uno roto. Esto lo atrapa antes de desplegar."""
    rotos = []
    for grupo, hrefs in _grupos().items():
        for h in hrefs:
            ruta = os.path.join(RAIZ, "app", *[p for p in h.split("/") if p],
                                "page.tsx")
            if not os.path.exists(ruta):
                rotos.append(f"{h} (tab «{grupo}»)")
    assert not rotos, f"el menú enlaza a pantallas que no existen: {rotos}"


def test_cada_pantalla_cuelga_del_TAB_QUE_LE_CORRESPONDE():
    """⚠️ **El error que esto atrapa, cometido dos veces el 2026-08-20.**

    Al agregar una entrada al menú anclé en `importActuals` sin verificar de qué
    grupo era, y «Guillermo» quedó colgando de **Escenarios** en vez de Admin.
    El owner lo reportó con «no hay ningún sub tab que se llame así» — porque
    estaba, pero en otro tab.

    La regla que se puede vigilar: **una pantalla bajo `/admin/` va en el tab
    Admin.** Las excepciones son las que ya existían y están anotadas: son
    puentes deliberados, no descuidos.
    """
    # Pantallas de `/admin/` que a propósito viven en OTRO tab, con el motivo.
    PUENTES = {
        # El owner las buscaba donde trabaja, no en Admin. Siguen accesibles
        # desde los dos lados; ver el comentario del grupo `admin` en TopNav.
        "/admin/import-actuals": "se sube desde Escenarios",
        "/admin/control": "se audita desde Planning",
        "/admin/mapping": "se mapea desde Master Data",
    }
    fuera = []
    for grupo, hrefs in _grupos().items():
        if grupo == "admin":
            continue
        for h in hrefs:
            if h.startswith("/admin/") and h not in PUENTES:
                fuera.append(f"{h} está en el tab «{grupo}», no en Admin")
    assert not fuera, (
        f"{fuera}. Si es a propósito, anotalo en PUENTES con el motivo")
