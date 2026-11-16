"""Las herramientas que Claude (claude.ai) puede usar contra FinPlan. TODAS de solo lectura.

Owner, 2026-11-16: «mi jefe hace consultas directas a Claude desde su
computadora» · «él puede ver todo».

⚠️ **Ninguna calcula por su cuenta.** Cada una llama a la MISMA función que ya
alimenta los Excel en vivo (`/consolidado/*`) o el P&L de la app
(`pl_api._monthly_results`). Una segunda forma de calcular el mismo número
termina dando otro el día que una de las dos cambia, y la diferencia aparece en
una conversación con el dueño. Si una cifra de Claude no coincide con la
pantalla, el error está en la pantalla o en la consulta, no acá.

⚠️ **Las de este archivo no escriben.** Las que cambian datos están en
`claude_escritura.py`, con un candado propio: solo tocan versiones marcadas
«editable desde Claude» (owner, 2026-11-16: Draft1-PAN para un modelo de negocio
nuevo). El registro de cada llamada (`claude_consultas`) lo escribe el servidor.

Las respuestas se recortan (`LIMITE_DEFECTO`) para no mandarle a Claude miles de
filas de un saque: cada herramienta acepta filtros (depto, cuenta, meses) y dice
cuántas filas había y cuántas mandó.
"""
from __future__ import annotations

import calendar
import os
from decimal import Decimal
from typing import Any, Awaitable, Callable

from sqlalchemy import select

from app.db import get_session
from app.errores import ErrorApi
from app.hotel_actual import HOTEL_ID, HOTEL_NAME

LIMITE_DEFECTO = 300
TIPOS = ("ACTUAL", "BUDGET", "FORECAST")

# ── Esquemas reutilizados ────────────────────────────────────────────────────
_VERSION = {
    "anio": {"type": "integer", "description": "Año del escenario, p. ej. 2026"},
    "tipo": {"type": "string", "enum": list(TIPOS),
             "description": "ACTUAL (real), BUDGET (presupuesto) o FORECAST (pronóstico)"},
    "version": {"type": "string",
                "description": ("Nombre exacto de la versión (ver `versiones`). Vacío = la que usa FinPlan: "
                                "el ACTUAL real, el FORECAST marcado ★ Current, el BUDGET más reciente. "
                                "El Pre-Cierre del mes en curso es tipo ACTUAL versión «Pre-Cierre».")},
}
_MESES = {
    "mes_desde": {"type": "integer", "minimum": 1, "maximum": 12, "description": "Primer mes (1-12). Por defecto 1"},
    "mes_hasta": {"type": "integer", "minimum": 1, "maximum": 12, "description": "Último mes (1-12). Por defecto 12"},
}
_DEPTO = {"depto": {"type": "string", "description": "Código de departamento, p. ej. 0110 Rooms, 0120 F&B, 0180 Administración"}}
_LIMITE = {"limite": {"type": "integer", "minimum": 1, "maximum": 2000,
                      "description": f"Máximo de filas a devolver (por defecto {LIMITE_DEFECTO})"}}


def _num(v):
    if isinstance(v, Decimal):
        return float(v)
    return v


def _rango(args) -> tuple[int, int]:
    d = int(args.get("mes_desde") or 1)
    h = int(args.get("mes_hasta") or 12)
    if not (1 <= d <= h <= 12):
        raise ValueError("mes_desde y mes_hasta tienen que estar entre 1 y 12, y desde ≤ hasta")
    return d, h


def _tipo(args) -> str:
    t = str(args.get("tipo") or "").upper()
    if t not in TIPOS:
        raise ValueError(f"tipo tiene que ser uno de {', '.join(TIPOS)}")
    return t


def _version(args):
    v = (args.get("version") or "").strip()
    return v or None


def _recortar(filas: list, limite: int | None) -> dict:
    lim = int(limite or LIMITE_DEFECTO)
    return {"filas_totales": len(filas), "filas_enviadas": min(len(filas), lim),
            "aviso": ("" if len(filas) <= lim else
                      f"Se mandan {lim} de {len(filas)} filas: filtrá por depto/cuenta o subí «limite»."),
            "filas": filas[:lim]}


def _suma_meses(meses: list, d: int, h: int) -> float:
    return round(sum(float(x or 0) for x in meses[d - 1:h]), 2)


