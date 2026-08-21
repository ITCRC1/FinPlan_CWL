# -*- coding: utf-8 -*-
"""Los saltos entre pantallas llevan el contexto, y llevan el correcto.

«Que dentro de un tab me pueda mover a otro tab internamente sin tener que
salir… pero en forma lógica» (owner, 2026-08-19).

Medido ese día: de 94 pantallas, **0 leían nada de la URL**. El escenario, el
mes y el departamento viven en `localStorage` y —a propósito— se recuerdan POR
PANTALLA. Un botón «ver el Cash Flow» encima de eso te lleva al cash flow de
OTRO escenario, y **no falla**: muestra un presupuesto real, el equivocado. Es
el mismo modo de falla que mandó todos los reportes a Working 2035.

Por eso el valor de estas pruebas no está en que el link exista, sino en que
lleve la coordenada correcta.
"""
import io
import json
import os
import re

RAIZ = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")


def _leer(*partes) -> str:
    return io.open(os.path.join(RAIZ, *partes), encoding="utf-8").read()


def _rutas() -> str:
    return _leer("lib", "rutas.ts")


def _destinos():
    """[(origen, href, item, porque)] declarados en el grafo."""
    src = _rutas()
    cuerpo = src[src.index("export const SALTOS"):src.index("/** Los saltos de una ruta")]
    fuera = []
    origen = None
    for linea in cuerpo.splitlines():
        m = re.match(r'\s*"(/[^"]*)":\s*\[', linea)
        if m:
            origen = m.group(1)
            continue
        d = re.search(r'href:\s*"([^"]+)",\s*item:\s*"(\w+)",\s*porque:\s*"(\w+)"', linea)
        if d and origen:
            fuera.append((origen, d.group(1), d.group(2), d.group(3)))
    return fuera


def test_el_grafo_no_esta_vacio():
    assert len(_destinos()) >= 20, "el grafo perdió destinos"


def test_todo_destino_es_una_pantalla_que_existe():
    """Un href hacia una ruta que no existe da 404 — y como el salto se ve
    igual de bien que los demás, nadie lo nota hasta que alguien lo aprieta."""
    for origen, href, _, _ in _destinos():
        p = os.path.join(RAIZ, "app", *href.strip("/").split("/"), "page.tsx")
        assert os.path.exists(p), f"{origen} salta a {href}, que no existe"


def test_todo_origen_es_una_pantalla_que_existe():
    for origen, _, _, _ in _destinos():
        p = os.path.join(RAIZ, "app", *origen.strip("/").split("/"), "page.tsx")
        assert os.path.exists(p), f"el grafo declara saltos desde {origen}, que no existe"


def test_ninguna_pantalla_salta_a_si_misma():
    for origen, href, _, _ in _destinos():
        assert origen != href, f"{origen} se ofrece saltar a sí misma"


def test_los_rotulos_salen_del_menu_y_existen_en_los_dos_idiomas():
    """El nombre del destino se reusa de `nav.items` para que el menú y el
    salto no le pongan dos nombres distintos al mismo lugar."""
    for idioma in ("es", "en"):
        cat = json.loads(_leer("messages", f"{idioma}.json"))
        items = cat["nav"]["items"]
        porques = cat["ira"]["porque"]
        for origen, _, item, porque in _destinos():
            assert item in items, f"{idioma}: falta nav.items.{item} (desde {origen})"
            assert porque in porques, f"{idioma}: falta ira.porque.{porque} (desde {origen})"


def test_el_mes_no_viaja_a_una_pantalla_anual():
    """Un parámetro que el destino ignora igual queda en la barra de
    direcciones, donde alguien lo copia esperando que haga algo."""
    src = _rutas()
    cuerpo = src[src.index("export const SALTOS"):]
    for linea in cuerpo.splitlines():
        if 'href: "/pl/full"' in linea or 'href: "/pl/simplified"' in linea:
            # Lo que importa es que NO viaje el mes. `SOLO_ESC` y `[]` cumplen
            # las dos; omitir `lleva` no, porque el default manda las tres.
            assert "SOLO_ESC" in linea or "lleva: []" in linea, (
                f"el P&L es anual y esta línea le manda el mes:\n    {linea.strip()}")


# ── Lo que hace que el salto lleve el escenario CORRECTO ────────────────────

