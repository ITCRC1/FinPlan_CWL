# -*- coding: utf-8 -*-
"""UNA MIGRACION NO PUEDE CREAR EL MISMO INDICE DOS VECES.

El 2026-09-10 la migracion 143 declaraba `index=True` en una columna DENTRO de
`op.create_table` y ademas llamaba a `op.create_index` con el nombre que
alembic autogenera para esa misma columna. El segundo intento falla, la
migracion se cae, `alembic upgrade head` corta el arranque (`Procfile`:
alembic && seed && uvicorn) y **la app no levanta**.

## Por que un guard y no «acordarse»

El sintoma no se parece a la causa. El backend contesta 502, el navegador dice
«Failed to fetch» —que es lo que se ve cuando no hay cabeceras CORS porque no
hay respuesta— y eso apunta al archivo que se estaba subiendo o a la red. Se
perdieron seis minutos de produccion buscando en el lugar equivocado.

Y es un error que solo aparece EN EL DEPLOY: local no hay Postgres, los tests
no corren migraciones, y el archivo se ve perfectamente razonable.
"""
import ast
import io
import os

VERSIONES = os.path.join(os.path.dirname(__file__), "..", "alembic", "versions")


def _nombre_auto(tabla: str, columna: str) -> str:
    """El nombre que alembic le pone al indice de `index=True`."""
    return f"ix_{tabla}_{columna}"


def _literal(nodo):
    return nodo.value if isinstance(nodo, ast.Constant) else None


def _revisar(arbol) -> list[str]:
    """Los choques de nombre de indice dentro de UN archivo de migracion."""
    creados: set[str] = set()          # nombres pasados a create_index
    automaticos: dict[str, str] = {}   # nombre auto -> "tabla.columna"

    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        fn = nodo.func
        nombre_fn = getattr(fn, "attr", None)

        if nombre_fn == "create_index" and nodo.args:
            n = _literal(nodo.args[0])
            if isinstance(n, str):
                creados.add(n)

        if nombre_fn == "create_table" and nodo.args:
            tabla = _literal(nodo.args[0])
            if not isinstance(tabla, str):
                continue
            for arg in nodo.args[1:]:
                if not (isinstance(arg, ast.Call)
                        and getattr(arg.func, "attr", None) == "Column"):
                    continue
                col = _literal(arg.args[0]) if arg.args else None
                indexada = any(
                    kw.arg == "index" and _literal(kw.value) is True
                    for kw in arg.keywords)
                if isinstance(col, str) and indexada:
                    automaticos[_nombre_auto(tabla, col)] = f"{tabla}.{col}"

    return [f"{automaticos[n]} lleva index=True Y hay un create_index('{n}')"
            for n in sorted(set(automaticos) & creados)]


def test_ninguna_migracion_crea_el_mismo_indice_dos_veces():
    problemas: list[str] = []
    for archivo in sorted(os.listdir(VERSIONES)):
        if not archivo.endswith(".py"):
            continue
        ruta = os.path.join(VERSIONES, archivo)
        try:
            arbol = ast.parse(io.open(ruta, encoding="utf-8").read())
        except SyntaxError as e:            # una migracion que ni parsea
            problemas.append(f"{archivo}: no parsea ({e})")
            continue
        for p in _revisar(arbol):
            problemas.append(f"{archivo}: {p}")
    assert not problemas, (
        "esto tumba el arranque entero en el deploy:\n  " + "\n  ".join(problemas))


def test_el_guard_caza_el_caso_que_tumbo_la_app():
    """La 143, tal como estaba escrita cuando rompio produccion."""
    roto = ast.parse(
        "op.create_table('t',\n"
        "    sa.Column('id', sa.String(36), primary_key=True),\n"
        "    sa.Column('precierre_id', sa.String(36), nullable=False, index=True))\n"
        "op.create_index('ix_t_precierre_id', 't', ['precierre_id'])\n")
    assert _revisar(roto) == ["t.precierre_id lleva index=True Y hay un "
                              "create_index('ix_t_precierre_id')"]

    # Y no se queja de lo que si es correcto: el indice por nombre, sin
    # `index=True` en la columna.
    sano = ast.parse(
        "op.create_table('t',\n"
        "    sa.Column('precierre_id', sa.String(36), nullable=False))\n"
        "op.create_index('ix_t_precierre_id', 't', ['precierre_id'])\n")
    assert _revisar(sano) == []
