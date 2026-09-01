# -*- coding: utf-8 -*-
"""La hoja de revisión del mes — idéntica al tab que el owner revisa a ojo.

## Qué es

En el libro de cierre (`Conc JUL 2026.xlsx`) hay un tab por mes —`Julio 2026`—
que **no es un intermedio**: es la superficie donde la revisión final se hace
mirando, y donde se validan los hallazgos. Pedido explícito del owner
(2026-08-31): *«el tab de Julio debe quedar exactamente como se ve»*.

Así que este módulo no propone un layout mejor. Reproduce ése: las mismas filas
en los mismos números de fila, las mismas columnas —con las columnas en blanco
que separan los bloques— y las mismas etiquetas, **erratas incluidas**
(«Total Operationg expenses», «Miscellaneos», «Actual 23026»). Cambiar una
etiqueta es cambiar lo que el ojo busca.

## El layout, medido sobre el archivo

    D = etiqueta   E = Forecast   F = Budget   H = Actual
    J = Var. vs Forecast          K = Var. vs Budget

`A B C G I` van vacías a propósito: son las que separan los bloques.

La variación es **Actual − comparativo**, verificado contra la fila 17:
`105.358,4 − 133.920,0 = −28.561,6`.

## De dónde salen los números

Las tres columnas comparten las mismas claves (`rev.ROOMS`, `opex.FB`,
`bg.RENT`…). La columna **Actual** la arma `valores_desde_precierre()` con las
filas ya traducidas del Integrity; las de **Forecast** y **Budget** las pasa
quien llame, leyéndolas de los escenarios de FinPlan.

Los totales **se calculan acá** y no se reciben: así la hoja cierra consigo
misma. Si el detalle y el total vinieran de dos lados, podrían discrepar — que
es el problema que este proyecto viene persiguiendo.
"""
from __future__ import annotations

from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

ZERO = Decimal("0")

#: Las columnas, tal como están en el tab del owner.
COL_ETIQUETA, COL_FORECAST, COL_BUDGET = 4, 5, 6      # D E F
COL_ACTUAL, COL_VAR_FCST, COL_VAR_BUD = 8, 10, 11     # H J K

#: Las diez divisiones del reporte, en su orden, y los grupos de FinPlan que
#: alimentan cada una. Verificado contra julio 2026: las diez reproducen la
#: columna Actual al centavo y suman 248.437,33.
#:
#: ⚠️ «F&B» incluye PRIVATE_BAR y «Retail-Gift Shop» incluye las DOS tiendas.
#: FinPlan los distingue —el Private Bar es centro de utilidad propio— pero esta
#: hoja los junta, que es como el owner la lee hoy. Abrirlos es decisión suya.
DIVISIONES: list[tuple[str, list[str]]] = [
    ("Rooms", ["ROOMS"]),
    ("F&B", ["FB", "PRIVATE_BAR"]),
    ("SPA", ["SPA"]),
    ("Tours", ["TOURS"]),
    ("Retail-Gift Shop", ["RETAIL", "TIENDA"]),
    ("Transportation", ["TRANSPORT"]),
    ("Laundry", ["LAUNDRY"]),
    ("Innoceana", ["INNOCEANA"]),
    ("Crowther Lab", ["CROWTHER"]),
    # `None` = los departamentos que el catálogo abre POR CUENTA (280
    # Misceláneos): no tienen grupo, y ponerles uno los rotularía mal.
    ("Miscellaneous", [None, "MISC_OTHER", "SUSTAINABILITY"]),
]

#: Overhead, en el orden del tab. «Claro Huerta» es el otro overhead del catálogo.
OVERHEADS: list[tuple[str, str]] = [
    ("Administrations", "ADMIN"),
    ("Sales & Marketing", "SALES"),
    ("Maintenance", "MAINTENANCE"),
    ("Information System", "IT"),
    ("Utilities", "UTILITIES"),
    ("Claro Huerta", "OTHER_OVERHEAD"),
    ("Cafeteria", "CAFETERIA"),
    ("Laundry", "LAUNDRY_OPS"),
]

