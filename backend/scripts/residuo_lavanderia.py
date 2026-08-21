# -*- coding: utf-8 -*-
"""Mide el RESIDUO de la lavandería: lo que el 0161 no logró sacarse de encima.

SOLO LECTURA. No escribe una fila.

El 0161 «Laundry Operations» es un departamento de reparto: todo su costo tiene
que salir hacia los demás y el departamento cerrar en cero. Cuando no cierra,
lo que queda es el RESIDUO — y no vale medirlo igual en los dos mundos:

* **Escenario que CALCULA** (checkbook): el motor escribe `allocation_entries`.
  El residuo = costo del 0161 − crédito de reparto (cuenta 4999). Aparece
  cuando un balde se queda **sin base para repartir**: sin kilos no hay linen,
  sin FTE no hay uniformes. Ese costo no se reparte NI se acredita, y se queda.
  Es el mismo modo de falla que la cafetería de octubre.

* **Escenario que SUBIÓ sus números** (histórico): el reparto ya viene hecho en
  el mayor y el motor no escribe nada. El residuo = gastos del 0161 − la cuenta
  de distribución (4900). El ingreso del servicio (47xx) NO entra: es ingreso,
  no algo que se reparta.

⚠️ Medir `allocation_entries` sola NO sirve: siempre suma cero por construcción
—el crédito se calcula de lo repartido—, así que un balde que nunca se repartió
es invisible ahí. Hay que comparar contra el COSTO del departamento.

⚠️ En un forecast los meses hasta `actuals_through` están CERRADOS: el reporte
los lee del ACTUAL enlazado, no de sus propias filas. Se saltan acá, o se cuenta
dos veces el residuo del ACTUAL y el del forecast no coincide con el reporte.

Uso:
    python -m scripts.residuo_lavanderia            # todos los escenarios
    python -m scripts.residuo_lavanderia --json     # para diffear
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

ZERO = Decimal("0")
CENTAVO = Decimal("0.01")
FUENTE = "0161"
CUENTA_CREDITO = "4999"      # donde el MOTOR deposita el crédito de reparto
CUENTA_DISTRIB = "4900"      # donde el MAYOR trae el reparto ya hecho
MESES = ["ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic"]


def _d(x) -> Decimal:
    return Decimal(str(x or 0))


async def _residuo_calculado(session, scenario) -> dict:
    """Escenario que calcula: costo del 0161 contra el crédito 4999."""
    from sqlalchemy import select
    from app.models.allocation_entry import AllocationEntry
    from app.models.laundry_allocation_config import LaundryAllocationConfig
    from app.models.laundry_params import LaundryParams
    from app.models.payroll_position import PayrollPosition
    from app.engine.recalculate import _dept_total_cost, MONTH_ATTRS

    filas = (await session.execute(
        select(AllocationEntry).where(
            AllocationEntry.scenario_id == scenario.id,
            AllocationEntry.allocation_type == "LAUNDRY",
        )
    )).scalars().all()

    cfgs = {c.dept_code: c for c in (await session.execute(
        select(LaundryAllocationConfig).where(
            LaundryAllocationConfig.scenario_id == scenario.id)
    )).scalars() if c.participates}
    params = (await session.execute(
        select(LaundryParams).where(LaundryParams.scenario_id == scenario.id)
    )).scalar_one_or_none()
    positions = (await session.execute(
        select(PayrollPosition).where(PayrollPosition.scenario_id == scenario.id)
    )).scalars().all()

    meses = []
    for m in range(1, 13):
        costo = await _dept_total_cost(session, scenario.id, FUENTE, m)
        del_mes = [f for f in filas if f.month == m]
        credito = sum((_d(f.amount_usd) for f in del_mes
                       if f.account == CUENTA_CREDITO), ZERO)
        repartido = sum((_d(f.amount_usd) for f in del_mes
                         if f.account != CUENTA_CREDITO), ZERO)

        # Las tres bases del mes: sin base, el balde no se reparte ni se acredita.
        kilos_por_dept = {dc: _d(c.kilos_for(m)) for dc, c in cfgs.items()}
        kilos_linen = sum(kilos_por_dept.values(), ZERO)
        kilos_uni = _d(params.uniformes_for(m)) if params else ZERO
        kilos_gst = _d(params.huespedes_for(m)) if params else ZERO
        fte_attr = f"fte_{MONTH_ATTRS[m - 1]}"
        fte = sum((_d(getattr(p, fte_attr)) for p in positions
                   if p.dept_code in cfgs), ZERO)

        # Los dos únicos modos en que el motor deja plata adentro del 0161.
        # Linen no puede: los kilos por depto son a la vez el tamaño del balde y
        # el peso del reparto, así que o hay kilos y hay a quién, o no hay balde.
        # Huéspedes tampoco: va a un solo departamento, sin pesos.
        kilos_total = kilos_linen + kilos_uni + kilos_gst
        sin_base = []
        if costo:
            if kilos_total <= ZERO:
                sin_base.append("TODO el costo (ni un kilo cargado: no reparte nada)")
            elif kilos_uni > ZERO and fte <= ZERO:
                sin_base.append("uniformes (hay kilos pero ningun FTE que lo reciba)")

        meses.append({
            "mes": m,
            "costo": costo,
            "repartido": repartido,
            "credito": credito,
            "residuo": costo + credito,     # el crédito viene negativo
            "kilos_linen": kilos_linen,
            "kilos_uniformes": kilos_uni,
            "kilos_huespedes": kilos_gst,
            "fte": fte,
            "sin_base": sin_base,
        })
    return {"modo": "calculado", "meses": meses}


async def _residuo_subido(session, scenario) -> dict:
    """Histórico: los gastos del 0161 contra la cuenta de distribución 4900.

    Devuelve además de qué CUENTA es cada dólar del residuo, que es la única
    forma de distinguir «al mayor le faltó meter una cuenta en la distribución»
    de «la distribución se pasó por unos centavos».
    """
    from sqlalchemy import select
    from app.models.actual_entry import ActualEntry

    filas = (await session.execute(
        select(ActualEntry).where(
            ActualEntry.scenario_id == scenario.id,
            ActualEntry.dept_code == FUENTE,
        )
    )).scalars().all()

    cerrados = int(getattr(scenario, "actuals_through", 0) or 0)
    cols = ["jan", "feb", "mar", "apr", "may", "jun",
            "jul", "aug", "sep", "oct", "nov", "dec"]
    meses = []
    por_cuenta: dict[str, Decimal] = {}
    for i, col in enumerate(cols, start=1):
        if i <= cerrados:
            # Mes cerrado: el reporte lo lee del ACTUAL enlazado. Su residuo se
            # mide allá, no acá.
            meses.append({"mes": i, "costo": ZERO, "repartido": ZERO,
                          "credito": ZERO, "residuo": ZERO, "ingreso": ZERO,
                          "cerrado": True, "sin_base": []})
            continue
        gasto = ZERO
        distrib = ZERO
        ingreso = ZERO
        for f in filas:
            v = _d(getattr(f, col))
            if not v:
                continue
            cod = (f.account_code or "").strip()
            if cod == CUENTA_DISTRIB:
                distrib += v
            elif cod.startswith("4"):
                ingreso += v            # el servicio vendido: no se reparte
            else:
                gasto += v
                por_cuenta[f"{cod} {f.account_name}".strip()] = (
                    por_cuenta.get(f"{cod} {f.account_name}".strip(), ZERO) + v)
        por_cuenta[f"{CUENTA_DISTRIB} (distribución)"] = (
            por_cuenta.get(f"{CUENTA_DISTRIB} (distribución)", ZERO) + distrib)
        meses.append({
            "mes": i,
            "costo": gasto,
            "repartido": -distrib,
            "credito": distrib,
            "residuo": gasto + distrib,
            "ingreso": ingreso,
            "cerrado": False,
            "sin_base": [],
        })
    return {"modo": "subido", "meses": meses, "meses_cerrados": cerrados,
            "por_cuenta": por_cuenta}


async def medir() -> list[dict]:
    from scripts._prodenv import usar_produccion
    usar_produccion()
    from sqlalchemy import select
    from app.db import SessionLocal
    from app.models.scenario import Scenario
    from app.engine.recalculate import lo_subido_manda

    salida = []
    async with SessionLocal() as db:
        escenarios = (await db.execute(
            select(Scenario).order_by(Scenario.year, Scenario.type, Scenario.version)
        )).scalars().all()
        for s in escenarios:
            subido = s.type == "ACTUAL" or await lo_subido_manda(db, s)
            r = await (_residuo_subido if subido else _residuo_calculado)(db, s)
            r["escenario"] = f"{s.type} {s.version} {s.year}"
            r["id"] = s.id
            r["status"] = s.status
            salida.append(r)
    return salida


def _fmt(x: Decimal) -> str:
    return f"{x:>12,.2f}"


def informe(datos: list[dict]) -> None:
    print("")
    print("RESIDUO DE LA LAVANDERIA (0161) - lo que no salio del departamento")
    print("=" * 84)
    limpio, sucio = [], []
    for e in datos:
        total_costo = sum((m["costo"] for m in e["meses"]), ZERO)
        total_res = sum((m["residuo"] for m in e["meses"]), ZERO)
        (sucio if abs(total_res) >= CENTAVO else limpio).append(
            (e, total_costo, total_res))

    for e, costo, res in sucio:
        print("")
        cerr = e.get("meses_cerrados") or 0
        nota = f", {cerr} mes(es) cerrado(s) se miden en el ACTUAL" if cerr else ""
        print(f"> {e['escenario']}  [{e['modo']}, {e['status']}{nota}]")
        print(f"  costo del 0161: {_fmt(costo)}   RESIDUO: {_fmt(res)}")
        print(f"  {'mes':>5} {'costo':>12} {'repartido':>12} {'credito':>12} "
              f"{'residuo':>12}   por que")
        for m in e["meses"]:
            if abs(m["residuo"]) < CENTAVO:
                continue
            por_que = ", ".join(m["sin_base"]) or "-"
            print(f"  {MESES[m['mes']-1]:>5} {_fmt(m['costo'])} "
                  f"{_fmt(m['repartido'])} {_fmt(m['credito'])} "
                  f"{_fmt(m['residuo'])}   {por_que}")
        # ¿Hay UNA cuenta que explique el residuo entero? Es la diferencia entre
        # «al mayor le faltó repartir una cuenta» y «se pasó por centavos».
        culpables = [(k, v) for k, v in (e.get("por_cuenta") or {}).items()
                     if abs(v - res) < CENTAVO and not k.startswith(CUENTA_DISTRIB)]
        if culpables:
            for k, v in culpables:
                print(f"  --> lo explica ENTERO la cuenta {k}: {v:,.2f} "
                      f"(la 4900 nunca la repartio)")

    if limpio:
        print("")
        print("> Cierran en cero (no se listan mes a mes):")
        for e, costo, _ in limpio:
            marca = "sin costo" if abs(costo) < CENTAVO else f"costo {costo:,.2f}"
            print(f"    - {e['escenario']:<28} [{e['modo']:>9}]  {marca}")

    total = sum((m["residuo"] for e in datos for m in e["meses"]), ZERO)
    print("")
    print("=" * 84)
    print(f"{len(sucio)} escenario(s) con residuo | {len(limpio)} en cero | "
          f"suma de todos los residuos: {total:,.2f}")


if __name__ == "__main__":
    datos = asyncio.run(medir())
    if "--json" in sys.argv:
        print(json.dumps(datos, default=str, ensure_ascii=False, indent=2))
    else:
        informe(datos)
