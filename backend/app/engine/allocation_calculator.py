"""
Allocation calculator — pure Python, no DB.

Cafetería (dept 0220): total cost distributed proportionally by FTE → account 6025.

Lavandería (dept 0161): total cost split by KILOS into 3 buckets, then:
  - Linen   (Σ kilos por área / total)  → account 7310, distributed by KILOS
  - Uniform (kilos_uniformes / total)    → account 7685, distributed by FTE
  - Guests  (kilos_huespedes / total)    → account 5301 (Cost of Sales),
            moved to dept 0162 (Laundry Revenue, operating) — the COGS of the
            laundry service sold to guests lives WITH its revenue, not in 0161.

Netting:
  - Each receiving dept gets a positive charge (debit).
  - The source dept (0161) gets a negative credit (account 4999) equal to the
    sum of ALL distributed charges (linen + uniform + guest) → 0161 nets to $0.
    Cafetería distributes its full cost → nets to $0. Lavandería: linen +
    uniform go to the consuming depts, the guest portion (COGS) goes to 0162.
"""
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

BasisType = Literal["FTE", "KILOS", "NIGHTS", "MANUAL", "POSITION", "CREDIT"]

ALLOCATION_ACCOUNT = "4999"  # Expense Distribution (credit)
CAFETERIA_ACCOUNT = "6025"   # Beneficios (cafetería charge)
ZERO = Decimal("0")
Q = Decimal("0.0001")


def _spread(
    total_cost: Decimal,
    weights: dict[str, Decimal],
    basis_type: BasisType,
    account: str,
) -> tuple[list[dict], Decimal]:
    """
    Distribute total_cost across weights proportionally (NO credit row).
    Returns (rows, allocated_sum).
    """
    total_weight = sum(weights.values())
    if total_weight <= ZERO or total_cost == ZERO:
        return [], ZERO

    rows: list[dict] = []
    allocated = ZERO
    for dept in sorted(weights.keys()):  # deterministic order
        w = weights[dept]
        if w <= 0:
            continue
        amount = (total_cost * w / total_weight).quantize(Q, rounding=ROUND_HALF_UP)
        rows.append({
            "target_dept": dept,
            "amount_usd": amount,
            "basis_value": w,
            "basis_type": basis_type,
            "account": account,
        })
        allocated += amount
    return rows, allocated


def calculate_cafeteria_distribution(
    total_cost: Decimal,
    fte_by_dept: dict[str, Decimal],
) -> list[dict]:
    """
    Distribute cafetería cost by FTE → account 6025. source_dept: 0220.
    fte_by_dept: {dept_code: fte_value} — REMOTE depts excluded by caller.
    """
    rows, allocated = _spread(total_cost, fte_by_dept, "FTE", CAFETERIA_ACCOUNT)
    if not rows:
        return []
    rows.append({
        "target_dept": "0220",
        "amount_usd": -allocated,
        "basis_value": ZERO,
        "basis_type": "CREDIT",
        "account": ALLOCATION_ACCOUNT,
    })
    return rows


def loaded_salary_breakdown(sw, ccss_rate, aguinaldo_divisor, cafeteria_pct) -> dict:
    """Costo CARGADO de un salario para reasignar: SW + CCSS + Aguinaldo +
    Cafetería (% del salario). Devuelve el desglose por concepto + total.
    CCSS = SW × ccss_rate (26.83%); Aguinaldo = SW / divisor (12); Cafetería =
    SW × cafeteria_pct."""
    sw = Decimal(str(sw or 0))
    ccss = sw * Decimal(str(ccss_rate or 0))
    div = Decimal(str(aguinaldo_divisor or 0))
    aguinaldo = (sw / div) if div > ZERO else ZERO
    cafeteria = sw * Decimal(str(cafeteria_pct or 0))
    total = sw + ccss + aguinaldo + cafeteria
    return {"sw": sw, "ccss": ccss, "aguinaldo": aguinaldo,
            "cafeteria": cafeteria, "total": total}


def calculate_salary_distribution(
    source_salary: Decimal,
    portion_pct: Decimal,
    fte_by_target_dept: dict[str, Decimal],
    source_dept: str,
    account: str = "6000",
) -> list[dict]:
    """Reasigna una PORCIÓN del salario de una posición de apoyo a los deptos
    DESTINO, proporcional al FTE de cada destino. DÉBITO a los destinos, CRÉDITO
    al depto fuente → netea $0 (el gasto se reasigna, no se agrega).

    source_salary: salario (USD) de la posición en el depto fuente ese mes.
    portion_pct:   fracción a reasignar (1 = todo el salario).
    fte_by_target_dept: FTE de cada depto DESTINO (peso del reparto).
    """
    amount = Decimal(str(source_salary)) * Decimal(str(portion_pct))
    if amount <= ZERO:
        return []
    rows, allocated = _spread(amount, fte_by_target_dept, "FTE", account)
    if not rows:
        return []
    rows.append({
        "target_dept": source_dept,
        "amount_usd": -allocated,
        "basis_value": ZERO,
        "basis_type": "CREDIT",
        "account": account,
    })
    return rows


