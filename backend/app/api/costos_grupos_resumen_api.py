# -*- coding: utf-8 -*-
"""SUMMARY COST — la vista de entrada del tab (spec `COSTOS_GRUPOS.md` §5).

**El orden del spec es deliberado: el resumen va de primero.** Quien abre el
tab —operación, Ventas, Gerencia— tiene que ver el número que necesita sin
recorrer el motor. El detalle de cómo se llegó ahí vive detrás.

Es una vista **derivada**: no acepta entradas y no recalcula por su cuenta.
Todo sale del mismo motor que alimenta las otras pantallas, así que no puede
decir algo distinto que ellas.

Tres bloques:

* **A · porcentual** — el formato que la Junta ya aprobó, ahora con las dos
  capas de comisión. ⚠️ Lleva advertencia visible: **estos porcentajes sirven
  para leer el P&L y fijar techos de comisión, NO para fijar pisos de precio**
  (§1). En vista mensual el overhead como % del revenue oscila fuertísimo entre
  meses; es efecto del denominador, no de la estructura.
* **B · dólares por driver** — la que se usa para negociar.
* **C · Golden Rate** — anual, contra el ADR real, con la brecha.

Y un **pie de calidad del dato**: qué se apoya en medición y qué en prorrateo.
Sin eso, un número prorrateado se lee como medido.
"""
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException

from app.auth import get_current_user
from app.db import get_db
from app.engine import costos_grupos as cg
from app.hotel_actual import HOTEL_ID

router = APIRouter(prefix="/costos-grupos", tags=["costos-grupos"])

CENTAVO = Decimal("0.01")


def _n(v: Decimal | float | int) -> str:
    return str(Decimal(str(v)).quantize(CENTAVO, rounding=ROUND_HALF_UP))


# ─── Los selectores del §5 ───────────────────────────────────────────────────
#
# El spec pide tres independientes y combinables: **Período** (mes · YTD · año
# completo), **Temporada** y **Base** (Actual · Budget · Forecast). Hasta el
# 2026-08-20 sólo existían mes y temporada, y la base estaba clavada en
# `cfg_parametros.escenario_base`.
#
# ⚠️ **Elegir otra base en la pantalla NO cambia `escenario_base`.** Ese
# parámetro es una decisión del owner —«los costos salen del Forecast Working
# 2026, que es la realidad»— y gobierna los Pisos y la Golden Rate que se usan
# para negociar. Acá es un filtro de LECTURA: se mira otro escenario sin mover
# el que manda. La respuesta dice cuál es el configurado para que la diferencia
# se vea.

PERIODOS = ("full", "ytd", "mes", "meses")


def meses_pedidos(crudo: str | None) -> set[int]:
    """`"1,2,3"` → `{1, 2, 3}`.

    ⚠️ **Lo que no es un mes se DESCARTA en silencio, y está bien acá**: la
    lista la arma la pantalla marcando casillas, así que un valor raro es un
    error de programa, no del owner. Lo que NO puede pasar es que un `"13"`
    entre y devuelva un cuadro vacío que se lea como «ese mes no tuvo costo».
    """
    fuera: set[int] = set()
    for parte in (crudo or "").split(","):
        parte = parte.strip()
        if parte.isdigit() and 1 <= int(parte) <= 12:
            fuera.add(int(parte))
    return fuera


async def _base_elegida(db, escenario_id: str | None):
    """El escenario a mirar, y el configurado. Devuelve `(sc, base, es_base)`."""
    base = await cg.escenario_base(db, HOTEL_ID)
    if not escenario_id:
        return base, base, True
    from sqlalchemy import select

    from app.models.scenario import Scenario

    sc = (await db.execute(
        select(Scenario).where(Scenario.id == escenario_id,
                               Scenario.hotel_id == HOTEL_ID)
    )).scalars().first()
    if sc is None:
        raise HTTPException(404, f"escenario no encontrado: {escenario_id}")
    return sc, base, bool(base and sc.id == base.id)


def _corte_ytd(sc, meses: list) -> int:
    """Hasta qué mes llega el YTD.

    ⚠️ **Sale del corte del escenario (`actuals_through`), no del calendario.**
    Un YTD que llegara hasta «hoy» incluiría meses sin dato y bajaría todos los
    unitarios sin avisar: el costo estaría dividido entre ocupación que todavía
    no ocurrió. Si el escenario no tiene corte —un presupuesto, por ejemplo—, se
    cae al último mes CON dato, que es lo mismo que hace el rolling forecast.
    """
    corte = int(getattr(sc, "actuals_through", 0) or 0)
    if corte:
        return corte
    con_dato = [m.mes for m in meses
                if m.hab_ocupadas > 0 or sum(m.revenue_por_dept.values(), 0)]
    return max(con_dato) if con_dato else 12


