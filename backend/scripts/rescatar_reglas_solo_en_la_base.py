# -*- coding: utf-8 -*-
"""Trae al seed las reglas de mapeo que solo existian en la base.

**Como aparecio (owner, 2026-08-14).** Revisando el mapeo exportado, la linea
`REV_ROOMS` salia con DOS nombres distintos: «Rooms Pure» en el depto 0110 y
«Rooms» en Villas y Residencias. Al mirar por que, aparecio lo de fondo: el seed
tiene UNA regla para esa linea y la base tiene TRES.

En total son **96 reglas de los deptos 0115 (Villas) y 0116 (Residencias) que
viven solo en la base**. Alguien las creo a mano o por migracion y nunca
volvieron al repositorio.

**Por que importa.** El seed es lo que arma una instalacion nueva. Una propiedad
nueva naceria sin esas 96 reglas, y su ingreso y su gasto de Villas caerian en
la nada -- o peor, en la linea de otro departamento por fallback. Corcovado no
lo nota porque su base ya las tiene: el hueco solo se ve el dia que se abre otro
hotel, que es tarde.

Es el mismo patron que ya documenta `test_reglas_solo_en_migracion.py`.

    python -m scripts.rescatar_reglas_solo_en_la_base --aplicar
"""
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from scripts._prodenv import usar_produccion  # noqa: E402

usar_produccion()

from sqlalchemy import select  # noqa: E402

from app.db import get_session  # noqa: E402
from app.models.mapping import AccountMapping  # noqa: E402

ARCHIVO = (pathlib.Path(__file__).resolve().parents[1]
           / "app" / "seed_data" / "mapping_pl.json")

CAMPOS = ["active_status", "report_id", "report_line_code", "report_line_name",
          "report_section", "display_order", "source_origin", "source_department",
          "account_code", "account_name_example", "financial_nature",
          "rollup_operator", "sign_rule", "notes", "dept_code"]


def _llave(r: dict) -> tuple:
    return (r["report_id"], str(r.get("source_department") or ""),
            str(r["account_code"]), str(r.get("source_origin") or ""))


async def main(aplicar: bool):
    d = json.loads(ARCHIVO.read_text(encoding="utf-8"))
    en_json = {_llave(r) for r in d["account_mapping"]}

    async with get_session() as s:
        filas = (await s.execute(select(AccountMapping))).scalars().all()

    nuevas = []
    for f in filas:
        r = {c: getattr(f, c, None) for c in CAMPOS}
        if _llave(r) not in en_json:
            nuevas.append(r)

    print(f"  base: {len(filas)} reglas | seed: {len(en_json)}")
    print(f"  solo en la base: {len(nuevas)}")
    por_dep = {}
    for r in nuevas:
        por_dep[r["dept_code"] or "?"] = por_dep.get(r["dept_code"] or "?", 0) + 1
    for dep, n in sorted(por_dep.items()):
        print(f"     depto {dep}: {n}")

    if not nuevas:
        print("\n  nada que rescatar")
        return
    if not aplicar:
        print("\n  (prueba en seco - corre con --aplicar)")
        return

    d["account_mapping"].extend(nuevas)
    ARCHIVO.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  {len(nuevas)} reglas agregadas al seed")


if __name__ == "__main__":
    asyncio.run(main("--aplicar" in sys.argv))
