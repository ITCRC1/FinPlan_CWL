# -*- coding: utf-8 -*-
"""Toda ruta que el frontend pide tiene que existir en el backend.

Owner, 2026-09-16, en el sub-tab «12m Summary»: «que paso con todos los datos..
ningun full year esta saliendo bien». La pantalla mostraba
`API 404: {"detail":"Not Found"}` y las doce columnas en guiones.

No era el dato. `/pl/{id}/doce-meses/` NO EXISTIA: el frontend lo llamaba desde
el 2026-09-08 —cuando el Cierre de Mes de CWL se puso al dia con las otras
propiedades (`1c251e5`)— y el backend nunca lo tuvo. Ocho dias de una pantalla
vacia que se leia como «no hay datos».

Este guard compara las dos listas. Una ruta que no existe deja de ser un 404 en
vivo y pasa a ser una prueba en rojo.
"""
import io
import pathlib
import re

import app.main as main

API_TS = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "lib" / "api.ts"

#: Huecos CONOCIDOS, con su razon. Sacar uno de aca sin implementarlo vuelve a
#: romper la prueba, que es la idea: son deuda anotada, no permiso.
#:
#: Hoy esta VACIO, y ese es el estado que hay que defender. El 2026-09-16 tenia
#: cuatro: `doce-meses`, `estadisticas`, `nonop/lines` y `opex/recalcular-tc`,
#: las cuatro del mismo commit (`1c251e5`).
PENDIENTES: dict[str, str] = {}

#: `/login` y `/reset-password` son rutas del NAVEGADOR (Next.js), no del API.
NO_SON_DEL_API = {"/login", "/reset-password"}


def _sin_comentarios(src: str) -> str:
    """Un backtick dentro de un comentario no es una llamada.

    `api.ts` documenta rutas en prosa (`/summary/`, `/laundry-breakdown/`) y
    esas menciones no piden nada. Sin este paso el guard avisaba de seis rutas
    que nadie llama — y un guard que grita de mas se termina ignorando.
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*(?://|\*).*$", "", src)


def _ruta(texto: str) -> str | None:
    """De la plantilla TS al patron comparable, o None si no es una ruta."""
    r = texto.split("?")[0]
    if "${" in r and "}" not in r.split("${", 1)[1]:
        return None                       # plantilla cortada por un salto de linea
    r = re.sub(r"\$\{[^}]*\}", "*", r)
    if " " in r or set(r) <= {"/", "*"}:
        return None
    return r.rstrip("/") or "/"


def _rutas_del_frontend() -> set[str]:
    src = _sin_comentarios(io.open(API_TS, encoding="utf-8").read())
    fuera = {_ruta(m.group(1))
             for m in re.finditer(r"`(?:\$\{BASE\})?(/[^`]*)`", src)}
    return {r for r in fuera if r and len(r) > 1 and r not in NO_SON_DEL_API}


def _rutas_del_backend() -> set[str]:
    fuera = set()
    for p in main.app.openapi()["paths"]:
        n = re.sub(r"\{[^}]*\}", "*", p).rstrip("/")
        fuera.add(n)
        if n.startswith("/api"):
            fuera.add(n[len("/api"):])
    return fuera


def _casa(ruta: str, patron: str) -> bool:
    """`*` casa contra cualquier segmento, venga del lado que venga.

    Hace falta en las dos direcciones. El backend parametriza lo que el
    frontend escribe literal (`/pl/{id}/` ← `/pl/${id}/`), y el frontend
    interpola lo que el backend tiene literal: `/allocations/${tipo}/…` es
    `cafeteria` o `laundry`, dos rutas fijas del backend.
    """
    a, b = ruta.split("/"), patron.split("/")
    return len(a) == len(b) and all(
        x == y or x == "*" or y == "*" for x, y in zip(a, b))


def _candidatas(ruta: str) -> list[str]:
    """Con y sin el ultimo `*`.

    ⚠️ Un `${...}` al FINAL es ambiguo: puede ser un segmento (`/pl/${id}/`) o
    el query armado aparte (`/precierre/${id}/cambios/${q}`). No hay como
    saberlo leyendo el texto, asi que se aceptan las dos lecturas.
    """
    formas = [ruta]
    if ruta.endswith("/*"):
        formas.append(ruta[: -len("/*")])
    return [f.rstrip("/") or "/" for f in formas]


def test_ninguna_pantalla_pide_una_puerta_inexistente():
    back = _rutas_del_backend()
    faltan = sorted(
        r for r in _rutas_del_frontend()
        if not any(_casa(c, b) for c in _candidatas(r)
                   for b in list(back) + list(PENDIENTES)))
    assert not faltan, (
        "el frontend llama rutas que el backend no tiene:\n  "
        + "\n  ".join(faltan)
        + "\nEso es un 404 en vivo: la pantalla sale vacia y se lee como «no hay datos»")


def test_los_pendientes_siguen_pendientes():
    """Si alguno ya se implemento, sacarlo de la lista — asi no se acumula
    deuda que ya no existe y el proximo lector puede confiar en ella."""
    back = _rutas_del_backend()
    ya = sorted(p for p in PENDIENTES if any(_casa(p, b) for b in back))
    assert not ya, f"ya existen, sacarlos de PENDIENTES: {ya}"


def test_la_que_rompio_el_12m_ya_existe():
    assert "/pl/*/doce-meses" in _rutas_del_backend()