MES_CORTO = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
             "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _filtrar(todos: list, sc, periodo: str, mes: int | None,
             temporada: str | None, meses: set[int] | None = None) -> tuple[list, str]:
    """Los meses seleccionados y cómo se llama esa selección.

    Período y temporada se cruzan por INTERSECCIÓN, como pide el §5.

    ⚠️ **Una lista de meses explícita MANDA sobre el período.** Si el owner
    marcó casillas, eso es lo que quiere ver; dejar que «año completo» le gane
    devolvería los doce meses con las casillas marcadas en la pantalla, y no
    habría forma de saber cuál de los dos se está mirando.
    """
    if meses:
        sel = [m for m in todos if m.mes in meses]
        etiqueta = " · ".join(MES_CORTO[m] for m in sorted(meses))
    elif periodo == "ytd":
        corte = _corte_ytd(sc, todos)
        sel = [m for m in todos if m.mes <= corte]
        etiqueta = f"YTD (enero a mes {corte})"
    elif periodo == "mes" and mes:
        sel = [m for m in todos if m.mes == mes]
        etiqueta = f"mes {mes}"
    else:
        sel = list(todos)
        etiqueta = "año completo"
    if temporada:
        sel = [m for m in sel if m.temporada == temporada]
        etiqueta += f" × {temporada}"
    return sel, etiqueta


# Los departamentos del resumen, en el orden del reporte del owner.
CONCEPTOS = ["ROOMS", "FB", "TOURS", "TRANSPORTATION", "SPA", "RETAIL",
             "LAUNDRY", "CLUB", "INNOCEANA", "SUSTAINABILITY", "MISC_OTHER"]


