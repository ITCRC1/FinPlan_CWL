# -*- coding: utf-8 -*-
"""Posiciones, checkbook de planilla y checkbook de OPEX para el Excel en vivo.

Owner, 2026-11-11: *«puedes meter el tab de posiciones por mes y su costo y
además el checkbook de gastos y checkbook de planilla»*.

⚠️ **Esto cambia una regla del consolidado, y la cambió el owner.** El
`consolidado_api` nació (2026-08-14) diciendo que por la llave de solo lectura
NO salían planilla por persona ni nombres. El 2026-11-11, preguntado
explícitamente —«un puesto con una sola persona muestra el salario de esa
persona a cualquiera que tenga la llave»—, el owner eligió **«con nombre y
salario»**. Quien tenga la llave ve la planilla persona por persona: la llave
se reparte con ese cuidado.

**Las cifras salen del MISMO armado que la pantalla.** Posiciones y planilla
reusan `payroll_position_report_api.planilla_por_posicion` —el reporte
«Planilla por código de posición»—; el OPEX lee `opex_entries` como el
checkbook. Una segunda lectura «que hace lo mismo» termina dando otra cifra el
día que una de las dos cambia.

Se resuelve por **año + tipo + versión**, con el mismo criterio del resto del
consolidado (`_escoger_escenario`): el ★ Current del forecast, el ACTUAL real.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.errores import ErrorApi
from app.auth import lector_del_consolidado
from app.db import get_session
from app.hotel_actual import HOTEL_ID, HOTEL_NAME
from app.models.scenario import Scenario

router = APIRouter()

TIPOS = ("BUDGET", "FORECAST", "ACTUAL")
CONTRATO = 1


async def _escenario(session, year: int, tipo: str, version: str | None) -> Scenario:
    from app.api.consolidado_api import _escoger_escenario

    tipo = tipo.upper()
    if tipo not in TIPOS:
        raise ErrorApi(422, "consolidado.tipo_invalido", tipos=", ".join(TIPOS))
    escenarios = (await session.execute(
        select(Scenario).where(Scenario.hotel_id == HOTEL_ID, Scenario.year == year,
                               Scenario.type == tipo)
        .order_by(Scenario.created_at.desc()))).scalars().all()
    escenario = _escoger_escenario(list(escenarios), tipo, version)
    if escenario is None:
        if version:
            raise ErrorApi(404, "consolidado.sin_escenario_version",
                           propiedad=HOTEL_NAME, tipo=tipo, version=version, anio=year)
        raise ErrorApi(404, "consolidado.sin_escenario", propiedad=HOTEL_NAME, tipo=tipo, anio=year)
    return escenario


def _cabecera(escenario: Scenario, tipo: str) -> dict:
    return {
        "contrato": CONTRATO,
        "hotel_id": HOTEL_ID,
        "hotel_name": HOTEL_NAME,
        "year": escenario.year,
        "tipo": tipo.upper(),
        "escenario": {"id": escenario.id, "version": escenario.version,
                      "status": escenario.status,
                      "actuals_through": escenario.actuals_through or 0},
    }


# ── Armado puro (sin base): lo que se prueba ─────────────────────────────────

def filas_posiciones(reporte: dict) -> list[dict]:
    """Una fila por posición: FTE y costo de cada mes.

    El costo del mes es la suma de los 17 conceptos de ESE mes, el mismo número
    que viaja al P&L. El anual es la suma de los doce meses ya redondeados, así
    la fila cuadra contra sus propias columnas.
    """
    claves = [c["key"] for c in reporte["conceptos"]]
    out = []
    for f in reporte["rows"]:
        costo = [round(sum(f["meses"][k][m] for k in claves), 2) for m in range(12)]
        out.append({
            "dept": f["dept_code"], "dept_name": f["dept_name"],
            "codigo": f["position_code"], "puesto": f["position_name"],
            "empleado": f["employee_name"], "tipo_plaza": f.get("employee_type", ""),
            "moneda": f["salary_currency"], "salario": f["salary_amount"],
            "fte": f["fte"], "fte_prom": f["fte_prom"],
            "costo": costo, "costo_anual": round(sum(costo), 2),
            "devengado": f["devengado"], "cargas": f["cargas"],
            "beneficios": f["beneficios"],
        })
    return out


def filas_planilla(reporte: dict) -> list[dict]:
    """El checkbook de planilla: posición × concepto × mes.

    Solo los conceptos con alguna cifra en el año: los 17 conceptos de cada
    posición, la mayoría en cero, harían una tabla de miles de filas vacías.
    """
    # El depto con que la MISMA plata aparece en el GL: el checkbook guarda el
    # sub-depto (0111 Front Desk) y el mayor por mes lo sube a su padre (0110),
    # salvo los que muestra aparte (Villas 0115). Sin esto el control
    # «checkbook vs GL» del libro en vivo no podría cruzar fila contra fila
    # (owner, 2026-11-12: «los checkbooks de planilla con el gl para poder
    # auditar los datos calculados»).
    from app.api.gl_api import DEPTOS_PROPIOS_EN_EL_MAYOR
    from app.engine import pl_engine

    def dept_gl(d: str) -> str:
        d = (d or "").strip()
        return d if d in DEPTOS_PROPIOS_EN_EL_MAYOR else pl_engine.consolidate_dept(d)

    out = []
    for f in reporte["rows"]:
        for c in reporte["conceptos"]:
            meses = f["meses"][c["key"]]
            if not any(abs(v) > 0.004 for v in meses):
                continue
            out.append({
                "dept": f["dept_code"], "dept_name": f["dept_name"],
                "dept_gl": dept_gl(f["dept_code"]),
                "codigo": f["position_code"], "puesto": f["position_name"],
                "empleado": f["employee_name"],
                "cuenta": c["code"], "concepto": c["label"], "grupo": c["grupo"],
                "meses": [round(v, 2) for v in meses],
                "anual": round(sum(round(v, 2) for v in meses), 2),
            })
    return out


def filas_opex(entradas, nombres_dept: dict[str, str]) -> list[dict]:
    """El checkbook de OPEX: cuenta × detalle × mes, en USD.

    Una línea en colones trae el dólar DERIVADO con el TC de cada mes (mig 077)
    — el mismo que suma el P&L —; la moneda va en su columna para que se sepa.
    """
    out = []
    for e in entradas:
        meses = [round(float(e.get_month(m) or 0), 2) for m in range(1, 13)]
        out.append({
            "dept": e.dept_code, "dept_name": nombres_dept.get(e.dept_code, ""),
            "cuenta": e.account_code, "nombre": e.account_name or "",
            "detalle": e.detail_code or "", "detalle_desc": e.detail_desc or "",
            "moneda": e.currency or "USD",
            "meses": meses, "anual": round(sum(meses), 2),
        })
    out.sort(key=lambda r: (r["dept"], r["cuenta"], r["detalle"]))
    return out


def filas_costos(entradas, nombres_dept: dict[str, str]) -> list[dict]:
    """El checkbook de costo de ventas (clase 5): depto × cuenta × mes, en USD.

    Owner, 2026-11-11 (Ojochal): «mete tambien el checkbook de costos de
    ventas». Los montos son los guardados —los que suma el P&L—: una línea con
    driver ya viene recalculada (% del ingreso, por noche, por huésped…), y el
    modo y el driver van en sus columnas para que se vea de dónde sale la cifra.
    Una línea en colones trae el dólar derivado con el TC de cada mes, como el OPEX.
    """
    out = []
    for e in entradas:
        meses = [round(float(e.get_month(m) or 0), 2) for m in range(1, 13)]
        out.append({
            "dept": e.dept_code, "dept_name": nombres_dept.get(e.dept_code, ""),
            "cuenta": e.account_code, "nombre": e.account_name or "",
            "modo": e.calc_mode or "MANUAL", "driver": e.driver_type or "",
            "tasa": float(e.driver_pct_or_rate or 0),
            "linea_ingreso": e.revenue_line_ref or "",
            "moneda": e.currency or "USD",
            "meses": meses, "anual": round(sum(meses), 2),
        })
    out.sort(key=lambda r: (r["dept"], r["cuenta"]))
    return out


# ── Endpoints ────────────────────────────────────────────────────────────────

async def _reporte_planilla(session, escenario: Scenario) -> dict:
    from app.api.payroll_position_report_api import planilla_por_posicion
    from app.models.payroll_position import PayrollPosition

    rep = await planilla_por_posicion(escenario.id, dept="", db=session)
    # El reporte de la pantalla no trae el tipo de plaza; se agrega acá sin
    # tocar su contrato.
    tipos = dict((await session.execute(
        select(PayrollPosition.id, PayrollPosition.employee_type)
        .where(PayrollPosition.scenario_id == escenario.id))).all())
    for f in rep["rows"]:
        f["employee_type"] = tipos.get(f["position_id"], "") or ""
    return rep


@router.get("/consolidado/posiciones/")
async def consolidado_posiciones(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Posiciones por mes: FTE y costo, con nombre y salario (owner, 2026-11-11)."""
    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        rep = await _reporte_planilla(session, escenario)
    return {**_cabecera(escenario, tipo), "posiciones": filas_posiciones(rep)}


