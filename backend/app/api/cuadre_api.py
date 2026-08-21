# -*- coding: utf-8 -*-
"""Cuadre: la hoja Resumen contra la hoja Detalle, línea por línea.

**Por qué existe (2026-08-14).** El archivo que se sube trae DOS hojas y cada una
alimenta una tabla distinta: el Resumen va a `actual_pl_line` (el P&L a nivel de
línea) y el Detalle al `actual_entry` (el GL, cuenta × departamento). Cuando no
coinciden, el que está mal es el DATO, no el reporte.

Ese día apareció así: el sistema decía que el gasto de Habitaciones del Actual
2024 era $394,940.48 y el auxiliar del owner decía $354,327.21. Rastrearlo tomó
media sesión y se hizo tres veces a mano. Esto lo vuelve una pantalla.

**Los alias son la mitad del trabajo.** Las dos hojas usan códigos distintos para
la misma línea —`OPEXP_ROOMS` contra `OPEX_ROOMS`, `OVH_ADMIN` contra
`OH_ADMIN`— así que sin normalizar, TODO parece descuadre. La primera vez que
corrí esta comparación a mano dio 60 líneas rojas y ninguna era real.

**Cuál de las dos manda NO depende del tipo de escenario.** El motor usa el
Detalle solo cuando sus siete totales de control coinciden con el Resumen
(`recalculate.veredicto_del_detalle`); si no, manda el Resumen — sea Actual,
Budget o Forecast. Este endpoint le pregunta esa decisión al motor en vez de
adivinarla, porque lo que la pantalla tiene que decir es cuál hoja está
produciendo el P&L de HOY, no cuál debería.

**Y ahora dice POR QUÉ (2026-08-16).** La decisión se tomaba en silencio: la
pantalla mostraba «manda el resumen» sin la evidencia, así que el desacuerdo
—que es justo lo que el owner quiere ver— quedaba invisible. El campo
`veredicto` trae el motivo en palabras, los meses que se evaluaron y la
diferencia de cada total de control que no cuadra.

⚠️ **Las filas se comparan sobre los DOCE meses; la compuerta mira solo los
meses propios.** No es una contradicción: un forecast con corte reporta sus
meses cerrados desde el Actual enlazado, así que el descuadre de esos meses es
información sobre el dato cargado (y hay que verlo) pero no puede decidir qué
hoja produce un P&L que ni los usa. `veredicto.meses_evaluados` dice cuáles
pesaron.
"""
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.errores import ErrorApi
from app.auth import get_current_user
from app.db import get_session
from app.models.actual_pl_line import ActualPLLine
from app.models.scenario import Scenario

router = APIRouter()

# Debajo de esto es redondeo, no descuadre.
TOLERANCIA = 1.0


