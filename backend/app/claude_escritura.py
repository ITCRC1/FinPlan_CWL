"""Lo que Claude puede CAMBIAR en FinPlan: solo en versiones marcadas «editable desde Claude».

Owner, 2026-11-16: «he creado la versión Budget Draft1-PAN para que si él le pide
a Claude que cree el budget lo haga… sería hacer un nuevo modelo de negocio».

⚠️ **El candado está ACÁ y no en la conversación.** Cada herramienta abre la
versión con `_editable()`, que exige las cuatro cosas a la vez:
  1. que se nombre la versión EXPLÍCITAMENTE (sin «la que elija el sistema»);
  2. `scenarios.claude_puede_editar = true` (lo marca un admin, persona por versión);
  3. que no sea ACTUAL ni el Pre-Cierre;
  4. que no esté enllavada (`status = locked`).
Si Claude se equivoca de nombre y apunta al Working, la herramienta se niega:
no depende de que el modelo «se acuerde» de no tocarlo.

Ninguna herramienta recalcula sola: los cambios quedan escritos y el P&L se
actualiza con `recalcular`, igual que en la app (el botón Recalcular).
Cada llamada queda en `claude_consultas` con sus argumentos completos.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select

from app.db import get_session
from app.hotel_actual import HOTEL_ID, HOTEL_NAME

MESES = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
D = Decimal


def _dec(v) -> Decimal:
    return D(str(v)).quantize(D("0.0001"), rounding=ROUND_HALF_UP)


def _meses(args) -> list[int]:
    ms = args.get("meses") or list(range(1, 13))
    ms = sorted({int(m) for m in ms})
    if not ms or any(m < 1 or m > 12 for m in ms):
        raise ValueError("meses: lista de números de mes entre 1 y 12")
    return ms


async def _editable(s, args):
    from app.models.scenario import Scenario
    version = (args.get("version") or "").strip()
    if not version:
        raise ValueError("Para MODIFICAR hay que nombrar la versión exacta (p. ej. «Draft1-PAN»).")
    tipo = str(args.get("tipo") or "BUDGET").upper()
    esc = (await s.execute(select(Scenario).where(
        Scenario.hotel_id == HOTEL_ID, Scenario.year == int(args["anio"]), Scenario.type == tipo,
        Scenario.version == version))).scalars().first()
    if esc is None:
        raise ValueError(f"No existe {tipo} {args['anio']} «{version}».")
    if not getattr(esc, "claude_puede_editar", False):
        raise PermissionError(f"«{tipo} {esc.year} {version}» no está habilitada para que Claude la modifique. "
                              "Solo se pueden cambiar las versiones marcadas «editable desde Claude».")
    if esc.type == "ACTUAL" or getattr(esc, "es_precierre", False):
        raise PermissionError("Los reales y el Pre-Cierre no se modifican nunca desde Claude.")
    if esc.is_locked:
        raise PermissionError(f"«{version}» está enllavada.")
    return esc


def _cab(esc) -> dict:
    return {"hotel": HOTEL_NAME, "version": f"{esc.type} {esc.year} {esc.version}",
            "recordatorio": "Los cambios quedaron escritos; el P&L se actualiza con `recalcular`."}


# ── Planilla ─────────────────────────────────────────────────────────────────

def _match(p, c) -> bool:
    if c.get("depto") and not str(p.dept_code).startswith(str(c["depto"])):
        return False
    if c.get("codigo") and p.position_code != str(c["codigo"]):
        return False
    if c.get("puesto") and str(c["puesto"]).lower() not in (p.position_name or "").lower():
        return False
    if c.get("empleado") and str(c["empleado"]).lower() not in (p.employee_name or "").lower():
        return False
    return True


async def editar_fte(args, usuario):
    """FTE por mes de posiciones puntuales (0 = la posición no cuesta ese mes)."""
    from app.models.payroll_position import PayrollPosition
    cambios = args.get("cambios") or []
    if not cambios:
        raise ValueError("cambios: lista de {depto, codigo o puesto o empleado, meses, fte}")
    async with get_session() as s:
        esc = await _editable(s, args)
        pos = (await s.execute(select(PayrollPosition).where(PayrollPosition.scenario_id == esc.id))).scalars().all()
        hecho = []
        for c in cambios:
            fte = _dec(c["fte"])
            if fte < 0 or fte > 1:
                raise ValueError("fte va de 0 a 1 por posición (para más gente, más posiciones)")
            ms = _meses(c)
            if not any(c.get(k) for k in ("depto", "codigo", "puesto", "empleado")):
                raise ValueError("Cada cambio necesita al menos depto, codigo, puesto o empleado")
            tocadas = [p for p in pos if _match(p, c)]
            for p in tocadas:
                for m in ms:
                    setattr(p, f"fte_{MESES[m - 1]}", fte)
            hecho.append({"filtro": {k: c.get(k) for k in ("depto", "codigo", "puesto", "empleado") if c.get(k)},
                          "posiciones": len(tocadas), "meses": ms, "fte": float(fte),
                          "nombres": [f"{p.dept_code} {p.position_name} — {p.employee_name}" for p in tocadas][:30]})
        await s.commit()
        return {**_cab(esc), "cambios": hecho}


async def fte_masivo(args, usuario):
    """Pone un FTE a TODAS las posiciones (o las de ciertos deptos) salvo las que se exceptúan.

    Es la herramienta del «hotel cerrado»: todo en 0 salvo el equipo mínimo.
    """
    from app.models.payroll_position import PayrollPosition
    fte = _dec(args.get("fte", 0))
    if fte < 0 or fte > 1:
        raise ValueError("fte va de 0 a 1")
    ms = _meses(args)
    deptos = [str(d) for d in (args.get("deptos") or [])]
    excepto = args.get("excepto") or []
    async with get_session() as s:
        esc = await _editable(s, args)
        pos = (await s.execute(select(PayrollPosition).where(PayrollPosition.scenario_id == esc.id))).scalars().all()
        n, se_quedan = 0, []
        for p in pos:
            if deptos and not any(str(p.dept_code).startswith(d) for d in deptos):
                continue
            if any(_match(p, e) for e in excepto):
                se_quedan.append(f"{p.dept_code} {p.position_name} — {p.employee_name}")
                continue
            for m in ms:
                setattr(p, f"fte_{MESES[m - 1]}", fte)
            n += 1
        await s.commit()
        return {**_cab(esc), "posiciones_cambiadas": n, "fte": float(fte), "meses": ms,
                "exceptuadas_sin_cambio": se_quedan}


async def editar_salario(args, usuario):
    from app.models.payroll_position import PayrollPosition
    async with get_session() as s:
        esc = await _editable(s, args)
        pos = [p for p in (await s.execute(select(PayrollPosition).where(PayrollPosition.scenario_id == esc.id))).scalars().all()
               if _match(p, args)]
        if not pos:
            raise ValueError("Ninguna posición coincide con el filtro")
        antes = []
        for p in pos:
            antes.append({"posicion": f"{p.dept_code} {p.position_name} — {p.employee_name}",
                          "salario_antes": float(p.salary_amount or 0), "moneda": p.salary_currency})
            p.salary_amount = _dec(args["salario"])
            if args.get("moneda"):
                p.salary_currency = str(args["moneda"]).upper()
        await s.commit()
        return {**_cab(esc), "salario_nuevo": float(_dec(args["salario"])), "posiciones": antes}


# ── Opex, costos, ingresos ───────────────────────────────────────────────────

async def _rates(s, esc):
    from app.models.exchange_rate import ExchangeRate
    return (await s.execute(select(ExchangeRate).where(ExchangeRate.scenario_id == esc.id))).scalars().all()


def _poner_opex(e, m: int, monto: Decimal, rates):
    """Escribe el monto del mes. Una línea en colones guarda colones y deriva el
    dólar con el TC del escenario, igual que la importación (`opex_api._derivar_importadas`)."""
    from app.models.exchange_rate import get_tc_for_month
    if (e.currency or "USD") == "CRC":
        setattr(e, f"crc_{MESES[m - 1]}", monto)
        e.set_month(m, e.derivar_usd(m, get_tc_for_month(rates, m)) if rates else D(0))
    else:
        e.set_month(m, monto)


async def editar_opex(args, usuario):
    """Monto mensual de UNA línea de opex (depto × cuenta × detalle). Si no existe, la crea en USD."""
    from app.models.opex_entry import OpexEntry
    ms = _meses(args)
    monto = _dec(args["monto"])
    async with get_session() as s:
        esc = await _editable(s, args)
        q = select(OpexEntry).where(OpexEntry.scenario_id == esc.id, OpexEntry.dept_code == str(args["depto"]),
                                    OpexEntry.account_code == str(args["cuenta"]))
        if args.get("detalle"):
            q = q.where(OpexEntry.detail_code == str(args["detalle"]))
        filas = (await s.execute(q)).scalars().all()
        creada = False
        if not filas:
            e = OpexEntry(scenario_id=esc.id, hotel_id=esc.hotel_id, dept_code=str(args["depto"]),
                          account_code=str(args["cuenta"]), account_name=str(args.get("nombre") or ""),
                          detail_code=str(args.get("detalle") or ""), detail_desc=str(args.get("descripcion") or ""),
                          currency="USD")
            s.add(e)
            filas, creada = [e], True
        if len(filas) > 1:
            raise ValueError(f"Hay {len(filas)} sub-líneas de {args['depto']}-{args['cuenta']}: indicá «detalle» "
                             f"({', '.join(sorted({f.detail_code or '(vacío)' for f in filas}))}).")
        rates = await _rates(s, esc)
        e = filas[0]
        for m in ms:
            _poner_opex(e, m, monto, rates)
        await s.commit()
        return {**_cab(esc), "linea": f"{e.dept_code}-{e.account_code} {e.detail_code}", "moneda": e.currency or "USD",
                "monto_por_mes": float(monto), "meses": ms, "creada": creada}


async def escalar_opex(args, usuario):
    """Multiplica el opex (y opcionalmente costos) por un factor: 0 = eliminar, 0.2 = dejar el 20 %."""
    from app.models.opex_entry import OpexEntry
    factor = _dec(args["factor"])
    if factor < 0 or factor > 5:
        raise ValueError("factor entre 0 y 5")
    ms = _meses(args)
    deptos = [str(d) for d in (args.get("deptos") or [])]
    cuentas = [str(c) for c in (args.get("cuentas") or [])]
    excepto = [str(c) for c in (args.get("excepto_cuentas") or [])]
    async with get_session() as s:
        esc = await _editable(s, args)
        rates = await _rates(s, esc)
        filas = (await s.execute(select(OpexEntry).where(OpexEntry.scenario_id == esc.id))).scalars().all()
        n, antes, despues = 0, D(0), D(0)
        for e in filas:
            if deptos and not any(str(e.dept_code).startswith(d) for d in deptos):
                continue
            if cuentas and not any(str(e.account_code).startswith(c) for c in cuentas):
                continue
            if any(str(e.account_code).startswith(c) for c in excepto):
                continue
            for m in ms:
                usd = D(str(getattr(e, MESES[m - 1]) or 0))
                antes += usd
                if (e.currency or "USD") == "CRC":
                    crc = D(str(getattr(e, f"crc_{MESES[m - 1]}") or 0))
                    _poner_opex(e, m, _dec(crc * factor), rates)
                else:
                    e.set_month(m, _dec(usd * factor))
                despues += D(str(getattr(e, MESES[m - 1]) or 0))
            n += 1
        await s.commit()
        return {**_cab(esc), "lineas": n, "factor": float(factor), "meses": ms,
                "opex_antes_usd": float(round(antes, 2)), "opex_despues_usd": float(round(despues, 2))}


async def editar_costo(args, usuario):
    """Una línea de costo de ventas (clase 5): monto MANUAL por mes o % de una línea de ingreso (DRIVER)."""
    from app.models.cost_entry import CostEntry
    ms = _meses(args)
    async with get_session() as s:
        esc = await _editable(s, args)
        e = (await s.execute(select(CostEntry).where(CostEntry.scenario_id == esc.id,
                                                     CostEntry.dept_code == str(args["depto"]),
                                                     CostEntry.account_code == str(args["cuenta"])))).scalars().first()
        if e is None:
            raise ValueError(f"No hay línea de costo {args['depto']}-{args['cuenta']} en esta versión")
        if args.get("pct") is not None:
            e.calc_mode, e.driver_type = "DRIVER", "REVENUE_LINE"
            e.driver_pct_or_rate = _dec(args["pct"])
            if args.get("linea_ingreso"):
                e.revenue_line_ref = str(args["linea_ingreso"]).upper()
            detalle = f"{float(e.driver_pct_or_rate):.2%} de {e.revenue_line_ref}"
        else:
            e.calc_mode, e.driver_type = "MANUAL", ""
            for m in ms:
                setattr(e, MESES[m - 1], _dec(args["monto"]))
            detalle = f"${float(_dec(args['monto'])):,.2f} por mes en {ms}"
        await s.commit()
        return {**_cab(esc), "linea": f"{e.dept_code}-{e.account_code}", "modo": e.calc_mode, "detalle": detalle}


async def editar_ingreso(args, usuario):
    """Monto mensual de una línea de ingreso (cuando la versión toma el ingreso escrito, `revenue_source=checkbook`)."""
    from app.models.revenue_entry import REVENUE_LINES, RevenueEntry
    linea = str(args["linea"]).upper()
    if linea not in REVENUE_LINES:
        raise ValueError(f"linea tiene que ser una de {', '.join(REVENUE_LINES)}")
    ms = _meses(args)
    async with get_session() as s:
        esc = await _editable(s, args)
        e = (await s.execute(select(RevenueEntry).where(RevenueEntry.scenario_id == esc.id,
                                                        RevenueEntry.line == linea))).scalars().first()
        if e is None:
            e = RevenueEntry(scenario_id=esc.id, hotel_id=esc.hotel_id, line=linea)
            s.add(e)
        for m in ms:
            setattr(e, MESES[m - 1], _dec(args["monto"]))
        fuente = getattr(esc, "revenue_source", "")
        await s.commit()
        return {**_cab(esc), "linea": linea, "monto_por_mes": float(_dec(args["monto"])), "meses": ms,
                "aviso": ("" if fuente == "checkbook" else
                          f"Esta versión calcula el ingreso por ocupación × tarifa (fuente «{fuente}»): este monto "
                          "no se usa hasta cambiar la fuente con `fuente_ingresos`.")}


async def fuente_ingresos(args, usuario):
    fuente = str(args["fuente"]).lower()
    if fuente not in ("drivers", "checkbook"):
        raise ValueError("fuente: «drivers» (ocupación × tarifa) o «checkbook» (montos escritos por línea)")
    async with get_session() as s:
        esc = await _editable(s, args)
        antes = esc.revenue_source
        esc.revenue_source = fuente
        await s.commit()
        return {**_cab(esc), "fuente_antes": antes, "fuente_ahora": fuente}


async def _tipos_hab(s, filtro: str):
    from app.models.room_type_config import RoomTypeConfig
    tipos = (await s.execute(select(RoomTypeConfig).where(RoomTypeConfig.hotel_id == HOTEL_ID))).scalars().all()
    f = (filtro or "todos").strip().lower()
    if f == "todos":
        return tipos
    return [t for t in tipos if f in (t.code or "").lower() or f in (t.name or "").lower()
            or f in (getattr(t, "short_name", "") or "").lower()]


async def editar_ocupacion(args, usuario):
    from app.models.occupancy_budget import OccupancyBudget
    pct = _dec(args["ocupacion"])
    if pct < 0 or pct > 1:
        raise ValueError("ocupacion es una fracción entre 0 y 1 (0.45 = 45 %)")
    ms = _meses(args)
    async with get_session() as s:
        esc = await _editable(s, args)
        tipos = await _tipos_hab(s, args.get("tipo_habitacion"))
        if not tipos:
            raise ValueError("Ningún tipo de habitación coincide")
        ids = {t.id for t in tipos}
        filas = (await s.execute(select(OccupancyBudget).where(OccupancyBudget.scenario_id == esc.id))).scalars().all()
        n = 0
        for o in filas:
            if o.room_type_id in ids and o.month in ms:
                o.occupancy_pct = pct
                n += 1
        await s.commit()
        return {**_cab(esc), "tipos": [t.name for t in tipos], "meses": ms, "ocupacion": float(pct), "filas": n,
                "aviso": "Las noches ocupadas se derivan al recalcular (ocupación × unidades × días)."}


async def editar_tarifa(args, usuario):
    from app.models.rate_card import RateCard
    ms = _meses(args)
    async with get_session() as s:
        esc = await _editable(s, args)
        tipos = await _tipos_hab(s, args.get("tipo_habitacion"))
        ids = {t.id for t in tipos}
        filas = (await s.execute(select(RateCard).where(RateCard.scenario_id == esc.id))).scalars().all()
        n = 0
        for r in filas:
            if r.room_type_id in ids and r.month in ms:
                if args.get("rack") is not None:
                    r.rack_rate = _dec(args["rack"])
                if args.get("neta") is not None:
                    r.net_rate = _dec(args["neta"])
                    r.net_rate_manual = True
                n += 1
        await s.commit()
        return {**_cab(esc), "tipos": [t.name for t in tipos], "meses": ms, "filas": n,
                "rack": args.get("rack"), "neta": args.get("neta")}


#: Recálculos en curso o terminados, por escenario. El recálculo completo puede
#: tardar minutos y claude.ai no espera tanto a una herramienta: se lanza en
#: segundo plano y se espera hasta `ESPERA_RECALCULO`; si no terminó, se contesta
#: «en curso» y `estado_recalculo` dice cuándo quedó.
_RECALCULOS: dict[str, dict] = {}
ESPERA_RECALCULO = 50


async def _correr_recalculo(scenario_id: str):
    import time as _t
    from app.engine.recalculate import recalculate_scenario
    reg = _RECALCULOS[scenario_id]
    try:
        async with get_session() as s:
            r = await recalculate_scenario(s, scenario_id)
        reg.update(estado="listo", fin=_t.time(),
                   resultado={k: v for k, v in (r or {}).items() if isinstance(v, (int, float, str))})
    except Exception as e:  # noqa: BLE001
        reg.update(estado="error", fin=_t.time(), error=f"{type(e).__name__}: {e}"[:500])


def _estado(scenario_id: str) -> dict:
    reg = _RECALCULOS.get(scenario_id)
    if not reg:
        return {"estado": "sin recálculo lanzado en esta sesión del servidor"}
    import time as _t
    fin = reg.get("fin") or _t.time()
    return {"estado": reg["estado"], "segundos": round(fin - reg["inicio"]),
            **({"resultado": reg["resultado"]} if reg.get("resultado") else {}),
            **({"error": reg["error"]} if reg.get("error") else {})}


async def recalcular(args, usuario):
    import asyncio
    import time as _t
    async with get_session() as s:
        esc = await _editable(s, args)
    actual = _RECALCULOS.get(esc.id)
    if actual and actual["estado"] == "en curso":
        return {**_cab(esc), "recordatorio": "Ya hay un recálculo en curso.", **_estado(esc.id)}
    _RECALCULOS[esc.id] = {"estado": "en curso", "inicio": _t.time(), "por": usuario.email}
    tarea = asyncio.create_task(_correr_recalculo(esc.id))
    try:
        await asyncio.wait_for(asyncio.shield(tarea), timeout=ESPERA_RECALCULO)
    except asyncio.TimeoutError:
        return {**_cab(esc), "recordatorio": ("El recálculo sigue en segundo plano. Consultá `estado_recalculo` "
                                              "en un minuto antes de leer el P&L."), **_estado(esc.id)}
    return {**_cab(esc), "recordatorio": "P&L recalculado.", **_estado(esc.id)}


async def estado_recalculo(args, usuario):
    async with get_session() as s:
        esc = await _editable(s, args)
        ultimo = getattr(esc, "last_recalc_at", None)
    return {**_cab(esc), **_estado(esc.id), "ultimo_recalculo_guardado": str(ultimo) if ultimo else None}


# ── Registro ─────────────────────────────────────────────────────────────────

_V = {"anio": {"type": "integer"}, "tipo": {"type": "string", "enum": ["BUDGET", "FORECAST"]},
      "version": {"type": "string", "description": "Nombre EXACTO de una versión habilitada para Claude, p. ej. Draft1-PAN"}}
_M = {"meses": {"type": "array", "items": {"type": "integer", "minimum": 1, "maximum": 12},
                "description": "Meses a cambiar (por defecto los 12)"}}
_F = {"depto": {"type": "string"}, "codigo": {"type": "string", "description": "Código de posición, p. ej. 0186-01"},
      "puesto": {"type": "string", "description": "Parte del nombre del puesto"},
      "empleado": {"type": "string", "description": "Parte del nombre del empleado"}}

ESCRITURA: dict[str, dict] = {
    "editar_fte": {"fn": editar_fte, "titulo": "Cambiar FTE de posiciones",
                   "descripcion": "FTE por mes (0 a 1) de posiciones puntuales. 0 = la posición no cuesta ese mes.",
                   "props": {**_V, "cambios": {"type": "array", "items": {"type": "object", "properties": {
                       **_F, **_M, "fte": {"type": "number", "minimum": 0, "maximum": 1}}, "required": ["fte"]}}},
                   "req": ["anio", "version", "cambios"]},
    "fte_masivo": {"fn": fte_masivo, "titulo": "FTE a todo el hotel salvo excepciones",
                   "descripcion": ("Pone el mismo FTE (p. ej. 0) a todas las posiciones —o a las de ciertos deptos— "
                                   "salvo las de «excepto». Sirve para «cerrar el hotel dejando solo el equipo mínimo»."),
                   "props": {**_V, **_M, "fte": {"type": "number", "minimum": 0, "maximum": 1},
                             "deptos": {"type": "array", "items": {"type": "string"}},
                             "excepto": {"type": "array", "items": {"type": "object", "properties": _F}}},
                   "req": ["anio", "version", "fte"]},
    "editar_salario": {"fn": editar_salario, "titulo": "Cambiar salario de posiciones",
                       "descripcion": "Salario mensual completo (FTE 1) de las posiciones que coinciden con el filtro.",
                       "props": {**_V, **_F, "salario": {"type": "number"}, "moneda": {"type": "string", "enum": ["CRC", "USD"]}},
                       "req": ["anio", "version", "salario"]},
    "editar_opex": {"fn": editar_opex, "titulo": "Cambiar una línea de opex",
                    "descripcion": "Monto mensual de una línea de opex (depto × cuenta × detalle). Si no existe, la crea en USD.",
                    "props": {**_V, **_M, "depto": {"type": "string"}, "cuenta": {"type": "string"},
                              "detalle": {"type": "string"}, "monto": {"type": "number"},
                              "nombre": {"type": "string"}, "descripcion": {"type": "string"}},
                    "req": ["anio", "version", "depto", "cuenta", "monto"]},
    "escalar_opex": {"fn": escalar_opex, "titulo": "Escalar el opex",
                     "descripcion": ("Multiplica el opex por un factor (0 = eliminar, 0.2 = dejar el 20 %), por meses, "
                                     "deptos y/o cuentas, con cuentas exceptuadas."),
                     "props": {**_V, **_M, "factor": {"type": "number"},
                               "deptos": {"type": "array", "items": {"type": "string"}},
                               "cuentas": {"type": "array", "items": {"type": "string"}},
                               "excepto_cuentas": {"type": "array", "items": {"type": "string"}}},
                     "req": ["anio", "version", "factor"]},
    "editar_costo": {"fn": editar_costo, "titulo": "Cambiar una línea de costo de ventas",
                     "descripcion": "Costo clase 5: «pct» = % de una línea de ingreso (driver) o «monto» mensual manual.",
                     "props": {**_V, **_M, "depto": {"type": "string"}, "cuenta": {"type": "string"},
                               "pct": {"type": "number"}, "linea_ingreso": {"type": "string"}, "monto": {"type": "number"}},
                     "req": ["anio", "version", "depto", "cuenta"]},
    "editar_ingreso": {"fn": editar_ingreso, "titulo": "Cambiar el ingreso de una línea",
                       "descripcion": ("Monto mensual de una línea de ingreso (ROOMS, FOOD, BEVERAGE, ACTIVITIES, TRANSPORT, "
                                       "SPA, RETAIL, SUSTAINABILITY…). Se usa cuando la versión toma el ingreso escrito."),
                       "props": {**_V, **_M, "linea": {"type": "string"}, "monto": {"type": "number"}},
                       "req": ["anio", "version", "linea", "monto"]},
    "fuente_ingresos": {"fn": fuente_ingresos, "titulo": "Elegir de dónde sale el ingreso",
                        "descripcion": "«drivers» = ocupación × tarifa calculado por el motor; «checkbook» = montos escritos.",
                        "props": {**_V, "fuente": {"type": "string", "enum": ["drivers", "checkbook"]}},
                        "req": ["anio", "version", "fuente"]},
    "editar_ocupacion": {"fn": editar_ocupacion, "titulo": "Cambiar la ocupación",
                         "descripcion": "Ocupación (fracción 0-1) por mes y tipo de habitación («todos» o parte del nombre/código).",
                         "props": {**_V, **_M, "tipo_habitacion": {"type": "string"}, "ocupacion": {"type": "number"}},
                         "req": ["anio", "version", "ocupacion"]},
    "editar_tarifa": {"fn": editar_tarifa, "titulo": "Cambiar la tarifa",
                      "descripcion": "Tarifa rack y/o neta por noche, por mes y tipo de habitación.",
                      "props": {**_V, **_M, "tipo_habitacion": {"type": "string"}, "rack": {"type": "number"},
                                "neta": {"type": "number"}},
                      "req": ["anio", "version"]},
    "estado_recalculo": {"fn": estado_recalculo, "titulo": "¿Terminó el recálculo?",
                         "descripcion": "Dice si el último recálculo de la versión terminó, cuánto tardó y si dio error.",
                         "props": {**_V}, "req": ["anio", "version"]},
    "recalcular": {"fn": recalcular, "titulo": "Recalcular el P&L de la versión",
                   "descripcion": ("Recalcula planilla, repartos y P&L de la versión, como el botón Recalcular de la app. "
                                   "Puede tardar: si no termina en ~50 s contesta «en curso»; seguí con `estado_recalculo`."),
                   "props": {**_V}, "req": ["anio", "version"]},
}