# ── Qué versiones ve el conector ─────────────────────────────────────────────
#
# El owner (2026-11-16): «solo necesita correr las versiones de históricos
# 2024-2026, Forecast 2026, Budget 2027 y Budget 2027 Draft1 Pan». Las otras
# (los Draft2..5, los Forecast viejos, el Pre-Cierre, el Budget 2026) existen en
# la base, pero desde Claude NO: con ellas a mano, una pregunta suelta como «el
# budget 2027» podía contestarse con un borrador abandonado sin que nadie lo note.
#
# Cada entrada es (tipo, año, versión). Versión `None` en FORECAST = «el que tiene
# el ★ vigente», que cambia de nombre cada mes. Se puede reemplazar sin tocar
# código con CLAUDE_VERSIONES="ACTUAL:2024:actual,FORECAST:2026:*,BUDGET:2027:Working".
_PERMITIDAS_DEFECTO = (
    ("ACTUAL", 2024, "actual"), ("ACTUAL", 2025, "actual"), ("ACTUAL", 2026, "actual"),
    ("FORECAST", 2026, None),
    ("BUDGET", 2027, "Working"), ("BUDGET", 2027, "Draft1-PAN"),
)


def _permitidas() -> tuple:
    crudo = (os.environ.get("CLAUDE_VERSIONES") or "").strip()
    if not crudo:
        return _PERMITIDAS_DEFECTO
    out = []
    for item in crudo.split(","):
        partes = [p.strip() for p in item.split(":")]
        if len(partes) == 3 and partes[1].isdigit():
            out.append((partes[0].upper(), int(partes[1]), None if partes[2] in ("", "*") else partes[2]))
    return tuple(out) or _PERMITIDAS_DEFECTO


def _permitida(esc) -> bool:
    if getattr(esc, "es_precierre", False):
        return False
    for tipo, anio, version in _permitidas():
        if esc.type != tipo or esc.year != anio:
            continue
        if version is None:
            if tipo != "FORECAST" or getattr(esc, "is_current_forecast", False):
                return True
        elif (esc.version or "").lower() == version.lower():
            return True
    return False


def _lista_permitidas() -> str:
    return "; ".join(f"{t} {a} {v or '(vigente)'}" for t, a, v in _permitidas())


def _anios_reales() -> set[int]:
    return {a for t, a, _ in _permitidas() if t == "ACTUAL"}


async def _escenario(session, anio: int, tipo: str, version):
    from app.api.consolidado_api import _escoger_escenario
    from app.models.scenario import Scenario
    escenarios = (await session.execute(
        select(Scenario).where(Scenario.hotel_id == HOTEL_ID, Scenario.year == anio,
                               Scenario.type == tipo).order_by(Scenario.created_at.desc()))).scalars().all()
    if not version:
        # Sin versión, FinPlan toma el BUDGET más nuevo — que hoy es un borrador.
        # Desde Claude, «el budget» es el de trabajo; el borrador hay que pedirlo
        # por su nombre.
        nombres = [v for t, a, v in _permitidas() if t == tipo and a == anio and v]
        if tipo == "BUDGET" and nombres:
            version = nombres[0]
    esc = _escoger_escenario(list(escenarios), tipo, version)
    if esc is None or not _permitida(esc):
        raise ValueError(f"{tipo} {anio}" + (f" «{version}»" if version else "")
                         + f" no está disponible desde Claude. Las versiones habilitadas son: {_lista_permitidas()}.")
    return esc


async def _fijar_version(args: dict) -> dict:
    """Resuelve y valida la versión ANTES de ir a un endpoint del consolidado, y
    le pasa el nombre exacto: así el endpoint no vuelve a elegir por su cuenta
    (sin versión elegiría el BUDGET más nuevo, que no es el permitido)."""
    async with get_session() as s:
        esc = await _escenario(s, int(args["anio"]), _tipo(args), _version(args))
        return {**args, "version": esc.version}


def _cab(esc) -> dict:
    return {"hotel": HOTEL_NAME, "anio": esc.year, "tipo": esc.type, "version": esc.version,
            "actuales_hasta_mes": int(getattr(esc, "actuals_through", 0) or 0)}


# ── Herramientas ─────────────────────────────────────────────────────────────

