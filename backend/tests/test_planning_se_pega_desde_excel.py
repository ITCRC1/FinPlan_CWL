# -*- coding: utf-8 -*-
"""Toda grilla editable del tab Planning acepta copy-paste de Excel.

Owner, 2026-10-04: *«asegurate que todo el tab de planning de todas las finplan
acepten copy paste»*.

## Por que es un test y no una lista

Las pantallas de Planning se escriben a mano, una por una, y cada una resuelve
sus celdas a su manera: unas guardan al salir del campo, otras tienen boton de
Guardar, otras abren un editor al hacer clic. El pegado se olvida en la
siguiente que alguien agregue — y no falla: simplemente mete los doce meses
dentro de la primera celda y el usuario los teclea de nuevo sin saber que habia
otra forma.

Este test **recorre el menu de Planning**, busca las pantallas que tienen una
grilla de meses con celdas editables, y exige que cada una enganche el pegado.
La lista se mantiene sola: una pantalla nueva con grilla entra sin que nadie la
agregue aca.

## Lo que NO exige

Las pantallas de solo lectura —el reporte de FTE, el checkbook de planilla, las
noches, el net rate— no tienen donde pegar. Y las que suben su Excel con un
boton tampoco lo necesitan: ya tienen el camino.
"""
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[2]
FRONT = RAIZ / "frontend"
NAV = FRONT / "components/TopNav.tsx"
LIB = FRONT / "lib/pegarGrilla.ts"

#: Pantallas con grilla de meses que NO se pegan, y por que. Cada una tiene que
#: tener su razon escrita: «todavia no» no es una razon, es una deuda sin dueno.
EXCEPCIONES: dict[str, str] = {}


def _rutas_de_planning() -> list[str]:
    """Las rutas del menu Planning, leidas del menu y no copiadas aca."""
    nav = NAV.read_text(encoding="utf-8")
    i = nav.index('key: "planning"')
    bloque = nav[i:nav.index("},\n  {", i)]
    return re.findall(r'href: "(/[^"]+)"', bloque)


def _cuerpo_del_map(src: str, desde: int) -> str:
    """El texto del `.map(...)` que empieza en `desde`, hasta su parentesis que
    cierra.

    ⚠️ Mirar «los proximos N caracteres» no sirve: la cabecera de meses y la
    primera fila de datos estan a pocas lineas, asi que un `<input>` de otra
    cosa —el nombre del empleado, el selector de escenario— cae dentro de la
    ventana y la pantalla se marca como editable cuando no lo es. Pasa en el
    checkbook de planilla, cuyas celdas de mes son de SOLO LECTURA.
    """
    prof, i = 0, desde
    while i < len(src):
        if src[i] == "(":
            prof += 1
        elif src[i] == ")":
            prof -= 1
            if prof == 0:
                return src[desde:i]
        i += 1
    return src[desde:desde + 2000]


def _tiene_grilla_editable(src: str) -> bool:
    """¿Hay un `<input>` dentro del recorrido de meses, no cerca de el?

    Es la forma que tienen todas: `MONTHS.map(...)` o `MONTH_KEYS.map(...)` con
    un campo adentro. No alcanza con contar inputs —casi toda pantalla tiene el
    selector de escenario o el subir-Excel— ni con buscar `MONTHS`, que tambien
    esta en las de solo lectura.
    """
    for m in re.finditer(r"(MONTHS|MESES|MONTH_KEYS|length: 12)\W*?\.map\(", src):
        if "<input" in _cuerpo_del_map(src, m.end() - 1):
            return True
    # Las grillas que recorren su propio arreglo de doce (`capture.map`,
    # `pct3.map`) se reconocen por el estado, no por el nombre del mes.
    for m in re.finditer(r"(pct\d|capture|precio|vals)\.map\(", src):
        if "<input" in _cuerpo_del_map(src, m.end() - 1):
            return True
    return False


def test_el_menu_de_planning_se_puede_leer():
    """Si esto falla, el resto del archivo esta comprobando una lista vacia —y
    pasaria en verde sin mirar nada."""
    rutas = _rutas_de_planning()
    assert len(rutas) >= 15, f"solo se leyeron {len(rutas)} rutas del menu"
    assert "/revenue/pax" in rutas