@router.get("/resumen/")
async def resumen(mes: int | None = None, temporada: str | None = None,
                  periodo: str = "full", escenario_id: str | None = None,
                  meses: str | None = None,
                  db=Depends(get_db), _=Depends(get_current_user)):
    """Los tres bloques. `mes` y `temporada` se cruzan por INTERSECCIÓN.

    ⚠️ Si la combinación queda vacía —«julio × ALTA»— se dice, en vez de
    devolver ceros. Un cero que en realidad es «no hay meses» se lee como «no
    hay costo», que es lo contrario.
    """
    par = await cg.cargar_parametros(db, HOTEL_ID)
    comp = await cg.cargar_composicion(db, HOTEL_ID)
    sc, base, es_base = await _base_elegida(db, escenario_id)
    if sc is None:
        raise HTTPException(409, "el escenario base no existe")

    todos = await cg.hechos_mensuales(db, sc, HOTEL_ID)
    sel, etiqueta = _filtrar(todos, sc, periodo, mes, temporada,
                             meses_pedidos(meses))
    if not sel:
        return {
            "vacio": True,
            "motivo": f"no hay meses en «{etiqueta}»",
            "escenario": f"{sc.type}/{sc.year}/{sc.version}",
        }

    # La comisión sale del tarifario del módulo. ⚠️ NO de `compute_net_factor`,
    # que hasta el 2026-08-20 devolvía 9,5640 (sumaba los doce meses sin
    # dividir). Arreglado; el módulo sigue leyéndolo del tarifario a propósito.
    factor = cg.factor_neto_del_rack(await cg.tarifas_rack(db, HOTEL_ID, 1))
    comision = (Decimal("1") - factor) if factor is not None else Decimal("0")
    margen = Decimal(par.get("margen_protegido_pct", "0.15"))
    metodo = par.get("metodo_absorcion", "M2")

    abiertos = [m for m in sel if m.dias_abiertos > 0]
    cu = cg.costos_unitarios(abiertos or sel, comp)
    pisos = cg.pisos_habitacion(sel, comp, par, comision, metodo, todos)

    # ── Bloque A · porcentual, con las dos capas ─────────────────────────────
    #
    # ⚠️ El factor neto es por DEPARTAMENTO. Habitaciones y paquetes llevan
    # comisión de agencia embebida en el revenue del P&L; tienda, spa y consumos
    # en sitio se venden directo y su factor es 1.0. Aplicarles el gross-up
    # descontaría una comisión que nadie cobró.
    con_agencia = {"ROOMS", "FB", "TOURS", "TRANSPORTATION"}
    factores = {c: (factor if (c in con_agencia and factor) else Decimal("1"))
                for c in CONCEPTOS}
    capas = cg.comision_maxima(sel, comp, par, factores, metodo)

    # ── Bloque C · Golden Rate. SIEMPRE anual ────────────────────────────────
    #
    # ⚠️ Sobre `todos`, no sobre `sel`: aislada, la alta parece necesitar mucho
    # menos porque los demás departamentos aportan de sobra en esos meses.
    # Vender alta contra una Golden Rate estacional destruye el año.
    gr = cg.golden_rate(todos, comp, par, comision, margen)
    gr_con_margen = gr.tarifa

    rev_rooms = sum((m.revenue_por_dept.get("REV_ROOMS", Decimal("0"))
                     for m in sel), Decimal("0"))
    ocup = sum((m.hab_ocupadas for m in sel), Decimal("0"))
    adr = (rev_rooms / ocup) if ocup else Decimal("0")

    return {
        "escenario": f"{sc.type}/{sc.year}/{sc.version}",
        "escenario_id": sc.id,
        # ⚠️ Cuál es el configurado, y si se está mirando otro. Sin esto, leer
        # un piso de un escenario distinto del que manda parece el piso oficial.
        "base_configurada": (f"{base.type}/{base.year}/{base.version}"
                             if base else ""),
        "es_base": es_base,
        "seleccion": {
            "etiqueta": etiqueta,
            "periodo": periodo,
            "meses": sorted(m.mes for m in sel),
            "meses_con_ocupacion": sorted(m.mes for m in sel if m.hab_ocupadas > 0),
            "cerrados": sorted(m.mes for m in sel if m.dias_abiertos == 0),
            "temporadas": sorted({m.temporada for m in sel if m.temporada}),
        },
        "parametros": {
            "comision": _n(comision), "margen_protegido": _n(margen),
            "fee": _n(Decimal(par.get("management_fee_pct", "0.03"))),
            "metodo_absorcion": metodo,
            "tratamiento_mes_cerrado": par.get("tratamiento_mes_cerrado", "B"),
        },

        # ── A ────────────────────────────────────────────────────────────────
        "bloque_a": [
            {
                "concepto": c.concepto,
                "costo": _n(c.costo),
                "revenue_neto": _n(c.revenue_neto),
                "factor_neto": _n(c.factor_neto),
                "margen_integral": _n(c.margen_integral),
                "capa1": _n(c.capa1),
                "capa2": _n(c.capa2),
            }
            for c in capas
        ],

        # ── B ────────────────────────────────────────────────────────────────
        "bloque_b": {
            "hab_propio_por_ocupada": _n(cu["hab_propio_por_ocupada"]),
            "fb_propio_por_huesped": _n(cu["fb_propio_por_huesped"]),
            "tours_propio_por_huesped": _n(cu["tours_propio_por_huesped"]),
            "transp_propio_por_ocupada": _n(cu["transp_propio_por_ocupada"]),
            "spa_propio_por_huesped": _n(cu["spa_propio_por_huesped"]),
            "overhead_por_disponible": _n(cu["overhead_por_disponible"]),
            "overhead_por_ocupada": _n(cu["overhead_por_ocupada"]),
            "pisos": {
                "marginal": _n(pisos.marginal),
                "departamental": _n(pisos.departamental),
                "integral": _n(pisos.integral),
                "con_margen": _n(pisos.con_margen),
            },
            "marginal_estimado": pisos.marginal_estimado,
        },

        # ── C ────────────────────────────────────────────────────────────────
        "bloque_c": {
            "tarifa": _n(gr_con_margen),
            "requerido": _n(gr.requerido),
            "costo_propio_rooms": _n(gr.costo_propio_rooms),
            "overhead": _n(gr.overhead),
            "no_operativo": _n(gr.no_operativo),
            "capital": _n(gr.capital),
            "contribucion_ajena": _n(gr.contribucion_ajena),
            "hab_ocupadas": _n(gr.hab_ocupadas),
            "detalle_contribucion": {k: _n(v)
                                     for k, v in gr.detalle_contribucion.items()},
            "adr_real": _n(adr),
            "brecha": _n(adr - gr_con_margen),
        },

        # ── Pie · calidad del dato ───────────────────────────────────────────
        #
        # ⚠️ No es una nota al pie. Un número prorrateado que se presenta como
        # medido convierte un supuesto en un compromiso.
        "calidad": cg._prorrateados(cu, [], pisos.marginal_estimado),
    }


