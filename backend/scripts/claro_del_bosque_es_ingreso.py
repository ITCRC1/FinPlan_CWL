# -*- coding: utf-8 -*-
"""El ingreso de Claro del Bosque estaba cargado como gasto de overhead.

**Como aparecio (owner, 2026-08-14).** Reviso el mapeo completo y dijo la regla:
«las cuentas 4 son revenue a excepcion de los allocations. 5 costo, 6 planilla,
7 opex y 8 gastos de propiedad». Contra esa regla, de 1,172 reglas hay
exactamente CUATRO que no la cumplen: las 4500-4503 del departamento 0205, que
se llaman «Ingreso Claro Huerta 1..4», son clase 4, y estaban mapeadas a
`OH_CLARO_HUERTA` -- una linea de GASTO -- con naturaleza «Expense».

No era criterio: las MISMAS cuentas en otros departamentos van a ingreso. La
4500 de Innoceana va a `REV_INNOCEANA` y la de Club Madresal a `REV_CLUB`.

**Por que no se notaba.** Un ingreso que resta gasto tiene el mismo efecto sobre
el GOP que un ingreso que suma, asi que el resultado salia bien. Lo que quedaba
torcido era todo lo demas: el ingreso del hotel subestimado, el overhead
subestimado, y todos los porcentajes sobre ingreso mal.

**El GOP TAMPOCO se mueve con el arreglo, y eso hay que cuidarlo.** El 0205 es
un departamento de overhead: su gasto vive en `TOTAL_OVERHEAD_EXPENSES` y el GOP
es `OPERATING_PROFIT - TOTAL_OVERHEAD_EXPENSES`. Al sacar el ingreso de ahi, el
overhead SUBE. Si el ingreso no entrara tambien en `OPERATING_PROFIT`, el GOP
bajaria por su monto.

Por eso lleva `PROFIT_CLARO_HUERTA = REV_CLARO_HUERTA`, sin restar gasto -- el
mismo patron que ya usan `PROFIT_SUSTAINABILITY` y `PROFIT_AREC`, que son
departamentos con venta cuyo costo vive en overhead.

Hoy esas cuatro cuentas tienen CERO movimiento en los 20 escenarios, asi que el
arreglo no mueve un solo numero. Es el momento barato para hacerlo.

    python -m scripts.claro_del_bosque_es_ingreso --aplicar
"""
import json
import pathlib
import sys

ARCHIVO = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "seed_data" / "mapping_pl.json")

CUENTAS = {"4500", "4501", "4502", "4503"}
DEPTO = "0205"
LINEA = "REV_CLARO_HUERTA"
NOMBRE = "Claro del Bosque"


def main(aplicar: bool):
    d = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    movidas = 0
    for f in d["account_mapping"]:
        if str(f["account_code"]) in CUENTAS and str(f.get("dept_code") or "") == DEPTO:
            f["report_line_code"] = LINEA
            f["report_line_name"] = NOMBRE
            f["report_section"] = "REVENUES"
            f["financial_nature"] = "Revenue"
            movidas += 1
    print(f"  {movidas} cuentas movidas a {LINEA}")

    codigos = {r["line_code"] for r in d["report_line_config"]}
    base_rev = next(r for r in d["report_line_config"] if r["line_code"] == "REV_INNOCEANA")
    base_pro = next(r for r in d["report_line_config"] if r["line_code"] == "PROFIT_INNOCEANA")
    if LINEA not in codigos:
        d["report_line_config"].append({**base_rev, "line_code": LINEA,
                                        "line_name": NOMBRE})
        print(f"  + {LINEA}")
    if "PROFIT_CLARO_HUERTA" not in codigos:
        d["report_line_config"].append({
            **base_pro, "line_code": "PROFIT_CLARO_HUERTA", "line_name": NOMBRE,
            # Sin restar gasto: el del 0205 ya esta en overhead. Ver el
            # encabezado -- restarlo aca lo contaria dos veces.
            "calculation_logic": LINEA})
        print("  + PROFIT_CLARO_HUERTA = " + LINEA)

    if not aplicar:
        print("\n  (prueba en seco - corre con --aplicar)")
        return
    ARCHIVO.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  escrito: {ARCHIVO}")


if __name__ == "__main__":
    main("--aplicar" in sys.argv)