def calculate_rooms_by_pct(
    cost_by_account: dict[str, Decimal],
    pct_by_dept: dict[str, Decimal],
    source_dept: str = "0110",
    fte: Decimal = ZERO,
) -> tuple[list[dict], dict[str, Decimal], list[str]]:
    """Reparte el costo de Rooms a sus sets con un % POR SET y POR MES.

    Se aplica a LO QUE LLEGUE a Rooms: el costo del departamento tal como quedó
    en el GL ese mes, sea cual sea. No hace falta decidir qué parte viene de qué
    posición ni de qué partida — se toma el total y se distribuye.

    `cost_by_account` = {cuenta: monto} — el costo de Rooms del mes, por cuenta.
    `pct_by_dept` = {'0115': 0.30, '0116': 0.10} — una casilla por set, del mes.

    Se eligen porcentajes explícitos y no un driver calculado: el owner sabe qué
    parte de la operación se va a las villas, y ese juicio no se deduce de la
    dotación ni de las noches vendidas.

    Lo que no se asigna se queda en Rooms — o sea que Rooms es el residuo, no un
    destino más. Por eso no se puede repartir más del 100%: devuelve el aviso y
    no arma el asiento, en vez de mover plata que no existe.

    ⚠️ ESTE REPARTO CORRE AL FINAL, después de cafetería, lavandería y salarios.

    Es lo que lo hace simple: para cuando corre, Rooms ya recibió su parte de
    todos los demás repartos, así que «lo que llegue a Rooms» YA INCLUYE la
    cafetería, la lavandería y los salarios repartidos. Villas se lleva su
    proporción de todo eso sin que haya que encadenar nada.

    Si corriera antes, habría que asegurarse de que el FTE de Villas estuviera
    movido para que la cafetería —que se distribuye por FTE— le diera su parte.
    Corriendo al final ese problema no existe.

    El FTE igual viaja con el costo, pero para REPORTE: para poder leer costo por
    FTE en Villas. Ya no es una dependencia de cálculo.

    Devuelve (filas, fte_por_set, avisos).
    """
    avisos: list[str] = []
    pcts = {d: Decimal(str(p or 0)) for d, p in pct_by_dept.items()
            if d != source_dept and Decimal(str(p or 0)) > ZERO}
    if not pcts:
        return [], {}, avisos
    total_pct = sum(pcts.values())
    if total_pct > Decimal("1"):
        avisos.append(
            f"Los porcentajes suman {total_pct * 100:.1f}%: no se puede reasignar "
            f"más del 100% del costo de Rooms. No se armó el asiento.")
        return [], {}, avisos

    cost_by_target = {
        dept: {cuenta: monto * pct for cuenta, monto in cost_by_account.items()}
        for dept, pct in pcts.items()
    }
    fte_por_set = {dept: (Decimal(str(fte or 0)) * pct) for dept, pct in pcts.items()}
    return calculate_rooms_by_position(cost_by_target, source_dept), fte_por_set, avisos


def calculate_rooms_by_position(
    cost_by_target: dict[str, dict[str, Decimal]],
    source_dept: str = "0110",
) -> list[dict]:
    """Reparto de Rooms a sus sets POR POSICIÓN: la posición se lleva todo su gasto.

    `cost_by_target` = {set: {cuenta: monto}} — el costo de las posiciones que se
    asignaron a cada set, abierto por cuenta.

    Se elige la POSICIÓN, no un porcentaje ni un driver: quien atiende las villas
    trabaja para las villas, y su costo entero —los 17 conceptos de planilla, no
    solo el salario— se carga ahí. Es una decisión que se puede señalar con el
    dedo y auditar; un porcentaje repartido no.

    El débito conserva la cuenta de cada concepto, para que el set muestre la
    misma estructura de planilla que cualquier otro departamento. El crédito es
    uno solo, a Rooms, en la cuenta de distribución. Netea cero.
    """
    filas: list[dict] = []
    total = ZERO
    for dept in sorted(cost_by_target):
        if dept == source_dept:
            continue
        for cuenta in sorted(cost_by_target[dept]):
            monto = cost_by_target[dept][cuenta]
            if monto == ZERO:
                continue
            m = monto.quantize(Q, rounding=ROUND_HALF_UP)
            filas.append({
                "target_dept": dept,
                "amount_usd": m,
                "basis_value": ZERO,
                "basis_type": "POSITION",
                "account": cuenta,
            })
            total += m
    if not filas:
        return []
    filas.append({
        "target_dept": source_dept,
        "amount_usd": -total,
        "basis_value": ZERO,
        "basis_type": "CREDIT",
        "account": ALLOCATION_ACCOUNT,
    })
    return filas


