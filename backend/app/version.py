# -*- coding: utf-8 -*-
"""Qué versión está corriendo esta instalación.

**Por qué existe (owner, 2026-08-14).** Con cuatro propiedades desplegando el
mismo repo, la pregunta «¿el hotel 3 ya tiene el arreglo?» no tenía respuesta sin
entrar a Railway. Y el día que un despliegue se queda atrás, nada lo dice: la app
responde igual de bien con el código de la semana pasada.

Peor todavía es el desfase entre CÓDIGO y BASE: si el commit trae una migración
que no corrió, la app arranca contra un esquema viejo y revienta en la primera
consulta que use la columna nueva. `/health` compara los dos y lo dice.
"""
import os
import pathlib
import re

_VERSIONES = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"

# Los archivos usan DOS formas — `revision = "104"` y
# `down_revision: Union[str, None] = "103"` — así que la anotación de tipo va
# opcional en el patrón. Sin eso las migraciones anotadas no se veían y el
# cálculo devolvía CUATRO cabezas donde hay una sola.
_RE_REV = re.compile(r'^revision(?:\s*:[^=\n]+)?\s*=\s*["\']([^"\']+)["\']', re.M)
_RE_DOWN = re.compile(r'^down_revision(?:\s*:[^=\n]+)?\s*=\s*["\']([^"\']+)["\']', re.M)


def sha_del_despliegue() -> str:
    """El commit que Railway desplegó. Vacío en local, y está bien que se note."""
    for var in ("RAILWAY_GIT_COMMIT_SHA", "GIT_COMMIT_SHA", "SOURCE_COMMIT"):
        v = (os.getenv(var) or "").strip()
        if v:
            return v[:12]
    return ""


def head_del_codigo() -> str | None:
    """La última migración que trae ESTE código.

    Se calcula del árbol y no de una constante: la revisión que nadie declara
    como su `down_revision` es la cabeza. Una constante escrita a mano se olvida.
    """
    if not _VERSIONES.is_dir():
        return None
    revisiones: set[str] = set()
    padres: set[str] = set()
    for p in _VERSIONES.glob("*.py"):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        m = _RE_REV.search(txt)
        if m:
            revisiones.add(m.group(1))
        d = _RE_DOWN.search(txt)
        if d:
            padres.add(d.group(1))
    cabezas = sorted(revisiones - padres)
    if len(cabezas) == 1:
        return cabezas[0]
    # Más de una cabeza = el árbol de migraciones se bifurcó, y `alembic upgrade
    # head` no sabría cuál aplicar. Es un problema real: se muestra, no se
    # esconde detrás de un valor cualquiera.
    return ",".join(cabezas) if cabezas else None
