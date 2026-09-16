# -*- coding: utf-8 -*-
"""Una migracion no puede nombrar una tabla que no existe.

## Lo que paso el 2026-09-15

La migracion 146 escribio `precierre_filas` y `precierre_posiciones`, en plural.
Las tablas son `precierre_fila` y `precierre_posicion`, en SINGULAR.

`op.add_column` sobre una tabla inexistente aborta `alembic upgrade head`, que
es lo PRIMERO que corre el Procfile. El backend no llego a arrancar: **502 en
produccion**, con la suite entera en verde.

Es la segunda vez que pasa la misma clase de cosa. La 143 creo un indice dos
veces y tambien tumbo el arranque (`test_migraciones_no_crean_el_indice_dos_
veces`). El patron es siempre el mismo: **nada local ejecuta el upgrade**, asi
que una migracion rota pasa todas las pruebas y se descubre cuando el servicio
no levanta.

## Como lo mira

Lee el SQL declarativo de cada migracion —`add_column`, `drop_column`,
`alter_column`, `create_index`, `create_unique_constraint`— y exige que cada
nombre de tabla ESCRITO COMO LITERAL sea una de dos cosas:

* una tabla de los modelos (`Base.metadata`), o
* una tabla que alguna migracion del repo crea con `create_table`.

Lo segundo cubre las tablas historicas que hoy ya no estan en los modelos.

Los nombres que llegan por variable (`op.add_column(t, ...)` dentro de un
bucle) NO se revisan: no hay como saber su valor sin ejecutar. Son dos en todo
el repo y se ven a ojo.
"""
import pathlib
import re

VERSIONES = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"

#: Solo literales entre comillas. `op.add_column(t, ...)` queda fuera a
#: proposito: ver el docstring.
_UNA_TABLA = re.compile(
    r'op\.(add_column|drop_column|alter_column)\(\s*["\'](\w+)["\']')
_SOBRE_TABLA = re.compile(
    r'op\.(create_index|create_unique_constraint)\(\s*["\'][^"\']*["\']\s*,\s*["\'](\w+)["\']')
_CREA = re.compile(r'op\.create_table\(\s*["\'](\w+)["\']')


def _fuentes() -> dict[str, str]:
    return {f.name: f.read_text(encoding="utf-8", errors="replace")
            for f in sorted(VERSIONES.glob("*.py"))}


def test_las_migraciones_nombran_tablas_que_existen():
    import app.models  # noqa: F401  — puebla el metadata
    from app.db import Base

    fuentes = _fuentes()
    conocidas = set(Base.metadata.tables)
    for src in fuentes.values():
        conocidas |= set(_CREA.findall(src))

    malas: dict[str, set] = {}
    for nombre, src in fuentes.items():
        usadas = {t for _op, t in _UNA_TABLA.findall(src)}
        usadas |= {t for _op, t in _SOBRE_TABLA.findall(src)}
        faltan = usadas - conocidas
        if faltan:
            malas[nombre] = faltan

    assert not malas, (
        "migraciones que tocan tablas inexistentes: "
        + "; ".join(f"{k}: {sorted(v)}" for k, v in sorted(malas.items()))
        + ". `alembic upgrade head` aborta y el backend no arranca — pasa la "
          "suite entera y devuelve 502 en produccion")


def test_el_guard_reconoce_el_error_que_tumbo_produccion():
    """La version rota de la 146 tiene que fallar este guard.

    Sin esto, el guard podria estar mirando un regex que no matchea nada y
    pasando siempre — que es la forma mas silenciosa de no proteger nada."""
    roto = 'op.add_column("precierre_filas", sa.Column("mes_crc", sa.Numeric))'
    assert _UNA_TABLA.findall(roto) == [("add_column", "precierre_filas")]

    bueno = 'op.add_column("precierre_fila", sa.Column("mes_crc", sa.Numeric))'
    assert _UNA_TABLA.findall(bueno) == [("add_column", "precierre_fila")]


def test_la_146_quedo_en_singular():
    """El caso concreto, clavado: es el que tumbo produccion."""
    src = (VERSIONES / "146_el_precierre_guarda_los_colones.py").read_text(
        encoding="utf-8", errors="replace")
    assert "precierre_filas" not in src and "precierre_posiciones" not in src
    assert 'op.add_column("precierre_fila"' in src
    assert 'op.add_column("precierre_posicion"' in src
