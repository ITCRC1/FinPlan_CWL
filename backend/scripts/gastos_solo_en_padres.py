# -*- coding: utf-8 -*-
"""Solo los departamentos PADRE llevan checkbook de gastos. Los hijos, planilla.

Owner, 2026-08-14, mirando el checkbook de Opex:

    «los grandes departamentos en Opex son muy claros, solo los departamentos
    padres pueden tener checkbook de gastos, ningun hijo puede tener gastos
    operativos» · «los hijos integran a nivel de planilla pero nada mas»

Es la regla USALI, y hasta hoy el sistema no la sostenia: el selector de
departamentos del checkbook de Opex sale de los `OpexEntry` que existen, asi que
cualquier hijo con filas en blanco aparecia ofreciendo veintipico de cuentas de
gasto para digitar.

Dos cosas, y ninguna toca un monto de un padre:

  A. **El gasto que ya esta posteado en un hijo se mueve al padre.** Hoy llega a
     su linea por herencia (`parent`), tomando la regla del padre; despues llega
     a la MISMA linea por regla exacta. El script lo comprueba cuenta por cuenta
     y aborta si alguna cambiaria.

  B. **Las filas en blanco de los hijos se borran.** Son las que hacian que el
     hijo apareciera en el selector. Al no quedar ninguna, deja de ofrecerse —
     sin tocar la pantalla, porque la pantalla solo muestra lo que hay.

La planilla NO se toca: los hijos siguen llevandola, que es justo lo que el
owner dice que si les corresponde.

Quien es hijo sale de `CHECKBOOK_DEPT_CONSOLIDATION` en `pl_engine`, que es el
mismo mapa que usa el motor — no una lista aparte que se quede vieja.

Uso:
    python -m scripts.gastos_solo_en_padres --prod              # ensayo
    python -m scripts.gastos_solo_en_padres --prod --aplicar
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

if "--prod" in sys.argv:
    from scripts._prodenv import usar_produccion
    usar_produccion()

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.engine import pl_engine  # noqa: E402
from app.engine.recalculate import load_active_account_mappings  # noqa: E402
from app.models.cost_entry import CostEntry  # noqa: E402
from app.models.opex_entry import OpexEntry  # noqa: E402
from app.models.scenario import Scenario  # noqa: E402

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]
TABLAS = (OpexEntry, CostEntry)


def _total(fila) -> Decimal:
    return sum(Decimal(str(getattr(fila, m) or 0)) for m in MESES)


async def main(aplicar: bool) -> int:
    async with SessionLocal() as db:
        resolve = pl_engine.construir_resolvedor(await load_active_account_mappings(db))
        nombres = {s.id: f"{s.type} {s.version} {s.year}" for s in
                   (await db.execute(select(Scenario))).scalars().all()}
        # La cadena completa: el 0132 cuelga del 0130 y el 0130 del 0140, asi que
        # el destino del 0132 es el 0140, no un hijo intermedio que tampoco puede
        # llevar gasto.
        def raiz(dept: str) -> str:
            cadena = pl_engine._cadena_de_padres(dept)
            return cadena[-1] if cadena else dept

        hijos = {d for d in pl_engine.CHECKBOOK_DEPT_CONSOLIDATION}

        con_plata, en_blanco = [], []
        for Modelo in TABLAS:
            for f in (await db.execute(select(Modelo))).scalars().all():
                if (f.dept_code or "").strip() not in hijos:
                    continue
                (con_plata if abs(_total(f)) > Decimal("0.005") else en_blanco).append(
                    (Modelo, f))

        print("=== A. El gasto posteado en un hijo se mueve al padre ===")
        if not con_plata:
            print("    Ningun hijo tiene gasto posteado.")
        problemas = []
        for Modelo, f in sorted(con_plata, key=lambda x: (x[1].dept_code or "",
                                                          x[1].account_code or "")):
            hijo = (f.dept_code or "").strip()
            padre = raiz(hijo)
            cuenta = (f.account_code or "").strip()
            r_v, modo_v = resolve(hijo, cuenta)
            r_n, modo_n = resolve(padre, cuenta)
            l_v = r_v.get("report_line_code") if r_v else None
            l_n = r_n.get("report_line_code") if r_n else None
            print(f"    {nombres.get(f.scenario_id, '?'):<24} {hijo} -> {padre}  "
                  f"{cuenta:<6} {float(_total(f)):>12,.2f}  "
                  f"{str(l_v):<12} {modo_v:<8} -> {str(l_n):<12} {modo_n}")
            if l_v != l_n:
                problemas.append((hijo, cuenta, l_v, l_n))
        if problemas:
            print(f"\n    X ABORTADO: {len(problemas)} cuenta(s) cambiarian de linea "
                  f"del P&L: {problemas}")
            return 1
        if con_plata:
            print("\n    OK Ninguna cuenta cambia de linea — solo el modo de ruteo.")

        print(f"\n=== B. Filas en blanco de hijos: {len(en_blanco)} ===")
        por_dept: dict[str, int] = {}
        for _M, f in en_blanco:
            por_dept[(f.dept_code or "").strip()] = por_dept.get(
                (f.dept_code or "").strip(), 0) + 1
        for d, n in sorted(por_dept.items()):
            print(f"    {d}: {n} filas en cero — hoy hacen que el hijo aparezca "
                  "en el selector de Opex")

        if not aplicar:
            print("\n· Ensayo. Para escribirlo, agrega --aplicar.")
            return 0

        # Llave unica (scenario_id, dept_code, account_code, detail_code): si el
        # padre ya tiene esa cuenta, se SUMA y se borra la del hijo.
        movidas = fusionadas = 0
        for Modelo, f in con_plata:
            padre = raiz((f.dept_code or "").strip())
            gemela = (await db.execute(select(Modelo).where(
                Modelo.scenario_id == f.scenario_id,
                Modelo.dept_code == padre,
                Modelo.account_code == f.account_code,
                Modelo.detail_code == f.detail_code))).scalars().first()
            if gemela is None:
                f.dept_code = padre
                movidas += 1
            else:
                for m in MESES:
                    setattr(gemela, m, Decimal(str(getattr(gemela, m) or 0))
                            + Decimal(str(getattr(f, m) or 0)))
                await db.delete(f)
                fusionadas += 1
        for _M, f in en_blanco:
            await db.delete(f)
        await db.commit()
        print(f"\nOK {movidas} movidas al padre, {fusionadas} fusionadas, "
              f"{len(en_blanco)} filas en blanco borradas.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
