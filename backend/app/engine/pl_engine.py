"""
P&L engine — pure Python, no DB.

Builds the Full P&L for CWL (CLAUDE.md §17) from already-fetched data:
  - revenue by line   (from revenue_calculator.RevenueResult)
  - payroll by dept   (sum of the 17 concepts, §12)
  - cost of sales by dept (class 5, §13)
  - opex by dept      (class 7 checkbooks)
  - allocations by dept (§14 — cafetería/lavandería, NETS to zero)
  - manual inputs     (§17.5 — rent, mgmt fees, insurance, capex, etc.)

Design mirrors the rest of engine/: the core computation is a pure function
that takes plain dicts and returns dataclasses, so it is unit-testable without
a database. The API layer (pl_api.py) fetches from the DB and calls this.

Chain (§7.1 / §17.3):
  TOTAL REVENUES
  − OPERATING EXPENSES (per dept = Payroll + CoS + OpEx + Allocations)
  = OPERATING PROFIT
  − OVERHEAD (Admin, Sales, Maintenance, IT, Utilities + cafetería net)
  = GOP
  − NON-OP (Rent + Mgmt Fees + Insurance)
  = EBITDA BEFORE CAPITAL
  − Capital (reserve + large capex)
  = EBITDA AFTER CAPITAL
  − Financial (bank interest) − Depreciation
  = EBT
  − Income Tax (30% of EBT if > 0)
  = NET PROFIT
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")


# ─── Department → P&L group mapping ───────────────────────────────────────────
# Operating (revenue) departments — contribute to OPERATING PROFIT.
OPERATING_DEPT_GROUPS: dict[str, list[str]] = {
    "ROOMS":     ["0110", "0111", "0112", "0113", "0114"],
    "FB":        ["0120", "0122", "0123"],   # 0122 Kitchen / 0123 Restaurant (subs de 0120)
    # Private Bar: centro de utilidad APARTE, no un outlet de A&B (owner,
    # 2026-08-12). Por eso tiene grupo propio y NO cuelga del 0120: su ingreso y
    # su costo se ven solos en el P&L, no diluidos en A&B.
    "PRIVATE_BAR": ["0121"],
    "SPA":       ["0130", "0132", "0140"],   # 0130/0132 presupuesto, 0140 GL/actuales
    "TOURS":     ["0150"],
    # Dos LOCALES distintos, no un duplicado (owner, 2026-08-11) — y desde el
    # 2026-08-13 cada uno con su propia línea del P&L: ingreso, gasto y utilidad
    # por separado. El Gift Shop se queda con RETAIL porque toda la cañería de
    # presupuesto y drivers ya cuelga de él; la Tienda sale como grupo propio.
    "TIENDA":    ["0151"],
    "RETAIL":    ["0165"],                    # Gift Shop
    "TRANSPORT": ["0152"],
    "LAUNDRY":   ["0162"],   # Laundry Revenue — ingreso del servicio (operativo)
    "INNOCEANA": ["0155"],
    "CROWTHER":  ["0156"],   # Crowther Lab — cost only, no revenue
    "CLUB":      ["260"],    # Club Madresal — operativo, membresía (Amarena; ambiente común CWL)
}

# Overhead departments — subtracted after Operating Profit.
OVERHEAD_DEPT_GROUPS: dict[str, list[str]] = {
    "ADMIN":       ["0180", "0181", "0182", "0183", "0184", "0186"],
    "SALES":       ["0190", "0191"],
    "MAINTENANCE": ["0200"],
    "IT":          ["0230"],
    "UTILITIES":   ["0210"],   # 0205 Claro del Bosque (Huerta) → cae a Other Overhead (solo gastos)
    "CAFETERIA":   ["0220"],  # allocation source — nets to ~0 after distribution
    "LAUNDRY_OPS": ["0161"],  # Laundry gastos (solo lava) — allocation source, nets to ~0
    # Área Recreativa: CENTRO DE COSTO, no departamento operativo (decisión del
    # owner 2026-08-11, D4 — así lo trata el Excel de Amarena, donde entra al
    # consolidado solo como una línea de overhead). Su COSTO (nómina + opex) baja
    # acá; su INGRESO se queda arriba, en REV_AREC, con los demás ingresos.
    #
    # El Excel además lo deja FUERA de «INGRESOS TOTALES», pero el propio escaneo
    # marcó eso para confirmar («si el área genera ingreso real, hoy se está
    # perdiendo del estado de resultados», ESCANEO_03 §5.12). No se replica: el
    # ingreso se queda. Hoy vale $0, así que la decisión no mueve un centavo, y
    # el corte del GOP sale idéntico en las dos variantes.
    "AREC":        ["270"],
}

# Any dept_code not listed above lands here so its cost is never silently dropped
# (keeps GOP = total revenue − total cost intact).
FALLBACK_OVERHEAD_GROUP = "OTHER_OVERHEAD"

# Display order
OPERATING_GROUP_ORDER = [
    "ROOMS", "FB", "PRIVATE_BAR", "SPA", "TOURS", "TIENDA", "RETAIL",
    "TRANSPORT", "LAUNDRY", "INNOCEANA", "CROWTHER", "CLUB",
    "AREC", "SUSTAINABILITY", "MISC_OTHER",
]
# Grupos que arriba SOLO traen ingreso: su costo no vive en el bloque operativo.
# SUSTAINABILITY y MISC_OTHER nunca tuvieron costo propio; AREC lo tiene, pero
# baja al overhead (ver OVERHEAD_DEPT_GROUPS).
REVENUE_ONLY_GROUPS = {"AREC", "SUSTAINABILITY", "MISC_OTHER"}
OVERHEAD_GROUP_ORDER = [
    "ADMIN", "SALES", "MAINTENANCE", "IT", "UTILITIES",
    "CAFETERIA", "LAUNDRY_OPS", "AREC", FALLBACK_OVERHEAD_GROUP,
]

GROUP_NAMES = {
    "ROOMS": "Rooms", "FB": "F&B", "PRIVATE_BAR": "Private Bar",
    "SPA": "SPA", "TOURS": "Tours",
    "TIENDA": "Tienda", "RETAIL": "Gift Shop", "TRANSPORT": "Transportation",
    "LAUNDRY": "Laundry", "LAUNDRY_OPS": "Laundry Operations",
    "INNOCEANA": "Innoceana", "CROWTHER": "Crowther Lab",
    "CLUB": "Club Madresal", "AREC": "Área Recreativa",
    "SUSTAINABILITY": "Sustainability Fee",
    "MISC_OTHER": "Other / Misc Revenue",
    "ADMIN": "Administrations", "SALES": "Sales & Marketing",
    "MAINTENANCE": "Maintenance", "IT": "Information System",
    "UTILITIES": "Utilities", "CAFETERIA": "Cafetería",
    FALLBACK_OVERHEAD_GROUP: "Other Overhead",
}

# Revenue line (RevenueResult attr) → operating group
REVENUE_LINE_TO_GROUP: dict[str, str] = {
    "rooms": "ROOMS",
    "food": "FB", "beverage": "FB", "fnb_misc": "FB",
    # El Private Bar comparte los números de cuenta con el Gift Shop (4301-4304),
    # así que por rango de cuenta caería en RETAIL. Lo que lo distingue es el
    # DEPARTAMENTO, y para eso el grupo necesita su propia llave de ingreso.
    "private_bar": "PRIVATE_BAR",
    "spa": "SPA",
    "activities": "TOURS",
    "transport": "TRANSPORT",
    "tienda": "TIENDA",
    "retail": "RETAIL",
    "laundry": "LAUNDRY",
    "innoceana": "INNOCEANA",
    "crowther": "CROWTHER",
    # Las tres fuentes del Club caen en el mismo grupo: la cuota, la actividad
    # de fin de año y los visitantes son un solo centro de utilidad.
    "club": "CLUB", "club_actividad": "CLUB", "club_visitantes": "CLUB",
    "arec": "AREC",
    "sustainability": "SUSTAINABILITY",
    "misc_other": "MISC_OTHER",
}

# Operating group → representative revenue-line key (for dept-based revenue
# classification of actuals, which is more reliable than account ranges).
GROUP_TO_REVENUE_LINE: dict[str, str] = {
    "ROOMS": "rooms", "FB": "food", "PRIVATE_BAR": "private_bar",
    "SPA": "spa", "TOURS": "activities",
    "TRANSPORT": "transport", "TIENDA": "tienda", "RETAIL": "retail",
    "LAUNDRY": "laundry",
    "INNOCEANA": "innoceana", "CROWTHER": "crowther",
    "CLUB": "club", "AREC": "arec",
    "SUSTAINABILITY": "sustainability", "MISC_OTHER": "misc_other",
}

# Revenue line (RevenueResult attr) → report_line_code, for budget/forecast
# scenarios whose revenue comes from rate cards (line level, no 4xxx detail).
# These REV_* codes match report_line_config (the validated DB-driven engine).
REVENUE_LINE_TO_REPORT_LINE: dict[str, str] = {
    "rooms": "REV_ROOMS",
    # ⚠️ Antes las tres caían en `REV_FB`. El checkbook SIEMPRE las tuvo
    # separadas (`RevenueEntry`: FOOD / BEVERAGE / FNB_MISC) y el dato se
    # tiraba. Desde que el P&L tiene las tres líneas (2026-08-14) eso dejaba
    # `REV_FB_BEV` y `REV_FB_MISC` en CERO en todo presupuesto, mientras el
    # Actual sí las trae con plata: comparar Actual contra Budget línea por
    # línea daba una variación falsa del tamaño de toda la bebida.
    "food": "REV_FB", "beverage": "REV_FB_BEV", "fnb_misc": "REV_FB_MISC",
    "private_bar": "REV_PRIVATE_BAR",
    "spa": "REV_SPA",
    "activities": "REV_TOURS",
    "transport": "REV_TRANSPORTATION",
    "tienda": "REV_TIENDA",
    "retail": "REV_RETAIL",
    "laundry": "REV_LAUNDRY",
    "innoceana": "REV_INNOCEANA",
    # …y en la misma línea del P&L, igual que food/beverage/fnb_misc → REV_FB.
    "club": "REV_CLUB", "club_actividad": "REV_CLUB",
    "club_visitantes": "REV_CLUB",
    "arec": "REV_AREC",
    "sustainability": "REV_SUSTAINABILITY",
    "misc_other": "REV_MISC_OTHER",
}


def revenue_seed_from_lines(revenue_by_line: dict[str, Decimal]) -> dict[str, Decimal]:
    """Collapse RevenueResult lines into {report_line_code: amount} seeds."""
    out: dict[str, Decimal] = {}
    for line, amount in (revenue_by_line or {}).items():
        rl = REVENUE_LINE_TO_REPORT_LINE.get(line)
        if rl is None:
            continue
        out[rl] = out.get(rl, ZERO) + _d(amount)
    return out


def payroll_account_for_column(col: str) -> str:
    """'c6000_sw' → '6000'. The 17 PayrollConceptEntry columns embed their code."""
    m = re.match(r"c(\d+)_", col or "")
    return m.group(1) if m else ""


# Payroll positions use sub-department codes; the P&L mapping uses the parent
# department. Only Rooms and F&B have children (per CWL org); Spa and the admin
# functions are coded as sub-depts too. Applied ONLY on the checkbook build path
# (not to imported actuals, which keep their own validated dept codes).
# El 0121 NO está acá a propósito: es el Private Bar, un centro de utilidad
# aparte con grupo propio (PRIVATE_BAR), no un outlet de A&B. Colgarlo del 0120
# metería su ingreso y su costo dentro de F&B, que es justo lo que el owner no
# quiere ver. Lo cuida test_private_bar_aparte.py.
CHECKBOOK_DEPT_CONSOLIDATION: dict[str, str] = {
    "0111": "0110", "0112": "0110", "0113": "0110", "0114": "0110",  # Rooms
    "0122": "0120", "0123": "0120",                                   # F&B
    # Spa (owner, 2026-08-13): el PADRE es 0140 y de él cuelgan 0130 gerencia y
    # 0132 planilla. La cadena sube recursiva (0132 → 0130 → 0140), así que las
    # reglas de mapeo viven en 0140 y los dos hijos las heredan.
    "0132": "0130", "0130": "0140",
    # Administración. El 0184 (RRHH) entró con la migración 092, pero la regla
    # vivía solo ahí: el seed deriva este mapa en cada deploy y se lo llevaba
    # puesto. Sin padre, el motor no sabe dónde rutearlo y toda la planilla de
    # Recursos Humanos cae en OPEX_ROOMS por descarte — sumada al gasto de
    # Habitaciones, sin dar error y con el GOP cuadrando.
    "0181": "0180", "0182": "0180", "0183": "0180", "0184": "0180", "0186": "0180",
    # Ventas remoto cuelga de Ventas (owner, 2026-08-13). No tenía reglas ni
    # padre, así que TODO lo suyo caía por descarte en Habitaciones. Colgarlo
    # es mejor que darle reglas propias: hoy no se usa, y si mañana se usa
    # hereda las 48 de su padre sin que nadie tenga que acordarse.
    "0191": "0190",
}


# ─── Dept→group + consolidation maps ──────────────────────────────────────────
# Bootstrap from the constants above (OPERATING/OVERHEAD_DEPT_GROUPS +
# CHECKBOOK_DEPT_CONSOLIDATION). The CANONICAL source is the department_catalog
# table; set_dept_catalog() overrides these at app startup. The engine stays
# PURE — it only holds dicts; the API/startup layer loads the catalog and pushes
# it in. Unit tests run WITHOUT the catalog → the constants apply (verified
# byte-for-byte identical to the catalog seed).
_DEPT_TO_GROUP: dict[str, str] = {}
_CONSOLIDATION: dict[str, str] = {}


def _load_default_maps() -> None:
    _DEPT_TO_GROUP.clear()
    for _g, _depts in {**OPERATING_DEPT_GROUPS, **OVERHEAD_DEPT_GROUPS}.items():
        for _d in _depts:
            _DEPT_TO_GROUP[_d] = _g
    _CONSOLIDATION.clear()
    _CONSOLIDATION.update(CHECKBOOK_DEPT_CONSOLIDATION)


_load_default_maps()


def set_dept_catalog(rows) -> None:
    """Override dept→group + consolidation from department_catalog rows (called
    once at app startup). rows: dicts/objects with dept_code, default_pl_group,
    parent_dept_code. Account-based revenue depts (no group, e.g. 280) are
    skipped → they keep resolving to the fallback (revenue routed by account).
    An empty catalog leaves the constants in place (safety fallback)."""
    def _get(r, k):
        return r[k] if isinstance(r, dict) else getattr(r, k, None)
    grp_map: dict[str, str] = {}
    cons_map: dict[str, str] = {}
    for r in rows:
        code = (_get(r, "dept_code") or "").strip()
        grp = (_get(r, "default_pl_group") or "").strip()
        par = (_get(r, "parent_dept_code") or "").strip()
        if code and grp:
            grp_map[code] = grp
        if code and par:
            cons_map[code] = par
    if not grp_map:
        return
    _DEPT_TO_GROUP.clear(); _DEPT_TO_GROUP.update(grp_map)
    _CONSOLIDATION.clear(); _CONSOLIDATION.update(cons_map)


def reset_dept_catalog() -> None:
    """Restore the constants-based maps (used by tests)."""
    _load_default_maps()


def consolidate_dept(dept_code: str) -> str:
    """Map a payroll sub-dept to its P&L parent (checkbook path only)."""
    return _CONSOLIDATION.get((dept_code or "").strip(), dept_code)


def construir_resolvedor(mappings: list[dict]):
    """Arma la búsqueda (departamento, cuenta) → regla de mapeo.

    Devuelve `resolve(dept, cuenta) -> (regla | None, cómo)`, donde `cómo` es
    uno de: 'exact', 'parent', 'dept-agnostic', 'FALLBACK', 'DROP'.

    Vive acá y no duplicado en el tab de Control. Antes había una copia
    marcada «réplica EXACTA», y una copia que se queda atrás hace que la
    herramienta de auditoría diga una cosa mientras el P&L hace otra — que es
    la peor forma de fallar para algo cuyo único trabajo es decir la verdad.

    El orden importa:

      exact         la regla del departamento, si existe.
      parent        la del padre. Los repartos caen en sub-departamentos
                    (0122 Cocina, 0123 Restaurante, 0132 Spa, 0182 Finance)
                    que casi nunca tienen regla propia.
      dept-agnostic reglas sin departamento, para cuentas que no dependen de él.
      FALLBACK      último recurso: cualquier regla que use esa cuenta. Es
                    inestable —depende del orden físico de las filas— así que
                    se marca para que el tab de Control lo delate.
    """
    def _prefiere_regla(nueva: dict, previa: dict) -> bool:
        """¿La regla nueva le gana a la que ya estaba, para el FALLBACK?

        Se queda la de departamento MENOR. No hay un criterio «correcto» acá —
        el punto es que sea el mismo siempre, corra cuando corra.

        (Las reglas sin departamento no llegan hasta acá: las agarra antes el
        paso `dept-agnostic`, que busca la llave `("", cuenta)`.)
        """
        return ((nueva.get("dept_code") or "").strip()
                < (previa.get("dept_code") or "").strip())

    lookup_exact: dict[tuple[str, str], dict] = {}
    lookup_by_acct: dict[str, dict] = {}
    for m in mappings:
        if m.get("active_status", "YES") != "YES":
            continue
        dc = (m.get("dept_code") or "").strip()
        ac = (m.get("account_code") or "").strip()
        if not ac:
            continue
        lookup_exact.setdefault((dc, ac), m)
        # El FALLBACK por cuenta se queda con la regla de MENOR departamento, no
        # con la que venga primera en la lista.
        #
        # Antes era `setdefault`, o sea el orden físico de las filas — y ese
        # orden cambia cada vez que se recarga el mapeo, porque `mapping_loader`
        # borra todo y reinserta desde el Excel. Con una sola regla por cuenta
        # da igual (es el caso de hoy: las 6 cuentas que caen por descarte
        # —4700, 4701, 4800, 4860, 4880, 4890, $1.4M— tienen exactamente una).
        # El día que aparezca una segunda, la plata se movería de línea sola,
        # sin que nadie tocara nada y sin dejar rastro. Ordenar por departamento
        # es arbitrario, pero es ESTABLE, que es lo único que hace falta.
        previo = lookup_by_acct.get(ac)
        if previo is None or _prefiere_regla(m, previo):
            lookup_by_acct[ac] = m

    def resolve(dept: str, cuenta: str):
        dept = (dept or "").strip()
        cuenta = (cuenta or "").strip()
        m = lookup_exact.get((dept, cuenta))
        if m:
            return m, "exact"
        for padre in _cadena_de_padres(dept):
            m = lookup_exact.get((padre, cuenta))
            if m:
                return m, "parent"
        m = lookup_exact.get(("", cuenta))
        if m:
            return m, "dept-agnostic"
        m = lookup_by_acct.get(cuenta)
        if m:
            return m, "FALLBACK"
        return None, "DROP"

    return resolve


def _cadena_de_padres(dept_code: str) -> list[str]:
    """Padres de un departamento, del más cercano al más lejano.

    Sirve para buscar regla de mapeo: si el 0122 Cocina no tiene una para la
    7685, la del 0120 A&B es la respuesta correcta. Corta ante un ciclo en el
    catálogo —un padre mal capturado no puede colgar el cálculo del P&L.
    """
    salida: list[str] = []
    actual = (dept_code or "").strip()
    vistos = {actual}
    while True:
        padre = (_CONSOLIDATION.get(actual) or "").strip()
        if not padre or padre in vistos:
            return salida
        salida.append(padre)
        vistos.add(padre)
        actual = padre


def group_for_dept(dept_code: str) -> str:
    """Return the P&L group for a dept_code; unknown depts → fallback overhead."""
    return _DEPT_TO_GROUP.get((dept_code or "").strip(), FALLBACK_OVERHEAD_GROUP)


def aggregate_by_group(by_dept: dict[str, Decimal]) -> dict[str, Decimal]:
    """Collapse a dept_code-keyed dict into a group-keyed dict."""
    out: dict[str, Decimal] = {}
    for dept, amount in by_dept.items():
        g = group_for_dept(dept)
        out[g] = out.get(g, ZERO) + (amount or ZERO)
    return out


def revenue_by_group(revenue_by_line: dict[str, Decimal]) -> dict[str, Decimal]:
    """Collapse RevenueResult lines into operating groups."""
    out: dict[str, Decimal] = {}
    for line, amount in revenue_by_line.items():
        g = REVENUE_LINE_TO_GROUP.get(line)
        if g is None:
            continue
        out[g] = out.get(g, ZERO) + (amount or ZERO)
    return out


# ─── Actuals: account_code → P&L classification ───────────────────────────────
# Revenue (4xxx) account ranges → a representative revenue-line key (collapsed to
# groups downstream, so e.g. all F&B accounts map to "food"). Ranges per §7.1.
# Allocation/distribution accounts (cafetería/lavandería redistribution): the CWL
# books use 4900 "Distribución"; 4999 is the spec's "Expense Distribution".
# 4901 se agrego el 2026-08-14. Los libros de CWL la usan para el reparto de la
# Cafeteria, y aca solo estaban la 4900 y la 4999.
#
# Hoy no causaba daño POR CASUALIDAD: la 4901 solo aparece en el depto 0220, que
# ya se salta por `ACTUAL_EXCLUDED_DEPTS` — o sea que lo unico que evitaba que se
# contara como ingreso era una exclusion puesta por otro motivo. El dia que la
# 4901 apareciera en cualquier otro departamento —o que alguien sacara el 0220 de
# esa lista— pasaba a sumar como venta, en silencio.
#
# El mapeo de cuentas SI la conocia (4901/0220 → OH_CAFETERIA), asi que los dos
# caminos del motor decian cosas distintas de la misma cuenta.
ALLOCATION_ACCOUNTS = {"4900", "4901", "4999"}
ALLOCATION_ACCOUNT = "4999"  # canonical (allocation_calculator output)

# Departments excluded from the ACTUALS P&L because their cost is already
# captured elsewhere and would double-count. Cafetería (0220): its cost is
# already inside each department's payroll via concept 6025 (Cafeteria), so the
# standalone cafetería pool is dropped — matching the official CWL report
# (Cafetería shows $0). Laundry (0161) is NOT excluded: it self-nets via 4900.
ACTUAL_EXCLUDED_DEPTS = {"0220"}


def revenue_line_for_account(code: str) -> str | None:
    """Map a 4xxx revenue account to a revenue-line key (None if not revenue)."""
    if code in ALLOCATION_ACCOUNTS:
        return None
    try:
        n = int(code)
    except (TypeError, ValueError):
        return None
    if 4000 <= n <= 4099:
        return "rooms"
    if 4100 <= n <= 4199:
        return "food"        # all F&B → FB group
    if 4200 <= n <= 4299:
        return "spa"
    if 4300 <= n <= 4399:
        return "retail"
    if 4400 <= n <= 4499:
        return "activities"  # tours
    if 4500 <= n <= 4599:
        return "transport"
    if 4600 <= n <= 4699:
        return "innoceana"
    if 4700 <= n <= 4799:
        return "laundry"
    if n == 4880:
        return "sustainability"   # Sustainability Fee — línea propia (driver pax×noche)
    if 4800 <= n <= 4899:
        return "misc_other"       # Other / Misc Revenue (catch-all 0250 Miscelaneos)
    return None


# ─── Cuentas 8xxx (below-GOP): UNA sola verdad ────────────────────────────────
# Espejo EXACTO del `account_mapping` de la base (report `P&L_DETAIL_OWNERS`).
# Si las dos se separan, el motor viejo manda la plata a otra línea sin avisar:
# hasta 2026-08-12 esta tabla decía 8020→mgmt_fee, 8030→capital_reserve y
# 8045→large_capex, cuando en el GL 8020 es capital, 8030 son cargos bancarios y
# 8045 es diferencial cambiario. `tests/test_belowgop_8020.py` vigila que sigan
# alineadas.
#
# 🔑 La cuenta 8020 lleva LAS DOS líneas: Capital Reserve y Large Capital
# Expenditure. El GL las junta en una sola cuenta —el detalle del libro sí las
# separa, y por eso el P&L del owner las muestra abiertas—, así que la apertura
# entra a nivel LÍNEA (snapshot importado `actual_pl_lines`, o `nonop_entries`
# en el checkbook), NUNCA por código de cuenta. Cuando lo único disponible es la
# cuenta, todo cae en CAPITAL_RESERVE: las dos viven dentro de CAPITAL_EXPENSE,
# así que el subtotal, el EBITDA After Capital, el EBT y el Neto no se mueven.
# Por eso `LARGE_CAPEX` no tiene —ni puede tener— una regla de cuenta propia.
NONOP_ACCOUNT_LINE: dict[str, str] = {
    "8000": "RENT",                 # RENT
    "8010": "RENT",                 # (alias histórico)
    "8005": "MGMT_FEE_3",           # OWNERS FEE
    "8015": "PROPERTY_INSURANCE",   # PROPERTY INSURANCE
    "8020": "CAPITAL_RESERVE",      # CAPITAL RESERVE + LARGE CAPITAL EXPENDITURE
    "8025": "OTHER_EXPENSES",       # FINES AND OTHER NON-DEDUCTIBLE EXPENSES
    "8030": "LEASINGS_RENTS",       # BANK AND COMMISSIONS CHARGES
    "8035": "BANK_INTEREST",        # INTEREST ON LOANS
    "8040": "DEPRECIATION",         # DEPRECIATION
    "8045": "FINANCIAL_LOSSES",     # EXCHANGE GAIN/LOSSES
    "8050": "BANK_INTEREST",        # (alias histórico)
    "8060": "INCOME_TAXES",         # INCOME TAX
    "8090": "FINANCIAL_LOSSES",     # Financial Losses (ajuste de reconciliación)
}

# Proyección con pérdida hacia los cajones del motor viejo (`NonOpActuals`), que
# no abre los financieros: leasings y diferencial cambiario comparten cajón con
# los intereses. La sección se respeta —siguen restando entre EBITDA After
# Capital y el EBT—, solo se pierde la sub-línea. El detalle fino vive en el
# camino DB-driven (`calculate_pl_from_mapping`), que sí las separa.
_NONOP_LINE_TO_BUCKET: dict[str, str] = {
    "RENT": "rent",
    "MGMT_FEE_3": "mgmt_fee",
    "MGMT_FEE_5_ROYALTIES": "royalties",
    "PROPERTY_INSURANCE": "properties_insurance",
    "OTHER_EXPENSES": "other_expenses",
    "CAPITAL_RESERVE": "capital_reserve",
    "LARGE_CAPEX": "large_capex",
    "LEASINGS_RENTS": "bank_interest",
    "BANK_INTEREST": "bank_interest",
    "FINANCIAL_LOSSES": "bank_interest",
    "DEPRECIATION": "depreciation",
    "ASSET_LOSS": "depreciation",
    "INCOME_TAXES": "income_tax",
}

# Las 8xxx sin regla caen a bank_interest: no se pierde plata, solo se corre la
# sub-línea (el EBT y el Neto nunca cambian).
NONOP_ACCOUNT_MAP: dict[str, str] = {
    acct: _NONOP_LINE_TO_BUCKET[line] for acct, line in NONOP_ACCOUNT_LINE.items()
}


def nonop_line_for_account(code: str) -> str | None:
    """Línea del reporte de dueños para una cuenta 8xxx. None si no está mapeada."""
    return NONOP_ACCOUNT_LINE.get((code or "").strip())


def nonop_bucket_for_account(code: str) -> str:
    return NONOP_ACCOUNT_MAP.get((code or "").strip(), "bank_interest")


def build_actual_inputs(rows: list[dict]) -> dict:
    """
    Turn raw ActualEntry-like rows into the kwargs that calculate_full_pl expects.

    Each row: {account_code, dept_code, amount} for ONE month.
    Returns: dict with revenue_by_line, payroll_by_dept, cos_by_dept,
             opex_by_dept, alloc_by_dept, nonop (NonOpActuals).
    """
    revenue_by_line: dict[str, Decimal] = {}
    payroll_by_dept: dict[str, Decimal] = {}
    cos_by_dept: dict[str, Decimal] = {}
    opex_by_dept: dict[str, Decimal] = {}
    alloc_by_dept: dict[str, Decimal] = {}
    nonop = NonOpActuals()

    for r in rows:
        code = (r.get("account_code") or "").strip()
        dept = (r.get("dept_code") or "").strip()
        amt = _d(r.get("amount"))
        if not code:
            continue
        if dept in ACTUAL_EXCLUDED_DEPTS:
            continue  # cafetería pool — already in dept payroll (6025)
        first = code[0]

        if code in ALLOCATION_ACCOUNTS:
            alloc_by_dept[dept] = alloc_by_dept.get(dept, ZERO) + amt
        elif first == "4":
            # Prefer dept-based grouping (accurate); fall back to account range.
            grp = group_for_dept(dept) if dept else None
            line = GROUP_TO_REVENUE_LINE.get(grp) or revenue_line_for_account(code)
            if line:
                revenue_by_line[line] = revenue_by_line.get(line, ZERO) + amt
        elif first == "5":
            cos_by_dept[dept] = cos_by_dept.get(dept, ZERO) + amt
        elif first == "6":
            payroll_by_dept[dept] = payroll_by_dept.get(dept, ZERO) + amt
        elif first == "7":
            opex_by_dept[dept] = opex_by_dept.get(dept, ZERO) + amt
        elif first == "8":
            bucket = nonop_bucket_for_account(code)
            setattr(nonop, bucket, getattr(nonop, bucket) + amt)
        # 9xxx (stats) → never in the P&L

    return {
        "revenue_by_line": revenue_by_line,
        "payroll_by_dept": payroll_by_dept,
        "cos_by_dept": cos_by_dept,
        "opex_by_dept": opex_by_dept,
        "alloc_by_dept": alloc_by_dept,
        "nonop": nonop,
    }


# ─── Manual inputs (§17.5) ────────────────────────────────────────────────────
@dataclass
class ManualInputs:
    rent: Decimal = ZERO
    # Management fee as % of revenue is an OPT-IN planning driver (default 0). It
    # is NOT the real fee — real below-GOP comes from the 8xxx accounts. A 0.03
    # default here used to fabricate a phantom 3% mgmt fee on every budget/forecast
    # that had no manual inputs, inflating Non Allocated Expenses. Keep it 0.
    mgmt_fee_pct_3: Decimal = ZERO
    mgmt_fee_pct_5: Decimal = ZERO          # royalties, when applicable
    properties_insurance: Decimal = ZERO
    other_expenses: Decimal = ZERO          # 8025 — multas y no deducibles
    capital_reserve: Decimal = ZERO
    capital_reserve_pct: Decimal = ZERO     # if > 0, reserve = revenue × pct
    large_capex: Decimal = ZERO
    bank_interest: Decimal = ZERO
    depreciation: Decimal = ZERO
    income_tax_rate: Decimal = Decimal("0.30")


@dataclass
class NonOpActuals:
    """
    Real recorded non-operating amounts for ACTUAL scenarios (from 8xxx accounts).
    When supplied, these are used DIRECTLY instead of computing them from
    ManualInputs — mgmt fees and income tax are real figures, not formulas.
    """
    rent: Decimal = ZERO
    mgmt_fee: Decimal = ZERO
    royalties: Decimal = ZERO
    properties_insurance: Decimal = ZERO
    other_expenses: Decimal = ZERO          # 8025 — multas y no deducibles
    capital_reserve: Decimal = ZERO
    large_capex: Decimal = ZERO
    bank_interest: Decimal = ZERO
    depreciation: Decimal = ZERO
    income_tax: Decimal = ZERO


# ─── P&L line result (engine output) ──────────────────────────────────────────
@dataclass
class PLLineResult:
    line_code: str
    line_name: str
    section: str
    amount_usd: Decimal
    dept_code: str | None = None
    is_calculated: bool = True


def get_line(lines: list[PLLineResult], code: str) -> Decimal:
    """Return the amount for a line_code (0 if absent)."""
    for ln in lines:
        if ln.line_code == code:
            return ln.amount_usd
    return ZERO


# ─── Renta: mensual con signo, consolidada al año ─────────────────────────────
def renta_por_mes(ebt_por_mes: list[Decimal],
                           tasa: Decimal) -> list[Decimal]:
    """El impuesto de renta de cada mes, con su signo, consolidado al año.

    **La regla, en palabras del owner.** «El impuesto de renta *se calcula mes a
    mes no importa si es negativo o positivo*. Y *se consolida anualmente*.» Y
    la precisión que la completa: «algunos meses puede ser negativo, otros
    positivos, pero *en forma anual debe ser positivo*.»

    O sea que el piso de cero **existe, pero es del AÑO, no del mes**:

      1. **Mensual** — `impuesto_mes = EBT_mes × tasa`, con signo. Un mes en
         pérdida da impuesto NEGATIVO: es un crédito, y así es como se devenga.
         No hay piso a nivel de mes.
      2. **Anual** — la suma no puede ser negativa. Si el ejercicio completo da
         pérdida, el impuesto del año es CERO. No es un reembolso: Hacienda no
         devuelve plata por un año en rojo, el resultado negativo se arrastra.

    **El error que corrige.** El P&L calculaba `MAX(0, EBT_mes × 30%)`, con el
    piso adentro de CADA mes. Dos consecuencias, y las dos cuestan plata:

      · Las pérdidas de un mes no compensaban las ganancias de otro, así que el
        impuesto del año salía inflado justo en el 30% de esas pérdidas. Medido
        el 2026-08-16 contra producción: el Budget Final 2027 provisionaba
        $128.861 de más (tasa efectiva 35,7%) y el Working 2027 $171.053 de más
        (39,2%), contra un estatutario del 30%. En Corcovado pega todos los años
        porque el lodge cierra en octubre.
      · Un mes en pérdida aparecía SIN efecto fiscal, cuando en realidad genera
        un crédito. Eso ensucia la lectura de un mes suelto y el flujo de caja
        mensual — y el owner mira meses sueltos.

    **El caso borde: el año que cierra en pérdida.** Si el impuesto del año es
    cero, la suma de los doce meses tiene que dar cero también; si no, el P&L
    mensual y el anual dirían dos cosas distintas sobre la misma cuenta. El
    criterio que se eligió es **cero en los doce meses**, y la razón es que un
    año en pérdida no genera crédito cobrable: no hay nada que devengar en
    ningún mes. Mostrar créditos mensuales que al final del año no valen nada
    sería anotar un activo que no existe. La regla, entonces:

        si ΣEBT_mes ≤ 0  →  cero en los doce meses
        si ΣEBT_mes > 0  →  EBT_mes × tasa en cada mes, con su signo

    En los dos casos **la suma de los doce es exactamente el impuesto del año**,
    que es la condición que no se puede romper.
    """
    n = len(ebt_por_mes)
    if n == 0:
        return []
    anual = sum(ebt_por_mes, ZERO)
    if anual <= ZERO or tasa <= ZERO:
        return [ZERO] * n
    # Cada mes lleva el impuesto de SU resultado, con signo. No se prorratea el
    # anual hacia atrás: la consolidación sale sola, porque los cargos de los
    # meses con ganancia y los créditos de los meses en pérdida se compensan.
    return [e * tasa for e in ebt_por_mes]


# El P&L tiene dos vocabularios de códigos para los mismos totales: el path IMPORTADO
# (snapshot de Actuals/budgets) emite el set "viejo" (GOP, EBITDA_BEFORE, TOTAL_OPEXP…)
# y el path CHECKBOOK (report_line_config) el "nuevo" (TOTAL_GOP, EBITDA_BEFORE_CAPITAL…).
# Para que TODOS los consumidores (home, dashboard, simplified, reportes) funcionen sin
# importar el modo del escenario, exponemos AMBOS códigos con el mismo valor.
_PL_ALIASES = [
    ("GOP", "TOTAL_GOP"),
    ("EBITDA_BEFORE", "EBITDA_BEFORE_CAPITAL"),
    ("EBITDA_AFTER", "EBITDA_AFTER_CAPITAL"),
    ("TOTAL_OPEXP", "TOTAL_OPERATING_EXPENSES"),
    ("TOTAL_OVERHEAD", "TOTAL_OVERHEAD_EXPENSES"),
    ("TOTAL_OP_PROFIT", "OPERATING_PROFIT"),
    ("TOTAL_NON_OP", "TOTAL_NON_OP_EXPENSES"),
]


def add_pl_aliases(lines: list[PLLineResult]) -> list[PLLineResult]:
    """Asegura que ambos vocabularios de código estén presentes con el mismo valor.
    Para cada par, toma el valor no-cero y lo copia al código que falte o esté en 0.
    Idempotente — no toca pares donde ambos ya coinciden."""
    by_code = {ln.line_code: ln for ln in lines}
    out = list(lines)
    for a, b in _PL_ALIASES:
        la, lb = by_code.get(a), by_code.get(b)
        va = la.amount_usd if la else ZERO
        vb = lb.amount_usd if lb else ZERO
        val = va if abs(va) >= abs(vb) else vb
        if val == ZERO:
            continue
        src = la or lb
        for code, ln in ((a, la), (b, lb)):
            if ln is None:
                out.append(PLLineResult(line_code=code, line_name=src.line_name,
                                        section=src.section, amount_usd=val,
                                        is_calculated=True))
            elif ln.amount_usd == ZERO:
                ln.amount_usd = val
    return out


# ─── Vocabulario CANÓNICO (report_line_config / snapshot) ─────────────────────
# El motor (calculate_full_pl) emite un vocabulario propio (REV_*, OPEXP_*,
# OPPROFIT_*, OVH_*, secciones cortas); el snapshot/budget usa el de
# report_line_config (REV_*, OPEX_*, PROFIT_*, OH_*, secciones largas). Para que
# CUALQUIER escenario sea comparable (Full P&L, dashboard), traducimos cada línea
# del vocabulario del motor a su equivalente canónico, ASEGURANDO que el código
# canónico exista con la sección canónica. Es ADITIVO: no cambia ningún monto ni
# borra códigos — solo agrega los que falten y corrige la sección.
# {motor_code: (canon_code, canon_section)}
_MOTOR_TO_CANON: dict[str, tuple[str, str]] = {
    # Revenue
    "REV_ROOMS": ("REV_ROOMS", "REVENUES"), "REV_FB": ("REV_FB", "REVENUES"),
    "REV_PRIVATE_BAR": ("REV_PRIVATE_BAR", "REVENUES"),
    "REV_TIENDA": ("REV_TIENDA", "REVENUES"),
    "REV_SPA": ("REV_SPA", "REVENUES"), "REV_TOURS": ("REV_TOURS", "REVENUES"),
    "REV_RETAIL": ("REV_RETAIL", "REVENUES"),
    "REV_TRANSPORT": ("REV_TRANSPORTATION", "REVENUES"),
    "REV_LAUNDRY": ("REV_LAUNDRY", "REVENUES"),
    "REV_INNOCEANA": ("REV_INNOCEANA", "REVENUES"),
    "REV_CROWTHER": ("REV_CROWTHER_LAB", "REVENUES"),
    "REV_CLUB": ("REV_CLUB", "REVENUES"),
    "REV_AREC": ("REV_AREC", "REVENUES"),
    "REV_SUSTAINABILITY": ("REV_SUSTAINABILITY", "REVENUES"),
    "REV_MISC_OTHER": ("REV_MISC_OTHER", "REVENUES"),
    "TOTAL_REVENUES": ("TOTAL_REVENUES", "REVENUES"),
    # Operating expenses
    "OPEXP_ROOMS": ("OPEX_ROOMS", "OPERATING EXPENSES"),
    "OPEXP_FB": ("OPEX_FB", "OPERATING EXPENSES"),
    "OPEXP_PRIVATE_BAR": ("OPEX_PRIVATE_BAR", "OPERATING EXPENSES"),
    "OPEXP_TIENDA": ("OPEX_TIENDA", "OPERATING EXPENSES"),
    "OPEXP_SPA": ("OPEX_SPA", "OPERATING EXPENSES"),
    "OPEXP_TOURS": ("OPEX_TOURS", "OPERATING EXPENSES"),
    "OPEXP_RETAIL": ("OPEX_RETAIL", "OPERATING EXPENSES"),
    "OPEXP_TRANSPORT": ("OPEX_TRANSPORTATION", "OPERATING EXPENSES"),
    "OPEXP_LAUNDRY": ("OPEX_LAUNDRY", "OPERATING EXPENSES"),
    "OPEXP_INNOCEANA": ("OPEX_INNOCEANA", "OPERATING EXPENSES"),
    "OPEXP_CROWTHER": ("OPEX_CROWTHER_LAB", "OPERATING EXPENSES"),
    "OPEXP_CLUB": ("OPEX_CLUB", "OPERATING EXPENSES"),
    # AREC no emite OPEXP_ (su costo baja al overhead como OVH_AREC → OH_AREC)
    "TOTAL_OPEXP": ("TOTAL_OPERATING_EXPENSES", "OPERATING EXPENSES"),
    # Operating profit
    "OPPROFIT_ROOMS": ("PROFIT_ROOMS", "OPERATING PROFIT"),
    "OPPROFIT_FB": ("PROFIT_FB", "OPERATING PROFIT"),
    "OPPROFIT_PRIVATE_BAR": ("PROFIT_PRIVATE_BAR", "OPERATING PROFIT"),
    "OPPROFIT_TIENDA": ("PROFIT_TIENDA", "OPERATING PROFIT"),
    "OPPROFIT_SPA": ("PROFIT_SPA", "OPERATING PROFIT"),
    "OPPROFIT_TOURS": ("PROFIT_TOURS", "OPERATING PROFIT"),
    "OPPROFIT_RETAIL": ("PROFIT_RETAIL", "OPERATING PROFIT"),
    "OPPROFIT_TRANSPORT": ("PROFIT_TRANSPORTATION", "OPERATING PROFIT"),
    "OPPROFIT_LAUNDRY": ("PROFIT_LAUNDRY", "OPERATING PROFIT"),
    "OPPROFIT_INNOCEANA": ("PROFIT_INNOCEANA", "OPERATING PROFIT"),
    "OPPROFIT_CROWTHER": ("PROFIT_CROWTHER_LAB", "OPERATING PROFIT"),
    "OPPROFIT_CLUB": ("PROFIT_CLUB", "OPERATING PROFIT"),
    "OPPROFIT_AREC": ("PROFIT_AREC", "OPERATING PROFIT"),
    "OPPROFIT_SUSTAINABILITY": ("PROFIT_SUSTAINABILITY", "OPERATING PROFIT"),
    "OPPROFIT_MISC_OTHER": ("PROFIT_MISC_OTHER", "OPERATING PROFIT"),
    "TOTAL_OP_PROFIT": ("OPERATING_PROFIT", "OPERATING PROFIT"),
    # Overhead
    "OVH_ADMIN": ("OH_ADMIN", "OVERHEAD EXPENSES"),
    "OVH_SALES": ("OH_SALES_MARKETING", "OVERHEAD EXPENSES"),
    "OVH_MAINTENANCE": ("OH_MAINTENANCE", "OVERHEAD EXPENSES"),
    "OVH_IT": ("OH_INFORMATION_SYSTEM", "OVERHEAD EXPENSES"),
    "OVH_UTILITIES": ("OH_UTILITIES", "OVERHEAD EXPENSES"),
    "OVH_AREC": ("OH_AREC", "OVERHEAD EXPENSES"),
    # ⚠️ Faltaban estos dos. El motor legacy emite `OVH_{grupo}` para TODOS los
    # grupos de overhead, y sin alias su gasto no aparecía bajo ningún `OH_*`:
    # en un escenario de checkbook, `SUM(OH_*)` sobre las líneas devueltas no
    # daba `TOTAL_OVERHEAD_EXPENSES`. Lo vigila
    # `test_el_puente_cubre_todos_los_grupos_de_overhead`.
    "OVH_CAFETERIA": ("OH_CAFETERIA", "OVERHEAD EXPENSES"),
    "OVH_LAUNDRY_OPS": ("OH_LAUNDRY", "OVERHEAD EXPENSES"),
    "TOTAL_OVERHEAD": ("TOTAL_OVERHEAD_EXPENSES", "OVERHEAD EXPENSES"),
    # GOP
    "GOP": ("TOTAL_GOP", "GOP"),
    # Non-operating / owner
    "RENT": ("RENT", "OWNER / NON-OP EXPENSES"),
    "MGMT_FEE": ("MGMT_FEE_3", "OWNER / NON-OP EXPENSES"),
    "ROYALTIES": ("MGMT_FEE_5_ROYALTIES", "OWNER / NON-OP EXPENSES"),
    "TOTAL_MGMT_FEES": ("TOTAL_RENT_MGMT_FEES", "OWNER / NON-OP EXPENSES"),
    "PROPERTIES_INSURANCE": ("PROPERTY_INSURANCE", "OWNER / NON-OP EXPENSES"),
    "OTHER_EXPENSES": ("OTHER_EXPENSES", "OWNER / NON-OP EXPENSES"),
    "TOTAL_NON_OP": ("TOTAL_NON_OP_EXPENSES", "OWNER / NON-OP EXPENSES"),
    # EBITDA before + capital
    "EBITDA_BEFORE": ("EBITDA_BEFORE_CAPITAL", "EBITDA"),
    "CAPITAL_RESERVE": ("CAPITAL_RESERVE", "CAPITAL"),
    "LARGE_CAPEX": ("LARGE_CAPEX", "CAPITAL"),
    "CAPITAL_EXPENSE": ("CAPITAL_EXPENSE", "CAPITAL"),
    # EBITDA after + financial + depreciation
    "EBITDA_AFTER": ("EBITDA_AFTER_CAPITAL", "EBITDA"),
    "BANK_INTEREST": ("BANK_INTEREST", "FINANCIAL EXPENSES"),
    "FINANCIAL_EXPENSES": ("FINANCIAL_EXPENSES", "FINANCIAL EXPENSES"),
    "DEPRECIATION": ("DEPRECIATION", "DEPRECIATION"),
    "TOTAL_DEPRECIATIONS": ("TOTAL_DEPRECIATIONS", "DEPRECIATION"),
    # Tax / net
    "EBT": ("EBT", "TAX / NET PROFIT"),
    "INCOME_TAXES": ("INCOME_TAXES", "TAX / NET PROFIT"),
    "NET_PROFIT": ("NET_PROFIT", "TAX / NET PROFIT"),
}


def canonicalize_pl_lines(lines: list[PLLineResult]) -> list[PLLineResult]:
    """Garantiza que cada línea del vocabulario del motor tenga su equivalente
    canónico (report_line_config) con la sección canónica. ADITIVO: no cambia
    ningún monto ni borra códigos; agrega el código canónico que falte (mismo
    valor) y corrige su sección. Escenarios que ya están en el vocabulario
    canónico no se ven afectados (sus motor_code no existen → se saltan)."""
    by_code = {ln.line_code: ln for ln in lines}
    out = list(lines)
    for motor_code, (canon_code, canon_section) in _MOTOR_TO_CANON.items():
        src = by_code.get(motor_code)
        if src is None:
            continue
        tgt = by_code.get(canon_code)
        if tgt is None:
            tgt = PLLineResult(canon_code, src.line_name, canon_section,
                               src.amount_usd, src.dept_code, src.is_calculated)
            out.append(tgt)
            by_code[canon_code] = tgt
        else:
            tgt.section = canon_section
    return out


def par_por(amount, rooms_available, rooms_occupied) -> tuple[float, float]:
    """USALI per-room metrics for a P&L line amount.

    PAR = Per Available Room  = amount / rooms_available
    POR = Per Occupied Room   = amount / rooms_occupied

    Returns (par, por) as floats. Divide-by-zero yields 0.0 (closed period /
    empty scenario), never raises.
    """
    amt = float(amount or 0)
    avail = float(rooms_available or 0)
    occ = float(rooms_occupied or 0)
    par = amt / avail if avail else 0.0
    por = amt / occ if occ else 0.0
    return par, por


def _d(x) -> Decimal:
    return x if isinstance(x, Decimal) else Decimal(str(x or 0))


# ─── Main engine ──────────────────────────────────────────────────────────────
def calculate_full_pl(
    *,
    revenue_by_line: dict[str, Decimal],
    payroll_by_dept: dict[str, Decimal],
    cos_by_dept: dict[str, Decimal],
    opex_by_dept: dict[str, Decimal],
    alloc_by_dept: dict[str, Decimal] | None = None,
    manual: ManualInputs | None = None,
    nonop: NonOpActuals | None = None,
    income_tax: Decimal | None = None,
) -> list[PLLineResult]:
    """
    Build the Full P&L line list (one month) in report order.

    All *_by_dept dicts are keyed by dept_code; allocations net to zero across
    all depts so totals are unaffected, but they shift per-dept operating profit.

    nonop: if provided (ACTUAL scenarios), the non-operating section + income tax
    use these real recorded amounts instead of the ManualInputs formulas.

    income_tax: el impuesto del mes ya resuelto con el año a la vista
    (`renta_por_mes`) — puede venir NEGATIVO, que es un crédito de un
    mes en pérdida. Manda sobre la fórmula mensual, pero NUNCA sobre una cifra
    contabilizada de verdad: si el escenario trae la renta en el detalle
    (`nonop.income_tax`), esa gana siempre.
    """
    manual = manual or ManualInputs()
    alloc_by_dept = alloc_by_dept or {}

    rev = revenue_by_group(revenue_by_line)
    pay = aggregate_by_group(payroll_by_dept)
    cos = aggregate_by_group(cos_by_dept)
    opx = aggregate_by_group(opex_by_dept)
    alc = aggregate_by_group(alloc_by_dept)

    lines: list[PLLineResult] = []

    def add(code, name, section, amount, dept=None, calculated=True):
        lines.append(PLLineResult(code, name, section, _d(amount), dept, calculated))

    # 1. REVENUES ──────────────────────────────────────────────────────────────
    total_revenue = ZERO
    for g in OPERATING_GROUP_ORDER:
        amt = rev.get(g, ZERO)
        if g == "SUSTAINABILITY" and amt == ZERO and "SUSTAINABILITY" not in rev:
            pass
        add(f"REV_{g}", GROUP_NAMES[g], "REVENUE", amt, dept=g)
        total_revenue += amt
    add("TOTAL_REVENUES", "Total Revenues", "REVENUE", total_revenue)

    # 2. OPERATING EXPENSES per dept = Payroll + CoS + OpEx + Allocations ────────
    op_exp: dict[str, Decimal] = {}
    total_op_exp = ZERO
    for g in OPERATING_GROUP_ORDER:
        if g in REVENUE_ONLY_GROUPS:
            continue  # el costo de estos no vive en el bloque operativo
        e = pay.get(g, ZERO) + cos.get(g, ZERO) + opx.get(g, ZERO) + alc.get(g, ZERO)
        op_exp[g] = e
        total_op_exp += e
        add(f"OPEXP_{g}", GROUP_NAMES[g], "OPEXP", e, dept=g)
    add("TOTAL_OPEXP", "Total Operating Expenses", "OPEXP", total_op_exp)

    # 3. OPERATING PROFIT per dept = Revenue − Operating Expenses ────────────────
    total_op_profit = ZERO
    for g in OPERATING_GROUP_ORDER:
        p = rev.get(g, ZERO) - op_exp.get(g, ZERO)
        total_op_profit += p
        add(f"OPPROFIT_{g}", GROUP_NAMES[g], "OP_PROFIT", p, dept=g)
    add("TOTAL_OP_PROFIT", "Total Operating Profit", "OP_PROFIT", total_op_profit)

    # 4. OVERHEAD = Payroll + OpEx + Allocations (no revenue, no CoS) ────────────
    total_overhead = ZERO
    for g in OVERHEAD_GROUP_ORDER:
        e = pay.get(g, ZERO) + opx.get(g, ZERO) + cos.get(g, ZERO) + alc.get(g, ZERO)
        if e == ZERO and g in (FALLBACK_OVERHEAD_GROUP, "CAFETERIA", "LAUNDRY_OPS"):
            # skip empty noise lines
            if g not in pay and g not in opx and g not in alc and g not in cos:
                continue
        total_overhead += e
        add(f"OVH_{g}", GROUP_NAMES[g], "OVERHEAD", e, dept=g)
    add("TOTAL_OVERHEAD", "Total Overhead Expenses", "OVERHEAD", total_overhead)

    # 5. GOP = Operating Profit − Overhead ──────────────────────────────────────
    gop = total_op_profit - total_overhead
    add("GOP", "Total Gross Operating Profit (GOP)", "GOP", gop)

    # 6. NON-OPERATING ────────────────────────────────────────────────────────────
    # Budget/Forecast: computed from ManualInputs (mgmt fee = revenue × %).
    # Actuals: real recorded amounts from 8xxx (nonop).
    if nonop is not None:
        rent = _d(nonop.rent)
        mgmt_fee = _d(nonop.mgmt_fee)
        royalties = _d(nonop.royalties)
        insurance = _d(nonop.properties_insurance)
        other_exp = _d(nonop.other_expenses)
    else:
        rent = _d(manual.rent)
        mgmt_fee = total_revenue * _d(manual.mgmt_fee_pct_3)
        royalties = total_revenue * _d(manual.mgmt_fee_pct_5)
        insurance = _d(manual.properties_insurance)
        other_exp = _d(manual.other_expenses)
    total_mgmt = mgmt_fee + royalties
    total_non_op = rent + total_mgmt + insurance + other_exp

    add("RENT", "Rent", "NON_OP", rent, calculated=False)
    add("MGMT_FEE", "Management Fees (3%)", "NON_OP", mgmt_fee)
    add("ROYALTIES", "Management Fees (5%) Royalties", "NON_OP", royalties)
    add("TOTAL_MGMT_FEES", "Total Rent and Management Fees", "NON_OP", rent + total_mgmt)
    add("PROPERTIES_INSURANCE", "Properties Insurance", "NON_OP", insurance, calculated=False)
    # 8025 (multas y gastos no deducibles) va ARRIBA del EBITDA, con los demás
    # gastos de dueño. Antes caía al cajón de intereses y aparecía debajo del
    # EBITDA After Capital: el EBT daba igual, la sub-línea no.
    add("OTHER_EXPENSES", "Other Expenses", "NON_OP", other_exp, calculated=False)
    add("TOTAL_NON_OP", "Total Non-Operating Expenses", "NON_OP", total_non_op)

    # 7. EBITDA BEFORE CAPITAL ───────────────────────────────────────────────────
    ebitda_before = gop - total_non_op
    add("EBITDA_BEFORE", "EBITDA Before Capital", "EBITDA_CAP", ebitda_before)

    # 8. CAPITAL ─────────────────────────────────────────────────────────────────
    src = nonop if nonop is not None else manual
    capital_reserve = _d(src.capital_reserve)
    large_capex = _d(src.large_capex)
    capital_exp = capital_reserve + large_capex
    add("CAPITAL_RESERVE", "Capital Reserve", "EBITDA_CAP", capital_reserve, calculated=False)
    add("LARGE_CAPEX", "Large Capital Expenditure", "EBITDA_CAP", large_capex, calculated=False)
    add("CAPITAL_EXPENSE", "Capital Expense", "EBITDA_CAP", capital_exp)

    ebitda_after = ebitda_before - capital_exp
    add("EBITDA_AFTER", "EBITDA After Capital", "EBITDA_AFTER", ebitda_after)

    # 9. FINANCIAL & DEPRECIATION ────────────────────────────────────────────────
    bank_interest = _d(src.bank_interest)
    depreciation = _d(src.depreciation)
    add("BANK_INTEREST", "Bank Interest Charges", "EBITDA_AFTER", bank_interest, calculated=False)
    add("FINANCIAL_EXPENSES", "Financial Expenses", "EBITDA_AFTER", bank_interest)
    add("DEPRECIATION", "Depreciation", "EBITDA_AFTER", depreciation, calculated=False)
    add("TOTAL_DEPRECIATIONS", "Total Depreciations", "EBITDA_AFTER", depreciation)

    # 10. EBT, TAX, NET PROFIT ───────────────────────────────────────────────────
    ebt = ebitda_after - bank_interest - depreciation
    add("EBT", "Earnings Before Income Taxes", "EBT", ebt)

    if nonop is not None and _d(nonop.income_tax) != ZERO:
        tax = _d(nonop.income_tax)          # real recorded tax (if booked)
        if tax < ZERO:
            tax = ZERO
    elif income_tax is not None:
        tax = _d(income_tax)                # ya resuelto con el AÑO a la vista
    else:
        # Income tax is not in the account detail — compute 30% of positive EBT.
        # Piso MENSUAL: sobre-provisiona si hay meses en pérdida. Solo se llega
        # acá sin el contexto de los doce meses (uso suelto del motor, tests).
        tax = ebt * _d(manual.income_tax_rate)
        if tax < ZERO:
            tax = ZERO
    add("INCOME_TAXES", "Income Taxes (30%)", "EBT", tax)

    net_profit = ebt - tax
    add("NET_PROFIT", "Net Profit", "NET_PROFIT", net_profit)

    return lines


# ─── DB-driven P&L (uses account_mapping + report_line_config) ────────────────

def _eval_calc_logic(expr: str, amounts: dict[str, Decimal]) -> Decimal:
    """
    Evaluate a calc_logic expression from report_line_config.

    Supports:
      SUM(PREFIX_*)     — sum all amounts whose key starts with PREFIX_
      SUM(EXACT_CODE)   — return amounts[EXACT_CODE]
      A - B + C         — simple additive/subtractive arithmetic
    """
    expr = expr.strip()
    if not expr or "SUM mapped" in expr or "Source" in expr:
        return ZERO

    def _termino(tok: str) -> Decimal:
        """Un término suelto: `SUM(PREFIJO_*)`, `SUM(CODIGO)` o un código."""
        m = re.fullmatch(r"SUM\((\w+)\*\)", tok)
        if m:
            p = m.group(1)
            return sum((v for k, v in amounts.items() if k.startswith(p)), ZERO)
        m = re.fullmatch(r"SUM\((\w+)\)", tok)
        if m:
            return amounts.get(m.group(1), ZERO)
        return amounts.get(tok, ZERO)

    # Se tokeniza SIEMPRE, aunque haya un solo término. Antes las dos formas de
    # `SUM(...)` se resolvían con un `fullmatch` sobre la expresión ENTERA, así
    # que `SUM(OPEX_*) + SUM(COS_*)` no calzaba con ninguna rama y caía en la
    # aritmética, que buscaba «SUM(OPEX_*)» como si fuera un código de línea: no
    # existe, devolvía cero, y el total salía en 0.00.
    #
    # Hizo falta al separar el costo de ventas de las cuentas clase 5 en su
    # propia línea (owner, 2026-08-14): `TOTAL_OPERATING_EXPENSES` pasó a sumar
    # dos grupos. El `-` de dentro de un nombre no molesta: los códigos usan
    # guión bajo, y se corta solo por `+`/`-` con espacios alrededor.
    tokens = re.split(r"\s+([-+])\s+", expr)
    result = ZERO
    op = "+"
    for tok in tokens:
        tok = tok.strip()
        if tok in ("+", "-"):
            op = tok
        elif tok:
            val = _termino(tok)
            result = result + val if op == "+" else result - val
    return result


def calculate_pl_from_mapping(
    acct_rows: list[dict],
    mappings: list[dict],
    report_lines: list[dict],
    seed_amounts: dict[str, Decimal] | None = None,
) -> list[PLLineResult]:
    """
    DB-driven P&L calculation.

    acct_rows:    [{account_code, dept_code, amount}] for one month
    mappings:     [{account_code, dept_code, report_line_code, active_status,
                    rollup_operator}] — loaded from account_mapping table
    report_lines: [{line_code, line_name, section, line_type, display_order,
                    calculation_logic, active}] — sorted by display_order
    seed_amounts: optional {report_line_code: amount} pre-seeded into the
                  accumulator before the account rows are applied. Used for
                  budget/forecast revenue, which is computed from rate cards at
                  the line level (REV_ROOMS, REV_FB, …) and has no 4xxx account
                  detail to roll up. Account rows then add on top.
    """
    resolver = construir_resolvedor(mappings)

    # Accumulate raw amounts by report_line_code (revenue seeds first)
    line_amounts: dict[str, Decimal] = {}
    if seed_amounts:
        for lc, amt in seed_amounts.items():
            line_amounts[lc] = line_amounts.get(lc, ZERO) + _d(amt)
    for row in acct_rows:
        code = str(row.get("account_code") or "").strip()
        dept = str(row.get("dept_code") or "").strip()
        amt = _d(row.get("amount"))
        if not code:
            continue

        m, _como = resolver(dept, code)
        if not m:
            continue  # unmapped — visible via /mapping/unmapped/ endpoint

        lc = m.get("report_line_code", "")
        if not lc:
            continue
        if m.get("rollup_operator") == "SUBTRACT":
            line_amounts[lc] = line_amounts.get(lc, ZERO) - amt
        else:
            line_amounts[lc] = line_amounts.get(lc, ZERO) + amt

    # Evaluate report lines in display_order, computing CALCULATED lines
    result: list[PLLineResult] = []
    for rl in sorted(report_lines, key=lambda x: x.get("display_order", 9999)):
        if not rl.get("active", True):
            continue
        lt = rl.get("line_type", "MAPPED")
        if lt == "KPI":
            continue  # KPIs sourced from separate operational data

        lc = rl.get("line_code", "")
        if lt in ("CALCULATED", "CALCULATED_REVIEW"):
            amt = _eval_calc_logic(rl.get("calculation_logic") or "", line_amounts)
        elif lt in ("MAPPED", "MAPPED_REVIEW"):
            amt = line_amounts.get(lc, ZERO)
        else:  # HEADER
            amt = ZERO

        # Make computed value available to downstream calc lines
        line_amounts[lc] = amt
        result.append(PLLineResult(
            line_code=lc,
            line_name=rl.get("line_name", lc),
            section=rl.get("section", ""),
            amount_usd=amt,
        ))

    return result


def calculate_budget_pl_from_mapping(
    acct_rows: list[dict],
    mappings: list[dict],
    report_lines: list[dict],
    *,
    revenue_by_line: dict[str, Decimal],
    manual: ManualInputs | None = None,
    extra_seeds: dict[str, Decimal] | None = None,
    income_tax: Decimal | None = None,
) -> list[PLLineResult]:
    """
    DB-driven P&L for a BUDGET/FORECAST built from the in-app checkbooks.

    Operating cost detail flows through the SAME validated engine the actuals
    use as account rows (payroll/cost/opex 6xxx/5xxx/7xxx).

    Below-GOP lines (rent, insurance, other, capital reserve, large capex, bank
    interest, leasings, financial losses, depreciation, asset loss) arrive via
    `extra_seeds` keyed by report_line_code — seeded directly because several
    lines share one GL account and the mapping can't split them.

    The two computed drivers are seeded here (formulas, no entered detail):
      - management fees: total revenue × pct (3% / 5%)
      - income tax: el impuesto del mes, con su signo. El piso de cero es
        ANUAL, así que se decide con los doce meses a la vista
        (`renta_por_mes`) y llega acá por `income_tax`. Sin ese
        contexto se cae al 30% del EBT del mes con piso mensual, que
        sobre-provisiona.
    Revenue is also seeded (line-level from rate cards, no 4xxx detail).
    """
    manual = manual or ManualInputs()
    seeds = revenue_seed_from_lines(revenue_by_line)
    # Blindaje: si una línea de ingreso no existe en el reporte configurado, el motor
    # la descartaría en silencio y ese ingreso desaparecería del P&L (pasaba con
    # REV_SUSTAINABILITY, que en el reporte se llama REV_MISC_OTHER). Se repliega al
    # cajón de "otros ingresos" para que el total nunca pierda plata.
    _codes = {r.get("line_code") for r in report_lines}
    if _codes:
        _fallback = "REV_MISC_OTHER" if "REV_MISC_OTHER" in _codes else None
        for _lc in [k for k in seeds if k.startswith("REV_") and k not in _codes]:
            _amt = seeds.pop(_lc)
            if _fallback:
                seeds[_fallback] = seeds.get(_fallback, ZERO) + _amt
    total_rev = sum(seeds.values(), ZERO)

    if extra_seeds:
        for lc, amt in extra_seeds.items():
            seeds[lc] = seeds.get(lc, ZERO) + _d(amt)

    # Honorarios de administración: DOS líneas abiertas a propósito —el 3% de
    # management fee y el 5% de royalties son conceptos distintos, aunque el GL
    # los junte en la cuenta 8005 y el Excel de Amarena los muestre en una sola.
    # `TOTAL_RENT_MGMT_FEES` las vuelve a juntar, así que el consolidado sale
    # igual en las dos lecturas.
    #
    # El porcentaje es un DRIVER OPCIONAL, no la verdad: manda solo si está
    # configurado. Antes esta asignación era `=` a secas y corría DESPUÉS de
    # `extra_seeds` → cualquier honorario digitado en el mini-checkbook de
    # below-GOP (`nonop_entries`) quedaba pisado por la fórmula, y sin
    # porcentaje cargado lo pisaba con CERO. La plata desaparecía sin avisar.
    for _lc, _pct in (("MGMT_FEE_3", manual.mgmt_fee_pct_3),
                      ("MGMT_FEE_5_ROYALTIES", manual.mgmt_fee_pct_5)):
        if _d(_pct) > ZERO:
            seeds[_lc] = total_rev * _d(_pct)
        else:
            seeds.setdefault(_lc, ZERO)
    # Capital Reserve as % of revenue (owner-validated). Overrides any manual
    # amount only when a pct is set.
    if _d(manual.capital_reserve_pct) > ZERO:
        seeds["CAPITAL_RESERVE"] = total_rev * _d(manual.capital_reserve_pct)

    # Pass 1 — everything except income tax, to read EBT.
    first = calculate_pl_from_mapping(acct_rows, mappings, report_lines, seed_amounts=seeds)
    ebt = get_line(first, "EBT")
    if income_tax is not None:
        # El impuesto del mes ya viene resuelto con el año a la vista (ver
        # `renta_por_mes`), con su signo. Es el camino normal.
        tax = _d(income_tax)
    else:
        # Sin contexto anual (uso suelto del motor, tests): 30% del EBT del mes.
        # Ojo: acá el piso de cero es MENSUAL y sobre-provisiona si hay meses en
        # pérdida. Quien calcula los doce meses debe pasar `income_tax`.
        tax = ebt * _d(manual.income_tax_rate)
        if tax < ZERO:
            tax = ZERO
    seeds["INCOME_TAXES"] = tax

    # Pass 2 — final, with tax seeded so NET_PROFIT = EBT − tax.
    return calculate_pl_from_mapping(acct_rows, mappings, report_lines, seed_amounts=seeds)


# ─── Line-level actuals (macro P&L, no account detail) ────────────────────────
def standard_pl_template() -> list[PLLineResult]:
    """The full set of standard P&L lines in report order, all zero."""
    return calculate_full_pl(
        revenue_by_line={}, payroll_by_dept={}, cos_by_dept={}, opex_by_dept={},
    )


def actual_pl_from_lines(amounts: dict[str, Decimal]) -> list[PLLineResult]:
    """
    Build a P&L line list directly from stored line-level actual amounts
    (keyed by line_code). Used for ACTUAL scenarios whose source is the macro
    P&L report (per line, no account/dept detail). Lines not provided stay 0.
    """
    out: list[PLLineResult] = []
    for t in standard_pl_template():
        amt = amounts.get(t.line_code, t.amount_usd)
        out.append(PLLineResult(
            t.line_code, t.line_name, t.section, _d(amt), t.dept_code,
            is_calculated=False,
        ))

    # The imported snapshot stores the below-GOP components (rent, mgmt, insurance)
    # and EBITDA Before Capital, but NOT the TOTAL_NON_OP line itself — it comes
    # through blank, so the waterfall shows GOP − 0 ≠ EBITDA Before and the cash
    # flow reads Non Allocated = 0. EBITDA Before already nets the real non-op, so
    # derive the total = GOP − EBITDA Before. This equals the real 8xxx figure to
    # the dollar and captures amounts (e.g. Other) not stored as their own line.
    # Display-only: it never changes EBITDA / EBT / tax / net (those are stored).
    if "TOTAL_NON_OP" not in amounts and "TOTAL_NON_OP_EXPENSES" not in amounts:
        gop_c = next((c for c in ("GOP", "TOTAL_GOP") if c in amounts), None)
        eb_c = next((c for c in ("EBITDA_BEFORE", "EBITDA_BEFORE_CAPITAL") if c in amounts), None)
        if gop_c and eb_c:
            derived = _d(amounts[gop_c]) - _d(amounts[eb_c])
            for ln in out:
                if ln.line_code == "TOTAL_NON_OP":
                    ln.amount_usd = derived
                    ln.is_calculated = True
                    break
    return out
