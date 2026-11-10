# -*- coding: utf-8 -*-
"""Cuentas del mayor por mes — el reporte de conciliación.

Owner, 2026-11-05: *«que lo pongas en el tab Reports al final para poder
conciliar los resultados… que traiga todas las cuentas… y que exista un
proceso de validación interno para que pegue con los reportes»*.

## De dónde salen las filas

| `source_mode` | fuente | ¿están las cinco clases? |
|---|---|---|
| `imported` | `actual_entries` | sí: 4, 5, 6, 7 y 8 |
| `checkbook` | los checkbooks + `nonop_entries` | **no**: falta el ingreso |

En un escenario de checkbook el ingreso se calcula de tarifas y ocupación y
vive por LÍNEA del P&L, no por cuenta — no hay 4xxx que mostrar. La respuesta
lo dice en `meta.completo` y la pantalla lo pone arriba, porque una grilla a
la que le falta el ingreso y no avisa es peor que no tenerla.

## El mapeo se resuelve COMO LO RESUELVE EL P&L: con el vigente HOY

Mi primer intento fue armar un resolvedor por mes, con el mapeo vigente en
cada uno. Es más correcto en teoría —la 7120 dejó `OH_ADMIN` en jul-2026 y las
dos reglas conviven en la tabla— pero **no reproduce lo que muestra el P&L**:
`compute_pl_month` toma `periodo=None` por defecto, y ése es el camino que usa
toda la app. Sólo el reporte a SCP pide un período.

Conciliar contra el P&L significa calcular como él calcula. Con el resolvedor
por mes la comparación acusaba a `OH_ADMIN` de 41.140,50 de diferencia en un
P&L que estaba bien.

Las cuentas cuyo mapeo cambió durante el año **sí se marcan**, porque es un
dato que el usuario tiene que tener: el P&L les aplica el renglón de hoy a los
doce meses.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.engine import gl_por_mes as gl
from app.engine import pl_engine
from app.engine import recalculate as recalc
from app.errores import ErrorApi
from app.models.actual_entry import ActualEntry
from app.models.belowgop_account_entry import BelowGopAccountEntry
from app.models.cost_entry import CostEntry
from app.models.department_catalog import DepartmentCatalog
from app.models.mapping import AccountMapping
from app.models.nonop_entry import NonOpEntry
from app.models.opex_entry import OpexEntry
from app.models.revenue_account_entry import RevenueAccountEntry
from app.models.scenario import Scenario

router = APIRouter()

ZERO = Decimal("0")

#: Los únicos renglones que SON la suma de unas cuentas, y por lo tanto los
#: únicos comparables contra el mayor.
#:
#: ⚠️ No alcanza con sacar las CALCULATED del catálogo: el motor emite además
#: renglones que **no están en la configuración** (`GOP`, `EBITDA_BEFORE`,
#: `EBITDA_AFTER`). Comparándolos salen con el mayor en cero y una diferencia
#: igual a todo el renglón — ruido que tapa las diferencias de verdad.
TIPOS_COMPARABLES = ("MAPPED", "MAPPED_REVIEW")

#: Las secciones que el checkbook NO sube por cuenta -- el P&L las siembra por
#: línea. Son las que hay que anclar para que la grilla las muestre.
SECCIONES_SEMBRADAS = {
    "REVENUES", "OWNER / NON-OP EXPENSES", "CAPITAL",
    "FINANCIAL EXPENSES", "DEPRECIATION", "TAX / NET PROFIT",
}


async def _escenario(scenario_id: str, db: AsyncSession) -> Scenario:
    esc = (await db.execute(
        select(Scenario).where(Scenario.id == scenario_id)
    )).scalar_one_or_none()
    if esc is None:
        raise ErrorApi(404, "escenario.no_encontrado")
    return esc


async def _nombres_de_departamento(db: AsyncSession):
    filas = (await db.execute(select(DepartmentCatalog))).scalars().all()
    nombres = {d.dept_code: d.dept_name for d in filas}
    return lambda c: nombres.get(c, "")


async def _resolvedores(db: AsyncSession, year: int):
    """El resolvedor que usa el P&L, y dos más sólo para detectar cambios.

    `hoy` es el que manda: es `periodo=None`, el mismo camino que
    `compute_pl_month`. `enero` y `diciembre` no tocan ningún número — sirven
    para marcar las cuentas cuyo mapeo cambió durante el año, que el P&L
    resuelve igual con la regla de hoy pero el usuario merece ver.
    """
    hoy = pl_engine.construir_resolvedor(
        await recalc.load_active_account_mappings(db))
    extremos = []
    for periodo in (f"{year}-01", f"{year}-12"):
        extremos.append(pl_engine.construir_resolvedor(
            await recalc.load_active_account_mappings(db, periodo=periodo)))
    return hoy, extremos


async def _nombres_de_cuenta_checkbook(db: AsyncSession, scenario_id: str) -> dict[str, str]:
    """cuenta → descripción, sacada de los checkbooks del escenario.

    Las tres tablas guardan `account_name`; `checkbook_account_rows_for_month`
    no lo devuelve. Gana el primero que aparezca: la misma cuenta lleva el
    mismo nombre en las tres.
    """
    fuera: dict[str, str] = {}
    for modelo in (OpexEntry, CostEntry, NonOpEntry):
        filas = (await db.execute(
            select(modelo).where(modelo.scenario_id == scenario_id)
        )).scalars().all()
        for f in filas:
            cod = (getattr(f, "account_code", "") or "").strip()
            nom = (getattr(f, "account_name", "") or "").strip()
            if cod and nom:
                fuera.setdefault(cod, nom)
    return fuera


async def _por_cuenta(db: AsyncSession, modelo, scenario_id: str) -> list[dict]:
    """Las filas de una tabla `{scenario, dept, cuenta, 12 meses}` del escenario.

    `revenue_account_entries` (4xxx) y `belowgop_account_entries` (8xxx) tienen
    la misma forma que `ActualEntry`, así que entran a la grilla sin traducir.
    """
    filas = (await db.execute(
        select(modelo).where(modelo.scenario_id == scenario_id)
    )).scalars().all()
    return [{
        "dept_code": f.dept_code, "account_code": f.account_code,
        "account_name": f.account_name, "outlet": "",
        **{m: getattr(f, m) for m in gl.MESES},
    } for f in filas]


async def _filas_del_mayor(db: AsyncSession, esc: Scenario) -> tuple[list[dict], str, bool]:
    """Las filas por cuenta × departamento, y de dónde salieron.

    Devuelve `(filas, fuente, completo)`. `completo` es False cuando la fuente
    no puede traer el ingreso por cuenta — el caso de los checkbooks.
    """
    if (esc.source_mode or "") == "imported":
        filas = (await db.execute(
            select(ActualEntry).where(ActualEntry.scenario_id == esc.id)
        )).scalars().all()
        return ([{
            "dept_code": f.dept_code, "account_code": f.account_code,
            "account_name": f.account_name, "outlet": f.outlet,
            **{m: getattr(f, m) for m in gl.MESES},
        } for f in filas], "actual_entries", True)

    # Checkbook: se pivota mes a mes la MISMA función que alimenta al P&L, así
    # lo que se ve acá es lo que el P&L consume y no una segunda lectura.
    #
    # Los nombres de cuenta NO vienen en esas filas —son {cuenta, depto,
    # monto}—, así que se traen de los checkbooks. Sin esto la grilla sale con
    # la columna de descripción vacía y hay que adivinar qué es cada número.
    nombres = await _nombres_de_cuenta_checkbook(db, esc.id)
    acumulado: dict[tuple[str, str], dict] = {}
    con_movimiento_real: set[tuple[str, str]] = set()
    for mes in range(1, 13):
        for r in await recalc.checkbook_account_rows_for_month(db, esc.id, mes):
            cuenta = str(r.get("account_code") or "").strip()
            dept = str(r.get("dept_code") or "").strip()
            if not cuenta:
                continue
            fila = acumulado.setdefault(
                (dept, cuenta),
                {"dept_code": dept, "account_code": cuenta,
                 "account_name": nombres.get(cuenta, ""),
                 "outlet": "", **{m: ZERO for m in gl.MESES}})
            fila[gl.MESES[mes - 1]] += Decimal(str(r.get("amount") or 0))
            con_movimiento_real.add((dept, cuenta))

    # ⚠️ El ingreso (4xxx) y el below-GOP (8xxx) NO salen de los checkbooks:
    # `checkbook_account_rows_for_month` no los sube, porque el P&L los siembra
    # por LÍNEA -- el ingreso se calcula de tarifas y noches, y varias líneas
    # de below-GOP comparten una misma cuenta del mayor. Por eso la grilla
    # mostraba el escenario sin ingreso y el total no daba la utilidad.
    #
    # La apertura por cuenta SÍ existe cuando alguien la cargó, en
    # `revenue_account_entries` y `belowgop_account_entries`. Se suma acá.
    # Si están vacías la grilla queda como estaba y el encabezado lo dice con
    # un número, no con un "incompleto" a secas.
    #
    # Las claves ya presentes NO se pisan: los repartos entran por
    # `AllocationEntry` con su cuenta 4999 y no pueden contarse dos veces.
    detalle_real = False
    for modelo in (RevenueAccountEntry, BelowGopAccountEntry):
        filas_modelo = await _por_cuenta(db, modelo, esc.id)
        if filas_modelo:
            detalle_real = True
        for f in filas_modelo:
            clave = (f["dept_code"], f["account_code"])
            if clave not in acumulado:
                acumulado[clave] = f

    # ── La liga contable del checkbook ───────────────────────────────────
    #
    # Owner, 2026-11-10: *«asigna cuenta y asigna departamento, realiza la liga
    # contable al checkbook»* -- después de señalar, con razón, que el ingreso
    # SÍ está en los checkbooks del Budget 2027.
    #
    # Está, pero por LÍNEA del P&L: la tabla es `(scenario, line)`, sin cuenta
    # ni departamento. Abrir la línea en sus cuentas es imposible sin inventar
    # el reparto -- sólo 3 de las 19 líneas de ingreso tienen una única cuenta.
    # Lo que sí se puede es darle a cada línea su asiento: ver
    # `gl.ancla_contable`.
    #
    # El monto se toma del P&L, no de una segunda lectura del checkbook, para
    # que la grilla cuadre contra el P&L **por construcción** y no por
    # coincidencia. Entran las secciones que el checkbook no sube por cuenta:
    # ingreso y todo lo que vive debajo del GOP.
    #
    # ⚠️ Si alguien cargó el detalle por cuenta de verdad
    # (`revenue_account_entries`), ÉSE manda y el ancla no se usa: sumar los
    # dos contaría el ingreso dos veces.
    if not detalle_real:
        ancla = gl.ancla_contable(await recalc.load_active_account_mappings(db))
        secciones = {l["line_code"]: (l.get("section") or "")
                     for l in await recalc.load_report_line_config(db)}
        for mes in range(1, 13):
            for linea in await recalc.compute_pl_month(db, esc, mes):
                sec = (secciones.get(linea.line_code) or "").strip().upper()
                if sec not in SECCIONES_SEMBRADAS:
                    continue
                destino = ancla.get(linea.line_code)
                if destino is None:
                    continue
                dept, cuenta, nombre = destino
                if (dept, cuenta) in con_movimiento_real:
                    continue
                fila = acumulado.setdefault(
                    (dept, cuenta),
                    {"dept_code": dept, "account_code": cuenta,
                     "account_name": nombre or nombres.get(cuenta, ""),
                     "outlet": "", "por_linea": True,
                     **{m: ZERO for m in gl.MESES}})
                fila[gl.MESES[mes - 1]] += Decimal(str(linea.amount_usd or 0))
    return (list(acumulado.values()), "checkbook", False)


def _fila(fila: dict, resolver, extremos, secciones, nombre_dept) -> dict:
    """Una fila del reporte, resuelta como la resuelve el P&L."""
    cuenta, dept = fila["account_code"], fila["dept_code"]
    regla, como = resolver(dept, cuenta)
    lc = str(regla.get("report_line_code") or "") if regla else ""
    sec = secciones.get(lc, "") if lc else ""
    credito = gl.es_credito(cuenta, sec)
    meses = [gl.con_signo_de_reporte(fila.get(mk), credito=credito)
             for mk in gl.MESES]

    # ¿El mapeo de esta cuenta cambió durante el año? No mueve ni un número
    # —el P&L usa el de hoy para los doce meses— pero explica por qué el mayor
    # de enero puede verse en un renglón distinto al del contador.
    vistos = set()
    for r in extremos:
        m2, _ = r(dept, cuenta)
        vistos.add(str(m2.get("report_line_code") or "") if m2 else "")
    clase = gl.clase_de(cuenta)

    return {
        "dept_code": dept,
        "dept_name": nombre_dept(dept) or dept,
        "account_code": cuenta,
        "account_name": str(fila.get("account_name") or "").strip(),
        "outlet": str(fila.get("outlet") or "").strip(),
        "clase": clase,
        "pl_line_code": lc,
        "pl_line_name": "",          # lo completa el llamador con el catálogo
        "pl_section": sec,
        "mapeo": como,
        "mapeo_cambio": len(vistos) > 1,
        "codigo_corporativo": "",
        "categoria": gl.categoria_de(cuenta, sec),
        # True = el monto viene de la LÍNEA del P&L, puesto en su cuenta de
        # asiento. El checkbook no lo tiene abierto por cuenta y abrirlo sería
        # inventar el reparto -- ver `gl.ancla_contable`.
        "por_linea": bool(fila.get("por_linea")),
        "clase_discrepa": gl.discrepa_clase(cuenta, credito=credito, seccion_pl=sec),
        "meses": meses,
        "total": sum(meses, ZERO),
    }


async def _catalogo_de_cuentas(db: AsyncSession) -> list[dict]:
    """TODAS las cuentas del mapeo, en cero. El catálogo, no los movimientos.

    Owner, 2026-11-10, señalando Admin · Account Mapping: *«¿por qué no jalas
    este master data a esta vista? ya tiene todo»*. Tenía razón: la grilla sólo
    mostraba las cuentas CON movimiento, así que una cuenta que existe y quedó
    sin presupuestar era indistinguible de una que no existe. Para armar un
    budget eso es justo lo que hay que ver.

    Son las mismas reglas ACTIVAS y VIGENTES que usa el P&L —se filtra igual
    que `load_active_account_mappings`— para que la cuenta que aparezca acá sea
    la que el motor va a resolver, y no una regla apagada o de otro año.

    ⚠️ Las filas salen en CERO, así que no mueven ningún total y no tocan la
    conciliación. Lo único que agregan es la pregunta «¿y esta cuenta?».
    """
    filas = (await db.execute(
        select(AccountMapping).where(
            AccountMapping.report_id == "P&L_DETAIL_OWNERS",
            AccountMapping.active_status == "YES")
    )).scalars().all()
    fuera = []
    for m in filas:
        if not recalc._vigente_en(m, None):
            continue
        fuera.append({
            "dept_code": m.dept_code or "",
            "account_code": (m.account_code or "").strip(),
            "account_name": (m.account_name_example or "").strip(),
            "outlet": "",
            **{mes: ZERO for mes in gl.MESES},
        })
    return fuera


async def _grilla(db: AsyncSession, esc: Scenario, *, catalogo: bool = False):
    filas, fuente, completo = await _filas_del_mayor(db, esc)
    con_movimiento = {(f["dept_code"], f["account_code"]) for f in filas}
    del_catalogo = await _catalogo_de_cuentas(db)
    faltan = [f for f in del_catalogo
              if (f["dept_code"], f["account_code"]) not in con_movimiento]
    if catalogo:
        filas = filas + faltan
    lineas_cfg = await recalc.load_report_line_config(db)
    secciones = {l["line_code"]: (l.get("section") or "") for l in lineas_cfg}
    nombres_linea = {l["line_code"]: (l.get("line_name") or "") for l in lineas_cfg}
    comparables = {l["line_code"] for l in lineas_cfg
                   if l.get("line_type") in TIPOS_COMPARABLES}
    resolver, extremos = await _resolvedores(db, esc.year)
    nombre_dept = await _nombres_de_departamento(db)

    grilla = [_fila(f, resolver, extremos, secciones, nombre_dept) for f in filas]
    for r in grilla:
        r["pl_line_name"] = nombres_linea.get(r["pl_line_code"], "")
    # La fila sin movimiento se marca: es del catálogo, no del escenario.
    vacias = {(f["dept_code"], f["account_code"]) for f in faltan}
    for r in grilla:
        r["sin_movimiento"] = (r["dept_code"], r["account_code"]) in vacias
    grilla.sort(key=lambda r: (r["categoria"] == "STATISTICS", r["account_code"],
                               r["dept_code"], r["outlet"]))
    return grilla, fuente, completo, comparables, secciones, len(del_catalogo), len(faltan)


def _n(v) -> float:
    return float(v or 0)


def _fila_json(r: dict) -> dict:
    return {**{k: v for k, v in r.items() if k not in ("meses", "total")},
            "meses": [_n(x) for x in r["meses"]],
            "total": _n(r["total"])}


@router.get("/gl/{scenario_id}/")
async def listar_gl(scenario_id: str, catalogo: bool = False,
                    db: AsyncSession = Depends(get_db)):
    """La grilla completa: una fila por cuenta × departamento, doce meses.

    `catalogo=1` agrega además, EN CERO, las cuentas del mapeo que el escenario
    no usó: para armar un presupuesto hay que ver la que falta, no sólo la que
    está.
    """
    esc = await _escenario(scenario_id, db)
    grilla, fuente, completo, _cmp, _sec, n_cat, n_vacias = await _grilla(
        db, esc, catalogo=catalogo)
    resumen = gl.resumen_por_categoria(grilla)

    # ⚠️ Cuánto ingreso trae la grilla contra el que dice el P&L.
    #
    # Antes esto era un sí/no: `completo=False` en todo escenario de checkbook,
    # dijera lo que dijera la grilla. Con la apertura por cuenta cargada el
    # aviso quedaba mintiendo al revés -- decía "falta el ingreso" teniéndolo
    # entero. Y sin ella, "incompleto" no dice CUÁNTO falta, que es lo único
    # que permite decidir si el reporte sirve para conciliar.
    #
    # La grilla lleva el ingreso en negativo (ver `gl_por_mes`); el P&L, no.
    # Se comparan en la misma vara.
    ingreso_grilla = -sum((r["total"] for r in grilla
                           if r["categoria"] == "REVENUE"), ZERO)
    ingreso_pl = ZERO
    for mes in range(1, 13):
        for linea in await recalc.compute_pl_month(db, esc, mes):
            if linea.line_code == "TOTAL_REVENUES":
                ingreso_pl += Decimal(str(linea.amount_usd or 0))
    falta_ingreso = ingreso_pl - ingreso_grilla
    completo = completo or abs(falta_ingreso) <= Decimal("0.01")
    return {
        "meta": {
            "scenario_id": esc.id,
            "hotel_id": esc.hotel_id,
            "year": esc.year,
            "type": esc.type,
            "version": esc.version,
            "source_mode": esc.source_mode,
            "revenue_source": esc.revenue_source,
            "actuals_through": esc.actuals_through or 0,
            "fuente": fuente,
            "completo": completo,
            # Para que el aviso diga un número y no un adjetivo.
            "ingreso_grilla": _n(ingreso_grilla),
            "ingreso_pl": _n(ingreso_pl),
            "falta_ingreso": _n(falta_ingreso),
            "cuentas": len({r["account_code"] for r in grilla}),
            # Cuántas cuentas existen en el mapeo y cuántas el escenario no
            # tocó. Se informan SIEMPRE, aunque no se pidan: el hueco tiene que
            # verse sin tener que ir a buscarlo.
            "cuentas_catalogo": n_cat,
            "cuentas_sin_movimiento": n_vacias,
            "catalogo": catalogo,
            "filas": len(grilla),
            # La convención viaja como CLAVE por el mismo motivo que `motivo`:
            # la pantalla la dice en el idioma en que se está mirando. Sin
            # decirla, un número entre paréntesis se interpreta al revés y el
            # reporte miente sin fallar.
            "signo": "revenue_credit",
        },
        "rows": [_fila_json(r) for r in grilla],
        "resumen": [{"categoria": f["categoria"], "suma": f["suma"],
                     "meses": [_n(x) for x in f["meses"]], "total": _n(f["total"])}
                    for f in resumen],
    }


@router.get("/gl/{scenario_id}/validacion/")
async def validar_gl(scenario_id: str, db: AsyncSession = Depends(get_db)):
    """El proceso de validación interno: ¿el mayor pega con el P&L?

    ⚠️ **La igualdad Σ = −utilidad no aplica a todo escenario.** Un FORECAST
    con `actuals_through > 0` MEZCLA: los meses cerrados toman las cifras del
    ACTUAL enlazado y los abiertos salen de las tarifas de este escenario. Sus
    propias filas de mayor no son la película completa, y pintar una alarma
    roja ahí sería enseñar a ignorar la alarma. Se dice, y se corren igual las
    tres pruebas que sí valen siempre.
    """
    esc = await _escenario(scenario_id, db)
    grilla, fuente, completo, comparables, secciones, _nc, _nv = await _grilla(db, esc)

    # ⚠️ Un escenario VACÍO no «cuadra»: no hay nada que cuadrar. Σ=0 contra
    # −utilidad=0 da cero y el validador se pintaba de verde para los Working
    # 2028-2035, que no tienen una sola fila. Una tranquilidad falsa es peor
    # que una alarma: la alarma se mira.
    vacio = not grilla
    mezcla = esc.type == "FORECAST" and (esc.actuals_through or 0) > 0
    aplica = completo and not mezcla and not vacio

    rev = None if esc.type == "ACTUAL" else await recalc.load_revenue_results(db, esc)
    por_linea: dict[str, Decimal] = {}
    for mes in range(1, 13):
        for ln in await recalc.compute_pl_month(db, esc, mes, rev):
            por_linea[ln.line_code] = por_linea.get(ln.line_code, ZERO) + ln.amount_usd

    res = gl.conciliar(
        grilla,
        utilidad_pl=por_linea.get("NET_PROFIT", ZERO),
        por_linea_pl=por_linea,
        comparables=comparables,
        secciones=secciones,
    )

    # ⚠️ El motivo viaja como CLAVE y no como prosa: la pantalla tiene dos
    # idiomas, y una frase en español dentro de la vista en inglés es un
    # defecto que se ve. La traducción vive en `messages/{es,en}.json`.
    motivo = ""
    if vacio:
        motivo = "vacio"
    elif not completo:
        motivo = "checkbook"
    elif mezcla:
        motivo = "mezcla"

    return {
        "aplica_igualdad": aplica,
        "motivo": motivo,
        "motivo_mes": esc.actuals_through or 0,
        "cuadra": bool(res["cuadra"]) if aplica else None,
        "total_reporte": _n(res["total_reporte"]),
        "utilidad_pl": _n(res["utilidad_pl"]),
        "esperado": _n(res["esperado"]),
        "diferencia": _n(res["diferencia"]),
        "tolerancia": _n(res["tolerancia"]),
        "sin_mapeo": [{**r, "total": _n(r["total"])} for r in res["sin_mapeo"]],
        "sin_mapeo_total": _n(res["sin_mapeo_total"]),
        "por_descarte": [{**r, "total": _n(r["total"])} for r in res["por_descarte"]],
        "por_descarte_total": _n(res["por_descarte_total"]),
        "clase_discrepa": [{**r, "total": _n(r["total"])} for r in res["clase_discrepa"]],
        "clase_discrepa_total": _n(res["clase_discrepa_total"]),
        "mapeo_cambio": [
            {"dept_code": r["dept_code"], "account_code": r["account_code"],
             "account_name": r["account_name"], "total": _n(r["total"])}
            for r in grilla if r.get("mapeo_cambio")
        ],
        "por_linea": [
            {"pl_line_code": l["pl_line_code"], "gl": _n(l["gl"]),
             "pl": _n(l["pl"]), "diferencia": _n(l["diferencia"])}
            for l in res["por_linea"]
            if abs(l["diferencia"]) > Decimal("0.01")
        ],
        "fuente": fuente,
    }
