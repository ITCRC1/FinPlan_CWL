# -*- coding: utf-8 -*-
"""La respuesta trae TODO lo que la pantalla lee. Ni uno menos.

Owner, 2026-10-06, subiendo el detalle de setiembre a la Auditoría del mayor:

    Esta pantalla no se pudo dibujar
    Cannot convert undefined or null to object

La pantalla hace `Object.entries(data.por_grupo)` sin preguntar, y la respuesta
no traía `por_grupo` — el motor siempre lo calculó, nada más que no se mandaba.
O sea: **toda subida exitosa terminaba en pantalla rota**, y el usuario no tenía
forma de saber que su archivo estaba bien.

Es el mismo patrón que ya mordió tres veces en este repo, al revés: ahí el
backend decía algo que el frontend no leía; acá el frontend lee algo que el
backend no dice. Las dos mitades del contrato viven en archivos distintos y
ningún compilador las mira.

**Esta prueba las mira.** Y no con una lista a mano —que es lo que se queda
atrás— sino leyendo las dos fuentes: los `data.X` de la pantalla contra las
llaves que el endpoint arma.
"""
import ast
import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[2]
PANTALLA = RAIZ / "frontend" / "app" / "pre-cierre" / "auditoria" / "page.tsx"
ENDPOINT = RAIZ / "backend" / "app" / "api" / "auditoria_gl_api.py"


def _lo_que_lee_la_pantalla() -> set[str]:
    return set(re.findall(r"\bdata\.([a-z_]+)", PANTALLA.read_text(encoding="utf-8")))


def _lo_que_manda_el_endpoint() -> set[str]:
    """Las llaves del `return {...}` de `revisar`, leídas del árbol sintáctico."""
    arbol = ast.parse(ENDPOINT.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.AsyncFunctionDef) and nodo.name == "revisar":
            for hijo in ast.walk(nodo):
                if isinstance(hijo, ast.Return) and isinstance(hijo.value, ast.Dict):
                    return {k.value for k in hijo.value.keys
                            if isinstance(k, ast.Constant)}
    raise AssertionError("no se encontró el return de `revisar`")


def test_la_pantalla_existe_donde_la_prueba_la_busca():
    """Si alguien mueve la pantalla, esta prueba tiene que avisar — no pasar en
    verde mirando un archivo que ya no está."""
    assert PANTALLA.exists(), PANTALLA


def test_no_falta_nada_de_lo_que_la_pantalla_lee():
    """El defecto, exacto: `por_grupo` se leía y no se mandaba."""
    faltan = _lo_que_lee_la_pantalla() - _lo_que_manda_el_endpoint()
    assert not faltan, (
        f"la pantalla lee {sorted(faltan)} y la respuesta no lo manda: "
        "toda subida exitosa va a romper el dibujo")


def test_por_grupo_viaja():
    """El campo del caso del owner, nombrado, para que se lea en el fallo."""
    assert "por_grupo" in _lo_que_manda_el_endpoint()


def test_el_motor_lo_calcula():
    """Si el motor dejara de calcularlo, mandarlo no alcanzaría."""
    from app.engine.auditoria_gl import Resumen

    assert "por_grupo" in Resumen.__dataclass_fields__