async def versiones(args, usuario):
    from app.models.scenario import Scenario
    async with get_session() as s:
        filas = (await s.execute(select(Scenario).where(Scenario.hotel_id == HOTEL_ID)
                                 .order_by(Scenario.year.desc(), Scenario.type, Scenario.created_at.desc()))).scalars().all()
        filas = [e for e in filas if _permitida(e)]
        out = [{"anio": e.year, "tipo": e.type, "version": e.version, "estado": e.status,
                "actuales_hasta_mes": int(getattr(e, "actuals_through", 0) or 0),
                "forecast_vigente": bool(getattr(e, "is_current_forecast", False)),
                "es_precierre": bool(getattr(e, "es_precierre", False)),
                "claude_puede_editar": bool(getattr(e, "claude_puede_editar", False))} for e in filas]
    return {"hotel": HOTEL_NAME, "versiones": out,
            "nota": ("Son las únicas versiones habilitadas para Claude. Sin versión se usa: el ACTUAL real, el "
                     "FORECAST vigente y, en BUDGET, la versión de trabajo («Working»); un borrador hay que "
                     "pedirlo por su nombre. Claude solo puede MODIFICAR las versiones con "
                     "claude_puede_editar=true.")}


async def pl(args, usuario):
    from app.api import pl_api
    from app.engine.recalculate import load_report_line_config
    d, h = _rango(args)
    tipo = _tipo(args)
    async with get_session() as s:
        esc = await _escenario(s, int(args["anio"]), tipo, _version(args))
        mensual = await pl_api._monthly_results(s, esc)
        config = await load_report_line_config(s)
        cab = _cab(esc)
    por_linea: dict[str, list[float]] = {}
    for m in mensual:
        for ln in m["lines"]:
            serie = por_linea.setdefault(ln.line_code, [0.0] * 12)
            serie[m["month"] - 1] += float(ln.amount_usd)
    secciones = {str(x).upper() for x in (args.get("secciones") or [])}
    lineas = []
    for c in config:
        serie = por_linea.get(c["line_code"])
        if serie is None or (secciones and str(c["section"]).upper() not in secciones):
            continue
        if not any(abs(v) > 0.005 for v in serie):
            continue
        fila = {"codigo": c["line_code"], "linea": c["line_name"], "seccion": c["section"],
                "total": _suma_meses(serie, d, h)}
        if args.get("por_mes"):
            fila["meses"] = {calendar.month_abbr[i]: round(serie[i - 1], 2) for i in range(d, h + 1)}
        lineas.append(fila)
    kpis = {}
    for m in mensual:
        if d <= m["month"] <= h:
            for k, v in (m.get("kpis") or {}).items():
                if isinstance(v, (int, float, Decimal)) and k in ("rooms_available", "rooms_occupied", "guests"):
                    kpis[k] = round(kpis.get(k, 0) + float(v), 2)
    if kpis.get("rooms_occupied"):
        rev = sum(f["total"] for f in lineas if f["codigo"] in ("REV_ROOMS", "REV_ROOMS_OTHER"))
        kpis["ocupacion"] = round(kpis["rooms_occupied"] / kpis["rooms_available"], 4) if kpis.get("rooms_available") else None
        kpis["adr"] = round(rev / kpis["rooms_occupied"], 2)
    return {**cab, "meses": f"{d}-{h}", "moneda": "USD",
            "signo": "ingresos y utilidades positivos; gastos positivos (se restan)",
            "indicadores": kpis, "lineas": lineas}


async def comparar(args, usuario):
    vs = args.get("versiones") or []
    if len(vs) < 2:
        raise ValueError("Pasá al menos dos versiones en «versiones» (cada una con anio, tipo y opcionalmente version).")
    d, h = _rango(args)
    codigos = set(args.get("lineas") or [])
    tablas, cabs = [], []
    for v in vs[:6]:
        r = await pl({**v, "mes_desde": d, "mes_hasta": h}, usuario)
        cabs.append(f'{r["tipo"]} {r["anio"]} {r["version"]}')
        tablas.append({f["codigo"]: f for f in r["lineas"]})
    orden = [c for c in tablas[0]] + [c for t in tablas[1:] for c in t if c not in tablas[0]]
    filas = []
    for c in dict.fromkeys(orden):
        if codigos and c not in codigos:
            continue
        nombre = next((t[c]["linea"] for t in tablas if c in t), c)
        vals = [t.get(c, {}).get("total", 0.0) for t in tablas]
        base = vals[0]
        filas.append({"codigo": c, "linea": nombre, "valores": dict(zip(cabs, vals)),
                      "variaciones_vs_primera": {cab: {"usd": round(v - base, 2),
                                                       "pct": (round((v - base) / abs(base), 4) if abs(base) > 0.5 else None)}
                                                 for cab, v in zip(cabs[1:], vals[1:])}})
    return {"hotel": HOTEL_NAME, "meses": f"{d}-{h}", "versiones": cabs, "lineas": filas}