@router.get("/consolidado/planilla/")
async def consolidado_planilla(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Checkbook de planilla: posición × concepto (6000–6030) × mes."""
    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        rep = await _reporte_planilla(session, escenario)
    return {**_cabecera(escenario, tipo), "lineas": filas_planilla(rep)}


@router.get("/consolidado/opex/")
async def consolidado_opex(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Checkbook de OPEX: departamento × cuenta × detalle × mes, en USD."""
    from app.models.department_catalog import DepartmentCatalog
    from app.models.opex_entry import OpexEntry

    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        entradas = (await session.execute(
            select(OpexEntry).where(OpexEntry.scenario_id == escenario.id))).scalars().all()
        nombres = dict((await session.execute(
            select(DepartmentCatalog.dept_code, DepartmentCatalog.dept_name))).all())
    return {**_cabecera(escenario, tipo), "lineas": filas_opex(entradas, nombres)}


@router.get("/consolidado/costos/")
async def consolidado_costos(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Checkbook de costo de ventas (clase 5): departamento × cuenta × mes, en USD."""
    from app.models.cost_entry import CostEntry
    from app.models.department_catalog import DepartmentCatalog

    async with get_session() as session:
        escenario = await _escenario(session, year, tipo, version)
        entradas = (await session.execute(
            select(CostEntry).where(CostEntry.scenario_id == escenario.id))).scalars().all()
        nombres = dict((await session.execute(
            select(DepartmentCatalog.dept_code, DepartmentCatalog.dept_name))).all())
    return {**_cabecera(escenario, tipo), "lineas": filas_costos(entradas, nombres)}


# ── Estadísticas por tipo de habitación y por set ────────────────────────────
#
# Owner, 2026-11-12: «las estadísticas que traigan también máximo detalle para
# habitaciones estándares y para villas». `/consolidado/estadisticas/` da el
# total del hotel (el encabezado del P&L); esta ruta lo abre por SET (0110
# estándar · 0115 Villas · 0116 Residencias) y por TIPO de habitación, mes a mes.
#
# Las cifras salen de donde ya salen en la app, con la misma regla que Plan vs.
# Integrity (`stats_integrity_api.plan`):
#   - ACTUAL: la estadística real por tipo (`actual_room_stats`, la de Room
#     Stats). 2024 y 2025 no la tienen: va el total del mes, «sin tipo».
#   - FORECAST con corte: meses cerrados del ACTUAL enlazado por tipo; los
#     propios solo tienen el total, «sin tipo».
#   - BUDGET y el resto: «Ingresos por tipo» de los drivers (noches × neta).

ROTULO_SET = {"0110": "Habitaciones estándar", "0115": "Villas", "0116": "Residencias"}


def _kpis(d: float, o: float, ing: float | None) -> dict:
    """Ocupación, ADR y RevPAR de las SUMAS, nunca promediando porcentajes."""
    return {"ocupacion": (o / d) if d else None,
            "adr": (ing / o) if o and ing is not None else None,
            "revpar": (ing / d) if d and ing is not None else None}


def filas_habitaciones(tipos: list[dict], por_tipo: dict, sin_tipo: dict) -> list[dict]:
    """Filas largas (una por tipo × mes), más el subtotal de cada set y el del hotel.

    `tipos`: [{"codigo","nombre","depto","unidades"}] en el orden del inventario.
    `por_tipo`: {(codigo, mes): {"disponibles","ocupadas","pax","ingreso"}}.
    `sin_tipo`: {mes: {...}} para los meses que el escenario solo trae en total
        (no se inventa un reparto por tipo).
    """
    out: list[dict] = []
    acum: dict[tuple[str, str, int], dict] = {}

    def sumar(clave, d, o, p, ing, unidades):
        a = acum.setdefault(clave, {"disponibles": 0.0, "ocupadas": 0.0, "pax": 0.0,
                                    "ingreso": 0.0, "unidades": 0})
        a["disponibles"] += d
        a["ocupadas"] += o
        a["pax"] += p
        a["ingreso"] += ing or 0.0
        a["unidades"] += unidades or 0

    for t in tipos:
        for m in range(1, 13):
            v = por_tipo.get((t["codigo"], m))
            if v is None:
                continue
            d, o, p, ing = v["disponibles"], v["ocupadas"], v["pax"], v.get("ingreso")
            out.append({"nivel": "Tipo", "depto": t["depto"],
                        "set": ROTULO_SET.get(t["depto"], t["depto"]),
                        "codigo": t["codigo"], "tipo": t["nombre"], "unidades": t["unidades"],
                        "mes": m, "disponibles": d, "ocupadas": o, "pax": p, "ingreso": ing,
                        **_kpis(d, o, ing)})
            sumar(("Set", t["depto"], m), d, o, p, ing, t["unidades"])
            sumar(("Hotel", "", m), d, o, p, ing, t["unidades"])
    for m, v in sorted(sin_tipo.items()):
        d, o, p, ing = v["disponibles"], v["ocupadas"], v.get("pax", 0.0), v.get("ingreso")
        out.append({"nivel": "Sin tipo", "depto": "",
                    "set": "Total del mes (el escenario no lo abre por tipo)",
                    "codigo": "", "tipo": "", "unidades": None, "mes": m,
                    "disponibles": d, "ocupadas": o, "pax": p, "ingreso": ing, **_kpis(d, o, ing)})
        sumar(("Hotel", "", m), d, o, p, ing, 0)
    for (nivel, depto, m), a in sorted(acum.items(), key=lambda x: (x[0][0] != "Set", x[0][1], x[0][2])):
        out.append({"nivel": nivel, "depto": depto,
                    "set": ROTULO_SET.get(depto, depto) if nivel == "Set" else "Total hotel",
                    "codigo": "", "tipo": "", "unidades": a["unidades"] or None, "mes": m,
                    "disponibles": a["disponibles"], "ocupadas": a["ocupadas"], "pax": a["pax"],
                    "ingreso": a["ingreso"], **_kpis(a["disponibles"], a["ocupadas"], a["ingreso"])})
    return out


@router.get("/consolidado/habitaciones/")
async def consolidado_habitaciones(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Estadísticas de habitaciones por tipo y por set (estándar · Villas), mes a mes."""
    from app.api import revenue_api
    from app.engine import recalculate as rc
    from app.models.room_type_config import RoomTypeConfig
    from app.models.scenario_stat import ScenarioStat

    async with get_session() as session:
        esc = await _escenario(session, year, tipo, version)
        rts = (await session.execute(select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == HOTEL_ID)
                                     .order_by(RoomTypeConfig.sort_order))).scalars().all()
        tipos = [{"codigo": rt.code or "", "nombre": rt.name, "depto": rt.dept_code or "0110",
                  "unidades": rt.units}
                 for rt in rts
                 if rt.active and (rt.vigente_desde_anio is None or rt.vigente_desde_anio <= esc.year)]
        codigo_de_id = {rt.id: (rt.code or "") for rt in rts}

        def cargar(destino: dict, meses_rev: list, solo: set | None = None) -> None:
            for m in meses_rev:
                if solo is not None and m["month"] not in solo:
                    continue
                for r in m["rows"]:
                    c = r.get("room_type_code") or codigo_de_id.get(r.get("room_type_id"), "")
                    if c:
                        destino[(c, m["month"])] = {
                            "disponibles": float(r.get("nights_available") or 0),
                            "ocupadas": float(r.get("nights_occupied") or 0),
                            "pax": float(r.get("pax") or 0),
                            "ingreso": float(r.get("revenue") or 0)}

        async def totales(scenario_id: str, desde: int = 1) -> dict:
            out = {}
            for st in (await session.execute(select(ScenarioStat).where(
                    ScenarioStat.scenario_id == scenario_id))).scalars():
                if st.month >= desde:
                    o = float(st.rooms_occupied or 0)
                    out[st.month] = {"disponibles": float(st.rooms_available or 0), "ocupadas": o,
                                     "pax": float(st.guests or 0),
                                     "ingreso": o * float(st.adr) if st.adr is not None else None}
            return out

        por_tipo: dict = {}
        sin_tipo: dict = {}
        corte = int(esc.actuals_through or 0)
        if esc.type == "ACTUAL":
            ra = await revenue_api._room_stats_from_actuals(esc.id, esc.year, session)
            if ra:
                cargar(por_tipo, ra["months"])
            else:
                sin_tipo = await totales(esc.id)
        elif esc.type == "FORECAST" and corte > 0:
            actual = await rc.linked_actual_scenario(session, esc)
            if actual is not None:
                ra = await revenue_api._room_stats_from_actuals(actual.id, actual.year, session)
                if ra:
                    cargar(por_tipo, ra["months"], set(range(1, corte + 1)))
            sin_tipo = await totales(esc.id, desde=corte + 1)
        else:
            r = await revenue_api.get_revenue_by_room_type(esc.id, session)
            cargar(por_tipo, r["months"])

    return {**_cabecera(esc, tipo), "filas": filas_habitaciones(tipos, por_tipo, sin_tipo)}


# ── Repartos (Cafetería, Lavandería, salarios) ───────────────────────────────
#
# Owner, 2026-11-12: «yo quiero ver cafetería como un verdadero departamento de
# costos que acumula y después reparte y que al final queda en 0» · «igual que
# lavandería». El reparto ya existe (`allocation_entries`): el CRÉDITO en el
# centro (4999) y un CARGO en cada depto que lo recibe, por su cuenta. Esta ruta
# lo entrega tal cual, mes a mes, para que el libro en vivo arme el centro de
# costo: lo que acumula (del GL), lo que reparte y a quién.
#
# Solo lee. No recalcula el reparto: entrega el último que guardó el Recalcular.

def filas_repartos(entradas, nombres_dept: dict[str, str]) -> list[dict]:
    """Una fila por (tipo, centro, depto que recibe, cuenta) con los 12 meses.

    El crédito del centro (su 4999) va como una fila más, con `rol` = «crédito»:
    así la suma de cada tipo da 0 cuando el centro quedó en cero.
    """
    from app.api.gl_api import DEPTOS_PROPIOS_EN_EL_MAYOR
    from app.engine import pl_engine

    def dept_gl(d: str) -> str:
        d = (d or "").strip()
        return d if d in DEPTOS_PROPIOS_EN_EL_MAYOR else pl_engine.consolidate_dept(d)

    acum: dict[tuple, list[float]] = {}
    for e in entradas:
        k = ((e.allocation_type or "").upper(), (e.source_dept or "").strip(),
             (e.target_dept or "").strip(), (e.account or "").strip())
        fila = acum.setdefault(k, [0.0] * 12)
        if 1 <= int(e.month or 0) <= 12:
            fila[int(e.month) - 1] += float(e.amount_usd or 0)
    out = []
    for (tipo, origen, destino, cuenta), meses in sorted(acum.items()):
        meses = [round(v, 2) for v in meses]
        out.append({
            "tipo": tipo, "origen": origen, "origen_nombre": nombres_dept.get(origen, ""),
            "destino": destino, "destino_nombre": nombres_dept.get(destino, ""),
            "destino_gl": dept_gl(destino), "cuenta": cuenta,
            # Salarios: la salida del depto que presta a la persona es «sale» y su
            # contraparte «entra» — nunca un negativo suelto rotulado «cargo».
            "rol": ("crédito" if destino == origen and cuenta.startswith("4")
                    else ("sale" if destino == origen else "entra") if tipo == "SALARY"
                    else "cargo"),
            "meses": meses, "anual": round(sum(meses), 2),
        })
    return out


def filas_reparto_salarios(reglas: list[dict], guardado: dict, nombres: dict[str, str]) -> list[dict]:
    """El reparto de salarios regla por regla, para verlo de punta a punta.

    Owner, 2026-11-12: «una mucama que da servicios a cafetería de empleados. se
    hace la salida de housekeeping y entra en cafetería, esto debe verse muy
    transparente. no deben quedar líneas negativas perdidas» · «recrear en un tab
    el allocation de salarios para ver si es necesario hacer cambios».

    `reglas`: una por regla activa, ya calculada mes a mes con las mismas piezas
    del recálculo (`_reparto_salarios_recreado`). Cada regla deja sus renglones:
    lo que cuesta la posición, cómo se arma el costo cargado, lo que SALE del
    origen y lo que ENTRA a cada destino — la salida y su entrada, juntas.
    `guardado`: {(destino, mes): monto} de lo que el recálculo dejó en la base,
    para el control final (recreado − guardado, debe dar 0).
    """
    def fila(n, r, concepto, destino, meses, pct=None, nota=""):
        meses = [round(float(v), 2) for v in meses]
        return {"regla": n, "origen": r["origen"], "origen_nombre": nombres.get(r["origen"], ""),
                "posicion": r["posicion"], "puesto": r["puesto"], "empleados": r["empleados"],
                "destino": destino, "destino_nombre": nombres.get(destino, "") if destino else "",
                "cuenta": r["cuenta"], "concepto": concepto, "pct": pct, "nota": nota,
                "meses": meses, "anual": round(sum(meses), 2)}

    out: list[dict] = []
    recreado: dict[tuple, float] = {}
    for n, r in enumerate(reglas, 1):
        out.append(fila(n, r, "0 · Planilla completa de la posición (17 conceptos)", "", r["planilla"]))
        out.append(fila(n, r, "1 · Salario usado (SW)", "", r["sw"],
                        nota="salario manual" if any(r["override"]) else ""))
        out.append(fila(n, r, "1 · + CCSS", "", r["ccss"]))
        out.append(fila(n, r, "1 · + Aguinaldo", "", r["aguinaldo"]))
        out.append(fila(n, r, "1 · + Cafetería (% del salario)", "", r["cafeteria"], pct=r["cafeteria_pct"]))
        out.append(fila(n, r, "1 · + Ajuste manual", "", r["dummy"]))
        out.append(fila(n, r, "1 · = Costo cargado", "", r["cargado"]))
        out.append(fila(n, r, "2 · SALE del origen", r["origen"], r["sale"], pct=r["portion_pct"]))
        for d, meses in sorted(r["entra"].items()):
            out.append(fila(n, r, "2 · ENTRA al destino", d, meses))
            for m, v in enumerate(meses, 1):
                recreado[(d, m)] = recreado.get((d, m), 0.0) + float(v)
        for m, v in enumerate(r["sale"], 1):
            recreado[(r["origen"], m)] = recreado.get((r["origen"], m), 0.0) + float(v)
        neto = [sum(float(x) for x in col) for col in zip(r["sale"], *r["entra"].values())]
        out.append(fila(n, r, "3 · Sale + entra (debe dar 0)", "", neto))
        if not r["entra"]:
            out.append(fila(n, r, "3 · No se movió nada: los destinos no tienen FTE", "", [0] * 12))

    vacia = {"origen": "", "posicion": "", "puesto": "", "empleados": "", "cuenta": ""}
    for d in sorted({k[0] for k in list(recreado) + list(guardado)}):
        rec = [recreado.get((d, m), 0.0) for m in range(1, 13)]
        gua = [float(guardado.get((d, m), 0)) for m in range(1, 13)]
        out.append(fila(0, vacia, "4 · Control: recreado − guardado en la base", d,
                        [a - b for a, b in zip(rec, gua)]))
    return out


async def _reparto_salarios_recreado(session, esc) -> tuple[list[dict], dict]:
    """Vuelve a calcular cada regla de salarios con las MISMAS piezas del
    recálculo (calc_sw, loaded_salary_breakdown, calculate_salary_distribution).
    Solo lee: no escribe ni toca el reparto guardado."""
    from decimal import Decimal
    from app.engine.allocation_calculator import (
        calculate_salary_distribution, loaded_salary_breakdown)
    from app.engine.payroll_calculator import AGUINALDO_DIVISOR, CCSS_RATE, calc_sw
    from app.models.allocation_entry import AllocationEntry
    from app.models.exchange_rate import ExchangeRate, get_tc_for_month
    from app.models.payroll_concept_entry import PayrollConceptEntry
    from app.models.payroll_params import PayrollParams
    from app.engine.recalculate import MONTH_ATTRS
    from app.models.payroll_position import PayrollPosition
    from app.models.salary_allocation_config import SalaryAllocationConfig

    sid = esc.id
    cfgs = [c for c in (await session.execute(select(SalaryAllocationConfig).where(
        SalaryAllocationConfig.scenario_id == sid))).scalars() if c.active]
    positions = (await session.execute(select(PayrollPosition).where(
        PayrollPosition.scenario_id == sid))).scalars().all()
    rates = (await session.execute(select(ExchangeRate).where(
        ExchangeRate.scenario_id == sid))).scalars().all()
    pp = (await session.execute(select(PayrollParams).where(
        PayrollParams.scenario_id == sid))).scalar_one_or_none()
    ccss_rate = pp.ccss_rate if pp else CCSS_RATE
    agu_div = pp.aguinaldo_divisor if pp else AGUINALDO_DIVISOR
    conceptos = (await session.execute(select(PayrollConceptEntry).where(
        PayrollConceptEntry.scenario_id == sid))).scalars().all()
    claves = [c.key for c in PayrollConceptEntry.__table__.columns if c.key.startswith("c6")]
    planilla_pos: dict[tuple, float] = {}
    for e in conceptos:
        k = (e.position_id, int(e.month))
        planilla_pos[k] = planilla_pos.get(k, 0.0) + sum(float(getattr(e, c) or 0) for c in claves)

    Z = Decimal("0")
    reglas = []
    for cfg in cfgs:
        fuente = [p for p in positions
                  if p.dept_code == cfg.source_dept and p.position_code == cfg.position_code]
        ov = list(getattr(cfg, "salary_override", None) or [])
        dm = list(getattr(cfg, "dummy_monthly", None) or [])
        targets = [t for t in (cfg.target_depts or []) if t]
        r = {"origen": cfg.source_dept, "posicion": cfg.position_code,
             "puesto": cfg.position_name or (fuente[0].position_name if fuente else ""),
             "empleados": ", ".join(sorted({(p.employee_name or "").strip() for p in fuente})),
             "cuenta": cfg.account or "6000",
             "portion_pct": float(cfg.portion_pct or 0),
             "cafeteria_pct": float(getattr(cfg, "cafeteria_pct", 0) or 0),
             "override": [bool(ov[i]) if i < len(ov) else False for i in range(12)],
             "planilla": [], "sw": [], "ccss": [], "aguinaldo": [], "cafeteria": [],
             "dummy": [], "cargado": [], "sale": [], "entra": {}}
        for month in range(1, 13):
            tc = get_tc_for_month(rates, month)
            if month - 1 < len(ov) and ov[month - 1]:
                sw = Decimal(str(ov[month - 1]))
            else:
                sw = sum((calc_sw(p, month, tc) for p in fuente), Z)
            b = loaded_salary_breakdown(sw, ccss_rate, agu_div, getattr(cfg, "cafeteria_pct", Z))
            dummy = Decimal(str(dm[month - 1])) if month - 1 < len(dm) and dm[month - 1] else Z
            cargado = b["total"] + dummy
            fte_attr = f"fte_{MONTH_ATTRS[month - 1]}"
            tgt_fte: dict[str, Decimal] = {}
            for p in positions:
                if p.dept_code in targets:
                    tgt_fte[p.dept_code] = tgt_fte.get(p.dept_code, Z) + (getattr(p, fte_attr) or Z)
            filas = calculate_salary_distribution(
                cargado, cfg.portion_pct, tgt_fte, cfg.source_dept, cfg.account or "6000")
            r["planilla"].append(sum(planilla_pos.get((p.id, month), 0.0) for p in fuente))
            for k in ("sw", "ccss", "aguinaldo", "cafeteria"):
                r[k].append(b[k])
            r["dummy"].append(dummy)
            r["cargado"].append(cargado)
            r["sale"].append(sum((f["amount_usd"] for f in filas if f["basis_type"] == "CREDIT"), Z))
            for f in filas:
                if f["basis_type"] != "CREDIT":
                    r["entra"].setdefault(f["target_dept"], [Z] * 12)[month - 1] += f["amount_usd"]
        reglas.append(r)

    guardado: dict[tuple, float] = {}
    for e in (await session.execute(select(AllocationEntry).where(
            AllocationEntry.scenario_id == sid,
            AllocationEntry.allocation_type == "SALARY"))).scalars():
        k = ((e.target_dept or "").strip(), int(e.month))
        guardado[k] = guardado.get(k, 0.0) + float(e.amount_usd or 0)
    return reglas, guardado


@router.get("/consolidado/reparto-salarios/")
async def consolidado_reparto_salarios(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast)"),
    quien: str = Depends(lector_del_consolidado),
):
    """Reparto de salarios regla por regla: lo que sale de cada depto y entra a cada destino."""
    from app.models.department_catalog import DepartmentCatalog

    async with get_session() as session:
        esc = await _escenario(session, year, tipo, version)
        reglas, guardado = await _reparto_salarios_recreado(session, esc)
        nombres = dict((await session.execute(
            select(DepartmentCatalog.dept_code, DepartmentCatalog.dept_name))).all())
    return {**_cabecera(esc, tipo), "lineas": filas_reparto_salarios(reglas, guardado, nombres)}


@router.get("/consolidado/repartos/")
async def consolidado_repartos(
    year: int = Query(..., ge=2000, le=2100),
    tipo: str = Query("BUDGET", description="BUDGET · FORECAST · ACTUAL"),
    version: str | None = Query(None, description="Versión exacta; por defecto ★ Current (forecast) o el real"),
    quien: str = Depends(lector_del_consolidado),
):
    """Repartos de Cafetería, Lavandería y salarios: centro → depto × cuenta × mes."""
    from app.models.allocation_entry import AllocationEntry
    from app.models.department_catalog import DepartmentCatalog

    async with get_session() as session:
        esc = await _escenario(session, year, tipo, version)
        entradas = (await session.execute(
            select(AllocationEntry).where(AllocationEntry.scenario_id == esc.id))).scalars().all()
        nombres = dict((await session.execute(
            select(DepartmentCatalog.dept_code, DepartmentCatalog.dept_name))).all())
    return {**_cabecera(esc, tipo), "lineas": filas_repartos(entradas, nombres)}