#: Las líneas de abajo del GOP y la cuenta de la que sale cada una. Verificado
#: contra las seis cuentas clase 8 de julio 2026.
BAJO_GOP: dict[str, int | None] = {
    "RENT": 8000,
    "MANAGEMENT FEES (3%)": 8005,
    "MANAGEMENT FEES (5%) Royalties": None,
    "PROPERTIES INSURANCE": None,
    "OTHER EXPENSES": 8025,
    "CAPITAL RESERVE": 8020,
    "LARGE CAPITAL EXPENDITURE": None,
    "DEPRECIATION": 8040,
    "Income Tax (30%)": 8060,
    "BAC INTERESES PRESTAMO": None,
    "B.C.R. INTERESES PRESTAMO": None,
    "LEASING CAMION": None,
    "PERDIDAS FINANCIERAS": None,
}

#: Las filas de estadísticas del encabezado.
STATS = [(3, "Total available Rooms", "rooms_disponibles"),
         (4, "Total Rooms Occupied", "rooms_ocupadas"),
         (6, "Total Guests", "huespedes"),
         (7, "% Occupancy", "ocupacion"),
         (8, "Average Daily Room Only", "adr")]


def _d(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v or 0))


# ─── Los valores de la columna Actual ─────────────────────────────────────────

def valores_desde_precierre(filas: list[dict]) -> dict[str, Decimal]:
    """Las claves de la hoja, calculadas desde las filas ya traducidas.

    `filas` es lo que devuelve `integrity_final.leer()`: cada una con su
    `categoria`, su `grupo` de FinPlan y su `mes_usd`.
    """
    v: dict[str, Decimal] = {}

    def sumar(clave, cond):
        v[clave] = sum((f["mes_usd"] for f in filas if cond(f)), ZERO)

    for etiqueta, grupos in DIVISIONES:
        g = set(grupos)
        sumar(f"rev.{etiqueta}",
              lambda f, g=g: f["categoria"] == "Ingresos" and f["grupo"] in g)
        sumar(f"opex.{etiqueta}",
              lambda f, g=g: f["categoria"] not in ("Ingresos", "No Operativo")
              and f["grupo"] in g)
    for etiqueta, grupo in OVERHEADS:
        sumar(f"oh.{etiqueta}",
              lambda f, grupo=grupo: f["categoria"] != "No Operativo"
              and f["grupo"] == grupo)
    for etiqueta, cuenta in BAJO_GOP.items():
        v[f"bg.{etiqueta}"] = (
            sum((f["mes_usd"] for f in filas if f["cuenta_base"] == cuenta), ZERO)
            if cuenta is not None else ZERO)
    return v


def valores_completos(filas: list[dict]) -> dict[str, Decimal]:
    """Las claves de la hoja **con la cascada ya resuelta** — divisiones y
    totales. Es lo que consume cualquiera que quiera los números sin dibujar el
    Excel: `valores_desde_precierre` sola devuelve el detalle y deja los totales
    sin calcular, que fue exactamente el error de la primera corrida."""
    return _totales(valores_desde_precierre(filas))


