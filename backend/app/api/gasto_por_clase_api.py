# -*- coding: utf-8 -*-
"""El gasto por CLASE de cuenta, mes a mes.

**Qué es (owner, 2026-08-14).** Las cuatro líneas del pie de su cuadro de cierre
son un corte por naturaleza del gasto, y la regla es tan simple como suena:

    Total Payroll and Benefits  →  todas las cuentas 6
    Total Cost                  →  todas las cuentas 5
    Total Operating Expenses    →  todas las cuentas 7
    Total Property Expenses     →  todas las cuentas 8

**Por qué no salía del P&L.** Las líneas del P&L están cortadas por
DEPARTAMENTO, no por naturaleza: `OPEX_ROOMS`, `OPEX_FB`… Sumarlas no da «todas
las 7», porque la planilla y el costo de esos mismos departamentos entran en la
misma línea. Es otro eje, y por eso necesita su propia consulta.

**De dónde sale, según el tipo de escenario:**

* BUDGET y FORECAST → de los checkbooks de la app (planilla, costo, opex) y del
  mini-checkbook de below-GOP para la clase 8.
* ACTUAL → del detalle del GL (`actual_entries`), por el primer dígito de la
  cuenta.

Los dos caminos coexisten en el mismo escenario a propósito: un forecast puede
tener meses reales cargados y meses proyectados, y hay que sumar los dos.

Devuelve **los doce meses**, no un agregado: quien llama arma mes, YTD o año sin
volver a preguntar. Sumar doce números en el cliente es gratis; doce viajes no.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from app.errores import ErrorApi
from app.auth import get_current_user
from app.db import get_session
from app.engine import recalculate as recalc
from app.models.actual_entry import ActualEntry
from app.models.belowgop_account_entry import BelowGopAccountEntry
from app.models.scenario import Scenario

router = APIRouter()

ZERO = Decimal("0")
MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]

# Cuentas de REPARTO. Son clase 4 pero NO son ingreso: es el credito con el que
# un departamento de servicio interno —Cafeteria, Lavanderia— se vacia contra los
# departamentos que lo consumen.
#
# Sin excluirlas, la apertura de ingreso mostraba «0220 Cafeteria -71,556» y
# «0161 Lavanderia -18,852» como si fueran ventas negativas (owner, 2026-08-14).
#
# ⚠️ Ojo con la 4901: el motor solo conoce 4900 y 4999
# (`pl_engine.ALLOCATION_ACCOUNTS`), y los libros reales usan tambien la 4901
# para la Cafeteria. Queda anotado — puede estar contandose como ingreso en el
# P&L, y eso es otra investigacion.
CUENTAS_DE_REPARTO = {"4900", "4901", "4999"}

# Departamentos que se FUSIONAN en la apertura de INGRESO (owner, 2026-08-14).
#
# La lavanderia esta partida a proposito: el 0162 factura y el 0161 lleva el
# gasto y lo reparte. Pero el ingreso venia cargado en los dos, segun el año y la
# version. Se movio el dato donde se pudo —los escenarios en borrador— y los
# enllavados no se pueden tocar sin abrir una foto historica.
#
# Fusionarlos EN LA VISTA resuelve las dos cosas de una: la venta de lavanderia
# sale en una sola fila en todas las versiones y todos los años, sin importar
# como quedo cargada.
#
# **Solo en ingreso.** En gasto siguen separados, que es justo el punto de
# tenerlos partidos: el 0161 tiene que poder cerrar en cero contra su reparto.
FUSION_INGRESO = {"0161": "0162"}

# Departamentos que NO salen en el GASTO: son POZOS de reparto. Su costo ya esta
# dentro de los departamentos que lo consumen, asi que mostrarlo aparte lo cuenta
# dos veces a la vista.
#
#   0220  Cafeteria  — viaja en la planilla de cada depto por el concepto 6025
#   0161  Lavanderia (operacion) — se reparte por la 4900
#   0162  Lavanderia (ingreso)   — es la cara de venta del mismo servicio
#
# Los tres SOLO se excluyen del gasto. En INGRESO la lavanderia si sale, en una
# sola linea: el 0161 se fusiona en el 0162 (ver FUSION_INGRESO).
#
# Es la misma razon por la que el motor excluye el 0220 del P&L de actuales
# (`pl_engine.ACTUAL_EXCLUDED_DEPTS`).
EXCLUIR_DE_GASTO = {"0220", "0161", "0162"}

# El nombre de cada clase, tal como lo escribe el owner en su cuadro.
CLASES = {
    "payroll": "Total Payroll and Benefits",   # 6xxx
    "cost": "Total Cost",                      # 5xxx
    "opex": "Total Operating Expenses",        # 7xxx
    "property": "Total Property Expenses",     # 8xxx
}


def _nombra(destino: dict, clave: str, nombre: str):
    """Guarda el nombre de una cuenta la primera vez que se la ve.

    El gasto de propiedad se abre por cuenta, y una lista de numeros sueltos
    —8005, 8020, 8040— no le dice nada a nadie (owner, 2026-08-14)."""
    if nombre:
        destino.setdefault("__nombres__", {}).setdefault(clave, nombre)


def _suma(destino: dict, clase: str, clave: str, mes: int, monto):
    """Acumula en {clase: {clave: [12 meses]}}. `clave` es el departamento, o la
    cuenta cuando se trata de la clase 8 —el gasto de propiedad se mira por
    cuenta del mayor, no por departamento, porque vive todo en el mismo."""
    if not monto:
        return
    serie = destino.setdefault(clase, {}).setdefault(clave or "(sin depto)", [0.0] * 12)
    serie[mes - 1] += float(monto)


async def _por_mes(session, scenario_id: str, detalle: dict | None = None) -> list[dict]:
    """Los cuatro totales, mes por mes. Si se pasa `detalle`, lo llena con la
    apertura por departamento (y por cuenta, para la clase 8)."""
    filas = []

    # Clase 8 del presupuesto: vive en su propio checkbook, con la cuenta en la
    # fila. Se lee una vez y se reparte por mes, en vez de doce consultas.
    below = (await session.execute(select(BelowGopAccountEntry).where(
        BelowGopAccountEntry.scenario_id == scenario_id))).scalars().all()

    # El nombre de cada cuenta 8xxx. `actual_rows_for_month` devuelve solo
    # codigo, depto y monto, asi que el nombre se busca aparte — una vez, no una
    # por mes.
    if detalle is not None:
        for f in (await session.execute(select(ActualEntry).where(
                ActualEntry.scenario_id == scenario_id))).scalars().all():
            if (f.account_code or "").startswith("8"):
                _nombra(detalle, f.account_code, f.account_name or "")
        for e in below:
            _nombra(detalle, str(e.account_code or ""), e.account_name or "")

    for m in range(1, 13):
        col = MESES[m - 1]
        payroll = cost = opex = prop = ZERO

        # ⚠️ Las dos fuentes NO se suman: se ELIGE una, igual que hace el motor
        # en `compute_pl_month`. Un escenario puede tener las dos cargadas —el
        # Actual tiene checkbooks Y detalle del GL— y sumarlas da exactamente el
        # doble. Se probó contra produccion: daba 2,100,673 de planilla donde el
        # cuadro del owner dice 1,170,402.
        #
        # Manda el GL cuando el mes lo tiene, porque es el dato real; si no hay,
        # se cae a los checkbooks, que es lo proyectado.
        filas_gl = await recalc.actual_rows_for_month(session, scenario_id, m)
        if filas_gl:
            for r in filas_gl:
                cuenta = str(r["account_code"] or "")
                dept = str(r.get("dept_code") or "")
                monto = Decimal(str(r["amount"] or 0))
                # El TOTAL de la clase suma todo; lo que se filtra es la
                # apertura. Si se filtrara el total, la pantalla dejaria de
                # amarrar con el P&L y no habria como notarlo.
                # El pozo de reparto sale del TOTAL tambien, no solo de la
                # apertura. Si saliera solo de la apertura, el renglon TOTAL del
                # cuadro no sumaria sus propias filas — y un total que no cuadra
                # con lo que tiene encima es peor que no tenerlo.
                #
                # ⚠️ Solo del GASTO. La primera version cortaba antes de mirar la
                # clase y se llevaba puesto el INGRESO de la lavanderia: la venta
                # del año bajaba 3,450 sin que nada lo dijera.
                if cuenta[:1] in ("5", "6", "7") and dept in EXCLUIR_DE_GASTO:
                    continue
                if cuenta.startswith("5"):
                    cost += monto
                    if detalle is not None: _suma(detalle, "cost", dept, m, monto)
                elif cuenta.startswith("6"):
                    payroll += monto
                    if detalle is not None: _suma(detalle, "payroll", dept, m, monto)
                elif cuenta.startswith("7"):
                    opex += monto
                    if detalle is not None: _suma(detalle, "opex", dept, m, monto)
                elif cuenta.startswith("8"):
                    prop += monto
                    # Clase 8 por CUENTA, no por departamento.
                    if detalle is not None:
                        _suma(detalle, "property", cuenta, m, monto)
                elif (cuenta.startswith("4") and detalle is not None
                        and cuenta not in CUENTAS_DE_REPARTO):
                    _suma(detalle, "revenue", FUSION_INGRESO.get(dept, dept), m, monto)
        else:
            pbd = await recalc.payroll_by_dept(session, scenario_id, m)
            cbd = await recalc.cos_by_dept(session, scenario_id, m)
            obd = await recalc.opex_by_dept(session, scenario_id, m)
            pbd = {d: v for d, v in pbd.items() if d not in EXCLUIR_DE_GASTO}
            cbd = {d: v for d, v in cbd.items() if d not in EXCLUIR_DE_GASTO}
            obd = {d: v for d, v in obd.items() if d not in EXCLUIR_DE_GASTO}
            payroll = sum(pbd.values(), ZERO)
            cost = sum(cbd.values(), ZERO)
            opex = sum(obd.values(), ZERO)
            prop = sum((Decimal(str(getattr(e, col) or 0)) for e in below), ZERO)
            if detalle is not None:
                def _abrir(clase, datos):
                    for d, v in datos.items():
                        _suma(detalle, clase, d, m, v)
                _abrir("payroll", pbd)
                _abrir("cost", cbd)
                _abrir("opex", obd)
                for e in below:
                    _suma(detalle, "property", str(e.account_code or ""), m,
                          Decimal(str(getattr(e, col) or 0)))

        filas.append({
            "month": m,
            "payroll": float(payroll), "cost": float(cost),
            "opex": float(opex), "property": float(prop),
            "total": float(payroll + cost + opex + prop),
        })
    return filas


@router.get("/gasto-por-clase/")
async def gasto_por_clase(
    scenarios: str = Query(..., description="ids separados por coma"),
    detalle: bool = Query(False, description="agrega la apertura por departamento"),
    _=Depends(get_current_user),
):
    """Los cuatro totales por clase, doce meses, para varios escenarios.

    Con `detalle=true` agrega la apertura: por departamento en planilla, costo,
    opex e ingreso; por CUENTA del mayor en gasto de propiedad, porque ahi todo
    vive en el mismo departamento y abrirlo por depto no diria nada."""
    ids = [x.strip() for x in scenarios.split(",") if x.strip()]
    if not ids:
        raise ErrorApi(422, "escenarios.requerido")
    salida = []
    async with get_session() as s:
        for sid in ids:
            e = await s.get(Scenario, sid)
            if e is None:
                continue   # un id que ya no existe no tumba la comparacion
            det: dict = {} if detalle else None
            meses = await _por_mes(s, sid, det)
            salida.append({
                "scenario_id": sid, "type": e.type,
                "version": e.version, "year": e.year,
                "meses": meses, "detalle": det,
                "nombres_cuenta": (det or {}).pop("__nombres__", {}) if det else {},
            })

    nombres: dict[str, str] = {}
    if detalle:
        from app.models.department_catalog import DepartmentCatalog
        async with get_session() as s:
            for d in (await s.execute(select(DepartmentCatalog))).scalars().all():
                nombres[d.dept_code] = d.dept_name
    return {"clases": CLASES, "escenarios": salida, "departamentos": nombres}
