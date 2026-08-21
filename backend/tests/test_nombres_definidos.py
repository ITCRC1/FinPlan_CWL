# -*- coding: utf-8 -*-
"""Ningún nombre usado dentro de una función queda sin definir.

**Por qué existe esta prueba (2026-08-14).** `revenue_api.py` usaba `HOTEL_ID`
en `_canonical_room_types()` y en `_otb_units()` sin haberlo importado. Python no
se queja al importar el módulo —el nombre se resuelve cuando la función CORRE—
así que el archivo cargaba bien, la app arrancaba bien, las 836 pruebas pasaban
en verde, y el error solo aparecía al abrir la pantalla que llama a esa función.

Es la peor forma de fallar: invisible en todo lo que miramos, y garantizada en
producción. Un import olvidado al mover código no lo detecta ni el typecheck ni
el arranque.

La prueba camina el AST y respeta el alcance de verdad —una función anidada VE
los locales de la que la contiene—, así que no se queja de los cierres.
"""
import ast
import builtins
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "app"
BUILTINS = set(dir(builtins))


def _liga(nodo) -> set[str]:
    """Nombres que ESTE ámbito liga, sin entrar en funciones anidadas."""
    out: set[str] = set()

    class V(ast.NodeVisitor):
        def visit_Name(self, n):
            if isinstance(n.ctx, (ast.Store, ast.Del)):
                out.add(n.id)

        def visit_arg(self, n):
            out.add(n.arg)

        def visit_Import(self, n):
            for a in n.names:
                out.add((a.asname or a.name).split(".")[0])

        def visit_ImportFrom(self, n):
            for a in n.names:
                out.add(a.asname or a.name)

        def visit_FunctionDef(self, n):
            out.add(n.name)

        def visit_AsyncFunctionDef(self, n):
            out.add(n.name)

        def visit_ClassDef(self, n):
            out.add(n.name)

        def visit_Global(self, n):
            out.update(n.names)

        def visit_Nonlocal(self, n):
            out.update(n.names)

        def visit_ExceptHandler(self, n):
            if n.name:
                out.add(n.name)
            self.generic_visit(n)

    ANIDADOS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

    def recorrer(n):
        """Baja por el árbol SIN entrar al cuerpo de lo anidado.

        Antes esto usaba `ast.walk`, que salta el nodo de la función pero igual
        visita a sus hijos — así que `visit_arg` recogía los parámetros de TODAS
        las funciones del archivo y los daba por ligados a nivel de módulo. El
        efecto: cualquier nombre que fuera parámetro en algún lado pasaba por
        definido en todos lados, y la prueba dejaba pasar justo lo que existe
        para atrapar. Costó un 500 en producción (`periodo` en `construir_anio`
        de `owners_q_api`, 2026-08-17).
        """
        for hijo in ast.iter_child_nodes(n):
            v.visit(hijo)
            if not isinstance(hijo, ANIDADOS):
                recorrer(hijo)

    v = V()
    for hijo in ast.iter_child_nodes(nodo):
        v.visit(hijo)
        if not isinstance(hijo, ANIDADOS):
            recorrer(hijo)
    return out


def _locales_de(fn) -> set[str]:
    loc = _liga(fn) | {a.arg for a in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs}
    if fn.args.vararg:
        loc.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        loc.add(fn.args.kwarg.arg)
    return loc


def _sin_definir(path: pathlib.Path) -> list[str]:
    arbol = ast.parse(path.read_text(encoding="utf-8"))
    fallos: list[str] = []

    def _leidos(fn):
        """Nombres leídos por ESTA función, sin bajar a las anidadas.

        Bajar seria contarlos dos veces y con el alcance equivocado: el cuerpo de
        una funcion anidada se revisa en su propia vuelta, donde ya se ven los
        locales de la que la contiene.
        """
        pila = list(ast.iter_child_nodes(fn))
        while pila:
            n = pila.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                continue
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                yield n
            pila.extend(ast.iter_child_nodes(n))

    def caminar(nodo, visibles: set[str]):
        for hijo in ast.iter_child_nodes(nodo):
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nuevos = visibles | _locales_de(hijo)
                for n2 in _leidos(hijo):
                    if n2.id not in nuevos and n2.id not in BUILTINS:
                        fallos.append(f"{path.name}:{n2.lineno}: «{n2.id}» en {hijo.name}()")
                caminar(hijo, nuevos)
            else:
                caminar(hijo, visibles)

    caminar(arbol, _liga(arbol))
    return fallos


def test_ninguna_funcion_usa_un_nombre_que_no_existe():
    culpables: list[str] = []
    for p in sorted(RAIZ.rglob("*.py")):
        culpables.extend(_sin_definir(p))
    assert not culpables, (
        "Estos nombres revientan con NameError cuando la función corre. El módulo "
        "importa bien y la app arranca bien — el error sale en la pantalla:\n  "
        + "\n  ".join(culpables)
    )


def test_la_prueba_atrapa_el_caso_que_se_le_escapo(tmp_path):
    """Regresión de la PRUEBA misma.

    Este es exactamente el archivo que pasó en verde y reventó en producción:
    `periodo` es parámetro de una función y se usa suelto en OTRA. Con el
    `ast.walk` viejo, el parámetro de la primera contaba como nombre de módulo
    y la segunda pasaba.
    """
    p = tmp_path / "caso.py"
    p.write_text(
        "def uno(periodo=None):\n"
        "    return periodo\n"
        "\n"
        "def dos():\n"
        "    return uno(periodo)\n",
        encoding="utf-8")
    fallos = _sin_definir(p)
    assert any("periodo" in f and "dos()" in f for f in fallos), fallos


def test_no_se_queja_de_un_cierre_legitimo(tmp_path):
    """Una función anidada SÍ ve los locales de la que la contiene."""
    p = tmp_path / "cierre.py"
    p.write_text(
        "def afuera(x):\n"
        "    def adentro():\n"
        "        return x\n"
        "    return adentro()\n",
        encoding="utf-8")
    assert _sin_definir(p) == []