async def indicadores(args, usuario):
    from app.api.consolidado_api import consolidado_estadisticas
    r = await consolidado_estadisticas(year=int(args["anio"]), tipo=_tipo(args), version=(await _fijar_version(args))["version"],
                                       quien=f"claude:{usuario.email}")
    return {"hotel": HOTEL_NAME, "version": r["escenario"]["version"], "anio": r["year"], "tipo": r["tipo"],
            "indicadores": r["indicadores"]}


async def habitaciones(args, usuario):
    from app.api.consolidado_planilla_api import consolidado_habitaciones
    r = await consolidado_habitaciones(year=int(args["anio"]), tipo=_tipo(args), version=(await _fijar_version(args))["version"],
                                       quien=f"claude:{usuario.email}")
    filas = r["filas"]
    nivel = (args.get("nivel") or "").strip()
    if nivel:
        filas = [f for f in filas if f["nivel"].lower() == nivel.lower()]
    if args.get("mes"):
        filas = [f for f in filas if f["mes"] == int(args["mes"])]
    return {"hotel": HOTEL_NAME, "version": r["escenario"]["version"],
            "nota": ("Niveles: Tipo (cada tipo de villa), Set (Standard 0110 / Villas 0115), Hotel (total) y "
                     "«Sin tipo» (meses que el escenario no abre por tipo)."), **_recortar(filas, args.get("limite"))}


async def gl(args, usuario):
    from app.api.consolidado_api import consolidado_gl
    d, h = _rango(args)
    r = await consolidado_gl(year=int(args["anio"]), tipo=_tipo(args), version=(await _fijar_version(args))["version"],
                             catalogo=False, quien=f"claude:{usuario.email}")
    filas = []
    dep, cta, cat = (args.get("depto") or "").strip(), (args.get("cuenta") or "").strip(), (args.get("categoria") or "").strip().upper()
    for c in r["cuentas"]:
        if dep and c["dept"] != dep:
            continue
        if cta and not str(c["cuenta"]).startswith(cta):
            continue
        if cat and str(c["categoria"]).upper() != cat:
            continue
        total = _suma_meses(c["meses"], d, h)
        if abs(total) < 0.005:
            continue
        fila = {"depto": c["dept"], "depto_nombre": c["dept_name"], "cuenta": c["cuenta"], "nombre": c["nombre"],
                "categoria": c["categoria"], "linea_pl": c["renglon"], "total": total}
        if args.get("por_mes"):
            fila["meses"] = {calendar.month_abbr[i]: round(c["meses"][i - 1], 2) for i in range(d, h + 1)}
        filas.append(fila)
    filas.sort(key=lambda f: -abs(f["total"]))
    return {"hotel": HOTEL_NAME, "version": r["escenario"]["version"], "anio": r["year"], "tipo": r["tipo"],
            "meses": f"{d}-{h}",
            "signo": "el INGRESO viene NEGATIVO (es crédito); gastos positivos. Suma de todo = −utilidad",
            "categorias": "REVENUE, COST_OF_SALES, PAYROLL, OPERATING_EXPENSES, ALLOCATIONS, BELOW_GOP",
            **_recortar(filas, args.get("limite"))}


async def posiciones(args, usuario):
    from app.api.consolidado_planilla_api import consolidado_posiciones
    r = await consolidado_posiciones(year=int(args["anio"]), tipo=_tipo(args), version=(await _fijar_version(args))["version"],
                                     quien=f"claude:{usuario.email}")
    filas = r["posiciones"]
    dep = (args.get("depto") or "").strip()
    if dep:
        filas = [f for f in filas if str(f["dept"]).startswith(dep)]
    return {"hotel": HOTEL_NAME, "version": r["escenario"]["version"],
            "nota": ("Una fila por posición: salario mensual en su moneda, FTE por mes (0 a 1), costo en USD por mes "
                     "(los 17 conceptos 6000-6030). El Actual y el Forecast traen la planilla del mayor por "
                     "departamento, sin FTE."), **_recortar(filas, args.get("limite"))}


