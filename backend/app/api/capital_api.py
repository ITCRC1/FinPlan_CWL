"""
Detalle de proyectos de capital: qué se compra, en qué área y en qué mes.

Es la lista que el dueño armaba en Excel y presentaba aparte. Acá vive dentro
del escenario, editable renglón por renglón y mes por mes, para poder ver la
ejecución en el tiempo — que era lo que el Excel no dejaba cruzar con nada.

NO alimenta el P&L: la línea de inversión de capital sigue saliendo de
nonop_entries. Este es el detalle que la explica. Ver el docstring del modelo.

Endpoints:
  GET    /api/capital/{scenario_id}/              renglones + totales por área
  POST   /api/capital/{scenario_id}/              crear renglón
  PUT    /api/capital/{scenario_id}/bulk/         reemplazo completo de la lista
  PUT    /api/capital/{scenario_id}/entry/{id}/   editar un renglón
  DELETE /api/capital/{scenario_id}/entry/{id}/
"""
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File
from app.importers.registro_dep import registro_de_subida
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.db import get_db
from app.models.scenario import Scenario
from app.models.capital_project import CapitalProject, MONTH_ATTRS
from app.export.capital_excel import export_capital_to_excel, import_capital_from_excel

router = APIRouter(tags=["capital"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class CapitalRow(BaseModel):
    area: str = ""
    name: str = ""
    notes: str = ""
    sort_order: int = 0
    jan: Decimal = Decimal("0"); feb: Decimal = Decimal("0")
    mar: Decimal = Decimal("0"); apr: Decimal = Decimal("0")
    may: Decimal = Decimal("0"); jun: Decimal = Decimal("0")
    jul: Decimal = Decimal("0"); aug: Decimal = Decimal("0")
    sep: Decimal = Decimal("0"); oct: Decimal = Decimal("0")
    nov: Decimal = Decimal("0"); dec: Decimal = Decimal("0")


class CapitalUpdate(BaseModel):
    area: Optional[str] = None
    name: Optional[str] = None
    notes: Optional[str] = None
    sort_order: Optional[int] = None
    jan: Optional[Decimal] = None; feb: Optional[Decimal] = None
    mar: Optional[Decimal] = None; apr: Optional[Decimal] = None
    may: Optional[Decimal] = None; jun: Optional[Decimal] = None
    jul: Optional[Decimal] = None; aug: Optional[Decimal] = None
    sep: Optional[Decimal] = None; oct: Optional[Decimal] = None
    nov: Optional[Decimal] = None; dec: Optional[Decimal] = None


async def _scenario(db: AsyncSession, scenario_id: str) -> Scenario:
    scen = await db.get(Scenario, scenario_id)
    if not scen:
        raise ErrorApi(404, "escenario.no_encontrado")
    return scen


def _dump(e: CapitalProject) -> dict:
    meses = {m: float(getattr(e, m) or 0) for m in MONTH_ATTRS}
    return {
        "id": e.id, "area": e.area, "name": e.name, "notes": e.notes,
        "sort_order": e.sort_order, **meses,
        "total": round(sum(meses.values()), 2),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("/capital/{scenario_id}/")
async def listar(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Renglones en el orden en que se capturaron, más totales por área y por mes."""
    await _scenario(db, scenario_id)
    rows = (await db.execute(
        select(CapitalProject)
        .where(CapitalProject.scenario_id == scenario_id)
        .order_by(CapitalProject.sort_order, CapitalProject.id)
    )).scalars().all()
    entries = [_dump(e) for e in rows]

    areas: dict[str, dict] = {}
    for e in entries:
        a = areas.setdefault(e["area"] or "Sin área",
                             {"area": e["area"] or "Sin área",
                              **{m: 0.0 for m in MONTH_ATTRS}, "total": 0.0, "count": 0})
        for m in MONTH_ATTRS:
            a[m] += e[m]
        a["total"] += e["total"]
        a["count"] += 1

    totales = {m: round(sum(e[m] for e in entries), 2) for m in MONTH_ATTRS}
    return {
        "scenario_id": scenario_id,
        "entries": entries,
        # El orden de las áreas sigue al de los renglones, no alfabético: es el
        # orden en que el dueño la presenta.
        "areas": list(areas.values()),
        "months": totales,
        "total": round(sum(totales.values()), 2),
    }


@router.post("/capital/{scenario_id}/")
async def crear(scenario_id: str, row: CapitalRow, db: AsyncSession = Depends(get_db)):
    scen = await _scenario(db, scenario_id)
    e = CapitalProject(id=str(uuid.uuid4()), scenario_id=scenario_id,
                       hotel_id=scen.hotel_id, **row.model_dump())
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return _dump(e)


@router.put("/capital/{scenario_id}/bulk/")
async def reemplazar(scenario_id: str, rows: list[CapitalRow], db: AsyncSession = Depends(get_db)):
    """Reemplaza la lista completa. Se usa al cargar desde Excel."""
    scen = await _scenario(db, scenario_id)
    await db.execute(delete(CapitalProject).where(CapitalProject.scenario_id == scenario_id))
    for i, r in enumerate(rows):
        d = r.model_dump()
        d["sort_order"] = d.get("sort_order") or i
        db.add(CapitalProject(id=str(uuid.uuid4()), scenario_id=scenario_id,
                              hotel_id=scen.hotel_id, **d))
    await db.commit()
    return {"ok": True, "count": len(rows)}


@router.put("/capital/{scenario_id}/entry/{entry_id}/")
async def actualizar(scenario_id: str, entry_id: str, upd: CapitalUpdate,
                     db: AsyncSession = Depends(get_db)):
    e = await db.get(CapitalProject, entry_id)
    if not e or e.scenario_id != scenario_id:
        raise ErrorApi(404, "renglon.no_encontrado")
    for campo, valor in upd.model_dump(exclude_unset=True).items():
        if valor is not None:
            setattr(e, campo, valor)
    await db.commit()
    await db.refresh(e)
    return _dump(e)


@router.get("/capital/{scenario_id}/excel/")
async def exportar(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """Descarga la lista como «Capital Project», con fórmulas y protegida."""
    scen = await _scenario(db, scenario_id)
    rows = (await db.execute(
        select(CapitalProject)
        .where(CapitalProject.scenario_id == scenario_id)
        .order_by(CapitalProject.sort_order, CapitalProject.id)
    )).scalars().all()
    version = f" · {scen.version}" if scen.version else ""
    titulo = f"{scen.hotel_id} — {scen.type} {scen.year}{version}"
    contenido = export_capital_to_excel(
        [{"area": e.area, "name": e.name, "notes": e.notes,
          **{m: float(getattr(e, m) or 0) for m in MONTH_ATTRS}} for e in rows],
        titulo,
    )
    # El nombre es exactamente «Capital Project», como lo pidió el dueño. El
    # escenario no va en el nombre sino en el encabezado de la hoja, para que el
    # archivo se llame siempre igual en el correo y en el disco.
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Capital Project.xlsx"'},
    )


@router.post("/capital/{scenario_id}/excel/", dependencies=[Depends(registro_de_subida)])
async def importar(scenario_id: str, file: UploadFile = File(...),
                   db: AsyncSession = Depends(get_db)):
    """Sube el archivo y REEMPLAZA la lista completa.

    Es reemplazo y no mezcla a propósito: el Excel es la versión que el dueño
    acaba de trabajar. Mezclar obligaría a decidir qué gana renglón por renglón,
    y un borrado hecho en Excel no se vería reflejado.
    """
    scen = await _scenario(db, scenario_id)
    filas = import_capital_from_excel(await file.read())
    if not filas:
        raise ErrorApi(400, "capital.archivo_sin_renglones")
    await db.execute(delete(CapitalProject).where(CapitalProject.scenario_id == scenario_id))
    for i, f in enumerate(filas):
        f["sort_order"] = i
        db.add(CapitalProject(id=str(uuid.uuid4()), scenario_id=scenario_id,
                              hotel_id=scen.hotel_id, **f))
    await db.commit()
    total = sum(float(f[m]) for f in filas for m in MONTH_ATTRS)
    return {"ok": True, "count": len(filas), "total": round(total, 2)}


@router.delete("/capital/{scenario_id}/entry/{entry_id}/")
async def borrar(scenario_id: str, entry_id: str, db: AsyncSession = Depends(get_db)):
    e = await db.get(CapitalProject, entry_id)
    if not e or e.scenario_id != scenario_id:
        raise ErrorApi(404, "renglon.no_encontrado")
    await db.delete(e)
    await db.commit()
    return {"ok": True}