@router.get("/reports/cuadre/{scenario_id}/")
async def cuadre(scenario_id: str, _=Depends(get_current_user)):
    """Resumen vs Detalle para un escenario, con los alias ya normalizados."""
    from app.engine import recalculate as recalc, pl_engine

    canon = {k: v[0] for k, v in pl_engine._MOTOR_TO_CANON.items()}
    nombres = {}

    async with get_session() as s:
        e = await s.get(Scenario, scenario_id)
        if e is None:
            raise ErrorApi(404, "escenario.no_encontrado")

        resumen: dict[str, float] = defaultdict(float)
        for l in (await s.execute(select(ActualPLLine).where(
                ActualPLLine.scenario_id == scenario_id))).scalars().all():
            resumen[canon.get(l.line_code, l.line_code)] += float(l.amount_usd or 0)

        # ⚠️ Cuál manda se le PREGUNTA AL MOTOR, no se adivina por tipo,
        # y se pide CON EL MOTIVO — la elección tiene que quedar a la vista.
        #
        # Esto decía «resumen si es ACTUAL, detalle si no», y el motor no
        # funciona así: `_detalle_fino_si_cuadra` usa el detalle solo cuando sus
        # siete totales del año coinciden con el resumen, sea cual sea el tipo.
        # Medido contra producción el 2026-08-15, la etiqueta mentía en CUATRO
        # de los seis escenarios de 2026 y anteriores — decía «resumen» en los
        # Actuales 2025 y 2026, que van por el detalle, y «detalle» en el Budget
        # Final 2026 y en los dos Forecast 2026, que van por el resumen.
        #
        # Esta pantalla existe para decirle al owner cuál de las dos hojas está
        # produciendo su P&L. Con la etiqueta al revés, mandaba a corregir la
        # hoja equivocada.
        veredicto = await recalc.veredicto_del_detalle(s, e)
        manda_el_detalle = veredicto["manda"] == "detalle"

        detalle: dict[str, float] = defaultdict(float)
        mappings = await recalc.load_active_account_mappings(s)
        report_lines = await recalc.load_report_line_config(s)
        meses_con_detalle = 0
        for m in range(1, 13):
            filas = await recalc.actual_rows_for_month(s, scenario_id, m)
            if not filas:
                continue
            meses_con_detalle += 1
            for ln in pl_engine.calculate_pl_from_mapping(filas, mappings, report_lines):
                c = canon.get(ln.line_code, ln.line_code)
                detalle[c] += float(ln.amount_usd)
                nombres.setdefault(c, ln.line_name)

    hay_resumen, hay_detalle = bool(resumen), bool(detalle)
    filas = []
    for c in sorted(set(resumen) | set(detalle)):
        r, d = resumen.get(c, 0.0), detalle.get(c, 0.0)
        if abs(r) < 0.005 and abs(d) < 0.005:
            continue
        dif = d - r
        filas.append({
            "line_code": c,
            "line_name": nombres.get(c, c),
            "resumen": r,
            "detalle": d,
            "diferencia": dif,
            "cuadra": abs(dif) < TOLERANCIA,
        })

    descuadres = [f for f in filas if not f["cuadra"]]
    neto_r = resumen.get("NET_PROFIT", 0.0)
    neto_d = detalle.get("NET_PROFIT", 0.0)

    return {
        "scenario": {"id": e.id, "type": e.type, "version": e.version,
                     "year": e.year, "status": e.status},
        # Sin una de las dos hojas no hay nada que comparar, y decirlo evita que
        # una pantalla vacía se lea como «cuadra todo».
        "hay_resumen": hay_resumen,
        "hay_detalle": hay_detalle,
        "meses_con_detalle": meses_con_detalle,
        "comparable": hay_resumen and hay_detalle,
        "filas": filas,
        "descuadres": len(descuadres),
        "neto_resumen": neto_r,
        "neto_detalle": neto_d,
        "neto_diferencia": neto_d - neto_r,
        # Cuál manda: la MISMA decisión que toma el motor al armar el P&L.
        "manda": "detalle" if manda_el_detalle else "resumen",
        # ...y por qué: motivo en palabras, meses evaluados y los totales de
        # control que no cuadran, con su diferencia.
        "veredicto": veredicto,
    }


@router.get("/reports/cuadre/")
async def escenarios_comparables(con_veredicto: bool = False,
                                 _=Depends(get_current_user)):
    """Qué escenarios tienen las dos hojas y se pueden cuadrar.

    Con `?con_veredicto=1` cada escenario comparable trae además **cuál hoja
    manda y por qué**, en una sola llamada — que es la pregunta que el owner
    hace de verdad: no «cuáles se pueden cuadrar» sino «cuál de los míos está
    reportando contra un control viejo».

    Va apagado por defecto a propósito: el veredicto recorre el año entero de
    cada escenario y esta ruta es el selector de la pantalla. Prenderlo siempre
    convertiría un listado en un recálculo.
    """
    from app.engine import recalculate as recalc

    async with get_session() as s:
        escs = (await s.execute(select(Scenario).order_by(
            Scenario.year.desc(), Scenario.type))).scalars().all()
        con_resumen = {r[0] for r in (await s.execute(
            select(ActualPLLine.scenario_id).distinct())).all()}
        salida = []
        for e in escs:
            fila = {"id": e.id, "type": e.type, "version": e.version,
                    "year": e.year, "status": e.status,
                    "tiene_resumen": e.id in con_resumen}
            if con_veredicto and e.id in con_resumen:
                fila["veredicto"] = await recalc.veredicto_del_detalle(s, e)
            salida.append(fila)
    return {"escenarios": salida}
