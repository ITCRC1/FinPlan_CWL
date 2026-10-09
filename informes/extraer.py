# -*- coding: utf-8 -*-
"""Guarda el corte del mes desde produccion. SOLO LECTURA.

    python informes/extraer.py --anio 2026 --mes 10

Es el mismo codigo que corre el boton de la aplicacion
(`app/informes/extraccion.py`): dos extracciones distintas serian dos verdades
para el mismo mes. Lo unico que agrega este script es guardarlo en disco, para
poder rearmar el informe cuantas veces haga falta sin volver a tocar produccion.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    # La consola de Windows viene en cp1252 y los avisos llevan acentos. Sin
    # esto el script revienta al IMPRIMIR el aviso, que es el momento en que mas
    # falta hace que se lea.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ / "backend"))
os.environ.setdefault(
    "FINPLAN_PGVARS",
    str(pathlib.Path(os.environ.get("TEMP", "/tmp")) / "claude" / "pgvars.json"))

DESTINO = RAIZ / "backend" / "app" / "informes" / "datos"


async def main(anio: int, mes: int, hotel: str):
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.db import engine
    from app.informes.extraccion import comparar, extraer

    S = async_sessionmaker(engine, expire_on_commit=False)
    async with S() as db:
        out = await extraer(db, anio, mes, hotel)
    await engine.dispose()

    print("escenarios:")
    for k, v in out["escenarios"].items():
        print(f"   {k}: {v['rotulo']}  ({v['id'][:12]})")
    print("\nCUADRE — estos numeros tienen que coincidir con la pantalla")
    for k in out["meses"]:
        f = next(x for x in out["meses"][k] if int(x["month"]) == mes)
        print(f"   {k}: planilla {f['payroll']:>13,.2f}  costo {f['cost']:>12,.2f}  "
              f"opex {f['opex']:>13,.2f}  propiedad {f['property']:>13,.2f}")
    for a in out["avisos"]:
        print("\n⚠  " + a)

    DESTINO.mkdir(parents=True, exist_ok=True)
    archivo = DESTINO / f"{anio}_{mes:02d}.json"

    # ⚠️ Lo mas importante que imprime el script. Si el mes se vuelve a subir,
    # los CUADROS se actualizan solos y el TEXTO del analisis NO. Un cuadro que
    # dice una cosa y el parrafo de al lado que dice otra es peor que no tener
    # informe, y no hay forma de notarlo leyendo.
    if archivo.exists():
        try:
            ant = json.loads(archivo.read_text(encoding="utf-8"))
        except Exception:
            ant = None
        if ant:
            cambios = comparar(ant, out, mes)
            copia = archivo.with_suffix(".anterior.json")
            copia.write_text(archivo.read_text(encoding="utf-8"), encoding="utf-8")
            if cambios:
                print("\n" + "=" * 70)
                print("CAMBIO desde la extraccion anterior - REVISAR EL TEXTO")
                print("=" * 70)
                for c in cambios:
                    print("   " + c)
                print("\n   Los cuadros ya salen con los numeros nuevos. Las cifras")
                print(f"   escritas en narrativa/n{anio}_{mes:02d}.py NO se actualizan")
                print("   solas: hay que repasar los parrafos que mencionen lo de "
                      "arriba.")
                print(f"\n   La extraccion anterior quedo en {copia.name}")
            else:
                print("\nSin cambios contra la extraccion anterior: el informe sale "
                      "igual.")

    archivo.write_text(json.dumps(out, ensure_ascii=False, default=str),
                       encoding="utf-8")
    print(f"\nguardado: {archivo}")
    print(f"   {len(out['mayor']):,} lineas de mayor · "
          f"{sum(len(v) for v in out['lineas'].values())} lineas de checkbook")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--anio", type=int, required=True)
    ap.add_argument("--mes", type=int, required=True)
    ap.add_argument("--hotel", default=None)
    a = ap.parse_args()
    asyncio.run(main(a.anio, a.mes, a.hotel))