def _totales(v: dict[str, Decimal]) -> dict[str, Decimal]:
    """Los totales de la cascada. Se calculan, nunca se reciben: así el cuadro
    cierra consigo mismo."""
    t = dict(v)
    t["cero"] = ZERO          # la fila 99, que está en cero en el tab
    t["TOTAL INCOMES"] = sum((_d(v.get(f"rev.{e}")) for e, _ in DIVISIONES), ZERO)
    t["Total Operationg expenses"] = sum(
        (_d(v.get(f"opex.{e}")) for e, _ in DIVISIONES), ZERO)
    for e, _ in DIVISIONES:
        t[f"profit.{e}"] = _d(v.get(f"rev.{e}")) - _d(v.get(f"opex.{e}"))
    t["OPERATING PROFIT"] = sum((t[f"profit.{e}"] for e, _ in DIVISIONES), ZERO)
    t["TOTAL OVERHEAD EXPENSES"] = sum(
        (_d(v.get(f"oh.{e}")) for e, _ in OVERHEADS), ZERO)
    t["TOTAL GROSS OPERATING PROFIT"] = (t["OPERATING PROFIT"]
                                         - t["TOTAL OVERHEAD EXPENSES"])
    bg = lambda k: _d(v.get(f"bg.{k}"))  # noqa: E731
    t["TOTAL RENTA AND MANAGEMENT FEE"] = (bg("RENT") + bg("MANAGEMENT FEES (3%)")
                                           + bg("MANAGEMENT FEES (5%) Royalties"))
    t["PROPERTY INSURANCE"] = bg("PROPERTIES INSURANCE")
    t["TOTAL OTHER EXPENSES"] = bg("OTHER EXPENSES")
    t["CAPITAL EXPENSE"] = bg("CAPITAL RESERVE") + bg("LARGE CAPITAL EXPENDITURE")
    t["TOTAL Owners Expenses"] = (t["TOTAL RENTA AND MANAGEMENT FEE"]
                                  + t["PROPERTY INSURANCE"]
                                  + t["TOTAL OTHER EXPENSES"])
    t["EBITDA"] = t["TOTAL GROSS OPERATING PROFIT"] - t["TOTAL Owners Expenses"]
    t["FINANCIAL EXPENSES"] = (bg("BAC INTERESES PRESTAMO")
                               + bg("B.C.R. INTERESES PRESTAMO")
                               + bg("LEASING CAMION") + bg("PERDIDAS FINANCIERAS"))
    t["TOTAL DEPRECIATIONS"] = bg("DEPRECIATION")
    t["EARNINGS BEFORE INCOME TAXES"] = (t["EBITDA"] - t["FINANCIAL EXPENSES"]
                                         - t["TOTAL DEPRECIATIONS"]
                                         - t["CAPITAL EXPENSE"])
    t["EARNINGS AFTER INCOME TAXES"] = (t["EARNINGS BEFORE INCOME TAXES"]
                                        - bg("Income Tax (30%)"))
    return t


# ─── La hoja ──────────────────────────────────────────────────────────────────

#: `(fila, etiqueta, clave)`. La clave `None` es un rótulo de sección: sólo
#: texto. Los números de fila son los del tab del owner y **no se corren**.
def _plan() -> list[tuple[int, str, str | None]]:
    p: list[tuple[int, str, str | None]] = []
    p.append((16, "REVENUE", None))
    for i, (e, _) in enumerate(DIVISIONES):
        p.append((17 + i, e, f"rev.{e}"))
    p.append((28, "TOTAL INCOMES", "TOTAL INCOMES"))
    p.append((30, "Operating Expenses", None))
    for i, (e, _) in enumerate(DIVISIONES):
        p.append((32 + i, e, f"opex.{e}"))
    p.append((44, "Total Operationg expenses", "Total Operationg expenses"))
    p.append((47, "Operating Profit", None))
    for i, (e, _) in enumerate(DIVISIONES):
        # El tab escribe «Miscellaneos» en este bloque y «Miscellaneous» arriba.
        etiqueta = "Miscellaneos" if e == "Miscellaneous" else e
        p.append((49 + i, etiqueta, f"profit.{e}"))
    p.append((62, "OPERATING PROFIT", "OPERATING PROFIT"))
    p.append((65, "OVERHEAD EXPENSES", None))
    for i, (e, _) in enumerate(OVERHEADS):
        p.append((68 + i, e, f"oh.{e}"))
    p.append((77, "TOTAL OVERHEAD EXPENSES", "TOTAL OVERHEAD EXPENSES"))
    p.append((79, "TOTAL GROSS OPERATING PROFIT", "TOTAL GROSS OPERATING PROFIT"))
    for fila, e in [(81, "RENT"), (82, "MANAGEMENT FEES (3%)"),
                    (83, "MANAGEMENT FEES (5%) Royalties")]:
        p.append((fila, e, f"bg.{e}"))
    p.append((85, "TOTAL RENTA AND MANAGEMENT FEES", "TOTAL RENTA AND MANAGEMENT FEE"))
    p.append((87, "PROPERTIES INSURANCE", "bg.PROPERTIES INSURANCE"))
    p.append((89, "PROPERTY INSURANCE", "PROPERTY INSURANCE"))
    p.append((91, "OTHER EXPENSES", "bg.OTHER EXPENSES"))
    p.append((93, "TOTAL OTHER EXPENSES", "TOTAL OTHER EXPENSES"))
    # ⚠️ El tab tiene DOS filas «CAPITAL EXPENSE»: ésta y la 121. Ésta está en
    # cero en las tres columnas y NO entra en «TOTAL Owners Expenses» (verificado:
    # 8.716,39 + 7.389,56 + 0 + 2.558,75 = 18.664,70, que es lo que dice la 103).
    # La que lleva la reserva de capital es la 121. Se conserva porque el layout
    # tiene que quedar igual, pero no comparte su valor.
    p.append((99, "CAPITAL EXPENSE", "cero"))
    p.append((103, "TOTAL Owners Expenses", "TOTAL Owners Expenses"))
    p.append((105, "EBITDA", "EBITDA"))
    for i, e in enumerate(["BAC INTERESES PRESTAMO", "B.C.R. INTERESES PRESTAMO",
                           "LEASING CAMION", "PERDIDAS FINANCIERAS"]):
        p.append((107 + i, e, f"bg.{e}"))
    p.append((112, "FINANCIAL EXPENSES", "FINANCIAL EXPENSES"))
    p.append((114, "DEPRECIATION", "bg.DEPRECIATION"))
    p.append((116, "TOTAL DEPRECIATIONS", "TOTAL DEPRECIATIONS"))
    p.append((118, "CAPITAL RESERVE", "bg.CAPITAL RESERVE"))
    p.append((119, "LARGE CAPITAL EXPENDITURE", "bg.LARGE CAPITAL EXPENDITURE"))
    p.append((121, "CAPITAL EXPENSE", "CAPITAL EXPENSE"))
    p.append((123, "EARNINGS BEFORE INCOME TAXES", "EARNINGS BEFORE INCOME TAXES"))
    p.append((125, "Income Tax (30%)", "bg.Income Tax (30%)"))
    p.append((128, "EARNINGS AFTER INCOME TAXES", "EARNINGS AFTER INCOME TAXES"))
    return p


