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

# ── La sub-linea que el presupuesto no abre: VACIA, no cero ─────────────────

def test_el_detalle_dice_si_la_version_abre_el_tercer_nivel():
    """⚠️ Un cero en la sub-linea es una AFIRMACION, y era falsa.

    Medido contra setiembre 2026 el 2026-10-09: **405 celdas de comparacion en
    cero** —316 de planilla y 89 de gasto— y las 405 significaban «esta version
    no abre el tercer nivel», no «presupuesto cero aca». Dos causas distintas:

    * **Gasto.** Ningun escenario trae la serie 800-810 que usa Integrity: los
      Forecast 2026 y el ACTUAL traen el detalle VACIO, y los Budget 2027 usan
      otra numeracion (005-011).
    * **Planilla.** Los conceptos de 2026 cuelgan todos de la posicion
      sintetica `GL` «(Actual GL)». El Budget Final tiene 94 posiciones y solo
      11 con conceptos: las 11 sinteticas.

    El exportador ya lo hacia bien —`const vacias = comp.map(() => null)`, con
    el comentario «El detalle no compara: vacio, no cero»— y la pantalla
    escribia 0.00. Los dos decian cosas distintas del mismo dato, que es el
    defecto que este proyecto ya pago una vez al reves («el excel no baja lo
    que esta viendo», 2026-08-27).

    Es la misma regla que `detalle_celda_api` ya tenia escrita: *«La version
    que no abrio NO va en cero: no va»*.
    """
    import inspect

    from app.api import precierre_api

    for fn in (precierre_api.gasto_por_detalle,
               precierre_api.planilla_por_posicion):
        fuente = inspect.getsource(fn)
        assert '"abre_detalle"' in fuente, fn.__name__


def test_la_pantalla_y_el_excel_dicen_LO_MISMO_de_la_sub_linea():
    """Si el exportador deja la celda vacia, la pantalla tambien.

    Es la regla de este proyecto desde el 2026-08-27: lo que se baja es lo que
    se ve. Que difieran en un cero es peor que no tener la columna.
    """
    import pathlib

    pantalla = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app"
                / "month-end" / "pl" / "Pantalla.tsx")
    txt = pantalla.read_text(encoding="utf-8", errors="replace")
    # El exportador: vacio.
    assert "const vacias = comp.map(() => null)" in txt
    # La pantalla: el guion largo cuando la version no abre el detalle.
    assert "c.abre_detalle === false" in txt
    # Y se dice por que, en vez de dejar una columna muda.
    assert "detalleNoCompara" in txt
