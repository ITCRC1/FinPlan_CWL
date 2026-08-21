"""Re-etiqueta a `280` las filas del GL que quedaron con el departamento `0240`.

**Por qué existe.** El `0240` no existe en el catálogo de departamentos y la
contabilidad nunca lo mandó: lo fabricó una versión vieja de nuestro propio
importador. `gl_detail_importer.dept_code_from_name` asigna el departamento a
partir del NOMBRE que trae el archivo, y su tabla hoy manda «miscel»/«sostenib»
al `280` y «propiedad» al `0250`. Las filas con `0240` son de antes de ese
cambio.

**No es corregir dato: es corregir una traducción nuestra.** El monto, el mes y
la cuenta no se tocan — solo la etiqueta de departamento.

**No mueve ninguna línea del P&L.** Hoy esas cuentas (4800, 4860, 4880, 4890)
llegan a su línea por FALLBACK, tomando prestada la regla del `280`; después
llegan a la MISMA línea por regla exacta. El script lo comprueba antes y después
y aborta si algo cambió.

Uso:
    python -m scripts.retag_0240_a_280 --prod              # ensayo
    python -m scripts.retag_0240_a_280 --prod --aplicar
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
from app.models.actual_entry import ActualEntry  # noqa: E402
from app.models.scenario import Scenario  # noqa: E402

VIEJO, NUEVO = "0240", "280"
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]


async def main(aplicar: bool) -> int:
    async with SessionLocal() as db:
        resolve = pl_engine.construir_resolvedor(await load_active_account_mappings(db))
        nombres = {s.id: f"{s.type} {s.version} {s.year}" for s in
                   (await db.execute(select(Scenario))).scalars().all()}

        filas = [f for f in (await db.execute(select(ActualEntry))).scalars().all()
                 if (f.dept_code or "").strip() == VIEJO]
        if not filas:
            print("No quedan filas con el departamento 0240.")
            return 0

        print(f"{len(filas)} filas con departamento {VIEJO}\n")
        print(f"  {'escenario':<24} {'cuenta':<7} {'total':>13}  "
              f"{'linea hoy':<22} {'modo':<9} -> {'linea nueva':<22} modo")
        problemas = []
        for f in sorted(filas, key=lambda x: (nombres.get(x.scenario_id, ""),
                                              x.account_code or "")):
            total = sum(Decimal(str(getattr(f, m) or 0)) for m in MESES)
            r_viejo, modo_viejo = resolve(VIEJO, f.account_code)
            r_nuevo, modo_nuevo = resolve(NUEVO, f.account_code)
            l_viejo = r_viejo.get("report_line_code") if r_viejo else None
            l_nuevo = r_nuevo.get("report_line_code") if r_nuevo else None
            print(f"  {nombres.get(f.scenario_id, '?'):<24} {f.account_code:<7} "
                  f"{float(total):>13,.2f}  {str(l_viejo):<22} {modo_viejo:<9} -> "
                  f"{str(l_nuevo):<22} {modo_nuevo}")
            if l_viejo != l_nuevo:
                problemas.append((f.account_code, l_viejo, l_nuevo))

        if problemas:
            print(f"\n✗ ABORTADO: {len(problemas)} cuenta(s) cambiarían de línea "
                  f"del P&L: {problemas}")
            return 1
        print("\n✓ Ninguna cuenta cambia de línea del P&L — solo el modo de ruteo.")

        if not aplicar:
            print("· Ensayo. Para escribirlo, agregá --aplicar.")
            return 0

        for f in filas:
            f.dept_code = NUEVO
        await db.commit()
        print(f"✓ {len(filas)} filas re-etiquetadas {VIEJO} -> {NUEVO}.")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv)))
