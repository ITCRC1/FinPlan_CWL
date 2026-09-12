# -*- coding: utf-8 -*-
"""El borrador en revision tiene que poder ABRIRSE.

No necesita base: mide el ORDER BY del listado, que es lo que se rompio.
"""

# ── El listado, la mas nueva primero ────────────────────────────────────────
#
# Owner, 2026-09-11, con diez vueltas de agosto: los ocho chips visibles decian
# «descartado» y no habia forma de abrir el borrador vivo. La pantalla se veia
# vacia y parecia que la subida no habia entrado.
#
# La causa: `listar()` ordenaba por (anio, mes) y nada mas. Entre vueltas del
# MISMO mes el orden lo decidia Postgres, y la pantalla muestra solo las ocho
# primeras.

def test_el_listado_ordena_por_fecha_dentro_del_mes():
    """Se lee del codigo: montar diez vueltas contra una base real para medir un
    ORDER BY costaria mas de lo que protege, y lo que se rompio fue exactamente
    esta clausula."""
    import inspect
    from app.api import precierre_api

    src = inspect.getsource(precierre_api.listar)
    assert "creado_en.desc()" in src, (
        "el listado tiene que ordenar por fecha dentro del mes: sin eso el "
        "borrador vivo se cae de los ocho chips que muestra la pantalla")
    assert "Precierre.id.desc()" in src, (
        "y desempatar por id: dos vueltas del mismo segundo existen")
