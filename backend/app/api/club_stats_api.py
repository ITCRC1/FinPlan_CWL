"""Conteo de socios del Club Madresal — el estadístico, no la plata.

El Club vende **acceso a las instalaciones** del hotel. Detrás hay un desarrollo
inmobiliario que NO es parte de este P&L; lo que sí entra es la cuota de acceso,
que se cobra en el departamento `260` y ya vive en `REV_CLUB`. Este conteo
explica esa cuota —cuántos socios pagan, cuántos están condicionados— pero no es
dinero: viaja con los KPIs de habitaciones, no por una línea del P&L.

Dos reglas que valen para todo este archivo:

**El total del año es DICIEMBRE, no la suma.** Son socios, no ingresos. Sumar
121 + 121 + 123… daría 1.500 socios donde hay 129.

**Se apaga desde Provisionamiento, no desde el código.** El owner avisó que esto
desaparece cuando el Club se opere por fuera del hotel — es de Amarena. Así que
`visible` sale de la matriz de habilitación del departamento `260`, no de un
`if hotel == "AMA"`. El día que salga, se desmarca la casilla y se apaga solo.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.textos import Idioma, t
from app.api._candado import candado
from app.api._apagados import dept_apagado
from app.api._ingreso_de_driver import persistir_ingreso_de_driver
from app.api._llega_al_pl import llega_al_pl, modo_ingresos
from app.db import get_db
from app.models.club_fee_budget import BASES, ClubFeeBudget
from app.models.club_membership_stat import ClubMembershipStat
from app.models.revenue_entry import REVENUE_LINE_ACCOUNT, REVENUE_LINE_LABELS
from app.models.scenario import Scenario

router = APIRouter(tags=["club-stats"])

DEPT_CLUB = "260"
CAMPOS = ("total", "condicionados", "pagando", "acuerdo_pago")
#: Los rótulos EN ESPAÑOL. Siguen acá porque son el respaldo si el catálogo de
#: textos no tuviera la clave; lo que sale por la API pasa por `_etiqueta()`,
#: que los resuelve en el idioma de quien pide.
ETIQUETAS = {
    "total": "Total Membresías",
    "condicionados": "Membresías Condicionados",
    "pagando": "Membresías Pagando",
    "acuerdo_pago": "Membresías En acuerdo de pago",
}


def _etiqueta(idioma: str, campo: str) -> str:
    return t(idioma, f"club.membresias.{campo}")


async def club_visible(db: AsyncSession, hotel_id: str) -> bool:
    """¿Esta propiedad usa el Club Madresal?

    Sale de la matriz de provisionamiento: si alguien desmarcó el departamento
    260, el tab se esconde. Una propiedad sin marcas lo tiene prendido, que es
    el default del sistema (se DESMARCA lo que no aplica).

    Sin dimensión a propósito: acá la pregunta no es «¿se le carga planilla?»
    sino «¿existe este negocio en esta propiedad?».
    """
    return not await dept_apagado(db, hotel_id, DEPT_CLUB)


async def membresias_por_mes(
    db: AsyncSession, scenario_id: str
) -> tuple[dict[str, list[int]], set[int]]:
    """Devuelve `({campo: [12 meses]}, meses_cargados)`.

    Viene TAMBIÉN qué meses tienen fila, porque para el total del año hay que
    distinguir «diciembre no se cargó» de «diciembre es cero». No es lo mismo, y
    confundirlos inventa socios (ver `cierre`).
    """
    out = {c: [0] * 12 for c in CAMPOS}
    cargados: set[int] = set()
    for s in (await db.execute(select(ClubMembershipStat).where(
            ClubMembershipStat.scenario_id == scenario_id))).scalars():
        if 1 <= (s.month or 0) <= 12:
            cargados.add(s.month)
            for c in CAMPOS:
                out[c][s.month - 1] = int(getattr(s, c) or 0)
    return out, cargados


def cierre(meses: list[int], cargados: set[int] | None = None) -> int:
    """El total del año: el saldo de DICIEMBRE, no la suma.

    **Cero es una respuesta válida.** En el dato real del owner los 35
    «Condicionados» se convierten en «Pagando» en septiembre, así que diciembre
    vale 0 — y su Excel muestra 0. Una versión anterior de esto devolvía «el
    último mes con dato» para cubrir el caso de un año a medio cargar, y con ese
    criterio la línea mostraba **35 condicionados que ya no existen**.

    La distinción correcta no es «cero o no cero», es **cargado o no cargado**:

      * diciembre tiene fila  → manda diciembre, aunque sea 0;
      * diciembre no tiene fila (año en curso) → el último mes cargado, que es
        el saldo más reciente que se conoce.
    """
    if cargados is None:                     # sin la info, se respeta diciembre
        return meses[11]
    if 12 in cargados:
        return meses[11]
    for m in sorted(cargados, reverse=True):
        return meses[m - 1]
    return 0


async def _escenario(db: AsyncSession, scenario_id: str) -> Scenario:
    s = await db.get(Scenario, scenario_id)
    if s is None:
        raise ErrorApi(404, "escenario.no_encontrado")
    return s


@router.get("/scenarios/{scenario_id}/club-membership/")
async def leer_membresias(scenario_id: str, db: AsyncSession = Depends(get_db),
                          idioma: str = Idioma):
    scenario = await _escenario(db, scenario_id)
    meses, cargados = await membresias_por_mes(db, scenario_id)
    return {
        "scenario_id": scenario_id,
        "year": scenario.year,
        "visible": await club_visible(db, scenario.hotel_id),
        "filas": [{"campo": c, "etiqueta": _etiqueta(idioma, c),
                   "meses": meses[c], "total_anio": cierre(meses[c], cargados)}
                  for c in CAMPOS],
        "meses_cargados": sorted(cargados),
        "nota_total": t(idioma, "club.total_es_el_saldo_de_diciembre"),
    }


class MesIn(BaseModel):
    month: int
    total: int = 0
    condicionados: int = 0
    pagando: int = 0
    acuerdo_pago: int = 0


class MembresiasIn(BaseModel):
    meses: list[MesIn]


@router.put("/scenarios/{scenario_id}/club-membership/")
async def guardar_membresias(
    scenario_id: str, body: MembresiasIn, db: AsyncSession = Depends(get_db),
):
    """Upsert por mes. Solo toca los meses que vienen en el cuerpo: mandar enero
    no borra febrero.

    **Y recalcula la cuota.** El conteo de socios es un factor de `socios ×
    precio`: si se corrige el conteo y el ingreso se queda con el de antes, la
    pantalla del driver muestra un número y el P&L otro, sin que nada avise. Es
    la misma falla callada de siempre, un paso más arriba.
    """
    await candado(db, scenario_id)
    scenario = await _escenario(db, scenario_id)

    existentes = {s.month: s for s in (await db.execute(select(ClubMembershipStat).where(
        ClubMembershipStat.scenario_id == scenario_id))).scalars()}
    for m in body.meses:
        if not 1 <= m.month <= 12:
            raise ErrorApi(422, "mes.fuera_de_rango")
        fila = existentes.get(m.month)
        if fila is None:
            fila = ClubMembershipStat(scenario_id=scenario_id, month=m.month)
            db.add(fila)
        for c in CAMPOS:
            setattr(fila, c, max(0, int(getattr(m, c) or 0)))
    await db.flush()

    # Solo si hay driver de cuota cargado. Sin él, `precio` vale 0 y volver a
    # empujar borraría un ingreso que quizá alguien digitó a mano.
    hay_driver = (await db.execute(select(ClubFeeBudget.id).where(
        ClubFeeBudget.scenario_id == scenario_id).limit(1))).first() is not None
    if hay_driver:
        filas, _ = await _driver_filas(db, scenario_id)
        await persistir_ingreso_de_driver(db, scenario, _montos_por_linea(filas))

    await db.commit()
    return await leer_membresias(scenario_id, db)


# ─────────────────────────────────────────────────────────────────────────────
# Los TRES ingresos del Club → tres líneas de ingreso, una por cuenta
# ─────────────────────────────────────────────────────────────────────────────
# La cuota tiene driver, misma forma que el Spa: un dato operativo que ya se
# lleva (allá el capture rate, acá el conteo de socios) × un precio que se
# presupuesta. Las otras dos se digitan — pero no son un «otros» anónimo: el
# catálogo las lleva con nombre y cuenta propia.
#
#   4500  Ingreso Madresal Club   ← socios(base) × precio
#   4501  Actividad fin de año    ← se digita
#   4502  Visitantes              ← se digita
#
# Las tres caen en REV_CLUB (`revenue_seed_from_lines` suma), así que partir la
# línea no mueve el total. Lo que gana es que el presupuesto quede en el mismo
# vocabulario que la contabilidad —tres cuentas, tres nombres— en vez de un
# «club» a secas que hay que desarmar a mano para compararlo.
#
# Hasta hace poco el checkbook NO TENÍA línea de Club, así que en el Budget 2027
# `REV_CLUB` daba cero — no por falta de carga, sino porque no había por dónde.
# Y hasta 2026-08-15 la línea existía pero solo la leía el modo `checkbook`:
# ver `_ingreso_de_driver.py`, que es por donde salen hoy las tres.

# Línea del checkbook → de dónde sale su monto en el driver. El orden es el de
# la cuenta, que es como el owner las lee.
LINEAS_CLUB = ("CLUB", "CLUB_ACTIVIDAD", "CLUB_VISITANTES")


async def _driver_filas(db: AsyncSession, scenario_id: str) -> tuple[list[dict], str]:
    """Las doce filas del driver, con las tres fuentes separadas y su total."""
    socios, _cargados = await membresias_por_mes(db, scenario_id)
    cuotas = {c.month: c for c in (await db.execute(select(ClubFeeBudget).where(
        ClubFeeBudget.scenario_id == scenario_id))).scalars()}
    base = next((c.base for c in cuotas.values() if c.base), "pagando")
    filas = []
    for m in range(1, 13):
        c = cuotas.get(m)
        precio = float(c.price_usd) if c else 0.0
        actividad = float(c.actividad_usd) if c else 0.0
        visitantes = float(c.visitantes_usd) if c else 0.0
        n = socios.get(base, [0] * 12)[m - 1]
        cuota = n * precio
        filas.append({
            "month": m, "socios": n, "precio": round(precio, 2),
            "cuotas": round(cuota, 2),
            "actividad": round(actividad, 2),
            "visitantes": round(visitantes, 2),
            "ingreso": round(cuota + actividad + visitantes, 2),
        })
    return filas, base


def _montos_por_linea(filas: list[dict]) -> dict[str, list[float]]:
    """Lo que va a cada línea del checkbook, en el orden de los meses."""
    return {
        "CLUB": [f["cuotas"] for f in filas],
        "CLUB_ACTIVIDAD": [f["actividad"] for f in filas],
        "CLUB_VISITANTES": [f["visitantes"] for f in filas],
    }


@router.get("/scenarios/{scenario_id}/club-fee/")
async def leer_cuota(scenario_id: str, db: AsyncSession = Depends(get_db),
                     idioma: str = Idioma):
    scenario = await _escenario(db, scenario_id)
    filas, base = await _driver_filas(db, scenario_id)
    return {
        "scenario_id": scenario_id, "year": scenario.year,
        "visible": await club_visible(db, scenario.hotel_id),
        # Ver `_llega_al_pl.py`: el escenario tiene que estar leyendo el
        # checkbook, si no se guarda y el P&L ni se entera.
        "modo_ingresos": modo_ingresos(scenario),
        "llega_al_pl": llega_al_pl(scenario),
        "base": base, "bases": list(BASES),
        "etiquetas_base": {b: _etiqueta(idioma, b) for b in BASES},
        "filas": filas,
        "total": round(sum(f["ingreso"] for f in filas), 2),
        "totales": {k: round(sum(v), 2) for k, v in _montos_por_linea(filas).items()},
        # Las tres líneas con su cuenta y su nombre, como las lleva el catálogo.
        # Van en la respuesta para que la pantalla no se invente los rótulos.
        "lineas": [
            {"linea": ln,
             "cuenta": REVENUE_LINE_ACCOUNT[ln][1],
             "dept": REVENUE_LINE_ACCOUNT[ln][0],
             "nombre": t(idioma, f"linea_ingreso.{ln}")}
            for ln in LINEAS_CLUB
        ],
        "nota": t(idioma, "club.tres_fuentes_una_linea"),
    }


class CuotaMesIn(BaseModel):
    month: int
    precio: float = 0
    actividad: float = 0
    visitantes: float = 0


class CuotaIn(BaseModel):
    base: str = "pagando"
    meses: list[CuotaMesIn]


@router.put("/scenarios/{scenario_id}/club-fee/")
async def guardar_cuota(
    scenario_id: str, body: CuotaIn, db: AsyncSession = Depends(get_db),
):
    """Guarda el driver y **deposita las tres fuentes en las líneas de ingreso**.

    El P&L no lee de acá: si el cálculo se quedara solo en esta tabla, la
    pantalla mostraría un ingreso que el estado de resultados no ve. Va por
    `persistir_ingreso_de_driver`, que lo deja en las dos fuentes —el checkbook
    y los montos del modo drivers— para que llegue esté como esté el escenario.
    Es el mismo camino que hace el Spa.
    """
    scenario = await candado(db, scenario_id)
    if body.base not in BASES:
        raise ErrorApi(422, "club.base_invalida", bases=", ".join(BASES))

    existentes = {c.month: c for c in (await db.execute(select(ClubFeeBudget).where(
        ClubFeeBudget.scenario_id == scenario_id))).scalars()}
    for m in body.meses:
        if not 1 <= m.month <= 12:
            raise ErrorApi(422, "mes.fuera_de_rango")
        fila = existentes.get(m.month)
        if fila is None:
            fila = ClubFeeBudget(scenario_id=scenario_id, hotel_id=scenario.hotel_id,
                                 month=m.month)
            db.add(fila)
        fila.price_usd = Decimal(str(max(0.0, m.precio)))
        fila.actividad_usd = Decimal(str(m.actividad))
        fila.visitantes_usd = Decimal(str(m.visitantes))
        fila.base = body.base
    # la base es del escenario: si cambió, todos los meses la siguen
    for fila in existentes.values():
        fila.base = body.base
    await db.flush()

    # Cada fuente a SU línea. Mandarlas todas a `CLUB` daría el mismo total en el
    # P&L, pero el reporte cuenta por cuenta mostraría un bulto en la 4500 donde
    # la contabilidad tiene tres renglones.
    filas, _ = await _driver_filas(db, scenario_id)
    await persistir_ingreso_de_driver(db, scenario, _montos_por_linea(filas))

    await db.commit()
    return await leer_cuota(scenario_id, db)
