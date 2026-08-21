"""Motor del reporte `Owners Q` — Python puro, sin base de datos.

Es AGREGACIÓN, no cálculo nuevo (§3.4 del spec). No crea cuentas, no prorratea,
no estima: toma las `Línea P&L` que el P&L ya produjo y las acomoda en las 48
filas que SCP espera.

Nada se codifica por fila acá adentro. Las filas, sus operandos y su naturaleza
vienen de `report_lines`; el ruteo viene de `report_line_mapping`. Si SCP mueve
una fila, se cambia el seed y este archivo no se toca.

DOS COSAS QUE PARECEN ERRORES Y NO LO SON (§4, R4):

  · **RevPar ≠ ADR × Occ%.** El ADR de la fila 11 excluye `REV_ROOMS_OTHER`
    (D1) y el RevPar de la 13 no. La brecha entre los dos es exactamente el
    otro ingreso de habitaciones. Es fiel al archivo que SCP recibe.

  · **Filas que siempre dan 0 y se imprimen igual** (20, 31, 41, 44, 50). SCP
    consolida por POSICIÓN de fila: omitirlas le rompe la consolidación.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from decimal import Decimal

ZERO = Decimal("0")

#: Las 32 columnas de datos, en el orden del Excel. `Q` (la etiqueta) no está
#: acá porque no es un dato: es la fila.
COLUMNAS_PTD = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
                "K", "L", "M", "N", "O", "P"]
COLUMNAS_YTD = ["R", "S", "T", "U", "V", "W", "X", "Y", "Z", "AA",
                "AB", "AC", "AD", "AE", "AF", "AG"]
COLUMNAS = COLUMNAS_PTD + COLUMNAS_YTD

#: Los seis bloques de datos. Cada uno con Valor / %Revenue / POR / PAR.
#: (prefijo, columna_valor, %rev, POR, PAR)
BLOQUES = [
    ("ptd_actual", "A", "B", "C", "D"),
    ("ptd_budget", "E", "F", "G", "H"),
    ("ptd_py",     "K", "L", "M", "N"),
    ("ytd_actual", "R", "S", "T", "U"),
    ("ytd_budget", "V", "W", "X", "Y"),
    ("ytd_py",     "AB", "AC", "AD", "AE"),
]

#: Diferenciales: (columna_diff, columna_%var, bloque_base, bloque_comparado)
DIFERENCIALES = [
    ("I", "J", "ptd_actual", "ptd_budget"),
    ("O", "P", "ptd_actual", "ptd_py"),
    ("Z", "AA", "ytd_actual", "ytd_budget"),
    ("AF", "AG", "ytd_actual", "ytd_py"),
]

#: Filas de estadística: no llevan %Revenue / POR / PAR (la hoja de CWL las deja
#: VACÍAS; la plantilla corporativa pone 0 — se replica el vacío, §5).
FILAS_STAT = {"STAT_ROOMS_AVAILABLE", "STAT_ROOMS_OCCUPIED", "STAT_ADR",
              "STAT_OCC", "STAT_REVPAR", "STAT_TOTAL_REVPAR"}

CONVENCIONES = ("raw", "favorable")


class ReporteError(Exception):
    """Algo que debe FALLAR EL BUILD, no caer en un residual silencioso."""


@dataclass
class DatosPeriodo:
    """Lo que hace falta para armar UN bloque (un dataset, un período).

    `lineas` son las `Línea P&L` ya agregadas por el P&L: {REV_ROOMS: 79310.61,
    OPEX_ROOMS: 65391.44, ...}. Este motor no sabe de cuentas ni departamentos.
    """
    lineas: dict[str, Decimal] = field(default_factory=dict)
    rooms_occupied: Decimal = ZERO
    rooms_available: Decimal = ZERO
    #: Residual sin regla activa, ya separado por naturaleza (§3.3). Va a la
    #: fila 19 si es ingreso y a la 36 si es gasto — nunca se descarta.
    residual_revenue: Decimal = ZERO
    residual_expense: Decimal = ZERO


def _d(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if v is None or v == "":
        return ZERO
    return Decimal(str(v))


#: Los períodos que puede pedir el reporte. La clave es lo que viaja por la API.
#:
#: El bloque «del mes» pasa a ser «del PERÍODO» —un mes, un trimestre o el año—
#: y el acumulado va SIEMPRE de enero al cierre de ese período. Para un mes son
#: las mismas dos cosas de siempre; para Q2 el bloque es abr-jun y el acumulado
#: ene-jun; para el año completo los dos son los doce meses.
MESES_ABREV = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
               "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]
MESES_LARGO = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
               "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]
TRIMESTRES = {"Q1": (1, 3), "Q2": (4, 6), "Q3": (7, 9), "Q4": (10, 12)}


def periodos_disponibles() -> list[dict]:
    """Los 17: doce meses, cuatro trimestres y el año."""
    out = [{"clave": f"M{m:02d}", "etiqueta": MESES_LARGO[m - 1],
            "tipo": "mes", "mes_cierre": m} for m in range(1, 13)]
    out += [{"clave": q, "etiqueta": f"{q} ({MESES_ABREV[a - 1]}-{MESES_ABREV[b - 1]})",
             "tipo": "trimestre", "mes_cierre": b} for q, (a, b) in TRIMESTRES.items()]
    out.append({"clave": "FY", "etiqueta": "Full Year", "tipo": "anio", "mes_cierre": 12})
    return out


def resolver_periodo(clave: str) -> tuple[list[int], list[int], str, bool]:
    """`clave` → (meses del período, meses del acumulado, etiqueta, es_un_mes).

    `es_un_mes` es lo que decide si el reporte sigue siendo el estándar de SCP:
    ellos piden UN mes con su acumulado. Un trimestre o el año son otra cosa, y
    el archivo tiene que decirlo.
    """
    clave = (clave or "").strip().upper()
    if clave.startswith("M") and clave[1:].isdigit():
        m = int(clave[1:])
        if not 1 <= m <= 12:
            raise ReporteError(f"mes fuera de rango: {clave}")
        return [m], list(range(1, m + 1)), MESES_LARGO[m - 1], True
    if clave in TRIMESTRES:
        a, b = TRIMESTRES[clave]
        return (list(range(a, b + 1)), list(range(1, b + 1)),
                f"{clave} ({MESES_ABREV[a - 1]}-{MESES_ABREV[b - 1]})", False)
    if clave == "FY":
        return list(range(1, 13)), list(range(1, 13)), "Full Year", False
    raise ReporteError(f"período desconocido: {clave!r}")


def dias_del_mes(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]


def dias_ytd(anio: int, hasta_mes: int) -> int:
    return sum(dias_del_mes(anio, m) for m in range(1, hasta_mes + 1))


def _div(num: Decimal | None, den: Decimal | None):
    """División con la guarda del §5: denominador 0 → VACÍO.

    Vacío, no 0 y no infinito. Un mes cerrado por temporada u obra tiene
    `rooms_available = 0`; poner 0 ahí diría «el ADR fue cero», que es una
    afirmación falsa sobre un mes en el que no se vendió nada.
    """
    if num is None or den is None or den == 0:
        return None
    return _d(num) / _d(den)


# ─── Valores de las 48 filas para UN dataset ──────────────────────────────────
def valores_de_filas(
    filas: list[dict],
    ruteo: dict[str, str],
    datos: DatosPeriodo,
    dias_periodo: int,
    habitaciones: int,
) -> dict[str, Decimal]:
    """Las 48 filas para un solo bloque, en `raw` (sin convención de signos).

    Orden de resolución: DETAIL → SUBTOTAL/CALC/STAT por dependencia, con
    detección de ciclos. No se evalúa por número de fila: la 13 y la 14
    dependen de la 16 y la 21, que están MÁS ABAJO.
    """
    por_codigo = {f["report_code"]: f for f in filas}
    valores: dict[str, Decimal] = {}

    # ── 1. DETAIL: suma de sus `Línea P&L` ───────────────────────────────────
    for f in filas:
        if f["line_type"] != "DETAIL":
            continue
        total = ZERO
        for lp in f.get("lineas_pl") or []:
            # El ruteo manda: si una línea apunta a otra fila, es un error de
            # seed, no algo que este motor deba adivinar.
            destino = ruteo.get(lp)
            if destino is not None and destino != f["report_code"]:
                raise ReporteError(
                    f"`{lp}` está en la fila {f['report_code']} del catálogo "
                    f"pero el mapeo la manda a {destino}")
            total += _d(datos.lineas.get(lp, ZERO))

        # Las filas `signed` entran con su SIGNO NATURAL (§6). El P&L guarda
        # todo gasto en positivo, así que pasar a signo natural es negar: un
        # gasto financiero real sale negativo y un ingreso financiero neto sale
        # positivo. Es lo que hace que la fila 56 pueda SUMAR la 52.
        #
        # Verificado contra el fixture: en las dos columnas de Budget la
        # diferencia era la negación exacta (−226,01 vs +226,01 en el mes,
        # −1.356,07 vs +1.356,07 en el acumulado).
        if f["nature"] == "signed":
            total = -total

        valores[f["report_code"]] = total

    # Residual sin regla activa — SIEMPRE aterriza, nunca se descarta (§3.3).
    if "REV_MISC_TOTAL" in valores:
        valores["REV_MISC_TOTAL"] += _d(datos.residual_revenue)
    if "UND_MISC" in valores:
        valores["UND_MISC"] += _d(datos.residual_expense)

    # ── 2. HEADER: sin valor ─────────────────────────────────────────────────
    for f in filas:
        if f["line_type"] == "HEADER":
            valores[f["report_code"]] = ZERO

    # ── 3. STAT / SUBTOTAL / CALC: por dependencia, con detección de ciclos ──
    rooms_av = _d(dias_periodo) * _d(habitaciones)

    def stat(codigo: str, resolver):
        if codigo == "STAT_ROOMS_AVAILABLE":
            return rooms_av
        if codigo == "STAT_ROOMS_OCCUPIED":
            return _d(datos.rooms_occupied)
        if codigo == "STAT_ADR":
            # D1: ADR sobre `REV_ROOMS` SOLO, sin `REV_ROOMS_OTHER`. Es lo que
            # hace que RevPar ≠ ADR × Occ%. No se "arregla".
            return _div(_d(datos.lineas.get("REV_ROOMS", ZERO)), _d(datos.rooms_occupied))
        if codigo == "STAT_OCC":
            return _div(_d(datos.rooms_occupied), rooms_av)
        if codigo == "STAT_REVPAR":
            return _div(resolver("REV_ROOMS_TOTAL"), rooms_av)
        if codigo == "STAT_TOTAL_REVPAR":
            return _div(resolver("TOT_OPERATING_REVENUE"), rooms_av)
        raise ReporteError(f"fila STAT desconocida: {codigo}")

    en_curso: set[str] = set()

    def resolver(codigo: str):
        if codigo in valores:
            return valores[codigo]
        if codigo in en_curso:
            raise ReporteError(f"ciclo en los operandos del reporte: {codigo}")
        f = por_codigo.get(codigo)
        if f is None:
            raise ReporteError(f"operando inexistente: {codigo}")
        en_curso.add(codigo)
        try:
            if f["line_type"] == "STAT":
                v = stat(codigo, resolver)
            else:  # SUBTOTAL / CALC
                v = ZERO
                for op in f.get("operandos") or []:
                    parte = resolver(op["code"])
                    if parte is None:
                        continue
                    v += _d(parte) * _d(op["sign"])
        finally:
            en_curso.discard(codigo)
        valores[codigo] = v
        return v

    for f in filas:
        if f["line_type"] in ("STAT", "SUBTOTAL", "CALC"):
            resolver(f["report_code"])

    return valores


# ─── Las 32 columnas ──────────────────────────────────────────────────────────
def _ratios(fila: dict, valor, total_revenue, rooms_occ, rooms_av) -> tuple:
    """%Revenue / POR / PAR de una celda.

    `% Revenue` va SIEMPRE sobre el total operating revenue (fila 21), también
    para los gastos departamentales. No es el % del ingreso de su propio
    departamento — verificado contra el fixture.
    """
    if fila["report_code"] in FILAS_STAT:
        return None, None, None      # la hoja de CWL las deja vacías
    if fila["line_type"] == "HEADER":
        return None, None, None
    return (_div(valor, total_revenue),
            _div(valor, rooms_occ),
            _div(valor, rooms_av))


def _porcentaje_var(diff, base):
    """`diff / ABS(base)`, con las guardas del §5.

    Si la base es 0 el cociente no existe: se reporta el SIGNO del movimiento
    (±1 = «apareció de la nada» / «desapareció del todo»), y 0 si tampoco hubo
    movimiento. Un departamento sin actividad en el año anterior produce ±1 y
    eso tiene que llegar al panel de excepciones, no confundirse con un 100%
    de crecimiento real.
    """
    if diff is None or base is None:
        return None
    if base == 0:
        if diff == 0:
            return ZERO
        return Decimal("1") if diff > 0 else Decimal("-1")
    return _d(diff) / abs(_d(base))


def construir_reporte(
    filas: list[dict],
    ruteo: dict[str, str],
    datasets: dict[str, DatosPeriodo],
    *,
    disponibles: dict[str, int],
    convencion: str = "favorable",
) -> list[dict]:
    """Las 48 filas × 32 columnas.

    `datasets` trae los seis bloques por su nombre (`ptd_actual`, `ytd_budget`…).
    Los seis pasan por LA MISMA función: no hay seis caminos paralelos que se
    puedan desincronizar, solo cambia el dataset de origen.

    El cálculo es siempre `raw`. La convención de signos se aplica DESPUÉS,
    como capa de presentación (§6) — así el fixture valida el motor y la
    convención se prueba aparte.
    """
    if convencion not in CONVENCIONES:
        raise ReporteError(f"convención desconocida: {convencion}")

    # Las habitaciones disponibles llegan ya calculadas —Σ (días × capacidad de
    # ese mes)— y **una por bloque**, porque este motor no sabe de calendarios
    # ni de capacidades.
    #
    # Una por bloque y no una para PTD y otra para YTD: el bloque de año
    # anterior corre sobre SU año, y febrero de un bisiesto tiene un día más.
    # Con 2026 vs 2025 da igual y por eso no se nota; con 2025 vs 2024, no.
    faltan = [n for n in datasets if n not in disponibles]
    if faltan:
        raise ReporteError(f"sin habitaciones disponibles para los bloques: {faltan}")

    # Valores crudos por bloque
    crudos: dict[str, dict[str, Decimal]] = {}
    for nombre, datos in datasets.items():
        crudos[nombre] = valores_de_filas(
            filas, ruteo, datos, _d(disponibles[nombre]), 1)

    salida: list[dict] = []
    for f in sorted(filas, key=lambda x: x["row_no"]):
        code = f["report_code"]
        celdas: dict[str, Decimal | None] = {}

        for nombre, c_val, c_pct, c_por, c_par in BLOQUES:
            datos = datasets.get(nombre)
            vals = crudos.get(nombre, {})
            v = vals.get(code)
            celdas[c_val] = v
            if datos is None:
                celdas[c_pct] = celdas[c_por] = celdas[c_par] = None
                continue
            pct, por, par = _ratios(
                f, v,
                vals.get("TOT_OPERATING_REVENUE"),
                _d(datos.rooms_occupied),
                _d(disponibles[nombre]),
            )
            celdas[c_pct], celdas[c_por], celdas[c_par] = pct, por, par

        for c_diff, c_var, base, comp in DIFERENCIALES:
            a = crudos.get(base, {}).get(code)
            b = crudos.get(comp, {}).get(code)
            if a is None or b is None:
                celdas[c_diff] = celdas[c_var] = None
                continue
            diff = _d(a) - _d(b)
            celdas[c_diff] = diff
            celdas[c_var] = _porcentaje_var(diff, b)

        # Los HEADER no llevan valores en ninguna columna.
        if f["line_type"] == "HEADER":
            celdas = {c: None for c in COLUMNAS}

        salida.append({
            "row_no": f["row_no"],
            "report_code": code,
            "label": f["label"],
            "indent": f["indent"],
            "line_type": f["line_type"],
            "nature": f["nature"],
            "celdas": celdas,
        })

    if convencion == "favorable":
        salida = aplicar_convencion(salida)
    return salida


#: Las ocho columnas de variación que la convención `favorable` invierte.
COLUMNAS_VARIACION = ["I", "J", "O", "P", "Z", "AA", "AF", "AG"]


def aplicar_convencion(filas_calculadas: list[dict]) -> list[dict]:
    """`favorable`: en las filas de GASTO, positivo = favorable.

    Se invierten SOLO las ocho columnas de variación y SOLO donde
    `nature == 'expense'`. Revenue, profit, stat y `signed` no se tocan.

    ⚠️ La fila 52 `INTEREST EXPENSE` es `signed`: entra con su signo natural
    (gasto financiero negativo, ingreso financiero neto positivo) y la 56 la
    SUMA. Nunca se invierte, en ninguna convención.

    Aplicarla dos veces devuelve el original — es una involución, y hay test.
    """
    for fila in filas_calculadas:
        if fila["nature"] != "expense":
            continue
        for c in COLUMNAS_VARIACION:
            v = fila["celdas"].get(c)
            if v is not None:
                fila["celdas"][c] = -_d(v)
    return filas_calculadas


# ─── Identidades del §9.2 — corren contra CUALQUIER período ───────────────────
#: (fila_resultado, [(operando, signo)]) — la aritmética que el reporte debe
#: cumplir consigo mismo, sea cual sea el mes.
IDENTIDADES = [
    ("TOT_OPERATING_REVENUE", [("REV_ROOMS_TOTAL", 1), ("REV_FB_TOTAL", 1),
                               ("REV_OOD_TOTAL", 1), ("REV_MISC_TOTAL", 1),
                               ("REV_FAIR_TRADE", 1)]),
    ("TOT_DEPARTMENTAL_EXPENSES", [("EXP_ROOMS", 1), ("EXP_FB", 1), ("EXP_OOD", 1)]),
    ("TOT_DEPARTMENTAL_PROFIT", [("TOT_OPERATING_REVENUE", 1),
                                 ("TOT_DEPARTMENTAL_EXPENSES", -1)]),
    ("TOT_UNDISTRIBUTED", [("UND_AG", 1), ("UND_CC_COMMISSIONS", 1), ("UND_ESDG", 1),
                           ("UND_IT", 1), ("UND_SALES_MARKETING", 1), ("UND_POM", 1),
                           ("UND_UTILITIES", 1), ("UND_MISC", 1)]),
    ("GOP", [("TOT_DEPARTMENTAL_PROFIT", 1), ("TOT_UNDISTRIBUTED", -1)]),
    ("INCOME_BEFORE_NONOP", [("GOP", 1), ("MANAGEMENT_FEES", -1)]),
    ("TOT_NONOP_EXPENSES", [("NONOP_RENT", 1), ("NONOP_PROPERTY_TAXES", 1),
                            ("NONOP_INSURANCE", 1), ("NONOP_OTHER", 1)]),
    ("EBITDA", [("INCOME_BEFORE_NONOP", 1), ("NONOP_INCOME", 1),
                ("TOT_NONOP_EXPENSES", -1)]),
    ("ADJUSTED_EBITDA", [("EBITDA", 1), ("OWNER_EXPENSES_CAPITAL", -1),
                         ("ASSET_PROJECT_MGMT_FEES", -1)]),
    ("TOT_DA", [("DEPRECIATION", 1)]),
    # f56 = f51 + f52 − f55. La 52 SUMA porque entra con su signo natural.
    ("NET_INCOME_BEFORE_TAXES", [("ADJUSTED_EBITDA", 1), ("INTEREST_EXPENSE", 1),
                                 ("TOT_DA", -1)]),
]

TOLERANCIA = Decimal("0.01")


def verificar_identidades(filas_calculadas: list[dict], columna: str = "A") -> list[dict]:
    """Devuelve las identidades que NO se cumplen. Lista vacía = todo cuadra."""
    v = {f["report_code"]: f["celdas"].get(columna) for f in filas_calculadas}
    fallas = []
    for destino, operandos in IDENTIDADES:
        esperado = ZERO
        incompleto = False
        for code, signo in operandos:
            x = v.get(code)
            if x is None:
                incompleto = True
                break
            esperado += _d(x) * signo
        obtenido = v.get(destino)
        if incompleto or obtenido is None:
            continue
        if abs(_d(obtenido) - esperado) > TOLERANCIA:
            fallas.append({
                "identidad": destino,
                "esperado": str(esperado),
                "obtenido": str(obtenido),
                "delta": str(_d(obtenido) - esperado),
                "columna": columna,
            })
    return fallas


def verificar_d1(filas_calculadas: list[dict], rev_rooms_other: Decimal,
                 columna_valor: str = "A", columna_por: str = "C") -> dict:
    """§9.3 — la brecha entre el ADR y el POR de la fila 16 es `REV_ROOMS_OTHER`.

    Si no coincide hay que DETENERSE y reportar la diferencia, no ajustar el
    ADR para que calce.
    """
    v = {f["report_code"]: f["celdas"] for f in filas_calculadas}
    adr = v.get("STAT_ADR", {}).get(columna_valor)
    occ = v.get("STAT_ROOMS_OCCUPIED", {}).get(columna_valor)
    rooms_rev = v.get("REV_ROOMS_TOTAL", {}).get(columna_valor)
    if adr is None or occ is None or rooms_rev is None:
        return {"ok": None, "motivo": "faltan datos"}
    brecha = _d(rooms_rev) - _d(adr) * _d(occ)
    delta = brecha - _d(rev_rooms_other)
    return {
        "ok": abs(delta) <= TOLERANCIA,
        "brecha": str(brecha),
        "rev_rooms_other": str(_d(rev_rooms_other)),
        "delta": str(delta),
    }
