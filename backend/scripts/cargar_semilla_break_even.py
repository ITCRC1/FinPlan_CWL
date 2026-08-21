# -*- coding: utf-8 -*-
"""Carga las dos semillas del módulo Break-Even (spec §8).

    python -m scripts.cargar_semilla_break_even                 # VERIFICA, no escribe
    python -m scripts.cargar_semilla_break_even --aplicar       # escribe

Por defecto **solo verifica**, que es lo que pide el spec: comprobar que la
propiedad existe, cuántas reglas ya hay y qué se insertaría, y recién entonces
escribir. Una carga que empieza escribiendo no tiene vuelta atrás.

## Las cuatro cosas que este cargador cuida

1. **`encoding='utf-8'` explícito.** Los nombres traen `Á`, `—`, `·` y `&`. En
   Windows el default es cp1252: entran corruptos y el match por nombre falla
   **en silencio**, que es peor que fallar.
2. **`ON CONFLICT (property_id, dept_code, account, pl_line) DO NOTHING`.** Una
   recarga nunca pisa un porcentaje ya ajustado por el usuario. Y la llave
   incluye `pl_line` porque **las 18 filas `LINEA` colisionan todas** en
   `(property, '', '')`: sin `pl_line` el archivo no es único.
3. **String vacío, jamás NULL**, en `dept_code` y `account`. En Postgres
   `NULL ≠ NULL`, así que con NULL el `ON CONFLICT` no aparea y la segunda
   corrida duplicaría las 18 filas `LINEA` sin decir nada.
4. **Los departamentos van primero.** Las reglas tienen FK al departamento; al
   revés, la carga muere a la mitad con las reglas escritas y los departamentos
   no.

## Lo que este cargador NO hace

No calcula ni recalcula nada. Las semillas son datos reales de CWL, ya mapeados
y validados contra el P&L al centavo — el spec dice literalmente «no regenerarlos
ni recalcularlos: se cargan tal cual».
"""
from __future__ import annotations

import asyncio
import csv
import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

#: Dónde viven las semillas dentro del repo.
def _carpeta_de_la_propiedad() -> pathlib.Path:
    """La carpeta de ESTA instalacion. Sin `HOTEL_ID`, la de Corcovado."""
    import os
    hotel = os.getenv("HOTEL_ID", "CWL")
    return (pathlib.Path(__file__).resolve().parents[1]
            / "app" / "seed_data" / hotel / "break_even")


#: ATENCION (2026-08-20): las semillas se movieron a
#: `app/seed_data/<HOTEL_ID>/break_even/` y ahora las carga el arranque
#: (`python -m app.seed` -> `app.seed_break_even`). Este script queda para
#: correrlas a mano contra produccion, y lee la MISMA carpeta: dos rutas
#: distintas eran dos verdades, y la que se olvidaba era siempre la del script.
SEMILLAS = _carpeta_de_la_propiedad()
CSV_DEPTOS = SEMILLAS / "be_departments_seed.csv"
CSV_CLASES = SEMILLAS / "be_classification_seed.csv"


def _leer(ruta: pathlib.Path) -> list[dict]:
    """SIEMPRE con utf-8 explícito. Ver el punto 1 del docstring."""
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _booleano(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "sí", "si")


