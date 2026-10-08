# -*- coding: utf-8 -*-
"""Arma el informe operativo en Word.

    python informes/generador/armar.py --anio 2026 --mes 10

Requiere que `extraer.py` ya haya corrido para ese mes. La narrativa se busca en
`narrativa/n{anio}_{mes}.py`; si no existe, el informe sale con los cuadros
completos y marcas «[PENDIENTE: clave]» donde falta el analisis, y al final
imprime la lista de lo que falta. Un informe con huecos visibles es util; uno al
que le faltan secciones sin avisar, no.
"""
from __future__ import annotations

import argparse
import importlib
import pathlib
import sys

# La consola de Windows viene en cp1252 y los avisos llevan acentos y
# simbolos. Sin esto el script revienta al IMPRIMIR el aviso, que es el
# momento en que mas falta hace que se lea.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

AQUI = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from datos import Datos                                      # noqa: E402
from formato import doc_nuevo                                # noqa: E402
import secciones as S1                                       # noqa: E402
import secciones2 as S2                                      # noqa: E402


def cargar_narrativa(anio: int, mes: int) -> dict:
    nombre = f"narrativa.n{anio}_{mes:02d}"
    try:
        mod = importlib.import_module(nombre)
    except ModuleNotFoundError:
        print(f"⚠  No hay narrativa para {anio}-{mes:02d} "
              f"({nombre.replace('.', '/')}.py).")
        print("   El informe sale con los cuadros y marcas [PENDIENTE] en el texto.")
        return {}
    return getattr(mod, "NARRATIVA", {})


def main(anio: int, mes: int, salida: str | None):
    D = Datos(anio, mes)
    nar = cargar_narrativa(anio, mes)
    agg = D.mayor()

    d = doc_nuevo()
    S1.portada(d, D, nar)
    S1.indice(d, D)
    d.add_page_break()
    S1.seccion1(d, D, nar)
    d.add_page_break()
    S1.seccion2(d, D, nar)
    d.add_page_break()
    S1.seccion3(d, D, nar)
    d.add_page_break()
    S2.seccion4(d, D, agg, nar)
    d.add_page_break()
    S2.seccion5(d, D, agg, nar)
    d.add_page_break()
    S2.seccion6(d, D, nar)
    d.add_page_break()
    S2.seccion7(d, D, nar)
    d.add_page_break()
    S2.seccion8(d, D, nar)
    S2.seccion9(d, D, nar)
    d.add_page_break()
    S2.seccion10(d, D, nar)
    d.add_page_break()
    S2.seccion11(d, D, nar)
    d.add_page_break()
    S2.seccion12(d, D, nar)

    mes_es = D.mes_nombre.capitalize()
    destino = pathlib.Path(salida) if salida else (
        AQUI.parent / f"CWL_Informe_Operativo_{mes_es}_{anio}.docx")
    d.save(destino)
    print(f"\nguardado: {destino}")
    print(f"   {len(d.tables)} cuadros · {len(d.paragraphs)} parrafos")

    # ── el cuadre, impreso siempre ────────────────────────────────────────
    print("\nCUADRE contra la pantalla Month-End Close — P&L:")
    for e in D.escs:
        print(f"   {e} {D.rotulo(e):26s} ingreso {D.total(e,'revenue'):>12,.2f}  "
              f"gasto {D.tot_gasto(e):>12,.2f}  GOP {D.gop(e):>13,.2f}")
    cred = sum(D.creditos_allocation().values())
    if abs(cred) > 0.005:
        mot = D.pl("ACT", "GOP") or D.pl("ACT", "TOTAL_GOP")
        dif = D.gop("ACT") - mot
        ok = "coincide" if abs(dif - cred) < 0.02 else "⚠ NO COINCIDE — investigar"
        print(f"\n   credito 4999 descartado por el reporte: {cred:>13,.2f}")
        print(f"   GOP reporte - GOP motor:                {dif:>13,.2f}  ({ok})")

    if S1.FALTANTES:
        print(f"\n⚠  Faltan {len(set(S1.FALTANTES))} claves de narrativa:")
        for k in sorted(set(S1.FALTANTES)):
            print(f"     {k}")
        print("\n   Se escriben en "
              f"informes/generador/narrativa/n{anio}_{mes:02d}.py")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--anio", type=int, required=True)
    ap.add_argument("--mes", type=int, required=True)
    ap.add_argument("--salida", default=None)
    a = ap.parse_args()
    main(a.anio, a.mes, a.salida)
