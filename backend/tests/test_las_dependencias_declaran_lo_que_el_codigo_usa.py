# -*- coding: utf-8 -*-
"""Lo que el codigo importa tiene que estar declarado, no llegar de rebote.

2026-09-30: el backend entero devolvia 502 y el login decia «Failed to fetch».
No era CORS ni el modulo nuevo — era esto:

    ModuleNotFoundError: No module named 'greenlet'
    ImportError: The SQLAlchemy asyncio module requires that the Python
    'greenlet' library is installed.

`requirements.txt` pedia `sqlalchemy>=2.0.0` a secas. `greenlet` llegaba de
rebote como dependencia transitoria; el dia que un build la resolvio sin el,
`alembic/env.py` reventó en su primera linea. Y como el Procfile encadena con
`&&`, uvicorn NUNCA arranco.

Lo peligroso es que el commit de ese dia no habia tocado `requirements.txt`:
basta con que se reinstalen las dependencias. Un pin abierto es una bomba con
temporizador que arranca sola.
"""
import io
import pathlib
import re

BACKEND = pathlib.Path(__file__).resolve().parents[1]
REQS = BACKEND / "requirements.txt"


def _requerimientos() -> str:
    return "".join(l for l in io.open(REQS, encoding="utf-8")
                   if not l.lstrip().startswith("#")).lower()


def test_sqlalchemy_pide_el_extra_asyncio():
    """El backend es async de punta a punta: el extra no es opcional."""
    req = _requerimientos()
    tiene_extra = re.search(r"sqlalchemy\[[^\]]*asyncio[^\]]*\]", req)
    tiene_greenlet = re.search(r"^\s*greenlet\b", req, re.M)
    assert tiene_extra or tiene_greenlet, (
        "requirements.txt pide sqlalchemy sin el extra `asyncio` y sin greenlet.\n"
        "`sqlalchemy.ext.asyncio` no importa sin greenlet, y `alembic/env.py` lo\n"
        "usa al arrancar: el deploy muere antes de uvicorn y todo devuelve 502.\n"
        "Poner `sqlalchemy[asyncio]>=...`.")


def test_el_codigo_de_verdad_usa_el_asyncio_de_sqlalchemy():
    """Si esto dejara de ser cierto, la prueba de arriba sobra — y hay que
    borrarla, no arrastrarla."""
    env = io.open(BACKEND / "alembic" / "env.py", encoding="utf-8").read()
    assert "sqlalchemy.ext.asyncio" in env, env[:400]
