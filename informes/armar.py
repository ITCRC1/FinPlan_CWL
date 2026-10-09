# -*- coding: utf-8 -*-
"""Arma el informe operativo en Word desde la linea de comandos.

    python informes/armar.py --anio 2026 --mes 10

Un solo comando: si falta el corte del mes lo extrae de produccion. La segunda
corrida NO vuelve a tocar produccion —usa el corte guardado—, que es lo que uno
quiere al reescribir un comentario. Para forzar una lectura nueva, `--extraer`.

Es el mismo armador que usa el boton de la aplicacion
(`app/informes/armador.py`). Lo unico que agrega este script es guardar el
archivo y escribir el cuadre en pantalla.
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ / "backend"))

CORTES = RAIZ / "backend" / "app" / "informes" / "datos"
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"]


def main(anio: int, mes: int, salida: str | None, extraer: bool):
    corte = CORTES / f"{anio}_{mes:02d}.json"
    if extraer or not corte.exists():
        print(f"Extrayendo {anio}-{mes:02d} de produccion...")
        r = subprocess.run([sys.executable, str(AQUI / "extraer.py"),
                            "--anio", str(anio), "--mes", str(mes)])
        if r.returncode != 0:
            raise SystemExit(r.returncode)
        print()

    from app.informes.armador import armar, cuadre
    from app.informes.datos import Datos

    D = Datos(anio, mes)
    doc, faltantes = armar(D)
    destino = pathlib.Path(salida) if salida else (
        AQUI / f"CWL_Informe_Operativo_{MESES[mes-1]}_{anio}.docx")
    doc.save(destino)
    print(f"guardado: {destino}")
    print(f"   {len(doc.tables)} cuadros · {len(doc.paragraphs)} parrafos")

    c = cuadre(D)
    print("\nCUADRE contra la pantalla Month-End Close — P&L:")
    for e in c["escenarios"]:
        print(f"   {e['clave']} {e['rotulo']:26s} ingreso {e['ingreso']:>12,.2f}  "
              f"gasto {e['gasto']:>12,.2f}  GOP {e['gop']:>13,.2f}")
    print("")
    print(f"   GOP reporte - GOP motor: {c['diferencia']:>13,.2f}  "
          f"({'coincide' if c['cuadra'] else 'NO COINCIDE'})")
    if not c["cuadra"]:
        print(f"      {c['motivo']}")
        print("      NO se publica el informe hasta entenderlo.")
    if abs(c["credito_allocation"]) > 0.005:
        print(f"   credito de reparto 4999 del mes: "
              f"{c['credito_allocation']:>13,.2f}  (entra al reporte)")

    if faltantes:
        print(f"\n⚠  Faltan {len(faltantes)} claves de narrativa:")
        for k in faltantes:
            print(f"     {k}")
        print(f"\n   Se escriben en "
              f"backend/app/seed_data/<HOTEL>/informes/{anio}_{mes:02d}.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--anio", type=int, required=True)
    ap.add_argument("--mes", type=int, required=True)
    ap.add_argument("--salida", default=None)
    ap.add_argument("--extraer", action="store_true",
                    help="vuelve a leer produccion aunque el corte ya exista")
    a = ap.parse_args()
    main(a.anio, a.mes, a.salida, a.extraer)