# archivo -> (selectores que tiene, columnas que pueden recibir el ?esc=)
#
# `/planning/big-picture` va con CERO a propósito: además de comparar tres
# escenarios, ESCRIBE sobre un cuarto. Recibir el parámetro ahí no es solo
# inútil, es empujar a escribir sobre el escenario que uno no eligió.
COMPARACION = {
    "app/pl/full/page.tsx": (3, 1),
    "app/pl/simplified/page.tsx": (2, 1),
    "app/planning/big-picture/page.tsx": (3, 0),
    # Fase 2. `/reports/pl-full` compara CINCO escenarios: es la más expuesta
    # del sistema a este error.
    "app/reports/pl-full/page.tsx": (5, 1),
    "app/reports/pl-by-dept-compare/page.tsx": (3, 1),
    "app/reports/revenue-mix/page.tsx": (3, 1),
    "app/reports/pl-ytd/page.tsx": (2, 1),
    "app/reports/summary/page.tsx": (2, 1),
    "app/reports/ytd/page.tsx": (2, 1),
    # Junta con CERO: sus tres puestos salen de llaves calculadas
    # (`PUESTOS[i].llave`), así que atar uno pediría desarmar esa lista.
    "app/reports/junta/page.tsx": (3, 0),
    # Fase 3.
    "app/operation-insight/summary/page.tsx": (2, 1),
    "app/operation-insight/headcounts/page.tsx": (2, 1),
    "app/marketing-insight/channel-mix/page.tsx": (2, 1),
    "app/marketing-insight/country/page.tsx": (2, 1),
    # Fase 4. El Dashboard compara CUATRO y es la portada: si sus columnas se
    # igualaran, lo primero que ve cualquiera al entrar diría «no cambió nada».
    "app/dashboard/page.tsx": (4, 1),
}


# Pantallas que EMITEN contexto pero no lo RECIBEN, y por qué. No es
# prudencia: en las dos primeras, preseleccionar un escenario que nadie eligió
# empuja a una acción destructiva sobre el objeto equivocado.
NO_RECIBEN = {
    "app/reports/tax/page.tsx":
        "«Aplicar» ESCRIBE los parámetros fiscales en el escenario del selector",
    "app/scenarios/page.tsx":
        "es el CRUD del escenario: tiene borrar y enllavar al lado",
    "app/break-e/comparar/page.tsx":
        "muestra CUATRO versiones; «el escenario de esta pantalla» no existe",
    "app/admin/import-actuals/page.tsx":
        "es la puerta del GL, emisor y no receptor",
}


def test_las_que_escriben_no_reciben_el_escenario_de_la_url():
    """⚠️ El `?esc=` no es gratis en todas partes.

    En una pantalla que LEE es una mejora. En una que ESCRIBE —o que tiene
    borrar y enllavar al lado— preseleccionar un escenario que el usuario no
    eligió lo empuja a actuar sobre el objeto equivocado.
    """
    for archivo, motivo in NO_RECIBEN.items():
        src = _leer(*archivo.split("/"))
        llamadas = re.findall(r"useEscenarioDe\([^;]*?\);", src, re.S)
        atadas = [c for c in llamadas if re.search(r",\s*true\s*\)\s*;?$", c.strip())]
        assert not atadas, (
            f"{archivo} empezó a recibir el escenario de la URL, y no puede: "
            f"{motivo}")


def test_una_pantalla_de_comparacion_ata_UNA_sola_columna_a_la_url():
    """⚠️ El error caro de todo esto.

    `/pl/full` compara tres escenarios en tres columnas. Si el `?esc=` de la
    dirección alimentara las tres, las tres mostrarían lo mismo y la variación
    daría CERO — que no se lee como un error, se lee como «no cambió nada».
    """
    for archivo, (cuantos, permitidas) in COMPARACION.items():
        src = _leer(*archivo.split("/"))
        llamadas = re.findall(r"useEscenarioDe\([^;]*?\);", src, re.S)
        assert len(llamadas) == cuantos, (
            f"{archivo} ahora tiene {len(llamadas)} selectores y no {cuantos}: "
            f"revisar cuál va atado a la URL")
        atadas = [c for c in llamadas if re.search(r",\s*true\s*\)\s*;?$", c.strip())]
        assert len(atadas) == permitidas, (
            f"{archivo}: hay {len(atadas)} columnas atadas al ?esc= y tiene que "
            f"haber {permitidas}, o la comparación se hace contra sí misma")
        if permitidas:
            # Se mira el ROL —el tercer argumento— y no el nombre de la llave.
            # El Dashboard llama a la suya `dashboard:main` y su rol es
            # `budget`: la convención es sobre QUÉ escenario recibe la columna,
            # no sobre cómo se llama la preferencia donde se recuerda.
            rol = re.search(r',\s*"(\w+)"\s*,\s*undefined', atadas[0])
            assert rol and rol.group(1) == "budget", (
                f"{archivo}: la columna atada al ?esc= tiene que ser la de rol "
                f"budget, que es la que se planifica — es "
                f"'{rol.group(1) if rol else '?'}'")