# ─── El cuadro aprobado por la Junta, ampliado ───────────────────────────────
#
# Owner, 2026-08-20: «quiero tener un tab así, resumido» y después «podés
# ampliar ese summary que quede más claro», con su reporte **PROPUESTA DE
# DESCUENTOS — COSTO FULLY LOADED** a la vista. Toda la aritmética está
# verificada contra sus cifras en
# `tests/test_costos_grupos_resumen_porcentual.py`.

@router.get("/fully-loaded/")
async def fully_loaded(mes: int | None = None, temporada: str | None = None,
                       periodo: str = "full", escenario_id: str | None = None,
                       meses: str | None = None,
                       db=Depends(get_db), _=Depends(get_current_user)):
    """El cuadro de descuentos: dólares, porcentajes, techo y estado.

    ⚠️ Vista **derivada**: no acepta entradas y no guarda nada.

    ⚠️ Y lleva la advertencia del §5 pegada a la respuesta, no suelta en un
    comentario: **estos porcentajes sirven para leer el P&L y fijar techos de
    comisión, NO para fijar pisos de precio.** El overhead va asignado por
    revenue a todos los departamentos; el piso sale del otro camino, donde se
    absorbe por habitación-noche.
    """
    par = await cg.cargar_parametros(db, HOTEL_ID)
    comp = await cg.cargar_composicion(db, HOTEL_ID)
    sc, base, es_base = await _base_elegida(db, escenario_id)
    if sc is None:
        raise HTTPException(409, "el escenario base no existe")

    todos = await cg.hechos_mensuales(db, sc, HOTEL_ID)
    sel, etiqueta = _filtrar(todos, sc, periodo, mes, temporada,
                             meses_pedidos(meses))
    # ⚠️ Una combinación vacía se DICE. Un cero que en realidad es «no hay
    # meses» se lee como «no hay costo», que es lo contrario.
    if not sel:
        return {"vacio": True,
                "motivo": f"no hay meses en «{etiqueta}»",
                "escenario": f"{sc.type}/{sc.year}/{sc.version}"}

    r = cg.resumen_fully_loaded(sel, comp, par, CONCEPTOS)

    return {
        "vacio": False,
        "escenario": f"{sc.type}/{sc.year}/{sc.version}",
        "escenario_id": sc.id,
        "base_configurada": (f"{base.type}/{base.year}/{base.version}"
                             if base else ""),
        "es_base": es_base,
        "seleccion": {
            "etiqueta": etiqueta,
            "periodo": periodo,
            "meses": sorted(m.mes for m in sel),
            "temporadas": sorted({m.temporada for m in sel if m.temporada}),
        },
        "totales": {
            "revenue": _n(r.revenue),
            "costo_departamental": _n(r.costo_departamental),
            "overhead": _n(r.overhead),
            "fee": _n(r.fee),
            "utilidad": _n(r.utilidad),
            "margen_ponderado": str(r.margen_ponderado),
            "overhead_pct": str(r.overhead_pct),
        },
        "filas": [
            {
                "concepto": f.concepto,
                "revenue": _n(f.revenue),
                "costo_departamento": _n(f.costo_departamento),
                "costo_departamento_pct": str(f.costo_departamento_pct),
                "overhead": _n(f.overhead),
                "overhead_pct": str(f.overhead_pct),
                "fee": _n(f.fee),
                "fee_pct": str(f.fee_pct),
                "costo_fully_loaded_pct": str(f.costo_fully_loaded_pct),
                "utilidad": _n(f.utilidad),
                "margen_actual": str(f.margen_actual),
                "descuento_maximo": str(f.descuento_maximo),
                "cubre": f.cubre,
                "estado": f.estado,
            }
            for f in r.filas
        ],
        # Los que hay que mirar primero, sin tener que recorrer la tabla.
        "pierden": r.pierden,
        "advertencia": (
            "Estos porcentajes sirven para leer el P&L y fijar techos de "
            "comisión, NO para fijar pisos de precio. El overhead va asignado "
            "por revenue a todos los departamentos; el piso de precio sale de "
            "Pisos por servicio, donde se absorbe por habitación-noche."),
    }