async def planilla(args, usuario):
    from app.api.consolidado_planilla_api import consolidado_planilla
    r = await consolidado_planilla(year=int(args["anio"]), tipo=_tipo(args), version=(await _fijar_version(args))["version"],
                                   quien=f"claude:{usuario.email}")
    filas = r["lineas"]
    dep, cta = (args.get("depto") or "").strip(), (args.get("cuenta") or "").strip()
    if dep:
        filas = [f for f in filas if str(f["dept"]).startswith(dep) or f.get("dept_gl") == dep]
    if cta:
        filas = [f for f in filas if str(f["cuenta"]).startswith(cta)]
    return {"hotel": HOTEL_NAME, "version": r["escenario"]["version"],
            "nota": "Posición × concepto de planilla (6000 salario, 6020 CCSS, 6021 aguinaldo…) × mes, en USD.",
            **_recortar(filas, args.get("limite"))}


async def checkbook(args, usuario):
    from app.api.consolidado_planilla_api import consolidado_costos, consolidado_opex
    clase = (args.get("clase") or "opex").lower()
    fn = consolidado_costos if clase.startswith("cost") else consolidado_opex
    r = await fn(year=int(args["anio"]), tipo=_tipo(args), version=(await _fijar_version(args))["version"], quien=f"claude:{usuario.email}")
    filas = r["lineas"]
    dep, cta = (args.get("depto") or "").strip(), (args.get("cuenta") or "").strip()
    if dep:
        filas = [f for f in filas if str(f["dept"]).startswith(dep)]
    if cta:
        filas = [f for f in filas if str(f["cuenta"]).startswith(cta)]
    filas = sorted(filas, key=lambda f: -abs(f.get("anual") or 0))
    return {"hotel": HOTEL_NAME, "version": r["escenario"]["version"], "clase": "costos (5)" if fn is consolidado_costos else "opex (7)",
            **_recortar(filas, args.get("limite"))}


async def mayor(args, usuario):
    """Los asientos del mayor de Integrity del mes (Auditoría del mayor)."""
    from app.models.mayor_movimiento import MayorMovimiento as MM
    anio, mes = int(args["anio"]), int(args["mes"])
    if anio not in _anios_reales():
        raise ValueError(f"El mayor se consulta solo para los años con reales habilitados: "
                         f"{', '.join(str(a) for a in sorted(_anios_reales()))}.")
    async with get_session() as s:
        q = select(MM).where(MM.hotel_id == HOTEL_ID, MM.anio == anio, MM.mes == mes)
        if args.get("cuenta"):
            q = q.where(MM.cuenta.like(str(args["cuenta"]).strip() + "%"))
        if args.get("depto"):
            q = q.where(MM.seg2 == str(args["depto"]).strip())
        filas = (await s.execute(q)).scalars().all()
        texto = (args.get("texto") or "").strip().lower()
        out = []
        for f in filas:
            if texto and texto not in " ".join([f.descripcion or "", f.desc_asiento or "", f.referencia or ""]).lower():
                continue
            neto = float((f.debito or 0) - (f.credito or 0))
            tc = float(f.tc or 0)
            colones = (f.moneda_archivo or "COL") == "COL"
            out.append({"fecha": f.fecha, "asiento": f.asiento, "cuenta": f.cuenta, "depto": f.seg2,
                        "proveedor_o_descripcion": f.descripcion, "articulo_o_referencia": f.referencia,
                        "descripcion_asiento": f.desc_asiento, "origen": f.origen,
                        "monto_crc" if colones else "monto": round(neto, 2),
                        "monto_usd": round(neto / tc, 2) if colones and tc else None})
        archivo = filas[0].archivo if filas else ""
    if not filas:
        return {"hotel": HOTEL_NAME, "anio": anio, "mes": mes,
                "aviso": "Ese mes no tiene el mayor subido en Pre-Cierre → Auditoría del mayor."}
    out.sort(key=lambda x: -abs(x.get("monto_usd") or x.get("monto_crc") or x.get("monto") or 0))
    return {"hotel": HOTEL_NAME, "anio": anio, "mes": mes, "archivo": archivo,
            "nota": "débito − crédito: gasto positivo, ingreso negativo. Colones convertidos al TC de cada línea.",
            **_recortar(out, args.get("limite"))}