def test_toda_grilla_editable_de_PLANNING_acepta_el_pegado():
    """⚠️ El defecto que esto persigue: los doce meses entran DENTRO de la
    primera celda.

    No falla, no avisa, y el usuario los teclea de nuevo. Owner, 2026-10-04,
    sobre la primera grilla que salio sin esto: *«rate y todo queda en la
    primera celda»*.
    """
    sin_pegado = []
    for ruta in _rutas_de_planning():
        pag = FRONT / "app" / ruta.lstrip("/") / "page.tsx"
        if not pag.exists():
            continue
        fuentes = [pag.read_text(encoding="utf-8")]
        # Una pantalla puede tener su grilla en un componente al lado.
        for hermano in pag.parent.glob("*.tsx"):
            if hermano != pag:
                fuentes.append(hermano.read_text(encoding="utf-8"))
        junto = "\n".join(fuentes)
        if not _tiene_grilla_editable(junto):
            continue
        if "onPaste" in junto:
            continue
        if ruta in EXCEPCIONES:
            continue
        sin_pegado.append(ruta)

    assert not sin_pegado, (
        "estas pantallas de Planning tienen grilla editable y no aceptan pegar "
        f"desde Excel: {sin_pegado}. Se engancha con una linea: "
        "`onPaste={e => manejarPegado(e, b => ...)}` de `lib/pegarGrilla`. "
        "Si de verdad no corresponde, va en EXCEPCIONES con su razon.")


def test_el_pegado_sale_de_UNA_libreria():
    """⚠️ Cada pantalla resolviendolo a su manera es como nacio el defecto.

    La de rack rates tiene su propio `num()` que borra todas las comas: un
    `2,1` copiado de un Excel en español entra como **21**. Con un solo parser
    —el de `lib/pegarGrilla`— esa clase de error se arregla una vez.
    """
    assert LIB.exists()
    lib = LIB.read_text(encoding="utf-8")
    for pieza in ("export function celdasPegadas(", "export function numeroDeExcel(",
                  "export function repartirPegado(", "export function manejarPegado(",
                  "export function pegarEnFila("):
        assert pieza in lib, f"falta {pieza}"

    # Y quien pega, pega con ella.
    propios = []
    for ruta in _rutas_de_planning():
        pag = FRONT / "app" / ruta.lstrip("/") / "page.tsx"
        if not pag.exists():
            continue
        for f in [pag, *[h for h in pag.parent.glob("*.tsx") if h != pag]]:
            src = f.read_text(encoding="utf-8")
            if "onPaste" in src and "@/lib/pegarGrilla" not in src:
                propios.append(str(f.relative_to(FRONT)))
    assert not propios, (
        f"estas pantallas pegan con su propio parser: {propios}. "
        "Con uno por pantalla, el mismo `2,1` entra distinto en cada una.")


#: Celdas que guardan el NUMERO del porcentaje —`52%` es 52— y por lo tanto no
#: pueden usar `numeroDeExcel`, que ve el `%` y divide entre cien.
POR_CIENTO = {
    "frontend/app/revenue/occupancy/page.tsx": "% de ocupacion por tipo y mes",
    "frontend/app/revenue/spa/page.tsx": "capture rate",
    "frontend/app/nonop/management-fees/page.tsx": "mgmt fee % y royalties %",
}


def test_una_celda_de_PORCENTAJE_no_usa_el_parser_de_dinero():
    """⚠️ Dos errores distintos en la misma celda, los dos medidos el 2026-10-04.

        el parser viejo    «52,0»  → 520     (borraba la coma)
        numeroDeExcel      «52%»   → 0,52    (divide entre cien)

    Owner, pegando ocupacion: *«lo que yo subo son %, digo 52%, lo que quiero es
    que tome el 52 y no que diga 520»*.

    Lo que decide cual parser va no es el texto pegado sino **que guarda la
    celda**, y eso solo lo sabe la pantalla. Por eso son dos funciones y no una
    con un `if`.
    """
    malas = []
    for rel, que in POR_CIENTO.items():
        p = FRONT / rel.removeprefix("frontend/")
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        # Sin los comentarios: el que explica por que NO se usa la nombra.
        codigo = re.sub(r"/\*[\s\S]*?\*/|//.*", "", src)
        if "numeroDeExcel" in codigo:
            malas.append(f"{rel} ({que})")
        if "numeroDePorcentaje" not in codigo and "onPaste" in codigo:
            malas.append(f"{rel}: pega sin `numeroDePorcentaje` ({que})")
    assert not malas, (
        "estas celdas guardan el NUMERO del porcentaje y estan usando el parser "
        f"de dinero: {malas}. `numeroDeExcel` divide entre cien cuando ve un `%`.")


def test_la_libreria_tiene_LAS_DOS_lecturas_del_porcentaje():
    """Una celda guarda la fraccion (0,52) y otra el numero (52). Las dos
    existen, y cada pantalla elige la suya."""
    lib = LIB.read_text(encoding="utf-8")
    assert "export function numeroDePorcentaje(" in lib
    assert "s.endsWith(\"%\") ? s.slice(0, -1) : s" in lib, (
        "`numeroDePorcentaje` volvio a dejar que se divida entre cien")
