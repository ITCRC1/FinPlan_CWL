"""API del tab `Reports` → `Owners Q` (reporte mensual a SCP, POR/PAR).

Los seis bloques (PTD/YTD × Actual/Budget/PY) se arman con LA MISMA función,
cambiando únicamente el escenario y el rango de meses. No hay seis caminos
paralelos que se puedan desincronizar.

El reporte no recalcula nada: lee las `Línea P&L` que el P&L ya produjo
(`compute_pl_month`) y las acomoda en las 48 filas de SCP.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import select

from app.db import get_session
# ⚠️ La entidad por defecto sale de la INSTALACIÓN. Antes eran ocho
# literales «CWL»: al clonar, Amarena habría reportado y guardado su
# capacidad bajo la entidad de Corcovado — y el control de contaminación
# del Chequeo no lo veía, porque estas tablas se llavean por `entidad`
# y no por `hotel_id`.
from app.hotel_actual import HOTEL_ID
from app.errores import ErrorApi
from app.i18n import DEFAULT_LOCALE
from app.textos import Idioma, t
from app.engine import owners_q as motor
from app.engine.pl_engine import construir_resolvedor
from app.engine.recalculate import (
    actual_rows_for_month, checkbook_account_rows_for_month, compute_pl_month,
    load_active_account_mappings,
)
from app.models.owners_q import Capacidad, ReportLine, ReportLineMapping, ReportSnapshot
from app.models.scenario import Scenario
from app.models.scenario_stat import ScenarioStat

router = APIRouter(prefix="/reports/owners-q", tags=["owners-q"])

ZERO = Decimal("0")
REPORT_KEY = "owners_q"


# ─── Catálogo ─────────────────────────────────────────────────────────────────
async def _catalogo(session) -> tuple[list[dict], dict[str, str]]:
    filas = (await session.execute(
        select(ReportLine).where(ReportLine.report_key == REPORT_KEY)
        .order_by(ReportLine.row_no)
    )).scalars().all()
    if not filas:
        raise ErrorApi(503, "owners_q.sin_semilla")
    ruteo = {
        r.linea_pl: r.report_code
        for r in (await session.execute(
            select(ReportLineMapping).where(ReportLineMapping.report_key == REPORT_KEY)
        )).scalars().all()
    }
    filas_d = [{
        "row_no": f.row_no, "report_code": f.report_code, "label": f.label,
        "indent": f.indent, "line_type": f.line_type, "nature": f.nature,
        "lineas_pl": f.lineas_pl or [], "operandos": f.operandos or [],
        # Cómo se pinta en el archivo de SCP. Viaja con la fila para que el
        # exportador no tenga que saber nada de filas concretas.
        "estilo": f.estilo or {},
    } for f in filas]
    return filas_d, ruteo


# ─── Escenarios ───────────────────────────────────────────────────────────────
async def _escenario(session, hotel_id: str, anio: int, tipo: str,
                     escenario_id: str | None = None) -> Scenario | None:
    if escenario_id:
        sc = await session.get(Scenario, escenario_id)
        if sc is None:
            raise ErrorApi(404, "escenario.id_no_existe", escenario=escenario_id)
        return sc
    q = select(Scenario).where(
        Scenario.hotel_id == hotel_id, Scenario.year == anio, Scenario.type == tipo,
    ).order_by(Scenario.created_at.desc())
    return (await session.execute(q)).scalars().first()


# ─── Un bloque ────────────────────────────────────────────────────────────────
async def _lineas_pl(session, scenario: Scenario, meses: list[int],
                     periodo: str | None = None) -> dict[str, Decimal]:
    """{Línea P&L: monto} sumando los meses pedidos.

    Sale del MISMO `compute_pl_month` que alimenta el P&L de la app. Si el P&L
    y este reporte se separan algún día, no va a ser por acá.

    `periodo` computa con el mapeo VIGENTE EN ESE MES. Sin esto el versionado
    del §8 queda a medias: el snapshot protege lo enviado, pero el recálculo en
    vivo de un período viejo saldría con el mapeo de hoy — que es exactamente
    la historia reescrita que D9 podía causar.
    """
    total: dict[str, Decimal] = {}
    for m in meses:
        for ln in await compute_pl_month(session, scenario, m, periodo=periodo):
            v = Decimal(str(ln.amount_usd or 0))
            total[ln.line_code] = total.get(ln.line_code, ZERO) + v
    return total


async def _residuales(session, scenario: Scenario, meses: list[int],
                      periodo: str,
                      idioma: str = DEFAULT_LOCALE
                      ) -> tuple[Decimal, Decimal, list[dict]]:
    """Cuentas CON movimiento y SIN regla activa (§3.3).

    No se descartan: ingreso → fila 19, gasto → fila 36, y siempre al panel de
    excepciones. La naturaleza se deduce de la clase de cuenta (4xxx = ingreso).
    """
    mappings = await load_active_account_mappings(session, periodo=periodo)
    resolver = construir_resolvedor(mappings)

    ingreso = gasto = ZERO
    detalle: dict[tuple[str, str], Decimal] = {}
    for m in meses:
        filas = await actual_rows_for_month(session, scenario.id, m)
        if not filas:
            filas = await checkbook_account_rows_for_month(session, scenario.id, m)
        for row in filas:
            code = str(row.get("account_code") or "").strip()
            dept = str(row.get("dept_code") or "").strip()
            amt = Decimal(str(row.get("amount") or 0))
            if not code or not amt:
                continue
            regla, _como = resolver(dept, code)
            if regla:
                continue
            if code.startswith("4"):
                ingreso += amt
            else:
                gasto += amt
            k = (dept, code)
            detalle[k] = detalle.get(k, ZERO) + amt

    excepciones = [{
        "dept_code": d, "account_code": c, "monto": str(v),
        "fila_destino": "REV_MISC_TOTAL" if c.startswith("4") else "UND_MISC",
        "motivo": t(idioma, "owners_q.cuenta_sin_regla_activa"),
    } for (d, c), v in sorted(detalle.items())]
    return ingreso, gasto, excepciones


async def _noches(session, scenario: Scenario, meses: list[int]) -> Decimal:
    rows = (await session.execute(
        select(ScenarioStat).where(
            ScenarioStat.scenario_id == scenario.id, ScenarioStat.month.in_(meses))
    )).scalars().all()
    return sum((Decimal(str(r.rooms_occupied or 0)) for r in rows), ZERO)


async def _capacidades(session, entidad: str, anio: int) -> dict[int, int]:
    filas = (await session.execute(
        select(Capacidad).where(Capacidad.entidad == entidad, Capacidad.anio == anio)
    )).scalars().all()
    return {c.mes: c.habitaciones_disponibles for c in filas}


def _rooms_available(caps: dict[int, int], anio: int, meses: list[int]) -> int:
    """Σ (días del mes × capacidad DE ESE MES).

    No es `días del período × capacidad`: la capacidad puede cambiar dentro del
    acumulado —Villas y Residencias la mueven— y multiplicar por la del último
    mes le aplicaría ese número a todo el año hacia atrás.
    """
    faltan = [m for m in meses if m not in caps]
    if faltan:
        raise ErrorApi(503, "owners_q.sin_capacidad_meses",
                       anio=anio, meses=faltan)
    return sum(motor.dias_del_mes(anio, m) * caps[m] for m in meses)


async def _bloque(session, scenario: Scenario | None, meses: list[int],
                  periodo: str, idioma: str = DEFAULT_LOCALE
                  ) -> tuple[motor.DatosPeriodo | None, list[dict]]:
    if scenario is None:
        return None, []
    ingreso, gasto, exc = await _residuales(session, scenario, meses, periodo, idioma)
    return motor.DatosPeriodo(
        lineas=await _lineas_pl(session, scenario, meses, periodo),
        rooms_occupied=await _noches(session, scenario, meses),
        residual_revenue=ingreso,
        residual_expense=gasto,
    ), exc


# ─── Construcción ─────────────────────────────────────────────────────────────
#: Los tres bloques del reporte, en el orden de las columnas de SCP.
#: `budget` y `py` son las POSICIONES —columnas E-J y K-P—, no una obligación
#: sobre qué escenario va ahí. El default es lo que SCP espera; el owner puede
#: poner un Forecast Working, un Final, u otro mes.
BLOQUES = ("actual", "budget", "py")

#: Qué escenario y qué período toma cada bloque si nadie elige. Es exactamente
#: lo que SCP pide, y no cambia salvo que se pida otra cosa a propósito.
DEFAULTS = {"actual": ("ACTUAL", 0), "budget": ("BUDGET", 0), "py": ("ACTUAL", -1)}


def _etiqueta(sc: Scenario | None) -> str:
    if sc is None:
        return "—"
    base = f"{sc.type.title()} {sc.year}"
    v = (sc.version or "").strip()
    return base if v in ("", "actual", "from-xlsx") else f"{base} · {v}"


async def construir(
    session, *, entidad: str, anio: int, mes: int,
    periodo: str | None = None,
    escenarios: dict[str, str | None] | None = None,
    meses: dict[str, int | None] | None = None,
    periodos: dict[str, str | None] | None = None,
    mapping_version: str | None = None,
    convencion: str = "favorable",
    escenario_budget: str | None = None,   # compatibilidad con la firma vieja
    idioma: str = DEFAULT_LOCALE,
) -> dict:
    """Arma el reporte.

    `escenarios` elige qué va en cada bloque (`actual`/`budget`/`py`) y `meses`
    permite que un bloque corra sobre OTRO mes —comparar junio contra mayo, por
    ejemplo—. Los dos son opcionales: sin ellos sale exactamente lo que SCP
    espera, que es lo que se manda.
    """
    escenarios = dict(escenarios or {})
    if escenario_budget and not escenarios.get("budget"):
        escenarios["budget"] = escenario_budget
    meses = dict(meses or {})
    periodos = dict(periodos or {})

    # Un `mes` suelto es el período `Mnn`: la API vieja sigue andando.
    periodo_base = (periodo or f"M{mes:02d}")
    rango_base, acum_base, etiqueta_base, es_un_mes = motor.resolver_periodo(periodo_base)
    mes_cierre = rango_base[-1]

    filas, ruteo = await _catalogo(session)
    version_mapeo = mapping_version or f"{anio}-{mes_cierre:02d}"

    # ── Qué escenario y qué período le toca a cada bloque ────────────────────
    elegidos: dict[str, Scenario | None] = {}
    for b in BLOQUES:
        tipo, salto = DEFAULTS[b]
        elegidos[b] = await _escenario(
            session, entidad, anio + salto, tipo, escenarios.get(b))

    def periodo_de(b: str) -> str:
        """El período de un bloque: el suyo, o el del reporte."""
        propio = periodos.get(b)
        if propio:
            return propio
        m = meses.get(b)
        return f"M{m:02d}" if m else periodo_base

    def rangos_de(b: str) -> tuple[list[int], list[int], str]:
        r, a, et, _ = motor.resolver_periodo(periodo_de(b))
        return r, a, et

    def mes_de(b: str) -> int:
        return rangos_de(b)[0][-1]

    def anio_de(b: str) -> int:
        sc = elegidos[b]
        # El año lo manda el ESCENARIO, no la aritmética: si el owner pone el
        # Forecast 2026 en la columna de año anterior, el bloque corre sobre
        # 2026, no sobre `anio - 1`.
        return sc.year if sc is not None else anio + DEFAULTS[b][1]

    datasets: dict[str, motor.DatosPeriodo] = {}
    excepciones: list[dict] = []
    for b in BLOQUES:
        r_periodo, r_acum, _et = rangos_de(b)
        for tramo, rango in (("ptd", r_periodo), ("ytd", r_acum)):
            datos, exc = await _bloque(session, elegidos[b], rango, version_mapeo,
                                       idioma)
            if datos is not None:
                datasets[f"{tramo}_{b}"] = datos
            if tramo == "ptd":
                excepciones += [{**e, "bloque": b} for e in exc]

    # Una capacidad por bloque, sobre el año de SU escenario: el de año anterior
    # corre sobre 2025 (o 2024, que es bisiesto), no sobre el año en curso.
    caps_por_anio = {}
    for a in {anio} | {anio_de(b) for b in BLOQUES}:
        caps_por_anio[a] = await _capacidades(session, entidad, a)

    disponibles = {}
    for b in BLOQUES:
        a = anio_de(b)
        r_periodo, r_acum, _et = rangos_de(b)
        for tramo, rango in (("ptd", r_periodo), ("ytd", r_acum)):
            if f"{tramo}_{b}" in datasets:
                disponibles[f"{tramo}_{b}"] = _rooms_available(caps_por_anio[a], a, rango)

    caps = caps_por_anio.get(anio, {})
    estilos = {f["report_code"]: f.get("estilo") or {} for f in filas}
    resultado = motor.construir_reporte(
        filas, ruteo, datasets, disponibles=disponibles, convencion=convencion)

    # Verificaciones que viajan CON el reporte, no en un test aparte: si algo
    # no cuadra, el que mira la pantalla se entera.
    identidades = []
    for col in ("A", "E", "K", "R", "V", "AB"):
        identidades += motor.verificar_identidades(resultado, col)
    d1 = motor.verificar_d1(
        resultado,
        datasets.get("ptd_actual", motor.DatosPeriodo()).lineas.get("REV_ROOMS_OTHER", ZERO))

    return {
        "report_key": REPORT_KEY,
        "entidad": entidad, "anio": anio, "mes": mes_cierre,
        "periodo": periodo_base, "periodo_etiqueta": etiqueta_base,
        "es_un_mes": es_un_mes,
        "periodos_disponibles": motor.periodos_disponibles(),
        "convencion": convencion,
        "mapping_version": version_mapeo,
        "habitaciones_por_mes": {str(m): caps.get(m) for m in acum_base},
        "rooms_available_ptd": disponibles.get("ptd_actual"),
        "rooms_available_ytd": disponibles.get("ytd_actual"),
        "rooms_available_por_bloque": disponibles,
        # Qué quedó en cada posición, con su período. Es lo que la pantalla
        # muestra y lo que el Excel imprime en `Month Ending`: si alguien puso
        # un Forecast en la columna de Budget, el archivo lo dice.
        "bloques": {
            b: {
                "escenario_id": elegidos[b].id if elegidos[b] else None,
                "etiqueta": _etiqueta(elegidos[b]),
                "tipo": elegidos[b].type if elegidos[b] else None,
                "anio": anio_de(b), "mes": mes_de(b),
                "periodo": periodo_de(b), "periodo_etiqueta": rangos_de(b)[2],
                "por_defecto": (not escenarios.get(b) and not meses.get(b)
                                and not periodos.get(b)),
            } for b in BLOQUES
        },
        # Estándar = lo que SCP pide: UN mes, con los tres bloques por defecto.
        # Un trimestre o el año completo son otro reporte, y el archivo lo dice.
        "es_estandar": es_un_mes and all(
            not escenarios.get(b) and not meses.get(b) and not periodos.get(b)
            for b in BLOQUES),
        "escenarios": {b: (elegidos[b].id if elegidos[b] else None) for b in BLOQUES},
        "columnas": motor.COLUMNAS,
        "filas": [{**f, "estilo": estilos.get(f["report_code"], {}),
                   "celdas": {k: (str(v) if v is not None else None)
                              for k, v in f["celdas"].items()}} for f in resultado],
        "identidades_falladas": identidades,
        "verificacion_d1": d1,
        "excepciones": excepciones,
    }


# ─── Vista de año: 12 meses + Q1..Q4 + Full Year ──────────────────────────────
MESES_ABREV = ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN",
               "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"]

#: Cada período va en PAR: el período solo y el acumulado hasta ahí (pedido del
#: owner, 2026-08-17). Enero solo y enero acumulado dan lo mismo, y se emiten
#: los dos igual: la columna «acumulado» tiene que existir en los doce meses o
#: la lectura horizontal se rompe.
#:
#: ⚠️ El acumulado NO se calcula sumando las filas de los meses. Se suman los
#: INSUMOS y se recalcula: el ADR, el Occ% y el RevPar de un trimestre no son
#: el promedio de los ADR mensuales. Un promedio de promedios miente cuando los
#: meses tienen distinto peso, que es siempre.
def _periodos_anio() -> list[tuple[str, list[int], str, bool]]:
    """(clave, meses, etiqueta, es_acumulado)"""
    out: list[tuple[str, list[int], str, bool]] = []
    for m in range(1, 13):
        out.append((f"M{m:02d}", [m], MESES_ABREV[m - 1], False))
        out.append((f"M{m:02d}_ACUM", list(range(1, m + 1)),
                    f"ACUM {MESES_ABREV[m - 1]}", True))
    for q, (ini, fin) in enumerate([(1, 3), (4, 6), (7, 9), (10, 12)], start=1):
        out.append((f"Q{q}", list(range(ini, fin + 1)), f"Q{q}", False))
        out.append((f"Q{q}_ACUM", list(range(1, fin + 1)), f"ACUM Q{q}", True))
    out.append(("FY", list(range(1, 13)), "FULL YEAR", True))
    return out


PERIODOS_ANIO = _periodos_anio()
ETIQUETAS_PERIODO = {c: e for c, _m, e, _a in PERIODOS_ANIO}
ES_ACUMULADO = {c: a for c, _m, _e, a in PERIODOS_ANIO}


async def construir_anio(
    session, *, entidad: str, anio: int, escenario_budget: str | None = None,
    datasets: tuple[str, ...] = ("actual", "budget", "py"),
) -> dict:
    """Las 48 filas × 17 períodos, por dataset.

    Cada período se arma con la MISMA `valores_de_filas` que el reporte mensual.
    No se suman filas ya calculadas: se suman los INSUMOS y se recalcula, que es
    lo único que deja bien el ADR y la ocupación de un trimestre.
    """
    filas, ruteo = await _catalogo(session)
    escenarios = {
        "actual": await _escenario(session, entidad, anio, "ACTUAL"),
        "budget": await _escenario(session, entidad, anio, "BUDGET", escenario_budget),
        "py": await _escenario(session, entidad, anio - 1, "ACTUAL"),
    }

    # La capacidad y los días son POR AÑO: el bloque de año anterior corre sobre
    # su propio calendario. Usar los del año en curso le aplicaría los días de un
    # bisiesto —o una capacidad que cambió— al año equivocado.
    caps_por_anio = {
        a: await _capacidades(session, entidad, a) for a in (anio, anio - 1)
    }
    if not caps_por_anio[anio]:
        raise ErrorApi(503, "owners_q.sin_capacidad", entidad=entidad, anio=anio)

    salida: dict[str, dict] = {}
    for nombre in datasets:
        sc = escenarios.get(nombre)
        if sc is None:
            continue
        # El P&L de cada mes se pide UNA sola vez y se reusa en el mes, su
        # trimestre y el año. Sin esto serían 36 recálculos en vez de 12.
        por_mes: dict[int, dict[str, Decimal]] = {}
        noches: dict[int, Decimal] = {}
        for m in range(1, 13):
            # Cada mes con el mapeo vigente EN ESE MES, y el año anterior con el
            # suyo. Un año que cruza un cambio de mapeo —2026 cruza el de D9 en
            # julio— tiene que mostrar cada mes como se reportó, no los doce con
            # la regla de hoy.
            por_mes[m] = await _lineas_pl(session, sc, [m], f"{sc.year}-{m:02d}")
            noches[m] = await _noches(session, sc, [m])

        periodos: dict[str, dict] = {}
        for clave, meses, etiqueta, es_acum in PERIODOS_ANIO:
            lineas: dict[str, Decimal] = {}
            for m in meses:
                for k, v in por_mes[m].items():
                    lineas[k] = lineas.get(k, ZERO) + v
            datos = motor.DatosPeriodo(
                lineas=lineas,
                rooms_occupied=sum((noches[m] for m in meses), ZERO))
            # `rooms_available` = Σ (días del mes × capacidad DE ESE MES): la
            # capacidad puede cambiar dentro del trimestre.
            vals = motor.valores_de_filas(
                filas, ruteo, datos,
                _rooms_available(caps_por_anio[sc.year], sc.year, meses), 1)
            periodos[clave] = {
                "etiqueta": etiqueta,
                "acumulado": es_acum,
                "meses": meses,
                "valores": {k: (str(v) if v is not None else None)
                            for k, v in vals.items()},
            }
        salida[nombre] = {"escenario_id": sc.id, "periodos": periodos}

    return {
        "entidad": entidad, "anio": anio,
        "filas": [{"row_no": f["row_no"], "report_code": f["report_code"],
                   "label": f["label"], "indent": f["indent"],
                   "line_type": f["line_type"], "nature": f["nature"],
                   "estilo": f.get("estilo") or {}} for f in filas],
        "orden_periodos": [c for c, _m, _e, _a in PERIODOS_ANIO],
        "datasets": salida,
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.get("/anio/")
async def get_owners_q_anio(
    entidad: str = HOTEL_ID,
    anio: int = Query(...),
    escenario_budget: str | None = None,
):
    async with get_session() as session:
        return await construir_anio(session, entidad=entidad, anio=anio,
                                    escenario_budget=escenario_budget)


@router.get("/")
async def get_owners_q(
    entidad: str = HOTEL_ID,
    anio: int = Query(...),
    mes: int = Query(6, ge=1, le=12),
    periodo: str | None = None,
    escenario_actual: str | None = None,
    escenario_budget: str | None = None,
    escenario_py: str | None = None,
    periodo_actual: str | None = None,
    periodo_budget: str | None = None,
    periodo_py: str | None = None,
    mapping_version: str | None = None,
    convencion: str = Query("favorable", pattern="^(raw|favorable)$"),
    idioma: str = Idioma,
):
    """`periodo` es `M01`..`M12`, `Q1`..`Q4` o `FY`; `mes` sigue andando.

    Sin los `escenario_*`/`periodo_*` y con un mes simple sale exactamente lo
    que SCP espera.

    Con ellos, cada una de las tres posiciones puede traer otro escenario u otro
    mes: comparar contra el Forecast Working, contra el Final, o junio contra
    mayo. La respuesta dice en `es_estandar` si se salió de lo convencional.
    """
    async with get_session() as session:
        return await construir(
            session, entidad=entidad, anio=anio, mes=mes, periodo=periodo,
            escenarios={"actual": escenario_actual, "budget": escenario_budget,
                        "py": escenario_py},
            periodos={"actual": periodo_actual, "budget": periodo_budget,
                      "py": periodo_py},
            mapping_version=mapping_version, convencion=convencion, idioma=idioma)


@router.get("/periodos/")
async def periodos():
    """Los 17 que se pueden pedir: doce meses, cuatro trimestres y el año."""
    return motor.periodos_disponibles()


@router.get("/escenarios/")
async def escenarios_disponibles(entidad: str = HOTEL_ID):
    """Los escenarios que se pueden poner en cualquiera de las tres posiciones."""
    async with get_session() as session:
        filas = (await session.execute(
            select(Scenario).where(Scenario.hotel_id == entidad)
            .order_by(Scenario.year.desc(), Scenario.type, Scenario.version)
        )).scalars().all()
        return [{"id": s.id, "etiqueta": _etiqueta(s), "tipo": s.type,
                 "anio": s.year, "version": s.version,
                 "actuals_through": s.actuals_through} for s in filas]


@router.get("/excel/")
async def export_excel(
    entidad: str = HOTEL_ID,
    anio: int = Query(...),
    mes: int = Query(6, ge=1, le=12),
    periodo: str | None = None,
    escenario_actual: str | None = None,
    escenario_budget: str | None = None,
    escenario_py: str | None = None,
    periodo_actual: str | None = None,
    periodo_budget: str | None = None,
    periodo_py: str | None = None,
    mapping_version: str | None = None,
    convencion: str = Query("favorable", pattern="^(raw|favorable)$"),
    incluir_anio: bool = True,
    idioma: str = Idioma,
):
    """El archivo que se le manda a SCP + la vista de año.

    El nombre del archivo NO dice "Owners Q": el entregable se llama como el
    formato original.
    """
    from fastapi.responses import Response

    from app.export.owners_q_excel import export_owners_q, nombre_archivo

    async with get_session() as session:
        datos = await construir(
            session, entidad=entidad, anio=anio, mes=mes, periodo=periodo,
            escenarios={"actual": escenario_actual, "budget": escenario_budget,
                        "py": escenario_py},
            periodos={"actual": periodo_actual, "budget": periodo_budget,
                      "py": periodo_py},
            mapping_version=mapping_version, convencion=convencion, idioma=idioma)
        anio_datos = None
        if incluir_anio:
            anio_datos = await construir_anio(session, entidad=entidad, anio=anio,
                                              escenario_budget=escenario_budget)
    blob = export_owners_q(datos, anio_datos)
    return Response(
        content=blob,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition":
                 f'attachment; filename="{nombre_archivo(entidad, anio, datos)}"'},
    )


@router.get("/catalogo/")
async def get_catalogo():
    async with get_session() as session:
        filas, ruteo = await _catalogo(session)
        return {"filas": filas, "ruteo": ruteo}


@router.get("/cobertura/")
async def get_cobertura():
    """Gate A en vivo: ¿toda `Línea P&L` con reglas tiene su fila?"""
    from app.seed_owners_q import verificar_cobertura
    async with get_session() as session:
        return await verificar_cobertura(session)


@router.get("/capacidad/")
async def get_capacidad(entidad: str = HOTEL_ID, anio: int = Query(...)):
    async with get_session() as session:
        rows = (await session.execute(
            select(Capacidad).where(Capacidad.entidad == entidad, Capacidad.anio == anio)
            .order_by(Capacidad.mes)
        )).scalars().all()
        return [{"mes": r.mes, "habitaciones_disponibles": r.habitaciones_disponibles}
                for r in rows]


class CapacidadIn(BaseModel):
    mes: int
    habitaciones_disponibles: int


@router.put("/capacidad/")
async def put_capacidad(rows: list[CapacidadIn], entidad: str = HOTEL_ID, anio: int = Query(...)):
    async with get_session() as session:
        for r in rows:
            if r.habitaciones_disponibles <= 0:
                raise ErrorApi(400, "owners_q.habitaciones_positivas", mes=r.mes)
            obj = (await session.execute(
                select(Capacidad).where(Capacidad.entidad == entidad,
                                        Capacidad.anio == anio, Capacidad.mes == r.mes)
            )).scalars().first()
            if obj is None:
                session.add(Capacidad(id=str(uuid.uuid4()), entidad=entidad, anio=anio,
                                      mes=r.mes,
                                      habitaciones_disponibles=r.habitaciones_disponibles))
            else:
                obj.habitaciones_disponibles = r.habitaciones_disponibles
        await session.commit()
    return {"ok": True, "actualizados": len(rows)}


# ─── Snapshots — lo que se le mandó a SCP ─────────────────────────────────────
class SnapshotIn(BaseModel):
    entidad: str = HOTEL_ID
    anio: int
    mes: int
    convencion: str = "favorable"
    nota: str = ""


@router.get("/snapshots/")
async def list_snapshots(entidad: str = HOTEL_ID):
    async with get_session() as session:
        rows = (await session.execute(
            select(ReportSnapshot).where(ReportSnapshot.report_key == REPORT_KEY,
                                         ReportSnapshot.entidad == entidad)
            .order_by(ReportSnapshot.anio.desc(), ReportSnapshot.mes.desc(),
                      ReportSnapshot.version.desc())
        )).scalars().all()
        return [{
            "id": r.id, "anio": r.anio, "mes": r.mes, "version": r.version,
            "convencion": r.convencion, "mapping_version": r.mapping_version,
            "enviado_el": r.enviado_el.isoformat() if r.enviado_el else None,
            "nota": r.nota,
        } for r in rows]


@router.post("/snapshots/")
async def crear_snapshot(body: SnapshotIn):
    """Congela lo enviado. NUNCA sobreescribe: cada publicación es una versión."""
    async with get_session() as session:
        rep = await construir(session, entidad=body.entidad, anio=body.anio,
                              mes=body.mes, convencion=body.convencion)
        # Un snapshot es «lo que se le MANDÓ a SCP». A SCP se le manda UN mes con
        # los tres bloques por defecto: congelar un trimestre, el año, o una
        # comparación armada a mano guardaría como enviado algo que nunca se
        # envió — y el badge «recalculado» compararía contra una quimera.
        if not rep.get("es_estandar", False):
            raise ErrorApi(400, "owners_q.solo_reporte_estandar")
        previas = (await session.execute(
            select(ReportSnapshot).where(
                ReportSnapshot.report_key == REPORT_KEY,
                ReportSnapshot.entidad == body.entidad,
                ReportSnapshot.anio == body.anio, ReportSnapshot.mes == body.mes)
        )).scalars().all()
        version = max((p.version for p in previas), default=0) + 1

        snap = ReportSnapshot(
            id=str(uuid.uuid4()), report_key=REPORT_KEY, entidad=body.entidad,
            anio=body.anio, mes=body.mes, version=version,
            enviado_el=datetime.utcnow(), convencion=body.convencion,
            mapping_version=rep["mapping_version"],
            valores={f["report_code"]: f["celdas"] for f in rep["filas"]},
            nota=body.nota,
        )
        session.add(snap)
        await session.commit()
        return {"ok": True, "id": snap.id, "version": version}


@router.delete("/snapshots/{snapshot_id}/")
async def borrar_snapshot(snapshot_id: str):
    """Saca un snapshot creado por error.

    Un snapshot es inmutable a propósito —es la prueba de qué se le mandó a
    SCP— pero «inmutable» no puede significar «no se puede deshacer un error».
    Uno creado por equivocación miente sobre lo que se envió, y esa mentira es
    peor que el hueco: el badge «recalculado» empezaría a comparar el
    recálculo de hoy contra algo que nunca salió.

    Borrar NO es corregir: no hay editar. Se saca y se vuelve a publicar.
    """
    async with get_session() as session:
        snap = await session.get(ReportSnapshot, snapshot_id)
        if snap is None:
            raise ErrorApi(404, "owners_q.snapshot_no_existe")
        datos = {"anio": snap.anio, "mes": snap.mes, "version": snap.version}
        await session.delete(snap)
        await session.commit()
    return {"ok": True, "borrado": datos}


@router.get("/snapshots/{snapshot_id}/delta/")
async def delta_snapshot(snapshot_id: str):
    """Qué cambió entre lo enviado y lo que el motor devuelve HOY.

    El snapshot no se toca. Esto es lo que alimenta el badge "recalculado".
    """
    async with get_session() as session:
        snap = await session.get(ReportSnapshot, snapshot_id)
        if snap is None:
            raise ErrorApi(404, "owners_q.snapshot_no_existe")
        hoy = await construir(session, entidad=snap.entidad, anio=snap.anio,
                              mes=snap.mes, convencion=snap.convencion,
                              mapping_version=snap.mapping_version)
        actual = {f["report_code"]: f["celdas"] for f in hoy["filas"]}
        etiquetas = {f["report_code"]: f["label"] for f in hoy["filas"]}

        diffs = []
        for code, celdas in snap.valores.items():
            for col, viejo in (celdas or {}).items():
                nuevo = (actual.get(code) or {}).get(col)
                if (viejo is None) != (nuevo is None):
                    diffs.append({"report_code": code, "label": etiquetas.get(code, code),
                                  "columna": col, "enviado": viejo, "hoy": nuevo})
                elif viejo is not None and nuevo is not None:
                    if abs(Decimal(viejo) - Decimal(nuevo)) > Decimal("0.01"):
                        diffs.append({"report_code": code, "label": etiquetas.get(code, code),
                                      "columna": col, "enviado": viejo, "hoy": nuevo,
                                      "delta": str(Decimal(nuevo) - Decimal(viejo))})
        return {"snapshot_id": snapshot_id, "recalculado": bool(diffs), "diferencias": diffs}