async def repartos(args, usuario):
    from app.api import consolidado_planilla_api as cp
    vista = (args.get("vista") or "repartos").lower()
    fn = {"repartos": cp.consolidado_repartos, "salarios": cp.consolidado_reparto_salarios,
          "centros": cp.consolidado_centros_costo}.get(vista)
    if fn is None:
        raise ValueError("vista tiene que ser «repartos», «salarios» o «centros»")
    r = await fn(year=int(args["anio"]), tipo=_tipo(args), version=(await _fijar_version(args))["version"], quien=f"claude:{usuario.email}")
    return {"hotel": HOTEL_NAME, "version": r["escenario"]["version"], "vista": vista,
            **_recortar(r["lineas"], args.get("limite"))}


# ── Registro ─────────────────────────────────────────────────────────────────

Herramienta = Callable[[dict, Any], Awaitable[dict]]

HERRAMIENTAS: dict[str, dict] = {
    "versiones": {
        "fn": versiones, "titulo": "Versiones disponibles",
        "descripcion": ("Lista las versiones del hotel que se pueden consultar desde Claude: los reales por año, "
                        "el Forecast vigente (y hasta qué mes trae reales) y los Budget habilitados. "
                        "Usala primero para saber qué nombres de versión existen."),
        "props": {}, "req": [],
    },
    "pl": {
        "fn": pl, "titulo": "Estado de resultados (P&L USALI)",
        "descripcion": ("El P&L del motor de FinPlan de una versión, para un rango de meses: ingresos por "
                        "departamento, gastos departamentales, utilidad departamental, overhead, GOP, gastos del "
                        "propietario, EBITDA y utilidad neta, más noches, huéspedes, ocupación y ADR. Es el mismo "
                        "número que la pantalla P&L y el reporte a dueños."),
        "props": {**_VERSION, **_MESES,
                  "por_mes": {"type": "boolean", "description": "true = también cada mes del rango"},
                  "secciones": {"type": "array", "items": {"type": "string"},
                                "description": "Filtrar por sección del P&L (opcional)"}},
        "req": ["anio", "tipo"],
    },
    "comparar": {
        "fn": comparar, "titulo": "Comparar versiones",
        "descripcion": ("Compara el P&L de 2 a 6 versiones lado a lado para el mismo rango de meses, con la "
                        "variación en USD y % contra la primera. Ej.: Pre-Cierre octubre contra Budget y contra "
                        "el Actual del año anterior."),
        "props": {"versiones": {"type": "array", "minItems": 2, "maxItems": 6,
                                "items": {"type": "object", "properties": _VERSION, "required": ["anio", "tipo"]}},
                  **_MESES,
                  "lineas": {"type": "array", "items": {"type": "string"},
                             "description": "Códigos de línea a mostrar (opcional), p. ej. TOTAL_REVENUES, TOTAL_GOP"}},
        "req": ["versiones"],
    },
    "indicadores": {
        "fn": indicadores, "titulo": "Indicadores de habitaciones",
        "descripcion": "Noches disponibles y ocupadas, huéspedes, ocupación, ADR y RevPAR por mes y del año.",
        "props": {**_VERSION}, "req": ["anio", "tipo"],
    },
    "habitaciones": {
        "fn": habitaciones, "titulo": "Habitaciones por tipo y por set",
        "descripcion": ("Por mes y por tipo de villa (y por set Standard/Villas y total hotel): disponibles, "
                        "ocupadas, pax, ocupación, ingreso de habitaciones, ADR y RevPAR."),
        "props": {**_VERSION, "nivel": {"type": "string", "enum": ["Tipo", "Set", "Hotel", "Sin tipo"]},
                  "mes": {"type": "integer", "minimum": 1, "maximum": 12}, **_LIMITE},
        "req": ["anio", "tipo"],
    },
    "gl": {
        "fn": gl, "titulo": "Cuentas del mayor por departamento (GL)",
        "descripcion": ("El GL de la versión: cada (departamento, cuenta) con su categoría y su línea del P&L, "
                        "total del rango de meses. Filtrable por depto, cuenta (prefijo) y categoría. Ordenado "
                        "por monto. Sirve para «¿en qué se gastó?» y «¿qué cuenta explica la diferencia?»."),
        "props": {**_VERSION, **_MESES, **_DEPTO,
                  "cuenta": {"type": "string", "description": "Prefijo de cuenta, p. ej. 7 (todo opex), 7395, 6000"},
                  "categoria": {"type": "string", "enum": ["REVENUE", "COST_OF_SALES", "PAYROLL",
                                                            "OPERATING_EXPENSES", "ALLOCATIONS", "BELOW_GOP"]},
                  "por_mes": {"type": "boolean"}, **_LIMITE},
        "req": ["anio", "tipo"],
    },
    "posiciones": {
        "fn": posiciones, "titulo": "Planilla por posición",
        "descripcion": ("Cada posición del checkbook de planilla: departamento, puesto, empleado, moneda, salario, "
                        "FTE por mes y costo mensual en USD. Incluye salarios por persona."),
        "props": {**_VERSION, **_DEPTO, **_LIMITE}, "req": ["anio", "tipo"],
    },
    "planilla": {
        "fn": planilla, "titulo": "Planilla por concepto",
        "descripcion": "Posición × concepto de planilla (salario, CCSS, aguinaldo, cafetería…) × mes, en USD.",
        "props": {**_VERSION, **_DEPTO,
                  "cuenta": {"type": "string", "description": "Concepto, p. ej. 6000, 6020"}, **_LIMITE},
        "req": ["anio", "tipo"],
    },
    "checkbook": {
        "fn": checkbook, "titulo": "Checkbook de opex o de costos",
        "descripcion": ("El checkbook con su máximo detalle: opex (clase 7, con la sub-línea de detalle) o costos "
                        "(clase 5, con su driver y su % sobre el ingreso), por mes."),
        "props": {**_VERSION, "clase": {"type": "string", "enum": ["opex", "costos"]}, **_DEPTO,
                  "cuenta": {"type": "string"}, **_LIMITE},
        "req": ["anio", "tipo"],
    },
    "mayor": {
        "fn": mayor, "titulo": "Asientos del mayor del mes",
        "descripcion": ("Los movimientos del mayor de Integrity de un mes (lo que se subió en Auditoría del "
                        "mayor): fecha, asiento, cuenta, proveedor, artículo y monto. Filtrable por cuenta, depto "
                        "y texto (proveedor o artículo). Ordenado por monto."),
        "props": {"anio": {"type": "integer"}, "mes": {"type": "integer", "minimum": 1, "maximum": 12},
                  "cuenta": {"type": "string", "description": "Prefijo de cuenta, p. ej. 7395 o 6000-0110"},
                  **_DEPTO, "texto": {"type": "string", "description": "Busca en proveedor, artículo o descripción"},
                  **_LIMITE},
        "req": ["anio", "mes"],
    },
    "repartos": {
        "fn": repartos, "titulo": "Repartos de cafetería, lavandería y salarios",
        "descripcion": ("vista=repartos: cada crédito y cargo de reparto; vista=centros: Cafetería y Lavandería "
                        "como centros de costo (acumula, reparte con la 4999, neto en 0); vista=salarios: el "
                        "reparto de salarios regla por regla (sale de un depto, entra a otro)."),
        "props": {**_VERSION, "vista": {"type": "string", "enum": ["repartos", "centros", "salarios"]}, **_LIMITE},
        "req": ["anio", "tipo"],
    },
}


