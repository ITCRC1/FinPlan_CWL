# -*- coding: utf-8 -*-
"""Cierre de períodos — qué meses son ACTUAL y cuáles son FORECAST.

Owner, 2026-08-20: *«debería haber un tab en admin para cerrar períodos y dar a
entender qué meses son actuales y qué meses son forecast»* · *«yo subo y cierro
el mes para indicar que los actuales vienen del GL y el forecast viene de los
checkbooks»*.

## Lo que faltaba

El corte del rolling forecast es **un número**: `scenarios.actuals_through`. Los
meses `1..corte` no se calculan con el checkbook del forecast — se leen del
escenario ACTUAL enlazado (`recalculate.py:757`). Los de después, sí.

Pero hasta hoy ese número **sólo se movía como efecto de un import** y no había
dónde verlo. La consecuencia práctica: mirabas un forecast y no sabías qué mitad
era realidad y qué mitad era plan.

## Los tres avisos que esta pantalla existe para dar

⚠️ **1. Cerrar un mes sin ACTUAL enlazado es una mentira silenciosa.** El desvío
del motor pide dos cosas: que el mes esté dentro del corte **y** que exista un
escenario ACTUAL del mismo hotel y año. Si no existe, el corte avanza igual y el
P&L **vuelve a leer el checkbook** sin avisar: el forecast diría «junio ya
cerró» mostrando el plan. Por eso acá se verifica el enlace, no se supone.

⚠️ **2. Un mes cerrado SIN DATO en el actual reporta ceros.** Que el escenario
ACTUAL exista no significa que junio tenga líneas cargadas. Cerrar hasta junio
con junio vacío no da error: da un mes en cero, que se lee como «el hotel no
vendió». Se cuenta el dato mes por mes.

⚠️ **3. Abrir un mes cerrado MUEVE NÚMEROS.** Bajar el corte devuelve ese mes al
checkbook del forecast, o sea al plan. No es un cambio de vista: el P&L, el cash
flow y todo lo que cuelga de ellos cambian. Se pide confirmación explícita, con
el detalle de qué meses se reabren.

⚠️ **Y el checkbook de un mes cerrado NO se borra ni se pisa.** Sigue guardado y
sigue siendo editable — pero editarlo no mueve el P&L mientras el mes esté
cerrado. Es un no-op silencioso, y esta pantalla es donde se ve por qué.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID
from app.models.scenario import Scenario

router = APIRouter(tags=["cierre"])

ACTUAL = "ACTUAL"
FORECAST = "FORECAST"

MESES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"]


async def _con_dato(db: AsyncSession, actual: Scenario | None) -> set[int]:
    """Qué meses del ACTUAL tienen líneas cargadas de verdad.

    ⚠️ Se mira el resumen **y** el detalle: un escenario puede traer uno y no el
    otro, y cualquiera de los dos alcanza para que el mes reporte.
    """
    if actual is None:
        return set()
    from app.engine.recalculate import (actual_pl_lines_for_month,
                                        actual_rows_for_month)

    fuera: set[int] = set()
    for m in range(1, 13):
        if await actual_pl_lines_for_month(db, actual.id, m):
            fuera.add(m)
            continue
        filas = await actual_rows_for_month(db, actual.id, m)
        if any(f.get("amount") for f in filas):
            fuera.add(m)
    return fuera


@router.get("/scenarios/{scenario_id}/cierre/")
async def leer_cierre(scenario_id: str, db: AsyncSession = Depends(get_db),
                      _=Depends(get_current_user)):
    """Mes por mes: si es ACTUAL o FORECAST, de dónde sale y si el dato existe."""
    from app.engine.recalculate import linked_actual_scenario

    sc = await db.get(Scenario, scenario_id)
    if sc is None:
        raise ErrorApi(404, "escenario.no_encontrado", escenario=scenario_id)

    corte = int(sc.actuals_through or 0)
    actual = await linked_actual_scenario(db, sc) if sc.type == FORECAST else None
    con_dato = await _con_dato(db, actual)

    meses = []
    for m in range(1, 13):
        cerrado = sc.type == FORECAST and m <= corte
        # ⚠️ El desvío del motor pide LAS DOS cosas: dentro del corte Y actual
        # enlazado. Si falta el enlace, el mes «cerrado» sigue saliendo del
        # checkbook — y eso hay que decirlo, no suponerlo.
        real = cerrado and actual is not None
        meses.append({
            "mes": m,
            "nombre": MESES[m],
            "estado": ACTUAL if real else FORECAST,
            "cerrado": cerrado,
            # Owner, 2026-08-20: «yo subo y cierro el mes para indicar que los
            # actuales vienen del GL y el forecast viene de los checkbooks».
            "fuente": ("el GL (escenario ACTUAL)" if real
                       else "el checkbook de este escenario"),
            "tiene_dato": m in con_dato,
            # El aviso concreto de esta fila, o vacío.
            "aviso": (
                "marcado como cerrado pero NO hay escenario ACTUAL enlazado: "
                "el P&L sigue leyendo el checkbook" if cerrado and actual is None
                else "cerrado y el ACTUAL no tiene dato de este mes: va a "
                     "reportar CERO" if real and m not in con_dato
                else ""),
        })

    return {
        "escenario": {"id": sc.id, "tipo": sc.type, "anio": sc.year,
                      "version": sc.version,
                      "etiqueta": f"{sc.type} {sc.year} {sc.version}",
                      "es_current": bool(getattr(sc, "is_current_forecast", False)),
                      "enllavado": sc.is_locked},
        "corte": corte,
        "actual_enlazado": ({"id": actual.id, "etiqueta":
                             f"{actual.type} {actual.year} {actual.version}"}
                            if actual else None),
        "meses": meses,
        # ⚠️ Sólo el forecast marcado como Current avanza solo al importar. Los
        # reforecasts y snapshots son fotos de una decisión y no se tocan.
        "avanza_solo": (sc.type == FORECAST
                        and bool(getattr(sc, "is_current_forecast", False))),
        "nota": ("El checkbook de un mes cerrado NO se borra: deja de leerse. "
                 "Sigue editable, pero editarlo no mueve el P&L mientras el mes "
                 "esté cerrado."),
    }


class CambioCorte(BaseModel):
    corte: int
    #: Obligatorio para ABRIR meses. Sin esto, bajar el corte devuelve meses al
    #: plan y mueve el P&L sin que nadie lo haya confirmado.
    confirmar_apertura: bool = False


@router.patch("/scenarios/{scenario_id}/cierre/")
async def mover_corte(scenario_id: str, cambio: CambioCorte,
                      db: AsyncSession = Depends(get_db),
                      usuario=Depends(get_current_user)):
    """Cierra o abre períodos. **Abrir exige confirmación.**"""
    from app.engine.recalculate import linked_actual_scenario

    sc = await db.get(Scenario, scenario_id)
    if sc is None:
        raise ErrorApi(404, "escenario.no_encontrado", escenario=scenario_id)
    if sc.type != FORECAST:
        raise ErrorApi(422, "cierre.solo_forecast", tipo=sc.type)
    if not 0 <= cambio.corte <= 12:
        raise ErrorApi(422, "cierre.mes_invalido", mes=cambio.corte)

    antes = int(sc.actuals_through or 0)

    # ⚠️ **Abrir mueve números.** Bajar el corte devuelve esos meses al
    # checkbook, o sea al plan: el P&L, el cash flow y todo lo que cuelga
    # cambian. No es un cambio de vista.
    if cambio.corte < antes and not cambio.confirmar_apertura:
        reabren = ", ".join(MESES[m] for m in range(cambio.corte + 1, antes + 1))
        raise ErrorApi(409, "cierre.apertura_sin_confirmar", meses=reabren)

    # ⚠️ Cerrar sin ACTUAL enlazado no se impide —el corte es del escenario y
    # el enlace puede llegar después— pero se DEVUELVE el aviso: sin él, el
    # forecast diría «cerrado» mostrando el plan.
    actual = await linked_actual_scenario(db, sc)
    con_dato = await _con_dato(db, actual)
    sin_dato = [MESES[m] for m in range(1, cambio.corte + 1) if m not in con_dato]

    sc.actuals_through = cambio.corte
    await db.commit()

    return {
        "corte": cambio.corte,
        "antes": antes,
        "abiertos": max(0, antes - cambio.corte),
        "cerrados": max(0, cambio.corte - antes),
        "avisos": [a for a in [
            ("No hay escenario ACTUAL enlazado: los meses cerrados van a seguir "
             "saliendo del checkbook." if actual is None and cambio.corte else ""),
            (f"El ACTUAL no tiene dato de: {', '.join(sin_dato)}. Esos meses van "
             f"a reportar CERO." if actual is not None and sin_dato else ""),
        ] if a],
    }