def calculate_rooms_manual(
    amounts_by_dept: dict[str, Decimal],
    account: str,
    source_dept: str = "0110",
) -> list[dict]:
    """Reparto MANUAL del costo de Rooms a sus sets, con el monto que se digita.

    Es el mismo asiento que el reparto automático —débito a cada set, crédito
    único a Rooms en la cuenta de distribución, netea cero— pero el monto lo pone
    el usuario en vez de salir de un driver.

    Se hace así por pedido del owner: mientras el costeo de villas y residencias
    se está armando, un reparto por noches vendidas repartiría sobre supuestos
    que todavía no están firmes. Un monto digitado es una decisión explícita y se
    audita mirando quién lo puso; un driver mal calibrado se ve igual de
    razonable y nadie lo revisa.

    El monto va en positivo: es el costo que se le CARGA al set.
    """
    filas: list[dict] = []
    total = ZERO
    for dept in sorted(amounts_by_dept):
        monto = amounts_by_dept[dept]
        if dept == source_dept or monto == ZERO:
            continue
        filas.append({
            "target_dept": dept,
            "amount_usd": monto.quantize(Q, rounding=ROUND_HALF_UP),
            "basis_value": ZERO,
            "basis_type": "MANUAL",
            "account": account,
        })
        total += filas[-1]["amount_usd"]
    if not filas:
        return []
    filas.append({
        "target_dept": source_dept,
        "amount_usd": -total,
        "basis_value": ZERO,
        "basis_type": "CREDIT",
        "account": ALLOCATION_ACCOUNT,
    })
    return filas


def calculate_rooms_distribution(
    cost_by_account: dict[str, Decimal],
    nights_by_dept: dict[str, Decimal],
    source_dept: str = "0110",
) -> list[dict]:
    """Reparte el costo de Rooms entre sus departamentos hijos por NOCHES VENDIDAS.

    El gasto entra al GL en Rooms (0110) y de ahí se redistribuye a Villas y
    Residencias con un asiento: débito a cada hijo en la MISMA cuenta que tenía
    el gasto —para que el detalle por cuenta se conserve— y un solo crédito a
    Rooms en la cuenta de distribución. Netea cero.

    Se reparte por noches vendidas y no por unidades a propósito: una villa que
    se vende poco tiene que cargar poco gasto. Con unidades cargaría lo mismo
    esté llena o vacía.

    Lo que le queda a 0110 después del reparto es «Rooms Standard».

    `nights_by_dept` NO debe incluir al depto fuente: si lo incluyera, Rooms se
    repartiría una parte a sí mismo y el asiento no querría decir nada.
    """
    pesos = {d: w for d, w in nights_by_dept.items() if d != source_dept and w > 0}
    filas: list[dict] = []
    repartido = ZERO
    for cuenta in sorted(cost_by_account):
        f, alloc = _spread(cost_by_account[cuenta], pesos, "NIGHTS", cuenta)
        filas += f
        repartido += alloc
    if not filas:
        return []
    filas.append({
        "target_dept": source_dept,
        "amount_usd": -repartido,
        "basis_value": ZERO,
        "basis_type": "CREDIT",
        "account": ALLOCATION_ACCOUNT,
    })
    return filas


