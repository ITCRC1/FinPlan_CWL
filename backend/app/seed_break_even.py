# -*- coding: utf-8 -*-
"""Siembra los departamentos y la clasificación de costos del Break-Even.

**Por qué existe (owner, 2026-08-20: «que no pierda estructura»).** Estas dos
semillas se cargaban con `scripts/cargar_semilla_break_even.py`, **a mano**, y
nadie las llamaba desde el arranque. Medido ese día: `python -m app.seed` corre
en cada despliegue y siembra nueve cosas; estas dos **no estaban**. Un clon
levantaba con `be_department` y `be_cost_classification` vacías, y eso no da
error — Break-Even muestra ceros y Costos de Grupos deja de poder separar
PAYROLL de COST OF SALES, porque `be_section` sale de acá. Cero se lee igual que
«no gastó».

Estructura que sólo existe si alguien se acuerda de correr un script es
estructura que se va a perder. Ahora entra por el arranque, como las demás.

**Por propiedad, no del grupo.** Los archivos viven en
`seed_data/<HOTEL_ID>/break_even/` y no en una carpeta común: los porcentajes
fijo/variable son de Corcovado, medidos contra su P&L. Una propiedad sin carpeta
**no hereda los de otra** — nace sin clasificación y el Chequeo se lo dice por
su nombre. Es el mismo criterio del paquete y las experiencias, que ya estaban
así (ver `app/seed_data/__init__.py`).

⚠️ **Idempotente por llave, no por «¿está vacía?»**: se relee en cada despliegue
y sólo inserta lo que falta. Un porcentaje que el owner ya ajustó **no se pisa**
— la semilla propone, no corrige.

⚠️ Los departamentos van PRIMERO: las reglas tienen FK contra ellos, y al revés
la carga muere a la mitad con las reglas escritas y los departamentos no.
"""
from __future__ import annotations

import csv
import pathlib
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.hotel_actual import HOTEL_ID
from app.models.break_even import BeCostClassification, BeDepartment

SEMILLAS = pathlib.Path(__file__).resolve().parent / "seed_data"


def carpeta(hotel_id: str | None = None) -> pathlib.Path:
    return SEMILLAS / (hotel_id or HOTEL_ID) / "break_even"


def _leer(ruta: pathlib.Path) -> list[dict]:
    """SIEMPRE con `utf-8` explícito.

    Los nombres traen «Á», «—», «·» y «&». En Windows el default es cp1252:
    entran corruptos y el apareo por nombre falla **en silencio**, que es peor
    que fallar.
    """
    if not ruta.exists():
        return []
    with ruta.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _booleano(v: str) -> bool:
    return str(v).strip().lower() in ("true", "1", "yes", "sí", "si")


def leer(hotel_id: str | None = None) -> tuple[list[dict], list[dict]]:
    """Las dos semillas de esta propiedad. Vacías si no tiene carpeta."""
    base = carpeta(hotel_id)
    deptos = _leer(base / "be_departments_seed.csv")
    clases = _leer(base / "be_classification_seed.csv")
    if not deptos and not clases:
        return [], []

    # Coherencia del archivo, medida ANTES de tocar la base.
    slugs = {d["slug"] for d in deptos}
    huerfanas = sorted({c["be_department_slug"] for c in clases} - slugs)
    if huerfanas:
        raise ValueError(
            "la clasificación referencia departamentos que la semilla de "
            f"departamentos no trae: {huerfanas}")

    # ⚠️ La llave incluye `pl_line` porque las filas `LINEA` colisionan todas
    # en (property, '', ''): sin `pl_line` el archivo no es único.
    llaves = [(c["dept_code"], c["account"], c["pl_line"]) for c in clases]
    if len(set(llaves)) != len(llaves):
        raise ValueError("la semilla trae llaves repetidas "
                         "(dept_code, account, pl_line)")
    return deptos, clases


async def seed_break_even(db, hotel_id: str | None = None) -> dict:
    hotel = hotel_id or HOTEL_ID
    deptos, clases = leer(hotel)
    if not deptos and not clases:
        return {"sembrado": False, "hotel": hotel,
                "nota": "esta propiedad no trae semilla de break-even"}

    # ── Departamentos ────────────────────────────────────────────────────────
    # `property_id=None` es a propósito: el universo de departamentos del
    # Break-Even vale para todas las propiedades, igual que `department_catalog`.
    existentes = {d.slug: d for d in (await db.execute(
        select(BeDepartment))).scalars()}
    nuevos_deptos = 0
    for d in deptos:
        if d["slug"] in existentes:
            continue
        db.add(BeDepartment(
            id=uuid.uuid4().hex, slug=d["slug"], name=d["name"],
            display_order=int(d["display_order"]),
            generates_revenue=_booleano(d["generates_revenue"]),
            dept_codes=d["dept_codes"], status=d["status"], property_id=None))
        nuevos_deptos += 1
    await db.flush()

    por_slug = {d.slug: d.id for d in (await db.execute(
        select(BeDepartment))).scalars()}

    # ── Clasificación ────────────────────────────────────────────────────────
    # ⚠️ `dept_code` y `account` van con string VACÍO, jamás NULL: en Postgres
    # `NULL ≠ NULL`, así que con NULL la llave no aparea y cada despliegue
    # duplicaría las filas `LINEA` sin decir nada.
    ya = {(c.dept_code or "", c.account or "", c.pl_line)
          for c in (await db.execute(
              select(BeCostClassification)
              .where(BeCostClassification.property_id == hotel))).scalars()}
    nuevas = 0
    for c in clases:
        llave = (c["dept_code"] or "", c["account"] or "", c["pl_line"])
        if llave in ya:
            continue
        db.add(BeCostClassification(
            id=uuid.uuid4().hex, property_id=hotel,
            be_department_id=por_slug[c["be_department_slug"]],
            dept_code=c["dept_code"] or "", account=c["account"] or "",
            account_name=c["account_name"], pl_line=c["pl_line"],
            section=c["section"], be_section=c["be_section"],
            original_class=c["original_class"],
            pct_variable=Decimal(c["pct_variable"]),
            map_source=c["map_source"],
            excluded_from_be=_booleano(c["excluded_from_be"]),
            source_rows=c["source_rows"][:120]))
        nuevas += 1
    await db.flush()
    return {"sembrado": True, "hotel": hotel,
            "departamentos": len(deptos), "departamentos_nuevos": nuevos_deptos,
            "reglas": len(clases), "reglas_nuevas": nuevas}
