# -*- coding: utf-8 -*-
"""En `app.models` ningun nombre puede venir de dos modulos distintos.

**Como aparecio (2026-08-14).** Al exportar la constante `DIMENSIONES` de
`stat_account` quedo pisando a la de `dept_enablement`, que se llama igual y es
otra cosa: una lista las dimensiones de una estadistica (DEPT, POSITION,
ROOMTYPE...) y la otra las dimensiones de provisionamiento (REVENUE, PAYROLL,
OPEX, COST, PROPERTY).

Python no avisa: la segunda importacion gana en silencio. Quien hiciera
`from app.models import DIMENSIONES` recibiria la equivocada y el error se veria
mucho despues, en una validacion que rechaza lo que deberia aceptar.

Hoy nadie importa asi —todos van al modulo especifico— pero eso es suerte, no
diseno.
"""
import ast
import collections
import io
import pathlib

INIT = pathlib.Path(__file__).resolve().parents[1] / "app" / "models" / "__init__.py"


def _importados() -> dict[str, list[str]]:
    """{nombre expuesto: [modulos que lo traen]}."""
    arbol = ast.parse(io.open(INIT, encoding="utf-8").read())
    por_nombre: dict[str, list[str]] = collections.defaultdict(list)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module:
            for alias in nodo.names:
                por_nombre[alias.asname or alias.name].append(nodo.module)
    return por_nombre


def test_ningun_nombre_viene_de_dos_modulos():
    choques = {n: mods for n, mods in _importados().items() if len(set(mods)) > 1}
    assert not choques, (
        "estos nombres se importan desde mas de un modulo en app/models/__init__.py "
        f"y el ultimo pisa al anterior sin avisar: {choques}. "
        "Renombra uno con `as`."
    )


def test_las_dos_DIMENSIONES_siguen_separadas():
    """El caso concreto, para que no se deshaga sin que nadie note."""
    from app.models import DIMENSIONES_ESTADISTICAS
    from app.models.dept_enablement import DIMENSIONES as DIMS_PROVISION
    assert "DEPT" in DIMENSIONES_ESTADISTICAS
    assert "REVENUE" in DIMS_PROVISION
    assert set(DIMENSIONES_ESTADISTICAS) != set(DIMS_PROVISION)


def test_todo_lo_que_declara___all___existe():
    """Un nombre en `__all__` que no se importa revienta con `import *`."""
    import app.models as m
    faltan = [n for n in m.__all__ if not hasattr(m, n)]
    assert not faltan, f"declarados en __all__ y no importados: {faltan}"
