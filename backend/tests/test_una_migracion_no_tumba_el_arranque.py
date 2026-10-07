# -*- coding: utf-8 -*-
"""Un default de texto en una columna numerica tumba el arranque, y SQLite no lo ve.

**Lo que paso (owner, 2026-10-07).** La migracion 152 recorria una sola lista de
columnas y les ponia `server_default=""` a todas. Dos de ellas —`anio` y `mes`—
son `Integer`. En PostgreSQL:

    ERROR: column "anio" is of type integer but default expression is of type text

El `Procfile` corre `alembic upgrade head` ANTES de levantar uvicorn, asi que la
migracion que falla no deja arrancar la app: **el backend quedo en 502**.

En SQLite pasa sin chistar —tipado flojo— asi que la suite entera quedo en verde
y el ensayo local tambien. Es la **tercera** vez que una migracion pasa las
pruebas y tumba el arranque, y la causa es siempre la misma: lo que se prueba en
SQLite no prueba PostgreSQL.

## Que vigila esta prueba, y que no

Compila el DDL contra el **dialecto de PostgreSQL** —sin base, solo el
compilador— y rechaza un `server_default` de texto en una columna que no es de
texto. Eso es exactamente lo que fallo.

⚠️ **No reemplaza correr las migraciones contra PostgreSQL de verdad.** Hay
formas de tumbar el arranque que esto no ve: un indice sobre una columna que no
existe, un `ALTER` sobre una tabla con datos que viola una restriccion. Para eso
hace falta la base, y sin ella esas pruebas se saltan. Lo que esta prueba cierra
es el agujero por el que ya se cayo tres veces.
"""
import pathlib
import re

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

BASE = pathlib.Path(__file__).resolve().parents[1]

#: Los tipos cuyo default NO puede ser una cadena que no sea un numero.
#: `Numeric` queda fuera a proposito: PostgreSQL castea `DEFAULT '0'` a numeric
#: sin problema, y es lo que ya hacen varias migraciones que arrancan bien.
NO_TEXTO = (sa.Integer, sa.BigInteger, sa.SmallInteger, sa.Boolean,
            sa.Date, sa.DateTime, sa.Time)


#: Lo que SI es un default valido para una columna que no es de texto. Esta
#: lista existe para que la prueba no avise de mas: `DEFAULT now()` y
#: `DEFAULT false` son correctos en PostgreSQL, y una prueba que los marca se
#: termina apagando — apagada no sirve de nada.
_VALE = re.compile(
    r"^(-?\d+(\.\d+)?"            # un numero: 0, -1, 0.00
    r"|true|false|null"             # literales
    r"|current_date|current_time(stamp)?|localtime(stamp)?"
    r"|.*\(.*\)"                   # una expresion: now(), gen_random_uuid()
    r")$", re.I)


def _defaults_sospechosos(tabla) -> list[str]:
    """Columnas cuyo `server_default` PostgreSQL no acepta para su tipo.

    ⚠️ El caso que importa es el **texto vacio en una columna numerica**, que es
    lo que tumbo el arranque. Lo demas se deja pasar a proposito: ver `_VALE`.
    """
    malas = []
    for c in tabla.columns:
        sd = c.server_default
        if sd is None or not isinstance(c.type, NO_TEXTO):
            continue
        texto = getattr(getattr(sd, "arg", None), "text", None) or str(
            getattr(sd, "arg", ""))
        texto = texto.strip().strip("'").strip()
        if not _VALE.match(texto):
            malas.append(f"{tabla.name}.{c.name} ({c.type}) default {texto!r}")
    return malas


def test_la_152_compila_contra_postgresql():
    """La migracion del dia que se cayo, con sus listas de columnas.

    Se importan las listas del modulo —`TEXTO`, `ENTERO`, `NUM`— y se compila la
    tabla. Si alguien vuelve a meter `anio` en la lista de texto, esto se cae.
    """
    import importlib.util

    ruta = next(BASE.glob("alembic/versions/152_*.py"))
    spec = importlib.util.spec_from_file_location("m152", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    cols = [sa.Column("id", sa.String(36), primary_key=True)]
    for nombre, tipo in m.TEXTO:
        cols.append(sa.Column(nombre, tipo, nullable=False, server_default=""))
    for nombre, tipo in m.ENTERO:
        cols.append(sa.Column(nombre, tipo, nullable=False))
    for nombre, tipo in m.NUM:
        cols.append(sa.Column(nombre, tipo, nullable=False, server_default="0"))
    md = sa.MetaData()
    t = sa.Table("mayor_movimientos_previos", md, *cols)

    assert not _defaults_sospechosos(t)
    ddl = str(CreateTable(t).compile(dialect=postgresql.dialect()))
    # El caso exacto: `anio INTEGER NOT NULL`, sin default.
    assert re.search(r"anio INTEGER NOT NULL(?!\s+DEFAULT)", ddl), ddl
    assert re.search(r"mes INTEGER NOT NULL(?!\s+DEFAULT)", ddl), ddl


def test_ningun_modelo_tiene_un_default_de_texto_en_columna_numerica():
    """Lo mismo, del lado de los modelos — que es de donde salen las migraciones.

    ⚠️ Importar la app es parte de lo que se prueba: sin ella el registro de
    modelos esta vacio y la prueba pasaria mirando nada.
    """
    from app.db import Base
    from app.main import app  # noqa: F401

    tablas = list(Base.metadata.tables.values())
    assert len(tablas) > 40, f"solo {len(tablas)} tablas: la app no se importo"
    malas = [x for t in tablas for x in _defaults_sospechosos(t)]
    assert not malas, (
        "Estas columnas llevan un default que PostgreSQL no acepta para su "
        "tipo. En SQLite pasa; en el arranque de Railway, no:\n  "
        + "\n  ".join(malas))


def test_todos_los_modelos_compilan_contra_postgresql():
    """Que el DDL de cada tabla se pueda generar para PostgreSQL.

    No prueba que el ALTER corra contra los datos de produccion — eso necesita
    la base— pero si caza un tipo o un default que el dialecto rechaza.
    """
    from app.db import Base
    from app.main import app  # noqa: F401

    dialecto = postgresql.dialect()
    fallan = []
    for t in Base.metadata.tables.values():
        try:
            str(CreateTable(t).compile(dialect=dialecto))
        except Exception as e:                           # noqa: BLE001
            fallan.append(f"{t.name}: {e}")
    assert not fallan, "\n  ".join(fallan)


@pytest.mark.parametrize("tipo,default,vale", [
    (sa.Integer, "", False),
    (sa.Integer, "0", True),
    (sa.Boolean, "", False),
    (sa.DateTime, "", False),
    (sa.String(10), "", True),       # el texto si acepta la cadena vacia
    (sa.Numeric(18, 4), "0", True),  # PostgreSQL castea esto
    # Los que antes daban falso positivo y son correctos:
    (sa.DateTime, "now()", True),
    (sa.Boolean, "false", True),
    (sa.DateTime, "CURRENT_TIMESTAMP", True),
    (sa.Integer, "basura", False),
])
def test_el_detector_distingue_bien(tipo, default, vale):
    """Que la prueba de arriba no avise de mas ni de menos.

    Una prueba que avisa de mas se termina apagando, y apagada no sirve.
    """
    md = sa.MetaData()
    t = sa.Table("x", md, sa.Column("c", tipo, server_default=default))
    assert bool(_defaults_sospechosos(t)) is (not vale)
