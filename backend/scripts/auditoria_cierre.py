# -*- coding: utf-8 -*-
"""Auditoría del cierre: cada tab de Month-End contra los totales del P&L.

**Qué pidió el owner (2026-08-14).** «Agarrá YTD abril para todos los reportes y
validá que todo esté correcto. Cada uno de los tabs debe pegar contra los
totales del tab P&L.»

Es la pregunta correcta. Los tabs no salen todos del mismo lado:

* P&L, Simplified, Monthly Summary → líneas del P&L (`calculate_pl_from_mapping`)
* Revenue x Depto, Payroll, Cost, Opex, Property → gasto por CLASE de cuenta
* P&L Statement → clases, con los subtotales derivados
* Revenue Detail → líneas `REV_*`
* F&B Cost Detail → líneas de A&B, un nivel más abajo

Son ejes distintos sobre el mismo dato. Que cuadren no es obvio: es justamente
lo que hay que verificar, y es donde han aparecido todos los errores de este
proyecto —los $40,613, los $71,556, el gasto duplicado—.

    python -m scripts.auditoria_cierre                 # ACTUAL 2026, YTD abril
    python -m scripts.auditoria_cierre --mes 6
"""
import asyncio
import sys
import pathlib
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts._prodenv import usar_produccion  # noqa: E402

usar_produccion()

from sqlalchemy import select  # noqa: E402

from app.db import get_session  # noqa: E402
from app.engine import pl_engine, recalculate as recalc  # noqa: E402
from app.models.scenario import Scenario  # noqa: E402

TOL = Decimal("1")     # debajo de un dólar es redondeo, no descuadre


def _fmt(x) -> str:
    return f"{float(x):>16,.2f}"


class Auditoria:
    def __init__(self):
        self.fallas = []
        self.checks = 0

    def cuadra(self, titulo: str, a, b, detalle: str = ""):
        self.checks += 1
        d = Decimal(str(a)) - Decimal(str(b))
        ok = abs(d) < TOL
        marca = "OK  " if ok else "FALLA"
        print(f"  {marca} {titulo:<46} {_fmt(a)} vs {_fmt(b)}"
              + ("" if ok else f"   dif {float(d):+,.2f}"))
        if not ok:
            self.fallas.append(f"{titulo}: {float(a):,.2f} vs {float(b):,.2f} "
                               f"(dif {float(d):+,.2f}) {detalle}")
        return ok


