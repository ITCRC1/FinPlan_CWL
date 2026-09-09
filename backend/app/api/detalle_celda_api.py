# -*- coding: utf-8 -*-
"""De qué está hecha UNA celda del cuadro, sin salir de la pantalla.

Owner, 2026-09-03: *«¿será posible que se pueda hacer link? Toco la línea de
Rooms Revenue y me abre el detalle, sin ir, solamente se despliega lo más
detallado que haya. Seguro tenga más sentido para payroll y gastos, donde los GL
son más. Si abro payroll de Rooms se me despliegan los GL que suman eso, como un
cuadro sin salir a la otra ventana… así voy presentando y puedo ver los detalles
de una vez»*.

## Lo que contesta

Dado un renglón del cuadro —una clase (`payroll`, `opex`, `cost`, `property`,
`revenue`) y su clave (el departamento, la cuenta o la línea)— devuelve **las
cuentas que suman ese número**, para CADA versión pedida, con los doce meses.

Así el mismo desplegable sirve para comparar: la misma cuenta, el actual al lado
del presupuesto y del forecast.

## El presupuesto TAMBIÉN se abre por cuenta

Owner, 2026-09-03: *«el presupuesto debe tener GL, siempre debe estar conectado
a un GL»*. Y lo está: cada línea del checkbook lleva su `account_code` —opex,
costo y below-GOP— y los 17 conceptos de planilla **son** cuentas del mayor
(`c6000_sw` es la 6000). Así que el desplegable abre por cuenta en las tres
versiones, y se comparan cuenta contra cuenta, que es todo el punto.

Lo que cambia es de qué TABLA sale, y eso se declara en `fuente`:

* un **ACTUAL** lo trae de `actual_entries` — el mayor cargado;
* un **BUDGET** o un **FORECAST** lo trae de sus auxiliares, que es donde vive
  su detalle. No es «menos detalle»: es el mismo nivel, en otra tabla.

⚠️ **La única excepción es el ingreso agregado**, y no se inventa. Una línea del
checkbook como `ROOMS` o `FOOD` agrega VARIAS cuentas del mayor, así que
`REVENUE_LINE_ACCOUNT` sólo declara cuenta donde la línea ES una cuenta (las
tres del Club). Ponerle una a `ROOMS` sería elegir una de las que agrupa. Donde
no se puede bajar a cuenta, se muestra la línea y se dice por qué.

## Por qué no se reusó Consulta GL

`consulta_api` contesta la pregunta contraria —«dame todo el GL filtrado, en
formato largo, para pivotear en Excel»— y sólo mira el mayor. Acá la pregunta es
«de qué está hecha ESTA celda», que empieza por la clase y la clave del cuadro y
tiene que funcionar sobre un presupuesto.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.db import get_session
from app.engine import pl_engine
from app.engine import recalculate as recalc
from app.errores import ErrorApi
from app.models.actual_entry import ActualEntry
from app.models.allocation_entry import AllocationEntry
from app.models.cost_entry import CostEntry
from app.models.department_catalog import DepartmentCatalog
from app.models.mapping import AccountMapping
from app.models.nonop_entry import NonOpEntry
from app.models.opex_entry import OpexEntry
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.revenue_account_entry import RevenueAccountEntry
from app.models.scenario import Scenario
from app.nombres_cuenta import limpiar_nombre, nombre_de_cuenta

router = APIRouter(tags=["detalle-celda"])

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]

#: Para decirle al usuario hasta qué mes manda el actual. «Actual hasta 7» no
#: se lee; «Actual hasta julio», sí.
MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
            "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

CERO = Decimal("0")

#: La clase del cuadro → el primer dígito de la cuenta en el mayor.
CLASE_A_DIGITO = {"cost": "5", "payroll": "6", "opex": "7", "property": "8"}

#: Las cuentas del crédito de distribución y la fusión del ingreso de
#: lavandería. ⚠️ Se IMPORTAN de `gasto_por_clase`, que es quien arma la
#: celda: dos copias de estas dos tablas es cómo el desplegable termina
#: sumando algo distinto de lo que dice el número que se tocó.
from app.api.gasto_por_clase_api import (   # noqa: E402
    CUENTAS_DE_REPARTO, FUSION_INGRESO)


def _f(x) -> float:
    return float(x or 0)


def _padre(dept: str) -> str:
    """El departamento del P&L al que pertenece un sub-departamento.

    ⚠️ Sube en CADENA: `consolidate_dept` resuelve un escalón y hay cadenas de
    dos —el 0132 cuelga del 0130 y el 0130 del 0140—. Es la misma función que
    usa `gasto_por_clase` para armar la celda; si acá subiera un escalón menos,
    el desplegable mostraría cuentas que no son las que suman ese número.
    """
    visto: set[str] = set()
    for _ in range(5):
        padre = pl_engine.consolidate_dept(dept)
        if padre == dept or padre in visto:
            return dept
        visto.add(dept)
        dept = padre
    return dept


async def _del_mayor(session, escenario, clase: str, clave: str) -> dict:
    """Las cuentas del mayor que caen en esa celda. Devuelve {cuenta: [12]}."""
    filas = (await session.execute(select(ActualEntry).where(
        ActualEntry.scenario_id == escenario.id))).scalars().all()
    # ⚠️ La llave es (DEPARTAMENTO, cuenta) y no la cuenta sola.
    #
    # Owner, 2026-09-03: *«los checkbooks deben estar por departamentos, si no
    # no se puede saber a qué corresponde; puede ser todos, pero internamente
    # separados»*.
    #
    # Sumando por cuenta a secas, la 7065 de Habitaciones y la 7065 del Club
    # caían en la misma fila y el resultado no era de nadie. Con la llave
    # compuesta cada una conserva su departamento, y la pantalla decide si
    # agrupa o no.
    out: dict[tuple[str, str], list[Decimal]] = {}
    nombres: dict[str, str] = {}
    digito = CLASE_A_DIGITO.get(clase)

    for e in filas:
        cuenta = str(e.account_code or "")
        dept = str(e.dept_code or "")
        if clase == "revenue":
            if cuenta in CUENTAS_DE_REPARTO:
                continue   # el crédito de distribución no es venta
            linea, tipo = pl_engine.linea_de_fila(cuenta, dept)
            if tipo != pl_engine.TIPO_INGRESO:
                continue
            # ⚠️ La celda se indexa por LÍNEA del P&L **y, si no hay línea, por
            # departamento** — es literal lo que hace `gasto_por_clase`:
            #
            #     clave_rev = ln_rev or FUSION_INGRESO.get(dept, dept)
            #
            # Sin la segunda mitad, el ingreso del Área Recreativa (270) —que
            # no resuelve a ninguna línea— abría un cuadro VACÍO sobre una
            # celda con $350,41. Medido.
            propia = linea or FUSION_INGRESO.get(dept, dept)
            if clave and propia != clave:
                continue
        elif clase == "property":
            # La clase 8 se abre por CUENTA, no por departamento: vive todo en
            # el mismo (0250).
            if not cuenta.startswith("8") or (clave and cuenta != clave):
                continue
        else:
            # ⚠️ El crédito de distribución (49xx) cuenta como OPEX, con signo
            # negativo. Es lo mismo que hace `gasto_por_clase` desde que dejó
            # de descartar los departamentos de reparto —el sobrante de
            # lavandería son ~1.100 al mes— y sin esto el desplegable no suma
            # la celda de ningún departamento que reciba reparto.
            es_reparto = cuenta in CUENTAS_DE_REPARTO
            if es_reparto:
                if clase != "opex":
                    continue
            elif not digito or cuenta[:1] != digito:
                continue
            # `clave` vacía = la clase entera. Es lo que se abre al tocar el
            # renglón del concepto («Payroll») en vez de una de sus
            # sub-filas por departamento.
            if clave and _padre(dept) != clave:
                continue
        serie = out.setdefault((dept, cuenta), [CERO] * 12)
        for i, col in enumerate(MESES):
            serie[i] += Decimal(str(getattr(e, col, None) or 0))
        if cuenta not in nombres:
            nombres[cuenta] = (e.account_name or "").strip()
    return {"series": out, "nombres": nombres}


async def _del_auxiliar(session, escenario, clase: str, clave: str) -> dict:
    """Lo mismo, para una versión SIN mayor: sale de los checkbooks."""
    out: dict[tuple[str, str], list[Decimal]] = {}
    nombres: dict[str, str] = {}

    def sumar(cuenta: str, fila, nombre: str = "", dept: str = "") -> None:
        serie = out.setdefault((dept, cuenta), [CERO] * 12)
        for i, col in enumerate(MESES):
            serie[i] += Decimal(str(getattr(fila, col, None) or 0))
        if nombre and cuenta not in nombres:
            nombres[cuenta] = nombre

    if clase == "opex":
        for r in (await session.execute(select(OpexEntry).where(
                OpexEntry.scenario_id == escenario.id))).scalars():
            if not clave or _padre(str(r.dept_code or "")) == clave:
                sumar(str(r.account_code or ""), r,
                      str(getattr(r, "account_name", "") or ""),
                      _padre(str(r.dept_code or "")))

        # ⚠️ **Y los asientos de REPARTO**, que son parte del opex del
        # departamento que los recibe.
        #
        # `gasto_por_clase` los suma con `alloc_by_dept`; sin ellos acá, el
        # desplegable quedaba corto en TODO departamento que consume
        # lavandería o cafetería. Medido en el BUDGET 2026: Rooms 7.023,06 de
        # menos, el Club 1.768,31, y la propia lavandería (0161) mostraba un
        # cuadro vacío sobre una celda de −9.838,52 —el crédito que reparte—.
        #
        # ⚠️ Van por MES y no por columnas: `AllocationEntry` tiene una fila
        # por mes, no doce columnas como los checkbooks.
        for a in (await session.execute(select(AllocationEntry).where(
                AllocationEntry.scenario_id == escenario.id))).scalars():
            destino = _padre(str(a.target_dept or ""))
            if clave and destino != clave:
                continue
            m = int(a.month or 0)
            if not 1 <= m <= 12:
                continue
            cuenta = str(getattr(a, "account", "") or pl_engine.ALLOCATION_ACCOUNT)
            # ⚠️ La llave lleva el departamento DESTINO, igual que las demás:
            # el reparto que llega a Habitaciones no es el mismo que el que
            # llega al Club, y con la llave sin departamento los dos caían en
            # una sola fila.
            out.setdefault((destino, cuenta), [CERO] * 12)[m - 1] += (
                a.amount_usd or CERO)
            nombres.setdefault(cuenta, "Distribución de gastos")
    elif clase == "cost":
        for r in (await session.execute(select(CostEntry).where(
                CostEntry.scenario_id == escenario.id))).scalars():
            if not clave or _padre(str(r.dept_code or "")) == clave:
                sumar(str(r.account_code or ""), r,
                      str(getattr(r, "account_name", "") or ""),
                      _padre(str(r.dept_code or "")))
    elif clase == "payroll":
        # ⚠️ La planilla no guarda una cuenta por fila: guarda los 17 CONCEPTOS
        # como columnas (`c6000_sw`, `c6020_ccss`…). Cada concepto ES una
        # cuenta del mayor, y así se abre igual que el actual — que es todo el
        # punto de este desplegable: comparar lo mismo con lo mismo.
        from app.api.consulta_api import CONCEPTOS
        acumulado: dict[tuple[str, str], list[Decimal]] = {}
        for r in (await session.execute(select(PayrollConceptEntry).where(
                PayrollConceptEntry.scenario_id == escenario.id))).scalars():
            if clave and _padre(str(r.dept_code or "")) != clave:
                continue
            mes = int(getattr(r, "month", 0) or 0)
            if not 1 <= mes <= 12:
                continue
            for campo, cuenta, rotulo in CONCEPTOS:
                v = Decimal(str(getattr(r, campo, None) or 0))
                if v == CERO:
                    continue
                acumulado.setdefault((_padre(str(r.dept_code or "")), cuenta),
                                     [CERO] * 12)[mes - 1] += v
                nombres.setdefault(cuenta, rotulo)
        out.update(acumulado)
    elif clase == "property":
        for r in (await session.execute(select(NonOpEntry).where(
                NonOpEntry.scenario_id == escenario.id))).scalars():
            if not clave or str(r.account_code or "") == clave:
                # El below-GOP es de la propiedad entera: no tiene
                # departamento y su llave lleva el 0250, que es donde viven sus
                # reglas de mapeo.
                sumar(str(r.account_code or ""), r,
                      str(getattr(r, "description", "") or ""), "0250")
    elif clase == "revenue":
        # 1) Si hay ingreso cargado POR CUENTA, ése es el detalle: es el mismo
        #    nivel que el mayor del actual.
        for r in (await session.execute(select(RevenueAccountEntry).where(
                RevenueAccountEntry.scenario_id == escenario.id))).scalars():
            linea, tipo = pl_engine.linea_de_fila(str(r.account_code or ""),
                                                  str(r.dept_code or ""))
            if tipo == pl_engine.TIPO_INGRESO and (not clave or linea == clave):
                sumar(str(r.account_code or ""), r,
                      str(getattr(r, "account_name", "") or ""),
                      str(r.dept_code or ""))
        if out:
            return {"series": out, "nombres": nombres}

        # 2) Si no, el checkbook de ingreso, que va por LÍNEA. Las líneas que
        #    SON una cuenta se muestran con su cuenta; las que agregan varias
        #    se muestran con su nombre y el aviso.
        from app.models.revenue_entry import (
            REVENUE_LINE_ACCOUNT, REVENUE_LINE_LABELS, RevenueEntry)
        agregadas = False
        for r in (await session.execute(select(RevenueEntry).where(
                RevenueEntry.scenario_id == escenario.id))).scalars():
            par = REVENUE_LINE_ACCOUNT.get(r.line)
            dept, cuenta = par if par else ("", "")
            linea, tipo = (pl_engine.linea_de_fila(cuenta, dept) if cuenta
                           else (None, None))
            if cuenta and (tipo != pl_engine.TIPO_INGRESO
                           or (clave and linea != clave)):
                continue
            if not cuenta:
                # ⚠️ Sin cuenta declarada no se puede saber si esta línea cae en
                # la celda que se abrió. Se compara por la línea del P&L a la
                # que va, que es lo que el motor usa.
                # `REVENUE_LINE_TO_REPORT_LINE` es la MISMA tabla con la que
                # el motor lleva el checkbook de ingreso al P&L. Rehacer el
                # mapeo acá daría un desplegable que no suma la celda.
                if clave and pl_engine.REVENUE_LINE_TO_REPORT_LINE.get(
                        str(r.line or "").lower()) != clave:
                    continue
                agregadas = True
            # El ingreso del checkbook va por LÍNEA y no tiene departamento;
            # las tres que sí lo declaran (el Club) lo traen del par.
            sumar(cuenta or r.line, r,
                  REVENUE_LINE_LABELS.get(r.line, r.line), dept)
        return {"series": out, "nombres": nombres, "agregado": agregadas}
    return {"series": out, "nombres": nombres}


@router.get("/gasto-por-clase/detalle-de-celda/")
async def detalle_de_celda(
    scenarios: str = Query(..., description="ids separados por coma"),
    clase: str = Query(..., description="revenue | cost | payroll | opex | property"),
    clave: str = Query("", description="departamento, cuenta o línea; vacío = toda la clase"),
):
    """Las cuentas que suman una celda del cuadro, por versión."""
    ids = [s for s in (scenarios or "").split(",") if s.strip()]
    if not ids:
        raise ErrorApi(422, "escenario.falta")
    if clase not in ("revenue", "cost", "payroll", "opex", "property"):
        raise ErrorApi(422, "clase.desconocida")

    async with get_session() as session:
        catalogo = {
            (m.dept_code or "", m.account_code): m.account_name_example
            for m in (await session.execute(select(AccountMapping).where(
                AccountMapping.active_status == "YES"))).scalars()
        }
        deptos = {d.dept_code: d.dept_name for d in
                  (await session.execute(select(DepartmentCatalog))).scalars()}

        versiones = []
        series: dict[str, dict[str, list[Decimal]]] = {}
        nombres: dict[str, str] = {}

        for sid in ids:
            escenario = await session.get(Scenario, sid)
            if escenario is None:
                continue
            # La MISMA pregunta que hace `gasto_por_clase` para elegir de dónde
            # lee la celda: si el mayor manda, el detalle es el mayor.
            manda_el_mayor = (escenario.type == "ACTUAL"
                              or await recalc.lo_subido_manda(session, escenario))
            r = (await _del_mayor(session, escenario, clase, clave)
                 if manda_el_mayor
                 else await _del_auxiliar(session, escenario, clase, clave))

            # ── La mezcla del forecast vivo ─────────────────────────────────
            #
            # Owner, 2026-09-03: *«hay que revisar el checkbook Forecast 2026,
            # porque ése está compuesto por actuales y por forecast; cómo se
            # está manejando esto en esta vista»*.
            #
            # ⚠️ No se estaba manejando. Este endpoint leía el checkbook del
            # forecast para los DOCE meses, y el P&L usa el ACTUAL hasta el
            # corte. Medido en el FORECAST Working 2026 (corte julio), opex de
            # Habitaciones:
            #
            #     desplegable  0  0  0     0     0  11.892  17.714 | 17.546 …
            #     el cuadro    0  0  0    25  1.513   2.185   8.329 | 17.546 …
            #
            # De agosto en adelante coinciden al centavo; hasta julio no. Eran
            # 38 celdas del forecast que no sumaban su propia línea del P&L.
            #
            # La mezcla es la de `compute_pl_month`: hasta `actuals_through`
            # manda el ACTUAL enlazado, y de ahí en adelante el propio
            # escenario. Rehacerla con otro criterio es como el desplegable y
            # el reporte terminan contando dos historias.
            corte = 0
            if escenario.type == "FORECAST" and (escenario.actuals_through or 0) > 0:
                enlazado = await recalc.linked_actual_scenario(session, escenario)
                if enlazado is not None:
                    corte = int(escenario.actuals_through or 0)
                    del_actual = await _del_mayor(session, enlazado, clase, clave)
                    mezcla: dict[tuple[str, str], list[Decimal]] = {}
                    llaves = set(r["series"]) | set(del_actual["series"])
                    for k in llaves:
                        propia = r["series"].get(k, [CERO] * 12)
                        real = del_actual["series"].get(k, [CERO] * 12)
                        # Cada mes de UNA sola fuente: sumarlas contaría dos
                        # veces lo mismo en los meses cerrados.
                        mezcla[k] = [real[i] if i < corte else propia[i]
                                     for i in range(12)]
                    r = {"series": mezcla,
                         "nombres": {**del_actual["nombres"], **r["nombres"]},
                         "agregado": r.get("agregado")}

            series[sid] = r["series"]
            for cuenta, nombre in r["nombres"].items():
                if nombre and cuenta not in nombres:
                    nombres[cuenta] = nombre
            versiones.append({
                "scenario_id": sid,
                "escenario": f"{escenario.type} {escenario.version} {escenario.year}",
                "fuente": ("Mayor (GL)" if manda_el_mayor
                           else f"Actual hasta {MESES_ES[corte - 1]} · auxiliar de ahí en adelante"
                           if corte else "Auxiliar (checkbook)"),
                #: Hasta qué mes los números son ACTUALES. 0 = ninguno.
                "actuals_through": corte,
                # ⚠️ Una línea de ingreso que agrega varias cuentas del mayor se
                # muestra como línea, no como cuenta: elegir una de las que
                # agrupa sería inventar.
                "agregado": bool(r.get("agregado")),
            })

        # Una fila por (departamento, cuenta). ⚠️ Ordenadas por departamento
        # primero: la pantalla las agrupa así, y devolverlas mezcladas la
        # obligaría a reordenarlas —una segunda decisión sobre lo mismo—.
        llaves = sorted({k for s in series.values() for k in s})
        filas = []
        for dept, cuenta in llaves:
            filas.append({
                "dept_code": dept,
                "dept_name": deptos.get(dept, dept),
                "cuenta": cuenta,
                "nombre": nombre_de_cuenta(cuenta, nombres.get(cuenta),
                                           catalogo, dept or clave),
                "series": {sid: [_f(v) for v in
                                 series[sid].get((dept, cuenta), [CERO] * 12)]
                           for sid in series},
            })

        rotulo = clave or "Todos los departamentos"
        if clase not in ("revenue", "property") and clave in deptos:
            rotulo = f"{clave} · {deptos[clave]}"
        elif clase == "property":
            rotulo = f"{clave} · {limpiar_nombre(catalogo.get(('', clave))) or ''}".strip(" ·")

        return {
            "clase": clase,
            "clave": clave,
            "rotulo": rotulo,
            "versiones": versiones,
            "filas": filas,
        }
