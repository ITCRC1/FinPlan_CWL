# -*- coding: utf-8 -*-
"""MASTER DATA — el sub-tab 3 del spec `COSTOS_GRUPOS.md` §5.

*«P&L mensual por departamento. Sólo lectura, trazable a FinPlan.»*

Réplica del `FULL YEAR ANALYSIS 2026.xlsx` del owner (hoja `Master Data`), con
sus ocho bloques y sus columnas de temporada. Pedido del owner (2026-08-20):
*«dame ese tab, será MI RESUMEN»* · *«toda la información está en FinPlan»* ·
*«es llamar todo ese detalle»* · *«sólo 2, lado a lado, para ver Budget y Actual
y Forecast»*.

⚠️ **No se carga nada.** Es una vista derivada: cada cifra sale del motor del
escenario. Si un número está mal acá, está mal en el P&L — y ése es el punto.

⚠️ **DOS escenarios lado a lado**, elegibles. No tres: el owner pidió dos.

⚠️ **Las columnas de temporada salen de `cfg_temporadas`, y son las que haya.**
Decisión del owner (2026-08-20): *«sólo mapeá tus datos, y demos esos como
válidos»*. Así que no se imita el corte en dos del Excel ni se agrupa MEDIA
dentro de BAJA para que la comparación cuadre: si FinPlan tiene tres
temporadas, salen tres columnas más el año. La pantalla dice qué meses entran
en cada una, que es lo único que hace falta para leerla.

⚠️ Y **`cfg_temporadas` no se escribe desde acá.** Esa tabla también gobierna
los Pisos y la Golden Rate, que están en uso para negociar: moverla para que
una comparación cuadre movería un número que alguien está usando hoy.

⚠️ **La planilla NO se puede deducir del número de cuenta.** El P&L de FinPlan
mete planilla y opex juntos en la línea departamental, y el corte vive en
`be_cost_classification.be_section` — la misma tabla de Break-Even, como pide el
spec («comparte criterio con Break-E»). Medido: hay cuentas `6xxxx` clasificadas
`OPERATING EXPENSES` y otras `PAYROLL`, así que por dígito la planilla saldría
inflada.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.engine import costos_grupos as cg
from app.hotel_actual import HOTEL_ID
from app.models.break_even import BeCostClassification
from app.models.scenario import Scenario

router = APIRouter(prefix="/costos-grupos", tags=["costos-grupos"])

ZERO = Decimal("0")

# La columna del total. Las de temporada se leen de `cfg_temporadas` en cada
# corrida, así que agregar o quitar una temporada es un UPDATE y no un
# despliegue.
ANIO = "ANIO"

# ⚠️ **La lista de departamentos NO se escribe a mano, y este proyecto ya pagó
# por hacerlo.** El Club Madresal desaparecía del P&L porque el motor tenía una
# lista de cinco departamentos escrita a mano y el Club no estaba: no fallaba,
# no había error en los logs, simplemente su ingreso no existía. Se arregló
# derivando la lista del sistema, y acá se hace igual.
#
# Medido el 2026-08-20 con la lista a mano: el cuadro mostraba **8 de las 15
# líneas `REV_` del P&L**, así que su TOTAL no era el ingreso del hotel. Faltaban
# Área Recreativa, Club, Crowther Lab, Innoceana, Misceláneos, Private Bar y
# **Tienda** — que no es Retail: son dos locales distintos (decisión del owner,
# 11-ago), así que el Gift Shop estaba y la Tienda no.

#: El ORDEN con el que el owner lee su hoja. Lo que no esté acá igual sale,
#: detrás: el orden es una preferencia, la lista es un hecho.
ORDEN_DEL_OWNER = ["REV_ROOMS", "REV_FB", "REV_SPA", "REV_TOURS",
                   "REV_TRANSPORTATION", "REV_RETAIL", "REV_LAUNDRY",
                   "REV_SUSTAINABILITY"]

#: Nombres visibles. Una línea sin nombre acá sale con su código, no se oculta.
NOMBRE_DEPTO = {
    "REV_ROOMS": "Rooms",
    "REV_FB": "F&B",
    "REV_SPA": "Spa",
    "REV_TOURS": "Tours y Actividades",
    "REV_TRANSPORTATION": "Transporte",
    "REV_RETAIL": "Retail - Gift Shop",
    "REV_LAUNDRY": "Laundry",
    "REV_SUSTAINABILITY": "Sustainability Fee",
    "REV_TIENDA": "Tienda",
    "REV_PRIVATE_BAR": "Private Bar",
    "REV_CLUB": "Club Madresal",
    "REV_AREC": "Área Recreativa",
    "REV_INNOCEANA": "Innoceana",
    "REV_CROWTHER_LAB": "Crowther Lab",
    "REV_MISC_OTHER": "Misceláneos y otros",
}


def _departamentos(meses: list, depto_de_linea: dict[str, str]) -> list[tuple]:
    """`(codigo, slug, nombre)` de **todo** lo que tenga línea de ingreso.

    ⚠️ Sale del dato del escenario, no de una lista. Un departamento nuevo
    aparece solo; uno que deje de existir se va solo. El `slug` —que es lo que
    conecta con el costo del GL— también sale del mapeo, no de un diccionario
    paralelo que habría que acordarse de actualizar.
    """
    presentes = {c for m in meses for c in m.revenue_por_dept}
    orden = [c for c in ORDEN_DEL_OWNER if c in presentes]
    orden += sorted(c for c in presentes if c not in ORDEN_DEL_OWNER)
    return [(c, depto_de_linea.get(c, ""), NOMBRE_DEPTO.get(c, c))
            for c in orden]

# Bloque 6 del Excel. Salen de las líneas `OH_*` del P&L.
OVERHEAD = [
    ("OH_ADMIN", "Administración"),
    ("OH_SALES_MARKETING", "Ventas y Mercadeo"),
    ("OH_MAINTENANCE", "Mantenimiento"),
    ("OH_INFORMATION_SYSTEM", "Sistemas de Información"),
    ("OH_UTILITIES", "Servicios Públicos"),
]

# Bloque 7. Cada uno es una línea del P&L, no un cálculo.
NO_OPERATIVO = [
    ("MGMT_FEE_3", "Management fee"),
    ("RENT", "Renta"),
    ("PROPERTY_INSURANCE", "Seguro de propiedad"),
    ("OTHER_EXPENSES", "Otros gastos"),
    ("CAPITAL_RESERVE", "Reserva de capital"),
    ("LARGE_CAPEX", "Capital mayor"),
]

# Las tres secciones de `be_cost_classification` que el Excel separa en bloques.
SECCION_COS = "COST OF SALES"
SECCION_PLANILLA = "PAYROLL"
SECCION_OPEX = "OPERATING EXPENSES"


def _d(v) -> Decimal:
    return Decimal(str(v or 0))


async def _escenario(db: AsyncSession, sid: str) -> Scenario:
    s = (await db.execute(
        select(Scenario).where(Scenario.id == sid,
                               Scenario.hotel_id == HOTEL_ID)
    )).scalars().first()
    if s is None:
        raise HTTPException(404, f"escenario no encontrado: {sid}")
    return s


async def _secciones_por_cuenta(db: AsyncSession) -> dict[tuple[str, str], str]:
    """`(dept_code, account) -> be_section`, de la tabla de Break-Even.

    ⚠️ Es la fuente del corte planilla/opex/costo de venta, y tiene que ser
    ésta: el spec pide explícitamente que **comparta criterio con Break-E**, y
    tener dos clasificaciones distintas del mismo gasto es cómo dos pantallas
    terminan contando cosas distintas del mismo hotel.
    """
    filas = (await db.execute(
        select(BeCostClassification.dept_code, BeCostClassification.account,
               BeCostClassification.be_section)
        .where(BeCostClassification.property_id == HOTEL_ID)
    )).all()
    return {(d or "", a or ""): (s or "") for d, a, s in filas}


async def _bloques_de_costo(db: AsyncSession, sc: Scenario,
                            temporada_de: dict[int, str],
                            columnas: tuple[str, ...]) -> dict:
    """Costo de venta · planilla · opex, por departamento y temporada.

    ⚠️ **Doce pasadas por el GL, y el año es la SUMA de los doce.** La versión
    anterior derivaba la baja restando (`Año − Alta`) para ahorrarse cinco
    pasadas; con las temporadas de verdad no hay nada que derivar, y que el año
    salga de sumar los meses convierte el total en un control en vez de en un
    número aparte que podría no cerrar.
    """
    from app.api import _be_base

    secciones = await _secciones_por_cuenta(db)

    def acumular(base, dentro: dict) -> None:
        for f in base.filas:
            if not f.es_costo or f.reparte:
                continue
            sec = secciones.get((f.dept_code or "", f.account or ""), "")
            if sec not in (SECCION_COS, SECCION_PLANILLA, SECCION_OPEX):
                continue
            slug = f.dept_slug or ""
            if not slug:
                continue
            dentro.setdefault(sec, {})
            dentro[sec][slug] = dentro[sec].get(slug, ZERO) + _d(f.amount)

    por_col: dict[str, dict] = {c: {} for c in columnas}
    # ⚠️ El puente `REV_ROOMS -> 'rooms'` sale del `account_mapping`, no de un
    # diccionario escrito acá: es el mismo que usa Break-Even, así que un
    # departamento nuevo queda conectado sin que nadie se acuerde de agregarlo.
    depto_de_linea: dict[str, str] = {}
    for m in range(1, 13):
        col = temporada_de.get(m, "")
        if col not in por_col:
            continue
        base = await _be_base.construir(db, sc, m)
        depto_de_linea.update(base.depto_de_linea or {})
        acumular(base, por_col[col])
        acumular(base, por_col[ANIO])

    fuera: dict = {}
    for sec in (SECCION_COS, SECCION_PLANILLA, SECCION_OPEX):
        fuera[sec] = {}
        slugs = {s for c in columnas for s in por_col[c].get(sec, {})}
        for slug in slugs:
            fuera[sec][slug] = {
                c: por_col[c].get(sec, {}).get(slug, ZERO) for c in columnas}
    return fuera, depto_de_linea


def _por_temporada(meses: list, temporada_de: dict[int, str],
                   columnas: tuple[str, ...], leer) -> dict[str, Decimal]:
    """Suma `leer(mes)` en cada temporada y en el año.

    ⚠️ Un mes cuya temporada no esté en `cfg_temporadas` **entra igual al año**
    y no a ninguna columna de temporada. Descartarlo lo haría desaparecer del
    total sin que nada avise, y el año dejaría de cuadrar contra el P&L.
    """
    fuera = {c: ZERO for c in columnas}
    for m in meses:
        col = temporada_de.get(m.mes, "")
        v = leer(m)
        if col in fuera:
            fuera[col] += v
        fuera[ANIO] += v
    return fuera


def _fila(label: str, valores: dict[str, Decimal], columnas: tuple[str, ...],
          formato: str = "usd", nota: str = "") -> dict:
    return {"label": label, "formato": formato, "nota": nota,
            "valores": {k: str(valores.get(k, ZERO)) for k in columnas}}


def _total(filas: list[dict], columnas: tuple[str, ...],
           label: str = "TOTAL") -> dict:
    acc = {k: sum((Decimal(f["valores"][k]) for f in filas), ZERO)
           for k in columnas}
    d = _fila(label, acc, columnas)
    d["es_total"] = True
    return d


def _div(num: dict, den: dict, columnas: tuple[str, ...]) -> dict[str, Decimal]:
    """División columna por columna. ⚠️ Denominador cero devuelve CERO, no una
    excepción: en un escenario vacío media pantalla no puede caerse."""
    return {k: (num.get(k, ZERO) / den[k] if den.get(k) else ZERO)
            for k in columnas}


async def _columna(db: AsyncSession, sc: Scenario,
                   temporada_de: dict[int, str],
                   columnas: tuple[str, ...]) -> dict:
    meses = await cg.hechos_mensuales(db, sc, HOTEL_ID)
    costo, depto_de_linea = await _bloques_de_costo(db, sc, temporada_de, columnas)
    departamentos = _departamentos(meses, depto_de_linea)

    def sumar(leer) -> dict[str, Decimal]:
        return _por_temporada(meses, temporada_de, columnas, leer)

    def fila(label, valores, formato="usd", nota=""):
        return _fila(label, valores, columnas, formato, nota)

    # ── 1. Operación ────────────────────────────────────────────────────────
    disp = sumar(lambda m: Decimal(m.hab_disponibles))
    ocup = sumar(lambda m: m.hab_ocupadas)
    noches = sumar(lambda m: m.noches_huesped)
    rev_rooms = sumar(lambda m: m.revenue_por_dept.get("REV_ROOMS", ZERO))

    operacion = [
        fila("Habitaciones disponibles", disp, "num"),
        fila("Habitaciones ocupadas", ocup, "num"),
        fila("Noches-huésped", noches, "num"),
        fila("% Ocupación", _div(ocup, disp, columnas), "pct"),
        fila("Huéspedes por habitación", _div(noches, ocup, columnas), "num2"),
        fila("ADR sólo habitación", _div(rev_rooms, ocup, columnas)),
    ]

    # ── 2. Ingresos ─────────────────────────────────────────────────────────
    ingresos = [
        fila(nombre, sumar(lambda m, c=code: m.revenue_por_dept.get(c, ZERO)))
        for code, _slug, nombre in departamentos
    ]
    ingresos.append(_total(ingresos, columnas))

    # ⚠️ **El control que faltaba.** El total de este bloque tiene que ser el
    # `TOTAL_REVENUES` del P&L. Si difiere, hay líneas de ingreso que el cuadro
    # no está mostrando — que es exactamente lo que pasaba hasta hoy con siete
    # de las quince. Se muestra la diferencia en vez de dejar un total que
    # parece el ingreso del hotel y no lo es.
    total_pl = sumar(lambda m: m.total_revenue_pl)
    sumado = {k: Decimal(ingresos[-1]["valores"][k]) for k in columnas}
    dif = {k: total_pl[k] - sumado[k] for k in columnas}
    if any(abs(v) > Decimal("0.01") for v in dif.values()):
        ingresos.append(fila(
            "⚠ Ingreso del P&L que este cuadro NO muestra", dif, "usd",
            "El total de arriba no llega al TOTAL_REVENUES del P&L: falta una "
            "línea de ingreso en la lista de departamentos."))

    # ── 3, 4 y 5. Costo de venta · planilla · opex ──────────────────────────
    def bloque_costo(seccion: str) -> list[dict]:
        filas = [fila(nombre, costo.get(seccion, {}).get(slug, {}))
                 for _code, slug, nombre in departamentos]
        filas.append(_total(filas, columnas))
        return filas

    # ── 6. Overhead ─────────────────────────────────────────────────────────
    overhead = [
        fila(nombre, sumar(lambda m, c=code: m.overhead_por_componente.get(c, ZERO)))
        for code, nombre in OVERHEAD
    ]
    overhead.append(_total(overhead, columnas, "TOTAL OVERHEAD"))

    # ── 7. No operativos y capital ──────────────────────────────────────────
    #
    # ⚠️ Cada concepto es una LÍNEA del P&L, no un reparto de un total. Antes
    # este bloque mostraba una sola cifra porque el motor descartaba las líneas
    # de abajo del GOP; ahora las guarda (`otras_lineas`) y acá se leen una por
    # una, que es como está en la hoja del owner.
    no_op = [fila(nombre, sumar(lambda m, c=code: m.otras_lineas.get(c, ZERO)))
             for code, nombre in NO_OPERATIVO]

    # ⚠️ Y el total NO es la suma de esas seis: es `TOTAL_NON_OP_EXPENSES` del
    # P&L. Si difieren, hay conceptos abajo del GOP que este bloque no nombra —
    # y eso tiene que VERSE, no taparse sumando lo que sí conozco.
    no_op_total = sumar(lambda m: m.no_operativo)
    suma_nombrados = {k: sum((Decimal(f["valores"][k]) for f in no_op), ZERO)
                      for k in columnas}
    resto = {k: no_op_total[k] - suma_nombrados[k] for k in columnas}
    if any(abs(v) > Decimal("0.01") for v in resto.values()):
        no_op.append(fila(
            "Otros conceptos abajo del GOP", resto, "usd",
            "El P&L trae más líneas no operativas que las seis nombradas. Se "
            "muestran acá en vez de sumarlas a una de las otras."))
    t = _total(no_op, columnas, "TOTAL NO OPERATIVO Y CAPITAL")
    no_op.append(t)

    # ── 8. Ratios de absorción ──────────────────────────────────────────────
    # ⚠️ El ingreso de los ratios es el del P&L, no la suma del cuadro: si el
    # cuadro se dejó una línea afuera, dividir por su suma inflaría todos los
    # porcentajes sin que nada avise.
    rev_total = total_pl
    oh_total = {k: Decimal(overhead[-1]["valores"][k]) for k in columnas}
    ratios = [
        fila("Ingreso total", rev_total),
        fila("Overhead % del ingreso", _div(oh_total, rev_total, columnas), "pct"),
        fila("No operativos % del ingreso",
             _div(no_op_total, rev_total, columnas), "pct"),
        fila("ABSORCIÓN TOTAL",
             _div({k: oh_total[k] + no_op_total[k] for k in columnas},
                  rev_total, columnas), "pct"),
    ]

    return {
        "escenario": {"id": sc.id, "tipo": sc.type, "anio": sc.year,
                      "version": sc.version,
                      "etiqueta": f"{sc.type} {sc.year} {sc.version}"},
        "bloques": [
            {"clave": "operacion", "titulo": "1. Operación", "filas": operacion},
            {"clave": "ingresos", "titulo": "2. Ingresos por departamento",
             "filas": ingresos},
            {"clave": "costo_venta", "titulo": "3. Costo de venta por departamento",
             "filas": bloque_costo(SECCION_COS)},
            {"clave": "planilla", "titulo": "4. Planilla por departamento",
             "filas": bloque_costo(SECCION_PLANILLA)},
            {"clave": "opex", "titulo": "5. OPEX por departamento",
             "filas": bloque_costo(SECCION_OPEX)},
            {"clave": "overhead", "titulo": "6. Gastos no distribuidos (overhead)",
             "filas": overhead},
            {"clave": "no_operativo",
             "titulo": "7. Gastos no operativos y capital", "filas": no_op},
            {"clave": "ratios", "titulo": "8. Ratios de absorción (calculados)",
             "filas": ratios},
        ],
    }


@router.get("/master-data/")
async def master_data(
    a: str = Query(..., description="escenario de la columna izquierda"),
    b: str | None = Query(None, description="escenario de la columna derecha"),
    db=Depends(get_db), _=Depends(get_current_user),
):
    """Los ocho bloques del `Master Data`, para uno o dos escenarios.

    ⚠️ Vista **derivada**: no acepta entradas y no guarda nada.
    """
    temporadas = await cg.cargar_temporadas(db, HOTEL_ID)
    temporada_de = {m: t.temporada for m, t in temporadas.items() if t.temporada}

    # ⚠️ Las columnas son **las temporadas que existan**, en el orden en que
    # aparece el año. Una lista escrita a mano dejaría afuera la temporada que
    # alguien agregue, y el año seguiría cuadrando: el gasto estaría en el
    # total y en ninguna columna.
    vistas: list[str] = []
    for m in range(1, 13):
        t = temporada_de.get(m)
        if t and t not in vistas:
            vistas.append(t)
    columnas_clave = tuple(vistas) + (ANIO,)

    cols = [await _columna(db, await _escenario(db, a), temporada_de, columnas_clave)]
    if b and b != a:
        cols.append(await _columna(db, await _escenario(db, b), temporada_de,
                                   columnas_clave))

    # Qué meses entran en cada columna. Es lo único que hace falta para leer la
    # pantalla, y evita tener que abrir `cfg_temporadas` para saberlo.
    meses_de = {c: [m for m in range(1, 13) if temporada_de.get(m) == c]
                for c in vistas}
    meses_de[ANIO] = list(range(1, 13))

    # ⚠️ Un mes sin temporada entra al año y a ninguna columna. No es un error
    # —el año sigue cuadrando contra el P&L— pero tiene que verse, porque su
    # gasto no aparece en ninguna de las columnas de temporada.
    huerfanos = [m for m in range(1, 13) if m not in temporada_de]

    return {
        "columnas": cols,
        "columnas_clave": list(columnas_clave),
        "meses_por_columna": meses_de,
        "meses_sin_temporada": huerfanos,
    }