# Pantallas que están en el grafo pero NO montan la barra, y por qué.
SIN_BARRA = {
    # Redirect puro: `router.replace` y devuelve null. No renderiza nada.
    "/break-e/configuracion",
}


def test_toda_pantalla_del_grafo_muestra_la_barra():
    """Un origen declarado en `SALTOS` que no monta `<IrA>` es trabajo perdido:
    los destinos existen y no hay forma de llegar a ellos.

    Se deriva del grafo y no de una lista escrita a mano: la lista se olvida de
    actualizar justo cuando el grafo crece, que es cuando importa.
    """
    origenes = {o for o, _, _, _ in _destinos()} - SIN_BARRA
    assert len(origenes) >= 30, f"el grafo encogió: {len(origenes)} orígenes"
    for r in sorted(origenes):
        src = _leer("app", *r.strip("/").split("/"), "page.tsx")
        # Una barra sin escenario es válida: `/revenue/inventory`,
        # `/revenue/availability` y `/revenue/room-nights` son dato del HOTEL,
        # no de un escenario, así que no tienen ninguno que pasarle.
        assert "<IrA " in src, f"{r} no monta la barra de saltos"
        assert 'from "@/components/IrA"' in src, f"{r} no importa IrA"


def test_el_volver_no_se_encadena():
    """El `de` es de ida nomás. Si se arrastrara, tres saltos dejarían un
    «volver» apuntando al primero — y mentiría sobre de dónde venís."""
    src = _leer("lib", "contexto.ts")
    cuerpo = src[src.index("export function conContexto"):src.index("export function useFijarContexto")]
    assert 'q.set("de", desde)' in cuerpo
    # `` obligatorio: `ctx.de` es subcadena de `ctx.dep`, que si va.
    assert not re.search(r"ctx\.de", cuerpo), (
        "conContexto empezó a propagar el `de` que ya traía: el «volver» "
        "dejaría de apuntar a la pantalla anterior")


def test_el_contexto_se_escribe_sin_ensuciar_el_historial():
    """Cambiar el mes con el selector no es navegar: con `push`, el botón
    «atrás» del navegador retrocedería mes por mes."""
    src = _leer("lib", "contexto.ts")
    assert "router.replace(" in src and "router.push(" not in src


def test_la_barra_no_usa_el_color_de_marca_como_texto():
    """`--brand` es color de borde y acento, no de texto.

    Da 6.6:1 en Lino y Papel —donde se diseñó— y **4.11:1 en Grafito y 3.26:1
    en Hoy**, por debajo del 4.5:1 que hace falta para leer. Una barra que se
    ve impecable en el tema propio y se apaga en el del otro no falla en
    ningún lado: simplemente no se lee.
    """
    src = _leer("components", "IrA.tsx")
    assert 'color: "var(--brand)"' not in src, (
        "la barra volvió a usar --brand como color de texto: no llega al "
        "mínimo legible en los dos temas oscuros")


def test_la_barra_se_distingue_del_fondo():
    """La primera versión usaba `--border-subtle` sobre `--bg-surface` y el
    owner no la encontró: sobre una pantalla con tablas, tarjetas y avisos, un
    recuadro de bajo contraste arriba de todo se lee como separador."""
    src = _leer("components", "IrA.tsx")
    assert "borderLeft" in src and "var(--brand)" in src, (
        "se fue la franja de marca, que es lo que hace encontrable la barra")
