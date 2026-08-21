# -*- coding: utf-8 -*-
"""Saca TODO el dato de la base a CSV, una tabla por archivo.

    python -m scripts.exportar_base                    # a ./export_base/
    python -m scripts.exportar_base --destino C:/ruta

**Por qué no es `pg_dump` (owner, 2026-08-20).** Hace falta llevarse la base a
una máquina sin internet, y `pg_dump` **se niega a leer un servidor más nuevo
que él**: el de Railway es PostgreSQL 18 y el instalado acá es 16. Bajar el
binario de 18 resolvería el síntoma y dejaría el problema: dentro de un año, con
Postgres 19, el respaldo vuelve a fallar el día que se necesita.

Este camino no depende de la versión de nadie porque **no lleva el esquema**: el
esquema lo construye `alembic upgrade head`, que es exactamente como se levanta
producción en cada despliegue. Lo único que hay que rescatar es el dato.

**Lo que se lleva y lo que no.**
`--sin-usuarios` deja afuera la tabla `users`. Son nueve personas reales con su
correo y el hash de su clave: una entrega a otra máquina o a otra persona va sin
ellas, y el sistema pide crear su primer admin al abrir. Para un respaldo de la
propia instalación se llevan, que es el default.

⚠️ **El manifiesto no es decoración.** Guarda la cuenta de filas de cada tabla y
la migración en que quedó la base. Sin él, un archivo truncado se restaura sin
dar error y la instalación nueva arranca con menos dato del que cree tener —
que es la forma en que este proyecto ya perdió estructura antes.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

#: Tablas que nunca se llevan: las recrea el propio destino.
NUNCA = {"alembic_version"}


async def _tablas(conn) -> list[str]:
    filas = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
        "ORDER BY tablename")
    return [f["tablename"] for f in filas if f["tablename"] not in NUNCA]


async def exportar(destino: pathlib.Path, sin_usuarios: bool) -> dict:
    import asyncpg

    from scripts._prodenv import usar_produccion
    url = usar_produccion().replace("postgresql+asyncpg://", "postgresql://")

    datos = destino / "datos"
    datos.mkdir(parents=True, exist_ok=True)

    conn = await asyncpg.connect(url)
    try:
        version = await conn.fetchval("SELECT version()")
        migracion = await conn.fetchval("SELECT version_num FROM alembic_version")
        tablas = await _tablas(conn)
        if sin_usuarios:
            tablas = [t for t in tablas if t != "users"]

        manifiesto = {"migracion": migracion, "servidor": version,
                      "sin_usuarios": sin_usuarios, "tablas": {}}
        total = 0
        for t in tablas:
            archivo = datos / f"{t}.csv"
            # `format csv` con encabezado: las columnas se aparean por NOMBRE al
            # restaurar. Por posición, una columna agregada en el medio por una
            # migración movería todos los valores una casilla — en silencio.
            await conn.copy_from_table(t, output=str(archivo),
                                       format="csv", header=True)
            n = await conn.fetchval(f'SELECT count(*) FROM "{t}"')
            manifiesto["tablas"][t] = n
            total += n
            print(f"  {t:38} {n:>8,}")
        manifiesto["total_filas"] = total
    finally:
        await conn.close()

    (destino / "manifiesto.json").write_text(
        json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(manifiesto['tablas'])} tablas · {total:,} filas · "
          f"migración {migracion}")
    print(f"→ {destino}")
    return manifiesto


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--destino", default="export_base")
    p.add_argument("--sin-usuarios", action="store_true",
                   help="deja afuera la tabla `users` (entrega a terceros)")
    a = p.parse_args()
    asyncio.run(exportar(pathlib.Path(a.destino).resolve(), a.sin_usuarios))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
