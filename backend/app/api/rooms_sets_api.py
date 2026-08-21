"""Rooms abierto en sus SETS — la segunda vista, a nivel de reporte.

El P&L no cambia nunca: Rooms es una línea y adentro consolidan Villas y
Residencias. Esta vista es la que abre esa línea en tres, para poder ver cuánto
cuesta cada conjunto y —como cada categoría sabe a qué set pertenece— cuánto
ingresa.

No toca la contabilidad. Lee el GL por departamento, le suma lo que cada
departamento recibió por reparto, y presenta:

  Rooms Standard = la familia Rooms (0110 + Front Desk, Reservation,
                   Housekeeping, Concierge) DESPUÉS de entregar el reparto.
  Villas         = lo que recibió por el asiento.
  Residencias    = lo mismo.

La suma de las tres es la línea de Rooms del P&L. Ese cuadre se calcula y se
devuelve: una vista de reporte que no amarra contra el estado de resultados no
sirve para decidir nada.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.db import get_db
from app.models.scenario import Scenario
from app.models.allocation_entry import AllocationEntry
from app.models.department_catalog import DepartmentCatalog
from app.models.room_type_config import RoomTypeConfig
from app.models.opex_entry import OpexEntry
from app.models.cost_entry import CostEntry
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.payroll_position import PayrollPosition

router = APIRouter(tags=["rooms-sets"])

ZERO = Decimal("0")
ROOMS = "0110"
STANDARD = "STANDARD"          # clave sintética: la familia Rooms, no un depto
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]
PAYROLL_COLS = [
    "c6000_sw", "c6001_overtime", "c6002_day_off", "c6003_working_holiday",
    "c6004_disabilities", "c6010_commissions", "c6020_ccss", "c6021_aguinaldo",
    "c6022_occ_hazard", "c6023_vacation_prov", "c6024_vacations_taken",
    "c6025_cafeteria", "c6026_severance", "c6027_incentive_bonus",
    "c6028_housing", "c6029_transport", "c6030_other",
]


def _clase(cuenta: str) -> str:
    """Clase USALI de la cuenta: '6' planilla, '7' opex, '5' costo, '4' reparto."""
    c = (cuenta or "").strip()
    return c[0] if c else ""


@router.get("/reports/rooms-sets/{scenario_id}/")
async def rooms_por_set(scenario_id: str, db: AsyncSession = Depends(get_db)):
    from app.engine.recalculate import rooms_family
    from app.engine.revenue_calculator import room_type_breakdown
    from app.api.revenue_api import _load_revenue_data

    scenario = await db.get(Scenario, scenario_id)
    if scenario is None:
        raise ErrorApi(404, "escenario.no_encontrado")

    familia, sets = await rooms_family(db, ROOMS)
    catalogo = {d.dept_code: d for d in (await db.execute(
        select(DepartmentCatalog))).scalars()}

    # ── Costo ────────────────────────────────────────────────────────────────
    # Una casilla por (set, mes) y por clase de cuenta. Se abre planilla vs opex
    # porque es la pregunta inmediata del owner cuando ve un costo por villa:
    # ¿es gente o es gasto?
    vacio = lambda: {"payroll": [0.0] * 12, "opex": [0.0] * 12,
                     "cos": [0.0] * 12, "distribucion": [0.0] * 12,
                     "total": [0.0] * 12}
    costo: dict[str, dict] = {STANDARD: vacio(), **{s: vacio() for s in sorted(sets)}}
    # El mismo costo, pero sin colapsar la cuenta. Los cubos contestan «¿es gente
    # o es gasto?»; esto contesta «¿qué gasto?», que es lo que pide el reporte de
    # máximo detalle. Se llena en el mismo lugar para que no puedan separarse.
    detalle: dict[str, dict[str, list[float]]] = {k: {} for k in costo}

    def cae_en(dept: str) -> str | None:
        if dept in sets:
            return dept
        if dept in familia:
            return STANDARD
        return None

    def cargar(destino: str, cuenta: str, mes_idx: int, monto: Decimal) -> None:
        if not monto:
            return
        c = _clase(cuenta)
        # La cuenta de distribución (4999) es el CRÉDITO del asiento: no es un
        # gasto de ninguna clase, es el gasto que SE FUE. Lleva cubo propio en
        # vez de repartirse entre planilla y opex.
        #
        # Sin cubo propio, Rooms Standard mostraba planilla $534,044 + opex
        # $111,506 = $645,550 pero un total de $553,443: los $92,107 que
        # entregó estaban en el total y en ningún renglón. Las columnas de la
        # pantalla no cuadraban contra su propia fila.
        cubo = {"6": "payroll", "7": "opex", "5": "cos"}.get(c, "distribucion")
        v = float(monto)
        costo[destino][cubo][mes_idx] += v
        costo[destino]["total"][mes_idx] += v
        detalle[destino].setdefault((cuenta or "").strip(), [0.0] * 12)[mes_idx] += v

    for e in (await db.execute(select(OpexEntry).where(
            OpexEntry.scenario_id == scenario_id))).scalars():
        d = cae_en(e.dept_code)
        if d:
            for m in range(12):
                cargar(d, e.account_code, m, e.get_month(m + 1) or ZERO)

    for e in (await db.execute(select(CostEntry).where(
            CostEntry.scenario_id == scenario_id))).scalars():
        d = cae_en(e.dept_code)
        if d:
            for m in range(12):
                cargar(d, e.account_code, m, e.get_month(m + 1) or ZERO)

    from app.engine import pl_engine
    for e in (await db.execute(select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id))).scalars():
        d = cae_en(e.dept_code)
        if not d or not (1 <= (e.month or 0) <= 12):
            continue
        for col in PAYROLL_COLS:
            cargar(d, pl_engine.payroll_account_for_column(col),
                   e.month - 1, getattr(e, col) or ZERO)

    repartos_recibidos: dict[str, list[float]] = {
        k: [0.0] * 12 for k in costo}
    for e in (await db.execute(select(AllocationEntry).where(
            AllocationEntry.scenario_id == scenario_id))).scalars():
        d = cae_en(e.target_dept)
        if not d or not (1 <= (e.month or 0) <= 12):
            continue
        cargar(d, e.account, e.month - 1, e.amount_usd or ZERO)
        repartos_recibidos[d][e.month - 1] += float(e.amount_usd or ZERO)

    # ── FTE ──────────────────────────────────────────────────────────────────
    # El de la familia es real (las personas están contratadas ahí). El del set
    # es el que viajó con el reparto: proporcional, para poder leer costo por
    # FTE. No es gente distinta — es la misma gente, prorrateada.
    fte: dict[str, list[float]] = {k: [0.0] * 12 for k in costo}
    for p in (await db.execute(select(PayrollPosition).where(
            PayrollPosition.scenario_id == scenario_id))).scalars():
        if p.dept_code not in familia:
            continue
        for m in range(12):
            fte[STANDARD][m] += float(getattr(p, f"fte_{MESES[m]}") or 0)
    for e in (await db.execute(select(AllocationEntry).where(
            AllocationEntry.scenario_id == scenario_id,
            AllocationEntry.allocation_type == "ROOMS"))).scalars():
        if e.target_dept in sets and e.basis_type != "CREDIT" and 1 <= e.month <= 12:
            # basis_value se repite en cada fila del mismo (set, mes) — es el FTE
            # del set, no una parte de él. Se toma el mayor, no la suma.
            fte[e.target_dept][e.month - 1] = max(
                fte[e.target_dept][e.month - 1], float(e.basis_value or 0))

    # ── Ingreso y noches, por categoría → set ────────────────────────────────
    rt = (await db.execute(select(RoomTypeConfig).where(
        RoomTypeConfig.hotel_id == scenario.hotel_id,
        RoomTypeConfig.active == True,  # noqa: E712
    ).order_by(RoomTypeConfig.sort_order))).scalars().all()
    set_de_rt = {t.id: ((t.dept_code or ROOMS) if (t.dept_code or ROOMS) in sets
                        else STANDARD) for t in rt}

    revenue: dict[str, list[float]] = {k: [0.0] * 12 for k in costo}
    noches_disp: dict[str, list[float]] = {k: [0.0] * 12 for k in costo}
    noches_ocup: dict[str, list[float]] = {k: [0.0] * 12 for k in costo}

    data = await _load_revenue_data(scenario_id, db)
    unidades = {t.id: t.units for t in data["room_types"]}
    rates_por_mes: dict[int, list] = {}
    for rc in data["rate_cards"]:
        rates_por_mes.setdefault(rc.month, []).append(rc)
    occ_por_mes: dict[int, list] = {}
    for ob in data["occupancies"]:
        occ_por_mes.setdefault(ob.month, []).append(ob)

    for m in range(1, 13):
        for r in room_type_breakdown(
                m, rates_por_mes.get(m, []), occ_por_mes.get(m, []), unidades):
            d = set_de_rt.get(r["room_type_id"], STANDARD)
            revenue[d][m - 1] += float(r["revenue"])
            noches_disp[d][m - 1] += float(r["nights_available"])
            noches_ocup[d][m - 1] += float(r["nights_occupied"])

    # ── Armado ───────────────────────────────────────────────────────────────
    def bloque(clave: str) -> dict:
        cat = [t for t in rt if set_de_rt.get(t.id) == clave]
        c = costo[clave]
        # El costo se arma sumando los renglones YA REDONDEADOS, no redondeando
        # el total por separado. Redondeando cada uno por su cuenta la fila se
        # descuadraba por un centavo al mes —hasta 3 al año— y en un reporte
        # cuyo argumento es «esto cuadra», un centavo que no cierra cuesta más
        # explicarlo que evitarlo.
        cubos = [[round(v, 2) for v in c[k]]
                 for k in ("payroll", "opex", "cos", "distribucion")]
        total = [round(sum(x[m] for x in cubos), 2) for m in range(12)]
        return {
            "key": clave,
            "dept_code": "" if clave == STANDARD else clave,
            "name": ("Rooms Standard" if clave == STANDARD
                     else (catalogo[clave].dept_name if clave in catalogo else clave)),
            "es_residuo": clave == STANDARD,
            "unidades": sum(int(t.units or 0) for t in cat),
            "categorias": [{"code": t.code, "name": t.name, "units": int(t.units or 0)}
                           for t in cat],
            "payroll": cubos[0],
            "opex": cubos[1],
            "cos": cubos[2],
            # Negativo en Rooms Standard (entregó) y cero en los sets: el débito
            # que reciben conserva la cuenta original, no la de distribución.
            "distribucion": cubos[3],
            "costo": total,
            "recibido_por_reparto": [round(v, 2) for v in repartos_recibidos[clave]],
            "revenue": [round(v, 2) for v in revenue[clave]],
            "fte": [round(v, 4) for v in fte[clave]],
            "noches_disponibles": [round(v, 1) for v in noches_disp[clave]],
            "noches_ocupadas": [round(v, 1) for v in noches_ocup[clave]],
            "costo_anual": round(sum(total), 2),
            "revenue_anual": round(sum(revenue[clave]), 2),
            # Cuenta por cuenta, para el reporte de máximo detalle. Sale del
            # MISMO recorrido que los cubos de arriba: si se calculara aparte,
            # las dos vistas del mismo costo podrían decir cosas distintas.
            "detalle": {c: [round(v, 2) for v in meses]
                        for c, meses in sorted(detalle[clave].items())},
        }

    filas = [bloque(STANDARD)] + [bloque(s) for s in sorted(sets)]

    consolidado = {
        "costo": [round(sum(f["costo"][m] for f in filas), 2) for m in range(12)],
        "revenue": [round(sum(f["revenue"][m] for f in filas), 2) for m in range(12)],
        "unidades": sum(f["unidades"] for f in filas),
    }
    consolidado["costo_anual"] = round(sum(consolidado["costo"]), 2)
    consolidado["revenue_anual"] = round(sum(consolidado["revenue"]), 2)

    # El reparto netea cero: lo que las villas reciben es exactamente lo que
    # Rooms entrega. Si esto no da cero, el asiento está roto y el número por
    # set no se puede creer — mejor decirlo que dibujarlo.
    neto = round(sum(
        float(e.amount_usd or 0) for e in (await db.execute(
            select(AllocationEntry).where(
                AllocationEntry.scenario_id == scenario_id,
                AllocationEntry.allocation_type == "ROOMS"))).scalars()), 2)

    return {
        "scenario_id": scenario_id,
        "year": scenario.year,
        "source_dept": ROOMS,
        "rows": filas,
        "consolidado": consolidado,
        "asiento_neto": neto,
        "cuadra": abs(neto) < 0.01,
        "hay_reparto": any(
            any(f["recibido_por_reparto"]) for f in filas if not f["es_residuo"]),
    }