# Las que CAMBIAN datos viven aparte (`claude_escritura`), con su candado propio:
# solo actúan sobre versiones marcadas «editable desde Claude».
from app.claude_escritura import ESCRITURA  # noqa: E402

TODAS: dict[str, dict] = {**HERRAMIENTAS, **ESCRITURA}


def lista_mcp() -> list[dict]:
    """La lista de herramientas en el formato de `tools/list` de MCP."""
    out = []
    for n, h in TODAS.items():
        escribe = n in ESCRITURA
        out.append({
            "name": n, "title": h["titulo"],
            "description": h["descripcion"] + (" SOLO en versiones habilitadas para Claude (p. ej. Draft1-PAN)."
                                               if escribe else ""),
            "inputSchema": {"type": "object", "properties": h["props"], "required": h["req"],
                            "additionalProperties": False},
            "annotations": {"title": h["titulo"], "readOnlyHint": not escribe, "destructiveHint": False,
                            "idempotentHint": not escribe or n != "recalcular", "openWorldHint": False},
        })
    return out


async def ejecutar(nombre: str, args: dict, usuario) -> dict:
    h = TODAS.get(nombre)
    if h is None:
        raise KeyError(nombre)
    try:
        return await h["fn"](args or {}, usuario)
    except ErrorApi as e:
        detalle = ", ".join(f"{k}={v}" for k, v in (getattr(e, "params", None) or {}).items())
        raise ValueError(f"{getattr(e, 'clave', 'error')}" + (f" ({detalle})" if detalle else "")) from e