def calculate_laundry_distribution(
    total_cost: Decimal,
    linen_kilos_by_dept: dict[str, Decimal],
    uniform_fte_by_dept: dict[str, Decimal],
    kilos_uniformes: Decimal = ZERO,
    kilos_huespedes: Decimal = ZERO,
    acct_linen: str = "7310",
    acct_uniform: str = "7685",
    acct_servicios: str = "5301",
    source_dept: str = "0161",
    guest_dept: str = "0162",
) -> dict:
    """
    3-way laundry distribution by kilos.

    Returns a dict:
      {
        "rows": [...],          # AllocationEntry-shaped rows, net to $0
        "linen_cost":   Decimal,
        "uniform_cost": Decimal,
        "guest_cost":   Decimal,   # charged to 0162 as COGS (acct_servicios)
        "total_kilos":  Decimal,
      }

    The guest portion is emitted as a charge to guest_dept (0162 Laundry
    Revenue); 0161 is credited for the full cost (linen + uniform + guest) so
    it nets to $0 as a pure cost/allocation dept.
    """
    linen_total = sum(linen_kilos_by_dept.values())
    total_kilos = linen_total + kilos_uniformes + kilos_huespedes

    empty = {
        "rows": [], "linen_cost": ZERO, "uniform_cost": ZERO,
        "guest_cost": ZERO, "total_kilos": total_kilos,
    }
    if total_kilos <= ZERO or total_cost == ZERO:
        return empty

    linen_cost = (total_cost * linen_total / total_kilos)
    uniform_cost = (total_cost * kilos_uniformes / total_kilos)
    # remainder avoids rounding drift so the 3 buckets sum to total_cost exactly
    guest_cost = total_cost - linen_cost - uniform_cost

    linen_rows, linen_alloc = _spread(linen_cost, linen_kilos_by_dept, "KILOS", acct_linen)
    uni_rows, uni_alloc = _spread(uniform_cost, uniform_fte_by_dept, "FTE", acct_uniform)

    # Guest portion = COGS of the laundry service SOLD. It moves OUT of 0161
    # (the cost-only/allocation dept, overhead) INTO guest_dept (0162 Laundry
    # Revenue, operating) so revenue and its cost live together and 0161 nets
    # fully to $0. Charged to acct_servicios (5301, Cost of Sales).
    guest_rows: list[dict] = []
    guest_alloc = ZERO
    if guest_cost != ZERO and guest_dept:
        guest_rows.append({
            "target_dept": guest_dept,
            "amount_usd": guest_cost,
            "basis_value": kilos_huespedes,
            "basis_type": "KILOS",
            "account": acct_servicios,
        })
        guest_alloc = guest_cost

    rows = linen_rows + uni_rows + guest_rows
    credit = linen_alloc + uni_alloc + guest_alloc
    if credit != ZERO:
        rows.append({
            "target_dept": source_dept,
            "amount_usd": -credit,
            "basis_value": ZERO,
            "basis_type": "CREDIT",
            "account": ALLOCATION_ACCOUNT,
        })

    return {
        "rows": rows,
        "linen_cost": linen_cost,
        "uniform_cost": uniform_cost,
        "guest_cost": guest_cost,
        "total_kilos": total_kilos,
    }


def verify_allocation_nets_zero(rows: list[dict]) -> bool:
    """Check that the sum of all amount_usd rows is effectively zero."""
    total = sum(r["amount_usd"] for r in rows)
    return abs(total) < Decimal("0.01")


def cuentas_de_reparto() -> frozenset[str]:
    """Las cuentas en las que ESTE motor escribe: 4999, 6025, 6000, 7310, 7685, 5301.

    Se arma sola, del módulo: las constantes de acá arriba más el valor por
    defecto de todo parámetro `account` / `acct_*` de las funciones
    `calculate_*`. Un reparto nuevo con una cuenta nueva queda cubierto sin que
    nadie se acuerde de venir a agregarla a una lista.

    ## Para qué sirve saberlo

    Una fila del mayor la carga una persona; estas las escribe el motor. La
    diferencia importa en dos lados:

    * `GET /departments/` deriva de acá qué departamento tiene dónde poner un
      gasto en el checkbook. Una cuenta que existe SOLO para recibir un reparto
      no es un lugar donde alguien digita: es el mismo criterio por el que la
      `4999` nunca contó.
    * La auditoría del mapeo exige que cada una de estas cuentas resuelva por
      regla EXACTA en su departamento destino. Si cae por descarte, la plata
      aterriza en la línea de otro departamento y el GOP cuadra igual — pasó el
      2026-08-14 con la `5301` del `0162`, que se fue al Spa.

    Ojo con el matiz: que una cuenta esté acá NO la vuelve exclusiva del motor.
    La `7310` y la `6000` también se digitan a mano en el checkbook. Por eso el
    criterio de `lleva_gasto` es «tiene alguna cuenta de gasto que NO sea de
    reparto», no «no tiene ninguna cuenta de reparto».
    """
    import inspect
    import sys

    cuentas = {ALLOCATION_ACCOUNT, CAFETERIA_ACCOUNT}
    modulo = sys.modules[__name__]
    for nombre, fn in vars(modulo).items():
        if not nombre.startswith("calculate_") or not inspect.isfunction(fn):
            continue
        for p in inspect.signature(fn).parameters.values():
            if p.name != "account" and not p.name.startswith("acct"):
                continue
            if isinstance(p.default, str) and p.default:
                cuentas.add(p.default)
    return frozenset(cuentas)
