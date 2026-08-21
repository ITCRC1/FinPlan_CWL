# -*- coding: utf-8 -*-
"""Un mes cerrado no se vuelve a calcular. Y si algo lo movió, se avisa.

## El ciclo real del owner

    «Subo julio → se actualiza el ACTUAL 2026 → el Forecast Working se actualiza
    automáticamente → cierro y hago ajustes en el forecast y lo guardo como
    Agosto una vez que ya lo he revisado. **Esto no sucede inmediato, puede ser
    días.**»

Durante esa ventana de días el Working está VIVO y se está editando. Cualquier
cosa que toque julio ahí se mete en la foto de agosto sin que nadie lo note, y
la foto queda con un julio distinto del que él revisó y cerró.

El agujero grande no era una grilla: era `recalculate_scenario`, que escribía
los doce meses sin filtro y se dispara como efecto secundario desde doce
pantallas —incluido un banner de moneda que se descarta con un clic—.

## Qué se congela y qué no

Se congela **lo que el escenario guarda de su propia mano** en un mes cerrado:

  · el dólar derivado de una línea del checkbook en colones  (`_derivar_monedas`)
  · la planilla por posición-mes                             (`_recalc_payroll`)
  · los asientos de reparto                                  (`_recalc_allocations`)

Son exactamente los tres datasets que la foto mensual COPIA (`COPY_DATASETS`),
o sea los tres por donde un cambio tardío se cuela en el snapshot.

**No** se congela lo que el escenario solo ESPEJA de un histórico ya subido. Un
forecast rodante toma sus meses cerrados del ACTUAL enlazado
(`_compute_pl_month_core`): ahí la única fuente es lo subido, no puede derivar,
y la regla del owner manda — *«en un histórico manda lo subido»*. Congelar el
espejo solo lo dejaría viejo. Por eso `_persist_pl` protege los meses cerrados
que el escenario **produce** (`meses_propios`), no los que refleja, y la rama
ACTUAL de `recalculate_scenario` —que es una proyección pura de lo cargado— no
se filtra en absoluto.

## Qué es un mes cerrado

  · FORECAST → los meses hasta el corte (`actuals_through`).
  · ACTUAL   → los meses que YA TIENEN DATO.
  · BUDGET   → ninguno. Un presupuesto no cierra meses.

Para el ACTUAL se mira el VALOR y no la presencia, igual que
`_ultimo_mes_con_dato`: una recarga anual sube los doce meses aunque solo los
primeros traigan cifras, y tomar la presencia daría el año entero por cerrado.

## Y si ya se movió

`divergencia()` compara el escenario vivo contra su última foto, mes cerrado por
mes cerrado, línea por línea. No impide: **muestra**. Es el aviso barato que
reemplaza al candado caro que ya se descartó (un candado por grilla cubría lo
chico y dejaba abierto el recálculo — seguridad falsa).

⚠️ **Sin foto previa no hay línea base.** Se dice así, con esas palabras. No se
inventa una comparación contra el propio escenario, que siempre daría cero y no
probaría nada.

## El aviso lo NOMBRA el motor y lo redacta la pantalla

`app/engine/` no puede enterarse del idioma —regla del proyecto, vigilada por
`tests/test_i18n_locale.py`—, así que el aviso viaja tres veces:

  · `mensaje`         el español de siempre, como RESPALDO
  · `mensaje_key`     la clave dentro de `mesesCerrados` en el catálogo del front
  · `mensaje_params`  los números y las listas, SUELTOS

Los conteos van sueltos a propósito: «N línea(s) … M mes(es)» es la forma de
escribir un plural cuando no se puede resolver, y en inglés ni siquiera es la
misma regla. El plural se arma con ICU en la pantalla, no concatenando acá. Las
listas de meses viajan como números —dato— y la pantalla les pone nombre con su
propio catálogo de meses, así coinciden con el resto de la app.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, func

from app.models.scenario import Scenario
from app.models.actual_pl_line import ActualPLLine
from app.models.actual_entry import ActualEntry

ZERO = Decimal("0")

MONTH_ATTRS = ["jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"]

#: Cómo se llama la foto de cada mes (`snapshot-month/`). Es la MISMA lista que
#: `scenarios_api._SNAP_MONTHS`; se repite acá para no importar la API desde el
#: motor. `test_la_foto_y_el_motor_nombran_igual` vigila que no se separen: si se
#: separaran, «la última foto» apuntaría a un mes distinto del que dice.
SNAP_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

#: Un dólar. Por debajo es redondeo, no un cambio.
TOLERANCIA = Decimal("1")


# ─── Qué meses están cerrados ────────────────────────────────────────────────
async def meses_con_dato_por_fuente(session, scenario_id: str) -> tuple[set[int], set[int]]:
    """`(resumen, detalle)` — los meses con cifras en CADA hoja, por separado.

    ⚠️ Separadas, no unidas, porque la diferencia entre las dos es un
    diagnóstico: un mes que está en el DETALLE y no en el RESUMEN significa que
    se subió el mayor y no su otra mitad. Medido en producción el 2026-08-20:
    eso era exactamente el descuadre de $199.667,97 del ACTUAL 2026 — junio en
    el detalle y no en el resumen. Sacando junio, los siete totales de control
    cuadran al centavo.

    ⚠️ Y por VALOR, no por presencia. El detalle guarda los doce meses en
    COLUMNAS, así que «tiene filas» es cierto para todos aunque valgan cero: la
    primera versión de este diagnóstico acusaba a julio, agosto y hasta
    diciembre de faltar, y habría mandado a subir resúmenes de meses sin
    actividad.
    """
    resumen = {m for (m,) in (await session.execute(
        select(ActualPLLine.month)
        .where(ActualPLLine.scenario_id == scenario_id,
               ActualPLLine.amount_usd != 0)
        .distinct()
    )).all()}

    # Se suma el valor ABSOLUTO: un mes con un ingreso y un gasto que se anulan
    # tiene dato igual, y sumar con signo lo daría por vacío.
    sumas = (await session.execute(
        select(*[func.coalesce(func.sum(func.abs(getattr(ActualEntry, c))), 0)
                 for c in MONTH_ATTRS])
        .where(ActualEntry.scenario_id == scenario_id)
    )).one()
    detalle = {i + 1 for i, v in enumerate(sumas) if v}
    return (resumen, detalle)


async def meses_con_dato(session, scenario_id: str) -> set[int]:
    """Los meses de un ACTUAL que traen cifras — por VALOR, no por presencia."""
    resumen, detalle = await meses_con_dato_por_fuente(session, scenario_id)
    return resumen | detalle


async def meses_cerrados(session, scenario: Scenario) -> set[int]:
    """Los meses de este escenario que ya se cerraron."""
    tipo = (getattr(scenario, "type", "") or "").upper()
    if tipo == "ACTUAL":
        return await meses_con_dato(session, scenario.id)
    if tipo == "FORECAST":
        corte = int(getattr(scenario, "actuals_through", 0) or 0)
        return set(range(1, corte + 1))
    # BUDGET: un presupuesto no cierra meses. Si trae `actuals_through` cargado
    # por accidente, no se le hace caso: el desvío al ACTUAL enlazado tampoco se
    # le aplica (`_compute_pl_month_core`), así que tomarlo acá inventaría un
    # cierre que ningún otro camino reconoce.
    return set()


# ─── La última foto ──────────────────────────────────────────────────────────
async def ultima_foto(session, scenario: Scenario) -> Scenario | None:
    """La foto mensual más reciente de este escenario, o None si no hay ninguna.

    Son los `FORECAST {Mes} {año}` que crea `snapshot-month/`: mismo hotel, mismo
    año, versión con nombre de mes, y NO el Current.
    """
    if (getattr(scenario, "type", "") or "").upper() != "FORECAST":
        return None
    fotos = (await session.execute(
        select(Scenario).where(
            Scenario.hotel_id == scenario.hotel_id,
            Scenario.year == scenario.year,
            Scenario.type == "FORECAST",
            Scenario.id != scenario.id,
            Scenario.version.in_(SNAP_MONTHS),
        )
    )).scalars().all()
    if not fotos:
        return None
    return max(fotos, key=lambda s: SNAP_MONTHS.index(s.version))


def mes_de_la_foto(foto: Scenario | None) -> int:
    """1..12 según el nombre de la versión, o 0 si no hay foto."""
    if foto is None:
        return 0
    try:
        return SNAP_MONTHS.index(foto.version) + 1
    except ValueError:
        return 0


# ─── La señal ────────────────────────────────────────────────────────────────
async def _pl_por_mes(session, scenario: Scenario, meses: list[int]) -> dict:
    """{mes: {line_code: (line_name, monto)}} para los meses pedidos."""
    # Import perezoso: `recalculate` importa este módulo, así que al revés sería
    # un ciclo en tiempo de import.
    from app.engine import recalculate as recalc

    revenue = (None if scenario.type == "ACTUAL"
               else await recalc.load_revenue_results(session, scenario))
    fuera: dict[int, dict[str, tuple[str, Decimal]]] = {}
    for m in meses:
        lineas = await recalc.compute_pl_month(session, scenario, m, revenue)
        fuera[m] = {ln.line_code: (ln.line_name, Decimal(str(ln.amount_usd or 0)))
                    for ln in lineas}
    return fuera


async def divergencia(session, scenario: Scenario,
                      tolerancia: Decimal = TOLERANCIA) -> dict:
    """¿Se movió algún mes cerrado desde la última foto? Qué mes, qué línea, cuánto.

    No bloquea nada. Devuelve siempre la misma forma, con `hay_foto` diciendo si
    la comparación se pudo hacer.
    """
    cerrados = sorted(await meses_cerrados(session, scenario))
    foto = await ultima_foto(session, scenario)
    mes_foto = mes_de_la_foto(foto)

    base = {
        "scenario_id": scenario.id,
        "escenario": f"{scenario.type} {scenario.version} {scenario.year}",
        "meses_cerrados": cerrados,
        "tolerancia": float(tolerancia),
        "hay_foto": foto is not None,
        "foto": None if foto is None else {
            "id": foto.id,
            "version": foto.version,
            "mes": mes_foto,
            "etiqueta": f"Forecast {foto.version} {foto.year}",
            "created_at": foto.created_at.isoformat() if foto.created_at else None,
        },
        # Meses cerrados que ninguna foto alcanzó: el owner cerró y no sacó la
        # foto. No es un error — puede estar todavía revisando—, pero sin esto
        # nada se lo recuerda y el cierre se queda sin registro.
        "meses_cerrados_sin_foto": [m for m in cerrados if m > mes_foto],
        "diferencias": [],
        "meses_movidos": [],
        # Los meses que la foto SÍ alcanzó a cubrir: los únicos comparables. Va
        # en la respuesta porque el aviso lo nombra y la pantalla lo redacta.
        "meses_comparables": [],
    }

    if not cerrados:
        return {**base, "veredicto": "sin_meses_cerrados",
                "mensaje_key": "sin_meses_cerrados", "mensaje_params": {},
                "mensaje": "Este escenario todavía no tiene meses cerrados: no "
                           "hay nada que proteger ni que comparar."}
    if foto is None:
        return {**base, "veredicto": "sin_foto",
                "mensaje_key": "sin_foto", "mensaje_params": {},
                "mensaje": "No hay ninguna foto previa de este escenario, así "
                           "que no hay contra qué comparar. La primera foto es "
                           "la que crea la línea base."}

    # Solo se comparan los meses que la foto alcanzó a cubrir. Un mes cerrado
    # DESPUÉS de la foto no puede haberse «movido» respecto de ella: nunca
    # estuvo adentro. Contarlo como diferencia sería inventar un desvío.
    comparables = [m for m in cerrados if m <= mes_foto]
    base = {**base, "meses_comparables": comparables}
    if not comparables:
        return {**base, "veredicto": "foto_anterior_al_cierre",
                "mensaje_key": "foto_anterior_al_cierre",
                "mensaje_params": {"foto": foto.version, "lista": cerrados},
                "mensaje": f"La última foto es de {foto.version} y los meses "
                           f"cerrados son {cerrados}: la foto es anterior al "
                           f"cierre, no hay meses en común para comparar."}

    ahora = await _pl_por_mes(session, scenario, comparables)
    antes = await _pl_por_mes(session, foto, comparables)

    difs = []
    for m in comparables:
        a, b = antes.get(m, {}), ahora.get(m, {})
        for code in sorted(set(a) | set(b)):
            va = a.get(code, ("", ZERO))[1]
            vb = b.get(code, ("", ZERO))[1]
            if abs(vb - va) <= tolerancia:
                continue
            difs.append({
                "mes": m,
                "line_code": code,
                "line_name": b.get(code, a.get(code, ("", ZERO)))[0],
                "foto": float(va),
                "ahora": float(vb),
                "delta": float(vb - va),
            })

    movidos = sorted({d["mes"] for d in difs})
    if not difs:
        return {**base, "veredicto": "sin_cambios", "diferencias": [],
                "meses_movidos": [],
                "mensaje_key": "sin_cambios",
                "mensaje_params": {"foto": foto.version, "lista": comparables},
                "mensaje": f"Los meses cerrados {comparables} están igual que en "
                           f"la foto de {foto.version}."}
    return {**base, "veredicto": "cambio_en_mes_cerrado", "diferencias": difs,
            "meses_movidos": movidos,
            "mensaje_key": "cambio_en_mes_cerrado",
            # `lineas` y `meses` son CONTEOS —el plural se resuelve con ICU en la
            # pantalla— y `lista` son los meses en sí, que la pantalla nombra.
            "mensaje_params": {"lineas": len(difs), "meses": len(movidos),
                               "foto": foto.version, "lista": movidos},
            "mensaje": f"{len(difs)} línea(s) del P&L se movieron en "
                       f"{len(movidos)} mes(es) YA CERRADO(s) desde la foto de "
                       f"{foto.version}: mes(es) {movidos}."}
