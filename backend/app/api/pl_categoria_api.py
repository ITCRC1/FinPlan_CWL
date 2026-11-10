# -*- coding: utf-8 -*-
"""El P&L por CATEGORÍA — el segundo formato del mismo P&L.

Owner, 2026-11-09: *«necesito que el P&L tenga 2 versiones de formato: 1) tal
como está en este momento, y 2) Ingreso − Costo − Planilla − Opex igual a GOP.
En este formato no es formato USALI, solo necesito poder ir viendo los totales
por departamento de cada categoría, GOP menos todo lo demás hasta llegar a Net
Profit»*.

## Qué cambia respecto del formato 1

El de siempre es USALI: agrupa por DEPARTAMENTO y dentro de cada uno mezcla
planilla, costo y opex en un solo renglón de «Operating Expenses». Sirve para
comparar contra el libro del owner y contra cualquier hotel del mundo, y por eso
no se toca.

Éste agrupa al revés: por NATURALEZA del gasto, y dentro de cada naturaleza abre
los departamentos. Responde otra pregunta —«¿cuánta planilla tiene Cocina?»—
que en el formato USALI hay que ir a buscar a otra pantalla.

## La identidad, y por qué es la única razón por la que esto se puede construir

    Ingreso − Costo − Planilla − OPEX − Reparto  =  GOP

Medido contra el Budget Working 2027, los doce meses, ámbito consolidado y
hotel: **diferencia $0.0000 en todos**. No es una aproximación — es la misma
plata sumada en otro orden.

Pero sólo cierra con DOS condiciones, y las dos son fáciles de romper:

1. **Entran TODOS los departamentos**, Cafetería (0220) y Lavandería (0161)
   incluidas. `gasto-por-clase` las excluye —es correcto para lo que ese
   endpoint hace— y con esa exclusión la diferencia era de $245.126,80 al año.
2. **El reparto va como su propio bloque.** Suma cero entre departamentos, pero
   sin él Cafetería muestra su gasto bruto ($18.688,80 en enero) y nunca netea.

Por eso el endpoint **mide el cuadre y lo devuelve** (`cuadre`): si algún día
deja de cerrar, la pantalla lo dice en vez de mostrar un GOP distinto al del P&L
de al lado. Dos pantallas del mismo sistema contando la misma plata y dando
números distintos es el modo de falla más caro que hay acá, porque ninguna de
las dos chilla.

## De dónde sale cada bloque

* **Ingreso y todo lo que va DEBAJO del GOP**: de `pl_detail_api`, recortando su
  misma plantilla. No se reconstruyen acá — si el ingreso o el impuesto se
  calcularan de nuevo serían un segundo motor que mantener, y el día que
  discrepen con el formato 1 nadie sabría cuál creer.
* **Costo, planilla, opex y reparto por departamento**: de las mismas cuatro
  agregaciones que alimentan el motor (`recalculate.*_by_dept`).
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query

from app.auth import get_current_user
from app.db import get_session
from app.errores import ErrorApi
from app.models.scenario import Scenario

from app.api.pl_detail_api import (AMBITOS, MAX_VERSIONES, _cascada, _nombre,
                                   _kpis)

router = APIRouter(tags=["pl-categoria"])

ZERO = Decimal("0")
CLUB_DEPT = "260"

#: Dónde corta la plantilla del formato 1. Todo lo que está DESPUÉS de este
#: rótulo baja igual al formato 2 — es literalmente la misma cascada.
#:
#: ⚠️ Se busca por rótulo y no por índice: la plantilla crece (el owner pide
#: renglones cada tanto) y un número fijo se desplaza en silencio, dejando el
#: GOP de un lado y «Rent» del otro sin que nada falle.
ROTULO_GOP = "TOTAL GROSS OPERATING PROFIT"

#: El encabezado y el total del bloque de ingreso.
#:
#: ⚠️ Van en constantes y no sueltos en el código porque la cascada del Excel
#: **se indexa por rótulo**: `tresCortes.ts` busca «TOTAL INGRESO» por su texto
#: para declarar la fórmula. Una prueba cruza las dos listas, y sólo puede
#: hacerlo si los rótulos se pueden leer de un lado.
SECCION_INGRESO = "INGRESO"
ROTULO_TOTAL_INGRESO = "TOTAL INGRESO"

#: Las cuatro naturalezas, en el orden en que el owner las nombró, más el
#: reparto. El reparto va al final porque es el que hace netear a los otros dos
#: departamentos: leerlo antes de ver su gasto bruto no se entiende.
BLOQUES = [
    ("cost", "COSTO DE VENTAS", "TOTAL COSTO DE VENTAS"),
    ("payroll", "PLANILLA", "TOTAL PLANILLA"),
    ("opex", "GASTOS OPERATIVOS", "TOTAL GASTOS OPERATIVOS"),
    ("reparto", "REPARTO · Cafetería y Lavandería", "TOTAL REPARTO"),
]


def _fila(tipo: str, rotulo: str, series):
    return {"tipo": tipo, "rotulo": rotulo, "series": series}


def _vacia(n: int):
    return [None] * n


def _suma_series(series: list[list[float]]) -> list[float]:
    out = [0.0] * 12
    for s in series:
        for i, v in enumerate(s):
            out[i] += v
    return out


def _filtra_ambito(d: dict, ambito: str) -> dict:
    """El Club es el departamento 260: el hotel es todo lo demás.

    ⚠️ En CWL el 260 está vacío, así que `consolidado` y `hotel` dan idéntico —
    medido. En Amarena no, y por eso el filtro existe igual."""
    if ambito == "club":
        return {k: v for k, v in d.items() if k == CLUB_DEPT}
    if ambito == "hotel":
        return {k: v for k, v in d.items() if k != CLUB_DEPT}
    return d


#: Cómo se mapea la salida de `build_actual_inputs` a las cuatro naturalezas.
_DEL_MAYOR = {"cost": "cos_by_dept", "payroll": "payroll_by_dept",
              "opex": "opex_by_dept", "reparto": "alloc_by_dept"}


async def _por_naturaleza(s, scenario_id: str, ambito: str) -> dict[str, dict[str, list[float]]]:
    """{naturaleza: {dept: [12 meses]}} — desde la MISMA fuente que su P&L.

    ⚠️ **Acá hay dos caminos y usar el que no es produce un reporte que no
    cuadra sin que nada falle.**

    * Un presupuesto armado en el sistema (`source_mode='checkbook'`) tiene su
      gasto en los checkbooks, y su P&L sale de ahí.
    * Un ACTUAL, o un presupuesto IMPORTADO, tienen su gasto en el MAYOR
      (`ActualEntry`) — sus checkbooks pueden estar vacíos o traer otra cosa.

    Leer siempre los checkbooks era sumar de una fuente y comparar contra otra:
    el ACTUAL 2026 daba **$90.408,84** de diferencia contra su propio GOP y el
    BUDGET 2026 Final **$205.676,93**. Medido el 2026-11-09.

    Por mes se mira si hay filas de mayor; si las hay, mandan. Es la misma
    prioridad que usa `_compute_pl_month_core`, y se decide mes a mes porque un
    forecast rodante tiene meses cerrados con mayor y meses futuros sin él.
    """
    from app.engine import pl_engine
    from app.engine import recalculate as recalc

    checkbook = {
        "cost": recalc.cos_by_dept,
        "payroll": recalc.payroll_by_dept,
        "opex": recalc.opex_by_dept,
        "reparto": recalc.alloc_by_dept,
    }
    out: dict[str, dict[str, list[float]]] = {k: {} for k in checkbook}

    def _acumular(clase: str, datos: dict, m: int):
        for dept, monto in _filtra_ambito(datos, ambito).items():
            if not monto:
                continue
            serie = out[clase].setdefault(str(dept or "(sin depto)"), [0.0] * 12)
            serie[m - 1] += float(monto)

    escenario = await s.get(Scenario, scenario_id)
    del_checkbook = getattr(escenario, "source_mode", "imported") == "checkbook"

    #: El ACTUAL enlazado de un forecast rodante. Sus meses CERRADOS no salen
    #: de sus propias filas: salen de ahí.
    #:
    #: ⚠️ **Es la misma regla de `_compute_pl_month_core`, copiada de su
    #: condición y no reinventada.** Leer las filas del propio forecast daba
    #: $101.557,44 de diferencia en el FORECAST October 2026 — y sólo en junio,
    #: julio, agosto y setiembre. Enero a mayo cuadraban porque el forecast se
    #: armó cuando esos meses ya estaban cerrados y su foto coincide; los cuatro
    #: siguientes cerraron después, y el ACTUAL tiene catorce cuentas más que la
    #: foto del forecast. Un desfase que aparece sólo en los meses del medio es
    #: justo el que nadie sale a buscar.
    enlazado = None
    if escenario is not None and escenario.type == "FORECAST":
        enlazado = await recalc.linked_actual_scenario(s, escenario)
    cierra_hasta = (getattr(escenario, "actuals_through", 0) or 0) if enlazado else 0

    for m in range(1, 13):
        if m <= cierra_hasta:
            # Mes cerrado de un rodante: manda el ACTUAL, como en el P&L.
            filas = await recalc.actual_rows_for_month(s, enlazado.id, m)
        else:
            filas = [] if del_checkbook else await recalc.actual_rows_for_month(
                s, scenario_id, m)
        if filas:
            entradas = pl_engine.build_actual_inputs(filas)
            for clase, llave in _DEL_MAYOR.items():
                _acumular(clase, entradas.get(llave) or {}, m)
        else:
            for clase, fn in checkbook.items():
                _acumular(clase, await fn(s, scenario_id, m), m)
    return out


async def _nombres_de_depto(s) -> dict[str, str]:
    from sqlalchemy import select

    from app.models.department_catalog import DepartmentCatalog

    filas = (await s.execute(select(DepartmentCatalog))).scalars().all()
    return {d.dept_code: d.dept_name for d in filas}


def _rotulo_depto(code: str, nombres: dict[str, str]) -> str:
    n = nombres.get(code, "")
    return f"{code} · {n}" if n else code


@router.get("/reports/pl-por-categoria/{ambito}/")
async def pl_por_categoria(
    ambito: str,
    scenario_id: str = Query(...),
    comparar: str | None = Query(
        None, description="hasta 3 versiones mas, separadas por coma"),
    _=Depends(get_current_user),
):
    """El MISMO P&L, agrupado por naturaleza del gasto en vez de por departamento.

    Devuelve la misma forma que `/reports/pl-detail/`: `filas` con
    `tipo`/`rotulo`/`series`, una serie de doce meses por version. Asi la
    pantalla y el Excel reusan el mismo armador de cuadros y no hay un segundo
    formato de payload que mantener.

    `cuadre` trae, por version, la diferencia entre el GOP de esta resta y el
    GOP del P&L de siempre. Tiene que ser cero.
    """
    if ambito not in AMBITOS:
        raise ErrorApi(422, "reporte.ambito_desconocido", ambito=ambito)
    #: El Club es UN departamento: su P&L va Ingreso → Planilla → Opex → Total
    #: Gastos → Net Profit, sin GOP y sin cascada debajo. Abrirlo «por
    #: departamento dentro de cada categoría» daría una fila por bloque, y el
    #: corte en el renglón del GOP —que su plantilla no tiene— reventaba con un
    #: 500. No es un fallo: es que este formato no le corresponde.
    if ambito == "club":
        raise ErrorApi(422, "reporte.formato_no_aplica", ambito=ambito)

    ids = [scenario_id] + [x.strip() for x in (comparar or "").split(",") if x.strip()]
    vistos, orden = set(), []
    for i in ids:
        if i not in vistos:
            vistos.add(i)
            orden.append(i)
    ids = orden[:MAX_VERSIONES]
    n = len(ids)

    async with get_session() as s:
        escenarios = []
        for sid in ids:
            e = await s.get(Scenario, sid)
            if e is None:
                raise ErrorApi(404, "escenario.no_encontrado")
            escenarios.append(e)

        nombres = await _nombres_de_depto(s)

        plantillas, cascadas, naturalezas = [], [], []
        for e in escenarios:
            plantilla, cascada = await _cascada(s, e.id, ambito)
            plantillas.append(plantilla)
            cascadas.append(cascada)
            naturalezas.append(await _por_naturaleza(s, e.id, ambito))

        # La plantilla de la PRINCIPAL manda: comparar dos cascadas distintas
        # daria filas que no se corresponden (misma regla que `pl-detail`).
        plantilla = plantillas[0]
        idx_gop = next(
            (j for j, (_t, rot, _c) in enumerate(plantilla) if rot == ROTULO_GOP), None)
        if idx_gop is None:
            raise ErrorApi(500, "reporte.sin_gop", ambito=ambito)

        def serie_de(vi: int, j: int) -> list[float]:
            c = cascadas[vi]
            return list(c[j]) if j < len(c) and c[j] else [0.0] * 12

        filas: list[dict] = []

        # ── 1 · INGRESO: la MISMA cabecera del formato 1, recortada hasta su
        #       total. No se recalcula: son las mismas filas, el mismo orden y
        #       los mismos codigos.
        for j, (tipo, rot, _c) in enumerate(plantilla):
            if tipo in ("esp",):
                continue
            if tipo == "sec" and rot.upper().startswith("REVENUE"):
                filas.append(_fila("sec", SECCION_INGRESO, _vacia(n)))
                continue
            if tipo == "det":
                filas.append(_fila("det", rot, [serie_de(vi, j) for vi in range(n)]))
                continue
            if tipo == "tot" and rot.upper().startswith("TOTAL REVENUE"):
                filas.append(_fila("tot", ROTULO_TOTAL_INGRESO,
                                   [serie_de(vi, j) for vi in range(n)]))
                break

        # El total de ingreso que acaba de emitirse, por version.
        total_ing = [list(filas[-1]["series"][vi]) for vi in range(n)]

        # ── 2 · Las cuatro naturalezas, cada una abierta por departamento ──────
        totales: dict[str, list[list[float]]] = {}
        for clase, titulo, rot_total in BLOQUES:
            # Los departamentos que aparecen en CUALQUIERA de las versiones: si
            # una tiene Cocina y la otra no, la fila existe igual y muestra el
            # cero. Sin esto, agregar un departamento en el forecast haria
            # desaparecer su comparacion en vez de mostrarla contra cero.
            depts = sorted({d for nat in naturalezas for d in nat[clase]})
            if not depts:
                continue
            filas.append(_fila("esp", "", _vacia(n)))
            filas.append(_fila("sec", titulo, _vacia(n)))
            for dept in depts:
                filas.append(_fila("det", _rotulo_depto(dept, nombres),
                                   [naturalezas[vi][clase].get(dept, [0.0] * 12)
                                    for vi in range(n)]))
            tot = [_suma_series(list(naturalezas[vi][clase].values()))
                   for vi in range(n)]
            totales[clase] = tot
            filas.append(_fila("tot", rot_total, tot))

        # ── 3 · GOP = ingreso − las cuatro ────────────────────────────────────
        gop_resta = []
        for vi in range(n):
            serie = list(total_ing[vi])
            for clase, *_ in BLOQUES:
                for i, v in enumerate(totales.get(clase, [[0.0] * 12] * n)[vi]):
                    serie[i] -= v
            gop_resta.append(serie)
        filas.append(_fila("esp", "", _vacia(n)))
        # ⚠️ El rótulo es EXACTAMENTE el del formato 1, y no uno más explicativo.
        # De este renglón cuelga toda la cascada de abajo —EBITDA Before Capital
        # lo nombra como operando—, y un rótulo propio dejaría EBITDA, EBT y NET
        # PROFIT como números pegados en el Excel mientras el detalle de arriba
        # baja con fórmula. La aritmética ya se lee en los encabezados de las
        # cinco secciones que tiene encima.
        filas.append(_fila("tot", ROTULO_GOP, gop_resta))

        # ── 4 · Todo lo que va DEBAJO del GOP, tal cual el formato 1 ──────────
        for j in range(idx_gop + 1, len(plantilla)):
            tipo, rot, _c = plantilla[j]
            if tipo in ("esp", "sec"):
                filas.append(_fila(tipo, rot if tipo == "sec" else "", _vacia(n)))
                continue
            filas.append(_fila(tipo, rot, [serie_de(vi, j) for vi in range(n)]))

        # ── 5 · El cuadre. Un reporte de control que no se controla a si mismo
        #       no controla nada.
        cuadre = []
        for vi in range(n):
            gop_motor = serie_de(vi, idx_gop)
            dif = [round(a - b, 2) for a, b in zip(gop_resta[vi], gop_motor)]
            cuadre.append({
                "scenario_id": escenarios[vi].id,
                "gop_resta": round(sum(gop_resta[vi]), 2),
                "gop_motor": round(sum(gop_motor), 2),
                "diferencia": round(sum(dif), 2),
                "peor_mes": max((abs(d) for d in dif), default=0.0),
                "cuadra": all(abs(d) < 0.02 for d in dif),
            })

        for f in filas:
            f["series"] = [[round(v, 2) for v in s] if s else None
                           for s in f["series"]]

        principal = escenarios[0]
        return {
            "ambito": ambito,
            "formato": "categoria",
            "scenario_id": principal.id,
            "escenario": _nombre(principal),
            "year": principal.year,
            "versiones": [{"scenario_id": e.id, "escenario": _nombre(e),
                           "kpis": await _kpis(s, e.id)} for e in escenarios],
            "filas": filas,
            "cuadre": cuadre,
        }


#: TODOS los rótulos que este formato emite y que la cascada del Excel indexa
#: por texto. La prueba `test_la_cascada_usa_EL_ROTULO_DE_ESTE_REPO` cruza esta
#: lista contra `tresCortes.ts`: un rótulo que cambie de un lado y no del otro
#: deja ese renglón bajando como número pegado, sin que nada falle.
ROTULOS_DEL_FORMATO = (
    [SECCION_INGRESO, ROTULO_TOTAL_INGRESO, ROTULO_GOP]
    + [titulo for _c, titulo, _t in BLOQUES]
    + [total for _c, _t, total in BLOQUES]
)
