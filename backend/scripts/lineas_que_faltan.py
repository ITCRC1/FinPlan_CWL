# -*- coding: utf-8 -*-
"""SOLO LECTURA. Que linea obligatoria dejo en cero cada escenario.

Es el reporte que contesta la pregunta del owner: **que tengo que cargar y en
que orden**. La lista de lineas obligatorias vive en
`app/seed_data/lineas_obligatorias.json`; el porque, en
`app/engine/lineas_obligatorias.py`.

No escribe nada. Calcula el P&L de cada escenario con el motor de hoy —no lee
`pl_lines`, que esta vacio o viejo en 6 de los 20 escenarios de produccion— y
respeta el corte del rolling forecast.

    python -m scripts.lineas_que_faltan                # todos
    python -m scripts.lineas_que_faltan --anio 2027    # solo un ano
    python -m scripts.lineas_que_faltan --detalle      # lista linea por linea
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                          # noqa: BLE001
    pass


def _arg(nombre: str) -> str | None:
    if nombre in sys.argv:
        i = sys.argv.index(nombre)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return None


async def main() -> None:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from app.api.pl_api import _monthly_results
    from app.engine import lineas_obligatorias as obligatorias

    anio = _arg("--anio")
    detalle = "--detalle" in sys.argv
    cfg = obligatorias.lista()
    if not cfg["lineas"]:
        raise SystemExit("No hay lista de lineas obligatorias en el repo.")

    print("=" * 104)
    print(f"LINEAS OBLIGATORIAS — {len(cfg['lineas'])} lineas, lista del {cfg.get('generado','?')}")
    for r in cfg.get("criterio", {}).get("regla", []):
        print(f"  {r}")
    print("=" * 104)

    async with SessionLocal() as db:
        escs = (await db.execute(select(Scenario))).scalars().all()
        if anio:
            escs = [e for e in escs if e.year == int(anio)]
        escs.sort(key=lambda s: (s.year, s.type, s.version))

        vacios, resumen = [], []
        for e in escs:
            etiqueta = f"{e.type} {e.version} {e.year}"
            try:
                por_mes = {m["month"]: {ln.line_code: float(ln.amount_usd)
                                        for ln in m["lines"]}
                           for m in await _monthly_results(db, e)}
            except Exception as ex:                        # noqa: BLE001
                print(f"  !! {etiqueta}: {str(ex)[:80]}")
                continue
            rep = obligatorias.revisar(por_mes, e.type, e.actuals_through)
            if rep["vacio"]:
                vacios.append(etiqueta)
                continue
            resumen.append((etiqueta, rep))

        print(f"\n{'escenario':<26}{'faltan':>8}{'vale en el historico':>24}   primeras lineas")
        print("-" * 104)
        for etiqueta, rep in sorted(resumen, key=lambda x: -x[1]["magnitud_historica_usd"]):
            top = ", ".join(f["line_code"] for f in rep["faltan"][:3]) or "—"
            print(f"{etiqueta:<26}{rep['cuantas_faltan']:>4}/{rep['obligatorias']:<3}"
                  f"{rep['magnitud_historica_usd']:>24,.0f}   {top}")

        if vacios:
            print(f"\nESCENARIOS VACIOS ({len(vacios)}) — no les falta una linea, "
                  "les falta todo. No son agujeros: estan sin empezar.")
            for v in vacios:
                print(f"  · {v}")

        if detalle:
            for etiqueta, rep in sorted(resumen, key=lambda x: -x[1]["magnitud_historica_usd"]):
                print("\n" + "=" * 104)
                print(obligatorias.resumen_texto(rep, etiqueta))


if __name__ == "__main__":
    asyncio.run(main())
