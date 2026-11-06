# -*- coding: utf-8 -*-
"""La ruta existe, pero el verbo no: eso es un 405 y nadie lo veía venir.

Owner, 2026-11-05, en *Gastos del Propietario — Below GOP*: «otro error», con
`Error: API 405: {"detail":"Method Not Allowed"}` al apretar **Guardar
cambios**.

`api.ts` llamaba `PUT /nonop/{id}/bulk/` y el backend sólo tiene `POST` ahí.
Comprobado contra producción antes de tocar nada:

    PUT   -> 405   (ese verbo no existe en la ruta)
    POST  -> 401   (existe, y pide credenciales)

## Por qué el guard de al lado no lo vio

`test_el_frontend_no_llama_puertas_que_no_existen` compara **rutas** y nada
más. La ruta estaba perfecta; lo que no estaba era el verbo. Media verificación
da media confianza, y de las dos mitades ésta no la cubría nadie: el 405 sólo
aparecía cuando el usuario apretaba el botón, que es el peor momento para
enterarse.

## Qué mira esta prueba

Por cada `api.<verbo>(\\`/ruta/\\`)` de `api.ts`, que ese par (ruta, verbo)
exista en el OpenAPI del backend. Si la ruta no existe, **no** se queja: de eso
ya se ocupa el otro guard, y dos pruebas gritando por lo mismo se terminan
ignorando las dos.
"""
import io
import pathlib
import re

import app.main as main

API_TS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "lib" / "api.ts"

#: Pares (ruta, verbo) que el frontend llama y el backend no acepta, con su
#: razón. Hoy está VACÍO y ese es el estado que hay que defender — son deuda
#: anotada, no permiso.
#:
#: El 2026-11-05 tenía uno: `/nonop/*/bulk` con PUT, que dejaba el botón
#: «Guardar cambios» del auxiliar below-GOP sin guardar nada.
PENDIENTES: dict[tuple[str, str], str] = {
    ("/allocations/*/*/config", "DELETE"):
        "`borrarFilaReparto` no la llama NINGUNA pantalla (2026-11-05). El "
        "backend tiene GET y PUT ahi; borrar una fila del reparto y reemplazar "
        "la config entera no son lo mismo, asi que esto NO se arregla cambiando "
        "el verbo — hay que decidir si la funcion existe o se va.",
}

VERBOS = ("get", "post", "put", "patch", "delete")


def _sin_comentarios(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*(?://|\*).*$", "", src)


def _normalizar(ruta: str) -> str | None:
    r = ruta.split("?")[0]
    if "${" in r and "}" not in r.split("${", 1)[1]:
        return None
    r = re.sub(r"\$\{[^}]*\}", "*", r)
    if " " in r or set(r) <= {"/", "*"}:
        return None
    r = r.rstrip("/")
    return r if len(r) > 1 else None


def _llamadas_del_frontend() -> set[tuple[str, str]]:
    """(ruta, verbo) por cada `api.<verbo>(...)` cuyo 1er argumento sea literal.

    Entre el verbo y el parentesis puede haber un generico (`<Foo[]>`, y
    tambien `<Array<Foo>>`, con `>` adentro), asi que se busca el `(` que abre
    la llamada y se exige que el argumento **empiece** ahi: backtick, comilla
    simple o doble.

    ⚠️ **No se escanea hacia adelante buscando el primer texto que parezca
    una ruta.** Esa era la primera version y mentia: `api.patch<unknown>(
    "/auth/me/tema", ...)` usa comillas, el patron de backticks la salteaba,
    seguia leyendo y se traia la plantilla de la funcion SIGUIENTE --
    reportando un `PATCH /auth/status` que nadie escribio nunca. Un guard que
    inventa un hallazgo se gana que le ignoren los cuatro que si eran ciertos.
    """
    src = _sin_comentarios(io.open(API_TS, encoding="utf-8").read())
    fuera: set[tuple[str, str]] = set()
    for m in re.finditer(r"\bapi\.(" + "|".join(VERBOS) + r")\b", src):
        resto = src[m.end():]
        abre = resto.find("(")
        if abre < 0 or "\n\n" in resto[:abre]:
            continue                      # no es una llamada
        arg = resto[abre + 1:].lstrip()
        if arg[:1] not in ("`", "'", '"'):
            continue                      # la ruta viene en una variable
        cierre = arg.find(arg[0], 1)
        if cierre < 0:
            continue
        crudo = arg[1:cierre]
        if crudo.startswith("${BASE}"):
            crudo = crudo[len("${BASE}"):]
        if not crudo.startswith("/"):
            continue
        ruta = _normalizar(crudo)
        if ruta:
            fuera.add((ruta, m.group(1).upper()))
    return fuera


def _puertas_del_backend() -> dict[str, set[str]]:
    """ruta normalizada -> verbos que acepta."""
    fuera: dict[str, set[str]] = {}
    for p, ops in main.app.openapi()["paths"].items():
        verbos = {v.upper() for v in ops if v.lower() in VERBOS}
        n = re.sub(r"\{[^}]*\}", "*", p).rstrip("/")
        for clave in (n, n[len("/api"):] if n.startswith("/api") else None):
            if clave:
                fuera.setdefault(clave, set()).update(verbos)
    return fuera


def _casa(ruta: str, patron: str) -> bool:
    a, b = ruta.split("/"), patron.split("/")
    return len(a) == len(b) and all(
        x == y or x == "*" or y == "*" for x, y in zip(a, b))


def _candidatas(ruta: str) -> list[str]:
    formas = [ruta] + ([ruta[: -len("/*")]] if ruta.endswith("/*") else [])
    return [f.rstrip("/") or "/" for f in formas]


def _verbos_aceptados(ruta: str, back: dict[str, set[str]]) -> set[str]:
    acepta: set[str] = set()
    for c in _candidatas(ruta):
        for patron, verbos in back.items():
            if _casa(c, patron):
                acepta |= verbos
    return acepta


def test_ninguna_pantalla_llama_con_el_verbo_equivocado():
    back = _puertas_del_backend()
    malos = []
    for ruta, verbo in sorted(_llamadas_del_frontend()):
        acepta = _verbos_aceptados(ruta, back)
        if not acepta:
            continue            # ruta inexistente: es del OTRO guard
        if verbo not in acepta and (ruta, verbo) not in PENDIENTES:
            malos.append(f"{verbo} {ruta}  (el backend acepta: {', '.join(sorted(acepta))})")
    assert not malos, (
        "el frontend llama con un verbo que el backend no acepta:\n  "
        + "\n  ".join(malos)
        + "\nEso es un 405 en vivo, y sólo aparece cuando el usuario aprieta el botón")


def test_los_pendientes_siguen_pendientes():
    back = _puertas_del_backend()
    ya = sorted(f"{v} {r}" for (r, v) in PENDIENTES
                if v in _verbos_aceptados(r, back))
    assert not ya, f"ya los acepta el backend, sacarlos de PENDIENTES: {ya}"


def test_la_prueba_encuentra_llamadas():
    """Un regex que no casa nada hace una prueba que nunca falla."""
    llamadas = _llamadas_del_frontend()
    assert len(llamadas) > 200, (
        f"sólo encontré {len(llamadas)} llamadas en api.ts; el patrón se rompió")
    verbos = {v for _, v in llamadas}
    assert {"GET", "POST", "PUT"} <= verbos, f"faltan verbos: {verbos}"