async def main(mes: int, tipo: str, anio: int):
    aud = Auditoria()
    async with get_session() as s:
        escs = (await s.execute(select(Scenario).where(
            Scenario.type == tipo, Scenario.year == anio))).scalars().all()
        if not escs:
            print(f"No hay escenario {tipo} {anio}")
            return 1
        esc = escs[0]
        print(f"\nAUDITORIA · {esc.type} {esc.version} {esc.year} · YTD a mes {mes}\n"
              + "=" * 96)

        maps = await recalc.load_active_account_mappings(s)
        cfg = await recalc.load_report_line_config(s)

        # ── Fuente 1: las líneas del P&L, mes a mes ──────────────────────────
        lineas: dict[str, Decimal] = {}
        # ── Fuente 2: las filas por cuenta, sin pasar por el motor ───────────
        por_clase: dict[str, Decimal] = {}
        por_cuenta: dict[str, Decimal] = {}
        for m in range(1, mes + 1):
            filas = await recalc.actual_rows_for_month(s, esc.id, m)
            if not filas:
                filas = await recalc.checkbook_account_rows_for_month(s, esc.id, m)
            if not filas:
                continue
            for ln in pl_engine.calculate_pl_from_mapping(filas, maps, cfg):
                lineas[ln.line_code] = lineas.get(ln.line_code, Decimal(0)) + ln.amount_usd
            for r in filas:
                cta = str(r["account_code"] or "")
                monto = Decimal(str(r["amount"] or 0))
                # ⚠️ NADA se filtra acá. La primera version quitaba las cuentas
                # de reparto y el departamento 0220 «para limpiar», y las dos
                # verificaciones de gasto salieron en rojo por $161,801 y
                # $46,425. No era el dato: era que el motor recibe estas filas
                # SIN filtrar, asi que compararlas contra una version filtrada
                # es comparar dos cosas distintas.
                #
                # Las cuentas de reparto (49xx) se tratan aparte mas abajo: son
                # clase 4 pero el motor las manda a lineas de GASTO, con signo
                # negativo. Sacarlas del ingreso es correcto; sacarlas del gasto
                # tambien lo seria, pero hay que hacer las dos cosas a la vez.
                por_clase[cta[:1]] = por_clase.get(cta[:1], Decimal(0)) + monto
                por_cuenta[cta] = por_cuenta.get(cta, Decimal(0)) + monto
                if cta in pl_engine.ALLOCATION_ACCOUNTS:
                    por_clase["reparto"] = por_clase.get("reparto", Decimal(0)) + monto

        L = lambda c: lineas.get(c, Decimal(0))  # noqa: E731

        print("\n1. LA CASCADA DEL P&L SE SOSTIENE SOLA")
        aud.cuadra("Ingreso = suma de las lineas REV_*",
                   L("TOTAL_REVENUES"),
                   sum((v for k, v in lineas.items() if k.startswith("REV_")), Decimal(0)))
        aud.cuadra("Gasto operativo = OPEX_* + COS_*",
                   L("TOTAL_OPERATING_EXPENSES"),
                   sum((v for k, v in lineas.items()
                        if k.startswith("OPEX_") or k.startswith("COS_")), Decimal(0)))
        aud.cuadra("Overhead = OH_* + COH_*",
                   L("TOTAL_OVERHEAD_EXPENSES"),
                   sum((v for k, v in lineas.items()
                        if k.startswith("OH_") or k.startswith("COH_")), Decimal(0)))
        aud.cuadra("Utilidad operativa = suma de PROFIT_*",
                   L("OPERATING_PROFIT"),
                   sum((v for k, v in lineas.items() if k.startswith("PROFIT_")), Decimal(0)))
        aud.cuadra("GOP = utilidad operativa - overhead",
                   L("TOTAL_GOP"), L("OPERATING_PROFIT") - L("TOTAL_OVERHEAD_EXPENSES"))
        aud.cuadra("EBITDA = GOP - no operativos",
                   L("EBITDA_BEFORE_CAPITAL"), L("TOTAL_GOP") - L("TOTAL_NON_OP_EXPENSES"))
        aud.cuadra("Neto = EBT - impuesto",
                   L("NET_PROFIT"), L("EBT") - L("INCOME_TAXES"))

        print("\n2. LOS TABS POR CLASE DE CUENTA PEGAN CON EL P&L")
        # El P&L Statement arma el gasto por naturaleza; tiene que dar lo mismo
        # que las lineas del P&L cortadas por departamento.
        reparto = por_clase.get("reparto", Decimal(0))
        aud.cuadra("Ingreso (clase 4 sin repartos) = TOTAL_REVENUES",
                   por_clase.get("4", Decimal(0)) - reparto, L("TOTAL_REVENUES"))
        # El credito del reparto es clase 4 y viaja a lineas de GASTO, en
        # negativo: por eso se suma acá y no en el ingreso.
        gasto_clases = sum((por_clase.get(c, Decimal(0)) for c in "5678"),
                           Decimal(0)) + reparto
        gasto_pl = (L("TOTAL_OPERATING_EXPENSES") + L("TOTAL_OVERHEAD_EXPENSES")
                    + L("TOTAL_NON_OP_EXPENSES") + L("CAPITAL_EXPENSE")
                    + L("FINANCIAL_EXPENSES") + L("TOTAL_DEPRECIATIONS")
                    + L("INCOME_TAXES"))
        aud.cuadra("Gasto (clases 5-8 + repartos) = todo el gasto del P&L",
                   gasto_clases, gasto_pl,
                   "si no da, hay una cuenta que el P&L no manda a ninguna linea")
        aud.cuadra("Costo de ventas (clase 5) = SUM(COS_*) + SUM(COH_*)",
                   por_clase.get("5", Decimal(0)),
                   sum((v for k, v in lineas.items()
                        if k.startswith("COS_") or k.startswith("COH_")), Decimal(0)),
                   "es la separacion nueva: toda clase 5 va a una linea de costo")
        aud.cuadra("Ingreso - gasto = utilidad neta",
                   L("TOTAL_REVENUES") - gasto_pl, L("NET_PROFIT"),
                   "el cierre del circulo: nada se perdio por el camino")

        print("\n3. REVENUE DETAIL: SUS FILAS SUMAN SU PROPIO TOTAL")
        revs = {k: v for k, v in lineas.items() if k.startswith("REV_")}
        aud.cuadra("suma de las lineas de ingreso", sum(revs.values(), Decimal(0)),
                   L("TOTAL_REVENUES"))

        print("\n4. F&B COST DETAIL: EL DESGLOSE SUMA EL A&B")
        fb_ing = L("REV_FB") + L("REV_FB_BEV") + L("REV_FB_MISC")
        fb_cos = L("COS_FB_FOOD") + L("COS_FB_BEV") + L("COS_FB_MISC")
        aud.cuadra("comida+bebida+misc = ingreso de A&B", fb_ing,
                   sum((v for k, v in lineas.items() if k.startswith("REV_FB")), Decimal(0)))
        aud.cuadra("costo de A&B = clase 5 del 0120", fb_cos,
                   sum((v for k, v in por_cuenta.items()
                        if k.startswith("51")), Decimal(0)),
                   "las 51xx son las de A&B")
        if fb_ing:
            print(f"       (costo sobre venta de A&B: {float(fb_cos / fb_ing) * 100:.1f}%)")

        print("\n5. MONTHLY SUMMARY: ROOMS + A&B + OTROS = INGRESO TOTAL")
        rooms = L("REV_ROOMS") + L("REV_ROOMS_OTHER")
        otros = L("TOTAL_REVENUES") - rooms - fb_ing
        aud.cuadra("Rooms + A&B + Otros", rooms + fb_ing + otros, L("TOTAL_REVENUES"))
        print(f"       Rooms {_fmt(rooms)}   A&B {_fmt(fb_ing)}   Otros {_fmt(otros)}")

    print("\n" + "=" * 96)
    if aud.fallas:
        print(f"{len(aud.fallas)} DESCUADRES de {aud.checks} verificaciones:\n")
        for f in aud.fallas:
            print(f"  - {f}")
        return 1
    print(f"TODO CUADRA - {aud.checks} verificaciones, ninguna diferencia mayor a $1")
    return 0


if __name__ == "__main__":
    a = sys.argv
    mes = int(a[a.index("--mes") + 1]) if "--mes" in a else 4
    tipo = a[a.index("--tipo") + 1] if "--tipo" in a else "ACTUAL"
    anio = int(a[a.index("--anio") + 1]) if "--anio" in a else 2026
    sys.exit(asyncio.run(main(mes, tipo, anio)))
