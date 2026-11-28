"""Conservar los conceptos de planilla digitados cuando se reemplazan las posiciones.

Owner, 2026-11-27: «asegúrate que no se borre en el futuro». Las horas extra (6001)
del Budget 2027 Working —y antes las comisiones, vacaciones tomadas, vivienda,
transporte y otros beneficios— se perdían al subir la planilla desde Excel: el
reemplazo borra las posiciones y, con ellas (ON DELETE CASCADE), todos sus
conceptos. El recálculo solo repone 6000, 6020 y 6021.

Ahora el reemplazo toma una FOTO de los conceptos digitados de las posiciones que va a
borrar y los devuelve a la posición nueva que tenga la misma llave (departamento +
código de posición). Lo que no encuentra a quién volver —la posición ya no viene en
el archivo— queda REGISTRADO en `payroll_conceptos_borrados`, con su monto.

Automáticos (no se conservan, el recálculo los rehace): 6000 salario, 6020 CCSS,
6021 aguinaldo, 6031 contract labour. Los que calcula una tasa (6001, 6027, 6023…)
sí se conservan: si la tasa está puesta, el recálculo los vuelve a calcular igual.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select

from app.engine.payroll_calculator import CONCEPT_COLS

AUTOMATICOS = frozenset({"c6000_sw", "c6020_ccss", "c6021_aguinaldo", "c6031_contract_labour"})
MANUALES = [c for c in CONCEPT_COLS if c not in AUTOMATICOS]
NOMBRE = {
    "c6001_overtime": "Horas extra", "c6002_day_off": "Día libre", "c6003_working_holiday": "Feriado laborado",
    "c6004_disabilities": "Incapacidades", "c6010_commissions": "Comisiones", "c6022_occ_hazard": "INS riesgos",
    "c6023_vacation_prov": "Vacaciones (provisión)", "c6024_vacations_taken": "Vacaciones tomadas",
    "c6025_cafeteria": "Cafetería", "c6026_severance": "Cesantía", "c6027_incentive_bonus": "Bono",
    "c6028_housing": "Vivienda", "c6029_transport": "Transporte", "c6030_other": "Otros beneficios",
}


def cuenta_de(col: str) -> str:
    """'c6001_overtime' → '6001'."""
    return col[1:5]


def llave(pos) -> tuple:
    """Departamento + código de posición; sin código, departamento + puesto + empleado."""
    codigo = (getattr(pos, "position_code", "") or "").strip()
    if codigo:
        return (pos.dept_code, codigo)
    return (pos.dept_code, "", (pos.position_name or "").strip().upper(), (pos.employee_name or "").strip().upper())


async def foto(db, scenario_id: str, posiciones) -> dict:
    """{llave: {mes: {col: monto}}} de los conceptos digitados (distintos de 0)."""
    from app.models.payroll_concept_entry import PayrollConceptEntry
    if not posiciones:
        return {}
    por_id = {p.id: llave(p) for p in posiciones}
    filas = (await db.execute(select(PayrollConceptEntry).where(
        PayrollConceptEntry.scenario_id == scenario_id,
        PayrollConceptEntry.position_id.in_(list(por_id))))).scalars().all()
    out: dict = defaultdict(dict)
    for e in filas:
        vals = {c: Decimal(getattr(e, c) or 0) for c in MANUALES if Decimal(getattr(e, c) or 0) != 0}
        if vals:
            out[por_id[e.position_id]][e.month] = vals
    return dict(out)


def cruzar(foto_vieja: dict, llaves_nuevas) -> tuple[dict, dict]:
    """(lo que vuelve: {llave: {mes: {col: monto}}}, lo que se pierde: igual forma)."""
    nuevas = set(llaves_nuevas)
    vuelve = {k: v for k, v in foto_vieja.items() if k in nuevas}
    pierde = {k: v for k, v in foto_vieja.items() if k not in nuevas}
    return vuelve, pierde


async def restaurar(db, scenario_id: str, year: int, nuevas, foto_vieja: dict) -> tuple[int, dict]:
    """Devuelve los conceptos a las posiciones nuevas con la misma llave.

    Devuelve (cuántos valores volvieron, lo que no encontró posición)."""
    from app.api.payroll_api import _get_or_create_entry
    por_llave = {}
    for p in nuevas:
        por_llave.setdefault(llave(p), p)    # si hay dos con la misma llave, va a la primera
    vuelve, pierde = cruzar(foto_vieja, por_llave)
    n = 0
    for k, meses in vuelve.items():
        pos = por_llave[k]
        for mes, vals in meses.items():
            entry = await _get_or_create_entry(db, scenario_id, pos, mes, year)
            for col, monto in vals.items():
                setattr(entry, col, monto)
                n += 1
    return n, pierde


def resumen_perdido(pierde: dict) -> list[dict]:
    """Lo perdido agrupado por posición y cuenta, para registrar y para la respuesta."""
    out = []
    for k, meses in pierde.items():
        tot: dict = defaultdict(lambda: [Decimal("0"), 0])
        for vals in meses.values():
            for col, monto in vals.items():
                tot[col][0] += monto; tot[col][1] += 1
        for col, (monto, n) in tot.items():
            out.append({"dept_code": k[0], "position_code": k[1] if len(k) > 1 else "", "cuenta": cuenta_de(col),
                        "concepto": NOMBRE.get(col, col), "col": col, "meses": n, "monto": monto,
                        "detalle": " · ".join(str(x) for x in k[2:]) if len(k) > 2 else ""})
    return out


async def registrar(db, scenario_id: str, hotel_id: str, quien: str, origen: str, filas: list[dict]) -> None:
    """Una fila en `payroll_conceptos_borrados` por cada concepto borrado (monto ≠ 0)."""
    from app.models.payroll_concepto_borrado import PayrollConceptoBorrado
    for f in filas:
        if not f.get("monto"):
            continue
        db.add(PayrollConceptoBorrado(
            scenario_id=scenario_id, hotel_id=hotel_id or "", quien=(quien or "")[:160], origen=origen,
            cuenta=f["cuenta"], concepto=f.get("concepto", "")[:40], dept_code=f.get("dept_code", "") or "",
            position_code=(f.get("position_code", "") or "")[:40], meses=int(f.get("meses", 0) or 0),
            monto=Decimal(f["monto"]).quantize(Decimal("0.01")), detalle=(f.get("detalle", "") or "")[:400]))
