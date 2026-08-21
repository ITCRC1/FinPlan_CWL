# -*- coding: utf-8 -*-
"""Arma `app/seed_data/lineas_obligatorias.json` desde el HISTORICO. SOLO LECTURA.

## Que es la lista

Las lineas del P&L que un escenario **tiene que traer con dato** para que
comparar contra el historico signifique algo. Si `OH_UTILITIES` esta en cero, el
GOP del 2027 no es mejor que el del 2025: es un GOP al que le falta la luz.

## Es una LISTA, no una regla

Igual que `orden_plantilla.json`. La regla de abajo **produjo** la lista una vez,
el 2026-08-16; despues la lista manda. Se queda en un archivo del repo para que
el owner la abra, borre lo que no aplica y agregue lo que sabe que va — sin
tocar codigo y sin que nadie tenga que adivinar el criterio despues.

Un criterio automatico corriendo en vivo se rompe solo: el ano que el hotel deje
de vender tours, «Tours esta en cero» pasaria de aviso legitimo a ruido eterno.

## El criterio con que se produjo (2026-08-16)

Una linea entra si cumple las tres:

1. **Es una linea donde ENTRA dato** — `line_type` MAPPED o MAPPED_REVIEW en
   `mapping_pl.json`. Las CALCULATED salen de sumar a las otras: avisar de
   `TOTAL_DEPRECIATIONS` en vez de `DEPRECIATION` le dice al owner que algo
   falta pero no donde cargarlo.
2. **Es recurrente** — al menos `UMBRAL` dolares al ano en 2 o mas de los anos
   ACTUAL cargados. Un gasto de un solo ano no es una obligacion.
3. **Sigue viva** — distinta de cero en el ACTUAL mas reciente con dato. Esto es
   lo que deja afuera a Innoceana: 141k en 2024, 150k en 2025 y **cero en 2026**
   porque el proyecto termino. Sin este filtro, cada escenario nuevo arrastraria
   para siempre el aviso de una linea que ya no existe.

## Lo que el criterio NO decide

El monto de referencia se guarda **por ano**, no promediado. El owner necesita
el orden de magnitud para saber que cargar primero, y un promedio entre un ano
completo y uno a medio cargar no es un orden de magnitud, es un numero inventado.

    python -m scripts.generar_lineas_obligatorias          # escribe el JSON
    python -m scripts.generar_lineas_obligatorias --ver     # solo muestra
"""
from __future__ import annotations

import asyncio
import collections
import datetime
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                          # noqa: BLE001
    pass

#: Un ano de linea por debajo de esto no obliga a nada. Es plata que cabe en el
#: redondeo de cualquier decision del owner.
UMBRAL = 5_000.0

DESTINO = pathlib.Path(__file__).resolve().parents[1] / "app" / "seed_data" / "lineas_obligatorias.json"
MAPEO = pathlib.Path(__file__).resolve().parents[1] / "app" / "seed_data" / "mapping_pl.json"

#: `source_origin` del mapeo -> donde se carga, en el vocabulario del owner.
#: Sale del mapeo, no de una tabla escrita a mano, para que no envejezca.
DONDE = {
    "Revenue": ("Ingresos", "/revenue"),
    "Revenue-Food": ("Ingresos", "/revenue"),
    "Revenue-Beverage": ("Ingresos", "/revenue"),
    "Revenue-Miscellaneus": ("Ingresos", "/revenue"),
    "Cost": ("Costos", "/costs"),
    "Food Cost": ("Costos", "/costs"),
    "Beverage Cost": ("Costos", "/costs"),
    "Miscellaneous Cost": ("Costos", "/costs"),
    "Opex": ("OPEX", "/opex"),
    "OpEx": ("OPEX", "/opex"),
    "Operating Expense": ("OPEX", "/opex"),
    "Payroll": ("Planilla", "/payroll"),
    "PAYROLL": ("Planilla", "/payroll"),
    "Below GOP": ("Below GOP / No operativo", "/nonop"),
    "Owners Fees": ("Below GOP / No operativo", "/nonop"),
    "Allocation": ("Repartos", "/allocations"),
    "Distribuciòn": ("Repartos", "/allocations"),
}


def _donde(origenes: list[str]) -> tuple[str, str]:
    """De donde sale la plata de esta linea, en orden de peso.

    Se devuelven **hasta dos** pantallas, no una: `OH_ADMIN` tiene 88 reglas
    repartidas entre planilla y opex, y mandar al owner solo a planilla lo
    dejaria buscando la mitad del dinero en la pantalla equivocada.
    """
    vistos: list[tuple[str, str]] = []
    for o in origenes:
        d = DONDE.get(o)
        if d and d not in vistos:
            vistos.append(d)
    if not vistos:
        return ("Checkbook", "")
    etiqueta = " · ".join(e for e, _ in vistos[:2])
    return (etiqueta, vistos[0][1])


