# -*- coding: utf-8 -*-
"""Rehace las tablas DERIVADAS de un escenario a partir de su detalle GL.

## Por que existe

Las cinco tablas de detalle por cuenta —`revenue_account_entries`,
`cost_entries`, `opex_entries`, `belowgop_account_entries` y la planilla
(`payroll_positions` con `position_code='GL'` + `payroll_concept_entries`)— las
escribe **un solo camino**: `POST /scenarios/import-gl-detail/`. Nada las deriva
de `actual_entries`, y ningun reporte avisa cuando faltan.

Asi que un escenario cuyo detalle GL llego por otra puerta —la carga original
del libro de trabajo, `apply-big-picture`, o un `copy-from` de antes del
2026-08-08, que no copiaba `gl_accounts` ni `costs`— queda con el mayor completo
y las derivadas vacias. Su P&L sale bien (para un escenario `imported` el motor
lee `actual_entries`), pero **la plantilla del Detalle sale sin esa clase**: el
owner la baja, la corrige y la vuelve a subir, y el reemplazo se lleva por
delante la plata que la plantilla nunca mostro.

Le paso al `FORECAST Working 2026`: 279 filas de mayor y CERO derivadas de
ingreso, costo, planilla y below-GOP. Su plantilla salia con $1.55M de opex y
nada mas, con $9.1M de movimiento escondido.

## Que hace

Reconstruye, con la MISMA agregacion del importador —`(dept_code,
account_code)`, sumando meses—, solo las tablas que estan **vacias**. Nunca pisa
una tabla que ya tiene filas: si el dato existe, manda el que esta.

Excluye las contrapartidas de allocation (clase 4 «Distribucion»), igual que el
parser: son el credito con que Cafeteria y Lavanderia reparten su costo, no
ingreso.

**No mueve el P&L.** Para un escenario `imported` el motor calcula desde
`actual_pl_lines` / `actual_entries`; ninguna de estas cinco tablas entra en
`_compute_pl_month_core`. Verificado con `scripts.foto_lineas` antes y despues.

    python -m scripts.derivadas_desde_gl                       # que haria, en todos
    python -m scripts.derivadas_desde_gl "FORECAST Working 2026"
    python -m scripts.derivadas_desde_gl "FORECAST Working 2026" --aplicar
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_M = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
      "nov", "dec"]


def etiqueta(e) -> str:
    return f"{e.type} {e.version} {e.year}"


def _agrupar(filas, prefijo: str, excluir=None) -> dict:
    """{(dept, cuenta): {'nombre': str, 'meses': {1..12: Decimal}}} de una clase.

    La misma agregacion del importador: el mayor puede traer la misma cuenta
    varias veces (outlets, origenes) y se suman. El nombre que queda es el de la
    fila que MAS aporta, como en `_agg` de `scenarios_api`.
    """
    fuera: dict = {}
    for e in filas:
        code = str(e.account_code or "")
        if not code.startswith(prefijo):
            continue
        if excluir and excluir(code, e.account_name or ""):
            continue
        k = ((e.dept_code or ""), code)
        a = fuera.setdefault(k, {"nombre": "", "_mejor": Decimal("-1e18"),
                                 "meses": {i: Decimal("0") for i in range(1, 13)}})
        total = Decimal("0")
        for i, m in enumerate(_M, start=1):
            v = Decimal(str(getattr(e, m) or 0))
            a["meses"][i] += v
            total += v
        if total > a["_mejor"]:
            a["_mejor"] = total
            a["nombre"] = e.account_name or ""
    return fuera


async def _reconstruir(db, esc, aplicar: bool) -> list[str]:
    from sqlalchemy import select, func
    from app.models.actual_entry import ActualEntry
    from app.models.revenue_account_entry import RevenueAccountEntry
    from app.models.cost_entry import CostEntry
    from app.models.opex_entry import OpexEntry
    from app.models.belowgop_account_entry import BelowGopAccountEntry
    from app.models.payroll_position import PayrollPosition
    from app.models.payroll_concept_entry import PayrollConceptEntry
    from app.importers.gl_detail_importer import (
        es_contrapartida_de_allocation, CONCEPT_BY_ACCT)

    gl = (await db.execute(select(ActualEntry).where(
        ActualEntry.scenario_id == esc.id))).scalars().all()
    if not gl:
        return ["sin detalle GL: no hay de donde reconstruir"]

    notas: list[str] = []

    async def vacia(Model) -> bool:
        n = (await db.execute(select(func.count()).select_from(Model).where(
            Model.scenario_id == esc.id))).scalar_one()
        return n == 0

    # ── clases 4 / 5 / 7 / 8 ────────────────────────────────────────────────
    plan = [
        (RevenueAccountEntry, "4", "ingreso", es_contrapartida_de_allocation),
        (CostEntry, "5", "costo", None),
        (OpexEntry, "7", "opex", None),
        (BelowGopAccountEntry, "8", "below-GOP", None),
    ]
    for Model, prefijo, nombre, excluir in plan:
        agrup = _agrupar(gl, prefijo, excluir)
        if not agrup:
            continue
        if not await vacia(Model):
            notas.append(f"{nombre}: ya tiene filas, no se toca")
            continue
        total = sum(sum(a["meses"].values()) for a in agrup.values())
        notas.append(f"{nombre}: {len(agrup)} filas, {float(total):,.2f}"
                     + ("" if aplicar else "  (solo listado)"))
        if not aplicar:
            continue
        for (dept, code), a in agrup.items():
            extra = ({"detail_code": "", "detail_desc": a["nombre"]}
                     if Model is OpexEntry else {})
            db.add(Model(scenario_id=esc.id, hotel_id=esc.hotel_id, dept_code=dept,
                         account_code=code, account_name=a["nombre"], **extra,
                         **{m: a["meses"][i + 1] for i, m in enumerate(_M)}))

    # ── clase 6: posiciones sinteticas «(Actual GL)» + conceptos ────────────
    #
    # Se replica lo que hace el importador: una posicion por departamento con
    # `position_code='GL'`, salario y FTE en cero (aporta costo, no headcount), y
    # un `PayrollConceptEntry` por (depto, mes) con el monto en su columna.
    #
    # ⚠️ Estas filas sobreviven a «Recalcular»: `_recalc_payroll` protege
    # expresamente la fila que trae numeros y cuya posicion no tiene salario.
    por_concepto: dict[tuple, dict] = {}
    nombres_depto: dict[str, str] = {}
    sin_concepto: set[str] = set()
    for e in gl:
        code = str(e.account_code or "")
        if not code.startswith("6"):
            continue
        col = CONCEPT_BY_ACCT.get(code)
        if not col:
            sin_concepto.add(code)
            continue
        dept = e.dept_code or ""
        nombres_depto.setdefault(dept, "")
        for i, m in enumerate(_M, start=1):
            v = Decimal(str(getattr(e, m) or 0))
            if not v:
                continue
            a = por_concepto.setdefault((dept, i), {})
            a[col] = a.get(col, Decimal("0")) + v

    if sin_concepto:
        notas.append("planilla: cuentas 6xxx sin concepto conocido -> "
                     + ", ".join(sorted(sin_concepto)))
    if por_concepto:
        if not await vacia(PayrollConceptEntry):
            notas.append("planilla: ya tiene conceptos, no se toca")
        else:
            total = sum(sum(v.values()) for v in por_concepto.values())
            depts = {d for (d, _m) in por_concepto}
            notas.append(f"planilla: {len(depts)} deptos / {len(por_concepto)} filas, "
                         f"{float(total):,.2f}" + ("" if aplicar else "  (solo listado)"))
            if aplicar:
                # Nombre canonico del depto: el de una posicion real, si la hay.
                reales = (await db.execute(select(
                    PayrollPosition.dept_code, PayrollPosition.dept_name).where(
                    PayrollPosition.scenario_id == esc.id,
                    PayrollPosition.position_code != "GL"))).all()
                nombre_real = {c: n for c, n in reales if n}
                existentes = {p.dept_code: p for p in (await db.execute(
                    select(PayrollPosition).where(
                        PayrollPosition.scenario_id == esc.id,
                        PayrollPosition.position_code == "GL"))).scalars().all()}
                for d in sorted(depts):
                    if d in existentes:
                        continue
                    pos = PayrollPosition(
                        scenario_id=esc.id, hotel_id=esc.hotel_id, dept_code=d,
                        dept_name=nombre_real.get(d, ""), position_code="GL",
                        position_name="(Actual GL)", employee_name="(Actual GL)",
                        salary_amount=Decimal("0"), salary_currency="USD",
                        **{f"fte_{m}": Decimal("0") for m in _M})
                    db.add(pos)
                    existentes[d] = pos
                await db.flush()
                for (d, mes), cols in por_concepto.items():
                    db.add(PayrollConceptEntry(
                        scenario_id=esc.id, position_id=existentes[d].id,
                        dept_code=d, month=mes, year=esc.year, **cols))

    return notas


async def main(argv: list[str]) -> int:
    aplicar = "--aplicar" in argv
    nombres = [a for a in argv if not a.startswith("--")]

    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.scenario import Scenario

    async with SessionLocal() as db:
        escs = list((await db.execute(select(Scenario).order_by(
            Scenario.year, Scenario.type, Scenario.version))).scalars())

    if nombres:
        pedido = " ".join(nombres).lower()
        objetivo = [e for e in escs if etiqueta(e).lower() == pedido]
        if not objetivo:
            print(f"No encontre '{' '.join(nombres)}'. Hay:")
            for e in escs:
                print("  ", etiqueta(e))
            return 1
    else:
        objetivo = escs

    for e in objetivo:
        async with SessionLocal() as db:
            esc = await db.get(Scenario, e.id)
            notas = await _reconstruir(db, esc, aplicar)
            if aplicar and notas:
                # Un escenario enllavado no se toca a escondidas: se dice y se
                # salta. Destrabarlo es decision del owner.
                if esc.is_locked:
                    print(f"{etiqueta(e):<26} ENLLAVADO — no se escribio nada")
                    await db.rollback()
                    continue
                await db.commit()
        pendiente = [n for n in notas if "no se toca" not in n]
        if pendiente:
            print(f"{etiqueta(e)}")
            for n in pendiente:
                print(f"    {n}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