async def main(aplicar: bool, property_id: str) -> int:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select, func
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.db import SessionLocal
    from app.models.hotel import Hotel
    from app.models.break_even import (
        BeDepartment, BeCostClassification, DEPT_ACTIVO,
    )

    for ruta in (CSV_DEPTOS, CSV_CLASES):
        if not ruta.exists():
            print(f"FALTA la semilla: {ruta}")
            return 1

    deptos = _leer(CSV_DEPTOS)
    clases = _leer(CSV_CLASES)
    print(f"\nSemillas leidas (utf-8): {len(deptos)} departamentos · "
          f"{len(clases)} reglas de clasificacion")

    # ── Verificacion previa, ANTES de escribir nada ───────────────────────────
    async with SessionLocal() as db:
        hotel = await db.get(Hotel, property_id)
        if hotel is None:
            print(f"La propiedad '{property_id}' NO existe en `hotels`. "
                  f"Nada que hacer.")
            return 1
        print(f"Propiedad: {property_id} — {hotel.name}")

        ya_deptos = (await db.execute(
            select(func.count()).select_from(BeDepartment))).scalar_one()
        ya_clases = (await db.execute(
            select(func.count()).select_from(BeCostClassification)
            .where(BeCostClassification.property_id == property_id))).scalar_one()
        print(f"En la base hoy: {ya_deptos} departamentos · {ya_clases} reglas")

        # Coherencia del archivo, medida antes de tocar la base.
        slugs_csv = {d["slug"] for d in deptos}
        faltan = sorted({c["be_department_slug"] for c in clases} - slugs_csv)
        if faltan:
            print(f"ABORTA: la clasificacion referencia departamentos que la "
                  f"semilla de departamentos no trae: {faltan}")
            return 1

        llaves = [(property_id, c["dept_code"], c["account"], c["pl_line"])
                  for c in clases]
        if len(set(llaves)) != len(llaves):
            print(f"ABORTA: la semilla tiene llaves duplicadas "
                  f"(property, dept_code, account, pl_line).")
            return 1

        activos = sum(1 for d in deptos if d["status"] == DEPT_ACTIVO)
        linea = sum(1 for c in clases if c["map_source"] == "LINEA")
        excl = sum(1 for c in clases if _booleano(c["excluded_from_be"]))
        print(f"Se insertarian: {activos} departamentos activos + "
              f"{len(deptos) - activos} pendientes · {len(clases)} reglas "
              f"({linea} LINEA, {excl} excluidas del BE)")

        if not aplicar:
            print("\nVERIFICACION: no se escribio nada. Correr con --aplicar.")
            return 0

        # ── Departamentos PRIMERO: las reglas tienen FK contra ellos ──────────
        for d in deptos:
            await db.execute(pg_insert(BeDepartment.__table__).values(
                id=__import__("uuid").uuid4().hex,
                slug=d["slug"], name=d["name"],
                display_order=int(d["display_order"]),
                generates_revenue=_booleano(d["generates_revenue"]),
                dept_codes=d["dept_codes"], status=d["status"],
                property_id=None,          # NULL = vale para todas las propiedades
            ).on_conflict_do_nothing(index_elements=["slug"]))
        await db.commit()

        por_slug = {d.slug: d.id for d in (await db.execute(
            select(BeDepartment))).scalars()}

        insertadas = 0
        for c in clases:
            r = await db.execute(pg_insert(BeCostClassification.__table__).values(
                id=__import__("uuid").uuid4().hex,
                property_id=property_id,
                be_department_id=por_slug[c["be_department_slug"]],
                # ⚠️ Vacio, nunca None: ver el punto 3 del docstring.
                dept_code=c["dept_code"] or "",
                account=c["account"] or "",
                account_name=c["account_name"],
                pl_line=c["pl_line"], section=c["section"],
                be_section=c["be_section"], original_class=c["original_class"],
                pct_variable=Decimal(c["pct_variable"]),
                map_source=c["map_source"],
                excluded_from_be=_booleano(c["excluded_from_be"]),
                source_rows=c["source_rows"][:120],
            ).on_conflict_do_nothing(constraint="uq_be_classification"))
            insertadas += r.rowcount or 0
        await db.commit()

        quedan = (await db.execute(
            select(func.count()).select_from(BeCostClassification)
            .where(BeCostClassification.property_id == property_id))).scalar_one()
        print(f"\n✓ {insertadas} reglas nuevas ({len(clases) - insertadas} ya "
              f"estaban y NO se pisaron). Total en la base: {quedan}")
    return 0


if __name__ == "__main__":
    from app.hotel_actual import HOTEL_ID
    prop = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--property=")),
                HOTEL_ID)
    raise SystemExit(asyncio.run(main("--aplicar" in sys.argv, prop)))