async def main(escribir: bool) -> None:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from app.api.pl_api import _monthly_results

    mapeo = json.loads(MAPEO.read_text(encoding="utf-8"))
    rlc = {r["line_code"]: r for r in mapeo["report_line_config"] if r.get("active")}
    activas = [m for m in mapeo["account_mapping"]
               if str(m.get("active_status", "")).upper() == "YES"]
    reglas: dict[str, list[dict]] = collections.defaultdict(list)
    for m in activas:
        reglas[m["report_line_code"]].append(m)

    # ── El historico: los escenarios ACTUAL, calculados con el motor de HOY ───
    #
    # No se lee `pl_lines`. Medido el 2026-08-16 contra produccion: el ACTUAL
    # 2025 tiene CERO filas persistidas y el 2026 difiere en 72 lineas del
    # calculo vivo. Derivar la lista de ahi habria producido una lista falsa.
    por_ano: dict[int, dict[str, float]] = {}
    meses_con_dato: dict[int, int] = {}
    async with SessionLocal() as db:
        escs = [s for s in (await db.execute(select(Scenario))).scalars().all()
                if s.type == "ACTUAL"]
        for e in sorted(escs, key=lambda s: s.year):
            meses = await _monthly_results(db, e)
            tot: dict[str, float] = collections.defaultdict(float)
            con = 0
            for m in meses:
                if any(abs(float(ln.amount_usd)) > 0.005 for ln in m["lines"]):
                    con += 1
                for ln in m["lines"]:
                    tot[ln.line_code] += float(ln.amount_usd)
            por_ano[e.year] = dict(tot)
            meses_con_dato[e.year] = con
            print(f"  ACTUAL {e.year}: {con} meses con dato")

    anos = sorted(por_ano)
    if not anos:
        raise SystemExit("No hay escenarios ACTUAL: sin historico no hay lista.")
    ultimo = anos[-1]

    lineas = []
    for code, cfg in rlc.items():
        if cfg["line_type"] not in ("MAPPED", "MAPPED_REVIEW"):
            continue                                        # (1) donde entra dato
        hist = {a: round(por_ano[a].get(code, 0.0), 2) for a in anos}
        if sum(1 for v in hist.values() if abs(v) >= UMBRAL) < 2:
            continue                                        # (2) recurrente
        if abs(hist[ultimo]) < 0.005:
            continue                                        # (3) sigue viva

        # El monto de referencia sale del ultimo ano COMPLETO. Un ano a medio
        # cargar subestimaria la magnitud justo en la linea que el owner
        # necesita priorizar.
        completos = [a for a in anos if meses_con_dato[a] >= 12 and abs(hist[a]) >= 0.005]
        ref_ano = completos[-1] if completos else max(hist, key=lambda a: abs(hist[a]))

        rs = reglas.get(code, [])
        origenes = [o for o, _ in collections.Counter(
            r.get("source_origin") or "" for r in rs).most_common()]
        etiqueta, pantalla = _donde(origenes)
        lineas.append({
            "line_code": code,
            "nombre": cfg["line_name"],
            "seccion": cfg["section"],
            "donde_se_carga": etiqueta,
            "pantalla": pantalla,
            "departamentos": sorted({(r.get("dept_code") or "").strip()
                                     for r in rs if (r.get("dept_code") or "").strip()}),
            "reglas_de_mapeo": len(rs),
            "historico": {str(a): hist[a] for a in anos},
            "referencia_usd": hist[ref_ano],
            "referencia_anio": ref_ano,
        })

    lineas.sort(key=lambda L: -abs(L["referencia_usd"]))

    salida = {
        "_nota": [
            "LINEAS QUE UN ESCENARIO DEBE TRAER CON DATO para ser comparable.",
            "",
            "Es una LISTA y no una regla: se produjo una vez desde el historico",
            "(ver scripts/generar_lineas_obligatorias.py) y desde ahi manda la",
            "lista. Se puede editar a mano: borrar lo que ya no aplica, agregar",
            "lo que se sabe que va. Nadie tiene que adivinar el criterio.",
            "",
            "AVISA, NO BLOQUEA. Un presupuesto en construccion tiene lineas",
            "vacias con todo derecho; el aviso dice cuales y cuanto valen en el",
            "historico, para saber que cargar y en que orden.",
            "",
            "`referencia_usd` es el ultimo ano ACTUAL COMPLETO — no un promedio.",
            "Se regenera con `python -m scripts.generar_lineas_obligatorias`.",
        ],
        "generado": datetime.date.today().isoformat(),
        "criterio": {
            "umbral_anual_usd": UMBRAL,
            "anos_historicos": [str(a) for a in anos],
            "meses_con_dato": {str(a): meses_con_dato[a] for a in anos},
            "regla": [
                "1. line_type MAPPED o MAPPED_REVIEW (donde ENTRA el dato).",
                f"2. >= {UMBRAL:,.0f} USD/anio en 2 o mas anios ACTUAL.",
                f"3. distinta de cero en el ACTUAL mas reciente ({ultimo}).",
            ],
        },
        "lineas": lineas,
    }

    print(f"\n{len(lineas)} lineas obligatorias")
    print(f"{'line_code':<26}{'donde':<28}{'ref':>13}  " + "".join(f"{a:>12}" for a in anos))
    for L in lineas:
        print(f"{L['line_code']:<26}{L['donde_se_carga'][:27]:<28}{L['referencia_usd']:>13,.0f}  "
              + "".join(f"{L['historico'][str(a)]:>12,.0f}" for a in anos))

    if escribir:
        DESTINO.write_text(json.dumps(salida, ensure_ascii=False, indent=1),
                           encoding="utf-8")
        print(f"\n-> {DESTINO}")
    else:
        print("\n(--ver: no se escribio nada)")


if __name__ == "__main__":
    asyncio.run(main(escribir="--ver" not in sys.argv))
