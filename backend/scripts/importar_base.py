# -*- coding: utf-8 -*-
"""Mete el dato exportado en una base VACÍA, y comprueba que llegó completo.

    # 1. el esquema lo hace alembic, igual que en producción
    alembic upgrade head
    # 2. el dato
    python -m scripts.importar_base --origen C:/ruta/export_base           # VERIFICA
    python -m scripts.importar_base --origen C:/ruta/export_base --aplicar # escribe

Por defecto **solo verifica**: compara el manifiesto contra los archivos y
contra la base, y dice qué haría. Una carga que empieza escribiendo no tiene
vuelta atrás.

## Las cuatro cosas que cuida

1. **Compara la migración.** Si el esquema del destino no es el mismo en que se
   sacó el dato, aborta. Una columna de diferencia no falla al copiar: entra el
   dato corrido o falta una columna entera, y el reporte cuadra igual.
2. **Todo en UNA transacción.** O entra completo o no entra nada. Un import a
   medias deja la instalación con parte del dato y sin nada que lo diga.
3. **Apaga las llaves foráneas mientras copia**, así el orden de las tablas no
   importa. Si el motor no lo permite (hace falta ser dueño de la base), pasa
   solo a las que puede y repite hasta que no avance más — y si algo queda
   afuera, lo dice por nombre en vez de darlo por bueno.
4. **Cuenta al final, tabla por tabla, contra el manifiesto.** Copiar sin error
   no prueba que llegó todo: un CSV truncado se copia perfecto.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))


async def importar(origen: pathlib.Path, aplicar: bool, url: str | None) -> int:
    import asyncpg

    manifiesto = json.loads((origen / "manifiesto.json").read_text(encoding="utf-8"))
    datos = origen / "datos"

    faltan = [t for t in manifiesto["tablas"] if not (datos / f"{t}.csv").exists()]
    if faltan:
        print(f"ABORTA: el paquete dice traer {len(manifiesto['tablas'])} tablas "
              f"y estos archivos no están: {faltan[:8]}")
        return 1

    if url is None:
        import os

        # ⚠️ El `.env` hay que cargarlo A MANO acá. `app/db.py` y `alembic/env.py`
        # llaman a `load_dotenv()` al importarse, pero este script no importa
        # ninguno de los dos —habla directo con asyncpg— así que sin esto la
        # variable del archivo no existe y el paso falla con «falta
        # DATABASE_URL» justo cuando la persona SÍ la escribió. Lo encontró
        # probar la guía paso por paso antes de entregarla.
        from dotenv import load_dotenv
        load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")
        url = os.environ.get("DATABASE_URL", "")
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    if not url:
        print("ABORTA: falta DATABASE_URL (o --url) con la base DESTINO.")
        return 1

    conn = await asyncpg.connect(url)
    try:
        destino_mig = await conn.fetchval(
            "SELECT version_num FROM alembic_version")
        print(f"esquema del destino: {destino_mig} · del paquete: "
              f"{manifiesto['migracion']}")
        if destino_mig != manifiesto["migracion"]:
            print("ABORTA: el esquema no coincide. Correr `alembic upgrade head` "
                  "con ESTE código antes de importar.")
            return 1

        ya = {}
        for t in manifiesto["tablas"]:
            ya[t] = await conn.fetchval(f'SELECT count(*) FROM "{t}"')
        con_dato = {t: n for t, n in ya.items() if n}
        print(f"tablas en el paquete: {len(manifiesto['tablas'])} · "
              f"filas a cargar: {manifiesto['total_filas']:,}")
        if con_dato:
            print(f"⚠️  el destino NO está vacío: {len(con_dato)} tablas con dato "
                  f"({sum(con_dato.values()):,} filas). Se REEMPLAZAN.")

        if not aplicar:
            print("\nVERIFICACIÓN: no se escribió nada. Correr con --aplicar.")
            return 0

        async with conn.transaction():
            # Sin llaves foráneas activas el orden deja de importar. Si el motor
            # no lo permite, se cae acá y lo dice — no sigue a ciegas.
            sin_llaves = True
            try:
                await conn.execute("SET session_replication_role = replica")
            except Exception as e:
                sin_llaves = False
                print(f"  (sin permiso para apagar las llaves foráneas: {e})")

            pendientes = list(manifiesto["tablas"])
            for t in reversed(pendientes):
                await conn.execute(f'DELETE FROM "{t}"')

            while pendientes:
                quedaron = []
                for t in pendientes:
                    try:
                        await conn.copy_to_table(
                            t, source=str(datos / f"{t}.csv"),
                            format="csv", header=True)
                    except Exception as e:
                        if sin_llaves:
                            raise
                        quedaron.append((t, e))
                if not quedaron:
                    break
                if len(quedaron) == len(pendientes):
                    print("ABORTA: estas tablas no pudieron entrar en ningún "
                          "orden:")
                    for t, e in quedaron[:5]:
                        print(f"   {t}: {e}")
                    raise RuntimeError("dependencias irresolubles")
                pendientes = [t for t, _ in quedaron]

            if sin_llaves:
                await conn.execute("SET session_replication_role = origin")

        # ── Contar, que es lo único que prueba que llegó ──────────────────
        malas = []
        for t, esperado in manifiesto["tablas"].items():
            hay = await conn.fetchval(f'SELECT count(*) FROM "{t}"')
            if hay != esperado:
                malas.append(f"{t}: {hay:,} de {esperado:,}")
        if malas:
            print("\n❌ El dato entró INCOMPLETO:")
            for m in malas:
                print("   ", m)
            return 1
        print(f"\n✓ {len(manifiesto['tablas'])} tablas · "
              f"{manifiesto['total_filas']:,} filas, contadas una por una.")
        if manifiesto.get("sin_usuarios"):
            print("  El paquete vino SIN usuarios: la app va a pedir crear el "
                  "primer admin al abrirla.")
        return 0
    finally:
        await conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--origen", required=True)
    p.add_argument("--url", default=None,
                   help="base DESTINO; si no, se usa DATABASE_URL")
    p.add_argument("--aplicar", action="store_true")
    a = p.parse_args()
    return asyncio.run(importar(pathlib.Path(a.origen).resolve(), a.aplicar, a.url))


if __name__ == "__main__":
    raise SystemExit(main())
