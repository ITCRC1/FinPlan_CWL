"""los nombres dicen qué es cada departamento (tiendas y spa)

No eran duplicados: es una estructura deliberada que los nombres escondían.

**Tiendas** — son DOS locales distintos que se dejan abiertos a propósito
(owner, 2026-08-11): `0151` Tienda y `0165` Gift Shop. El nombre de 0151 era
«Tienda / Gift Shop», que se leía como si los dos fueran lo mismo, y encima se
quedaba con los DOS alias del importador — una línea del GL que dijera «gift
shop» habría aterrizado en la tienda equivocada el día que el importador
empiece a leer `name_aliases`. Cada uno se queda con el suyo.

**Spa** — sigue la misma regla que todo el sistema: la madre lleva el gasto y
los hijos llevan la planilla. `0140` acepta el OPEX, `0132` es la planilla y
`0130` estaba pensado para gerencia y hoy no se usa. Se le marca «(gerencia)»
para que nadie lo confunda con el que recibe los gastos.

El alias 'spa' lo tenían 0130 y 0140 a la vez; queda solo en 0140, que es el que
recibe el gasto.

Revision ID: 091
Revises: 090
"""
from alembic import op
import sqlalchemy as sa

revision = "091"
down_revision = "090"
branch_labels = None
depends_on = None

# (dept_code, nombre nuevo, name_en, alias nuevos, nombre anterior para revertir)
CAMBIOS = [
    ("0151", "Tienda", "Store", ["tienda"], "Tienda / Gift Shop"),
    ("0165", "Gift Shop", "Gift Shop", ["gift", "gift shop"], "Retail"),
    ("0130", "Spa (gerencia)", "Spa (management)", None, "Spa"),
]
ALIAS_PREVIOS = {
    "0151": ["gift", "tienda"],
    "0165": None,
    "0130": ["spa"],
}


def upgrade() -> None:
    import json
    for code, nombre, en, alias, _antes in CAMBIOS:
        # CAST(... AS json) y no `:a::json`: el `::` del cast confunde al
        # parser de parámetros de SQLAlchemy, que lee `:a:` como el nombre.
        op.execute(sa.text(
            "UPDATE department_catalog SET dept_name = :n, name_en = :e, "
            "name_aliases = CAST(:a AS json) WHERE dept_code = :c"
        ).bindparams(c=code, n=nombre, e=en,
                     a=(None if alias is None else json.dumps(alias))))


def downgrade() -> None:
    import json
    for code, _n, _e, _a, antes in CAMBIOS:
        prev = ALIAS_PREVIOS.get(code)
        op.execute(sa.text(
            "UPDATE department_catalog SET dept_name = :n, name_en = '', "
            "name_aliases = CAST(:a AS json) WHERE dept_code = :c"
        ).bindparams(c=code, n=antes,
                     a=(None if prev is None else json.dumps(prev))))