PLAN = _plan()

_TITULO = Font(bold=True)
_NUM = "#,##0.00"


def construir(mes_nombre: str, anio: int, stats: dict,
              actual: dict, forecast: dict | None = None,
              budget: dict | None = None) -> Workbook:
    """La hoja, con el layout del tab del owner.

    `actual`/`forecast`/`budget` comparten claves (ver `valores_desde_precierre`).
    Lo que no venga se escribe en cero, como en el tab.
    """
    a, f, b = _totales(actual), _totales(forecast or {}), _totales(budget or {})
    wb = Workbook()
    ws = wb.active
    ws.title = f"{mes_nombre} {anio}"

    for fila, etiqueta, clave in STATS:
        ws.cell(fila, COL_ETIQUETA, etiqueta)
        for col, fuente in ((COL_FORECAST, forecast), (COL_BUDGET, budget),
                            (COL_ACTUAL, actual)):
            val = (fuente or {}).get(f"stat.{clave}") if fuente else None
            if val is None and fuente is actual:
                val = stats.get(clave)
            if val is not None:
                ws.cell(fila, col, float(_d(val)))

    ws.cell(14, COL_FORECAST, mes_nombre).font = _TITULO
    for col, texto in ((COL_ETIQUETA, "Grupo / Cuenta"),
                       (COL_FORECAST, f"Forecast {anio}"),
                       (COL_BUDGET, f"Budget {anio}"),
                       (COL_ACTUAL, f"Actual {anio}"),
                       (COL_VAR_FCST, "Var. vs Forecast"),
                       (COL_VAR_BUD, "Var. vs Budget")):
        c = ws.cell(15, col, texto)
        c.font = _TITULO
        c.alignment = Alignment(horizontal="center")

    for fila, etiqueta, clave in PLAN:
        c = ws.cell(fila, COL_ETIQUETA, etiqueta)
        if clave is None or etiqueta.isupper():
            c.font = _TITULO
        if clave is None:
            continue
        va, vf, vb = _d(a.get(clave)), _d(f.get(clave)), _d(b.get(clave))
        for col, val in ((COL_FORECAST, vf), (COL_BUDGET, vb), (COL_ACTUAL, va),
                         (COL_VAR_FCST, va - vf), (COL_VAR_BUD, va - vb)):
            celda = ws.cell(fila, col, float(val))
            celda.number_format = _NUM

    ws.column_dimensions[get_column_letter(COL_ETIQUETA)].width = 34
    for col in (COL_FORECAST, COL_BUDGET, COL_ACTUAL, COL_VAR_FCST, COL_VAR_BUD):
        ws.column_dimensions[get_column_letter(col)].width = 15
    ws.freeze_panes = "E16"
    return wb
