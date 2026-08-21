# -*- coding: utf-8 -*-
"""Checkbook de gastos por departamento — bajar el Excel y subirlo lleno.

El formato y los dos motores (`app/checkbook/build.py`, `read.py`) llegaron como
paquete cerrado del owner el 18-ago-2026, validados contra su archivo original.
Este módulo es lo único que se adaptó: el paquete traía un router de ejemplo con
SQL contra tablas inventadas —`departamentos`, `gl_actual`,
`estadisticas_ocupacion`— y su propio comentario decía «ajustar el SQL al
esquema real de FinPlan».

Traducción de cada consulta:

    departamentos            → department_catalog  (dept_code, dept_name)
    account_mapping          → existe, pero por source_department / account_code
    gl_actual                → opex_entries        (formato ancho jan..dec)
    estadisticas_ocupacion   → scenario_stats      (rooms_available / occupied)

⚠️ **El «año de versión» se resuelve como ESCENARIO, no como año.** En FinPlan un
mismo año tiene Budget Working, Draft y Final: pedir «los montos de 2026» sin
decir de cuál es pedir una referencia que no es de nadie. Los tres años de
referencia salen de un escenario por año, elegido con la misma regla que usa
toda la app (`escenario_de_referencia`).

⚠️ **El detalle 800–810 SÍ existe en FinPlan.** La especificación dice que no y
recomienda crear una tabla nueva; se escribió para otro FinPlan. `opex_entries`
ya tiene `detail_code`/`detail_desc` y su llave única es
`(scenario_id, dept_code, account_code, detail_code)`, que es exactamente la
granularidad del archivo. Por eso la vuelta es de **fidelidad completa**: entra
el detalle, no un resumen por cuenta.
"""
from __future__ import annotations

import io
import os
import tempfile

from fastapi import APIRouter, Depends, File, Query, UploadFile
from app.importers.registro_dep import registro_de_subida
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errores import ErrorApi
from app.auth import get_current_user
from app.checkbook import build, leer, validar
from app.db import get_db
from app.models.department_catalog import DepartmentCatalog
from app.models.opex_entry import OpexEntry
from app.models.scenario import Scenario
from app.models.scenario_stat import ScenarioStat

router = APIRouter(prefix="/checkbook", tags=["checkbook"])

#: Cuántos años de referencia lleva el archivo. Lo fija el formato: el bloque de
#: cada cuenta reserva tres filas (`hdr+13..+15`).
# Dos, no tres. «No creo que ocupemos mas de 2 anios» (owner, 18-ago-2026).
N_ANIOS_REF = 2

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Qué TIPO de escenario representa a cada año de referencia.
#:
#: «Para 2027 solo ocupamos Forecast 2026 y Actual 2025» (owner, 18-ago-2026).
#: El año inmediatamente anterior todavía se está moviendo, así que el dato
#: bueno es el FORECAST; el de dos años atrás ya cerró, así que es el ACTUAL.
#: Si el tipo que toca no existe para ese año, se cae al otro antes que dejar la
#: referencia vacía.
TIPO_POR_DISTANCIA = {1: "FORECAST", 2: "ACTUAL"}

#: Dentro del mismo tipo: lo cerrado le gana a lo que se está moviendo.
PRIORIDAD_VERSION = ["final", "actual", "approved", "working", "draft"]


def _puntaje(s: Scenario, tipo_pref: str) -> tuple:
    v = (s.version or "").strip().lower()
    for i, clave in enumerate(PRIORIDAD_VERSION):
        if clave in v:
            orden = i
            break
    else:
        orden = len(PRIORIDAD_VERSION)
    # El tipo preferido primero; después la versión más cerrada.
    return (0 if s.type == tipo_pref else 1, orden, v)


async def _escenario_de_referencia(db: AsyncSession, hotel_id: str, anio: int,
                                   distancia: int = 1) -> Scenario | None:
    """El escenario que representa a ese año, o None si no hay ninguno."""
    filas = (await db.execute(select(Scenario).where(
        Scenario.hotel_id == hotel_id, Scenario.year == anio))).scalars().all()
    if not filas:
        return None
    tipo = TIPO_POR_DISTANCIA.get(distancia, "ACTUAL")
    return min(filas, key=lambda s: _puntaje(s, tipo))


async def _scenario_or_404(db: AsyncSession, scenario_id: str) -> Scenario:
    s = await db.get(Scenario, scenario_id)
    if not s:
        raise ErrorApi(404, "escenario.no_encontrado")
    return s


async def _depto_or_404(db: AsyncSession, dept_code: str) -> DepartmentCatalog:
    d = await db.get(DepartmentCatalog, dept_code)
    if not d:
        raise ErrorApi(404, "departamento.no_en_catalogo", depto=dept_code)
    return d


async def _montos(db: AsyncSession, scenario_id: str, dept_code: str) -> dict[str, list[float]]:
    """`{cuenta: [12 montos]}` del departamento en ese escenario.

    Suma los detalles: la referencia de un año anterior va por cuenta, no por
    línea de detalle — el 800 del año pasado no es el mismo 800 de este.
    """
    filas = (await db.execute(select(OpexEntry).where(
        OpexEntry.scenario_id == scenario_id,
        OpexEntry.dept_code == dept_code))).scalars().all()
    out: dict[str, list[float]] = {}
    for f in filas:
        serie = out.setdefault(str(f.account_code), [0.0] * 12)
        for i, m in enumerate(MESES):
            serie[i] += float(getattr(f, m) or 0)
    return out


async def _noches_ocupadas(db: AsyncSession, scenario_id: str) -> dict:
    """`{noches_ocupadas: [12]}` de un escenario, para el bloque del SUMMARY."""
    filas = (await db.execute(select(ScenarioStat).where(
        ScenarioStat.scenario_id == scenario_id))).scalars().all()
    serie = [0] * 12
    for f in filas:
        if 1 <= f.month <= 12:
            serie[f.month - 1] = int(float(f.rooms_occupied or 0))
    return {"noches_ocupadas": serie}


def _refs(pares: list[str]) -> dict[str, str]:
    """`["2026:<id>", "2025:<id>"]` → `{"2026": "<id>"}`.

    Va como lista de pares y no como un parametro por ano porque los anos
    dependen del escenario elegido: no se pueden declarar de antemano.
    """
    out: dict[str, str] = {}
    for par in pares or []:
        anio, _, sid = par.partition(":")
        if anio.strip().isdigit() and sid.strip():
            out[anio.strip()] = sid.strip()
    return out


def _nombre_archivo(cfg: dict) -> str:
    """El nombre del archivo sale de la fila 1 del tab Budget.

    «¿Será que el nombre del archivo puede adoptarse según la línea 1 del tab
    Budget?» (owner, 18-ago-2026). Esa fila es el título que ya identifica el
    archivo —departamento, año y para qué es— así que el nombre deja de ser una
    convención aparte que hay que recordar y pasa a ser lo mismo que se ve al
    abrirlo.

    Los `|` del título y lo que Windows no acepta en un nombre se cambian por
    guiones; el resto queda igual.
    """
    titulo = (f"{cfg['departamento'].upper()}   |   PRESUPUESTO {cfg['anio_version']}"
              f"   |   CHECKBOOK DE GASTOS")
    limpio = titulo
    for malo in r'\\/:*?"<>|':
        limpio = limpio.replace(malo, "-")
    limpio = " ".join(limpio.split())          # espacios de sobra fuera
    return f"{limpio}.xlsx"


async def _lineas_actuales(db: AsyncSession, scenario_id: str, dept_code: str,
                           detalles: int, det_ini: int = 800
                           ) -> tuple[dict[str, dict[str, dict]], list[dict]]:
    """`{cuenta: {detalle: {descripcion, montos}}}` y qué no entró.

    Es lo que hace que el archivo sea una IDA Y VUELTA y no un formulario en
    blanco.

    ⚠️ **Se mapea por POSICIÓN, no por código.** Los códigos de detalle de
    FinPlan y los del archivo son listas distintas para la misma idea: medido en
    producción (Budget 2027 Final, 417 cuentas), FinPlan usa `''`, `001`…`011`
    y el formato del owner usa `800`…`810`. Buscar por igualdad no habría
    coincidido con NINGUNA línea —y 73 de ellas ni siquiera tienen código—: el
    archivo habría salido en blanco y se habría visto perfectamente normal.

    Así que la línea n-ésima de una cuenta va a la ranura n-ésima. Es lo que el
    campo significa: «Detalle» es un renglón dentro de la cuenta, no una llave
    con sentido propio.

    Devuelve además las cuentas cuyas líneas NO entraron. Hoy ninguna las supera
    —el máximo medido son 11, justo las que trae el formato— pero un archivo que
    pierde renglones en silencio es exactamente lo que no puede pasar.
    """
    filas = (await db.execute(select(OpexEntry).where(
        OpexEntry.scenario_id == scenario_id,
        OpexEntry.dept_code == dept_code)
        .order_by(OpexEntry.account_code, OpexEntry.detail_code))).scalars().all()

    por_cuenta: dict[str, list] = {}
    for f in filas:
        por_cuenta.setdefault(str(f.account_code), []).append(f)

    out: dict[str, dict[str, dict]] = {}
    desbordes: list[dict] = []
    for cuenta, lineas in por_cuenta.items():
        if len(lineas) > detalles:
            desbordes.append({"cuenta": cuenta, "lineas": len(lineas), "ranuras": detalles})
        for j, f in enumerate(lineas[:detalles]):
            out.setdefault(cuenta, {})[str(det_ini + j)] = {
                "descripcion": f.detail_desc or "",
                "montos": [float(getattr(f, m) or 0) for m in MESES],
            }
    return out, desbordes


async def _armar_config(db: AsyncSession, scenario: Scenario, dept_code: str,
                        detalles: int, elegidos: dict[str, str] | None = None) -> dict:
    depto = await _depto_or_404(db, dept_code)

    # ── Las cuentas: las que el departamento YA tiene en este escenario ──────
    #
    # No se sacan del Account Mapping. El mapping dice a qué línea del P&L va
    # una cuenta —no qué cuentas usa un departamento—, y ofrecer las 200 del
    # catálogo daría un archivo de 3.600 filas donde el 90% son ceros. Si el
    # departamento está vacío, se cae al mapping como semilla.
    propias = await _montos(db, scenario.id, dept_code)
    nombres = {str(f.account_code): (f.account_name or "")
               for f in (await db.execute(select(OpexEntry).where(
                   OpexEntry.scenario_id == scenario.id,
                   OpexEntry.dept_code == dept_code))).scalars().all()}
    cuentas = [{"cuenta": int(c), "descripcion": nombres.get(c) or f"Cuenta {c}"}
               for c in sorted(propias, key=lambda x: int(x))]
    if not cuentas:
        raise ErrorApi(
            422, "checkbook.depto_sin_cuentas", depto=dept_code,
            escenario=f"{scenario.type} {scenario.year} {scenario.version or ''}")

    # ── Referencias: tres años atrás, un escenario por año ───────────────────
    referencias: dict[str, dict[str, list[float]]] = {}
    usados: dict[str, str] = {}
    ids: dict[str, str] = {}
    opciones: dict[str, list] = {}
    est_ref: dict[str, dict] = {}
    etiquetas: dict[str, str] = {}
    for n in range(1, N_ANIOS_REF + 1):
        anio = scenario.year - n
        # Si vino elegido a mano, manda ese. La regla (Forecast el anterior,
        # Actual el previo) es un default razonable, no una imposicion: el owner
        # puede querer comparar contra el Budget Final de ese ano, o contra un
        # Draft. «Necesito que estos escenarios den la oportunidad de cambiarlas
        # si yo quisiera» (owner, 18-ago-2026).
        pedido = (elegidos or {}).get(str(anio))
        ref = None
        if pedido:
            ref = await db.get(Scenario, pedido)
            if ref and ref.year != anio:
                raise ErrorApi(422, "checkbook.referencia_de_otro_ano",
                               anio=anio, anio_ref=ref.year)
        if not ref:
            ref = await _escenario_de_referencia(db, scenario.hotel_id, anio, n)
        if not ref:
            continue
        montos = await _montos(db, ref.id, dept_code)
        # Solo las cuentas que el archivo lleva: una referencia de una cuenta
        # que no está en el archivo no tiene dónde escribirse.
        referencias[str(anio)] = {c: montos[c] for c in montos
                                  if any(int(c) == x["cuenta"] for x in cuentas)}
        usados[str(anio)] = f"{ref.type} {ref.year} {ref.version or ''}".strip()
        # Como se rotula esa columna en el SUMMARY: «Forecast 2026», no
        # «TOTAL 2026» — un mismo anio tiene Working, Draft y Final.
        etiquetas[str(anio)] = (f"{ref.type.capitalize()} {anio}"
                                + (f" {ref.version}" if ref.version and
                                   ref.version.lower() not in ("actual", "from-xlsx") else ""))
        est_ref[str(anio)] = await _noches_ocupadas(db, ref.id)
        ids[str(anio)] = ref.id
        opciones[str(anio)] = [
            {"id": x.id,
             "label": f"{x.type} {x.year}" + (f" · {x.version}" if x.version else "")}
            for x in sorted(
                (await db.execute(select(Scenario).where(
                    Scenario.hotel_id == scenario.hotel_id,
                    Scenario.year == anio))).scalars().all(),
                key=lambda x: (x.type, x.version or ""))]

    # ── Estadísticas de ocupación del año de versión ─────────────────────────
    stats = (await db.execute(select(ScenarioStat).where(
        ScenarioStat.scenario_id == scenario.id))).scalars().all()
    estadisticas: dict = {}
    if stats:
        disp, ocup = [0] * 12, [0] * 12
        for s in stats:
            if 1 <= s.month <= 12:
                disp[s.month - 1] = int(float(s.rooms_available or 0))
                ocup[s.month - 1] = int(float(s.rooms_occupied or 0))
        estadisticas = {"noches_disponibles": disp, "noches_ocupadas": ocup}

    lineas, desbordes = await _lineas_actuales(db, scenario.id, dept_code, detalles)

    cfg = {
        "departamento": f"{depto.dept_name} ({dept_code})",
        "codigo_departamento": dept_code,
        "anio_version": scenario.year,
        "detalles_por_cuenta": detalles,
        "detalle_inicial": 800,
        "incluir_leyenda": True,
        # ⚠️ SIN proteger. «Las hojas deben estar desprotegidas excepto las
        # editables, y que todo se pueda mover; ahorita todo esta bloqueado»
        # (owner, 18-ago-2026).
        #
        # La proteccion existia para repartir el archivo sin que una formula se
        # destruya al pegar. Pero en la practica bloqueaba el uso: no se podia
        # recorrer la hoja, ni copiar un total, ni pegar un rango. Un archivo
        # que se protege tanto que no se puede llenar no protege nada.
        #
        # Las formulas siguen siendo formulas y las celdas de captura siguen
        # marcadas en azul: quien lo llena sabe donde escribir. Si algun dia hay
        # que repartirlo a mucha gente, se vuelve a prender desde aca.
        "proteger": False,
        "estadisticas": estadisticas,
        "referencias": referencias,
        # Noches ocupadas de los años de referencia: el SUMMARY las muestra
        # arriba para poder sacar el costo por habitación ocupada.
        "estadisticas_ref": est_ref,
        "etiquetas_ref": etiquetas,
        # ⚠️ Lo que el departamento YA tiene cargado, línea por línea. Sin esto
        # el archivo salía en blanco y bajarlo era perder lo cargado: había que
        # volver a teclear lo que FinPlan ya sabe, y las descripciones de
        # detalle del owner (columna F) desaparecían en cada regeneración.
        "lineas": lineas,
        "cuentas": cuentas,
    }
    validar(cfg)
    return cfg, usados, desbordes, ids, opciones


@router.get("/{scenario_id}/departamentos/")
async def departamentos(scenario_id: str, db: AsyncSession = Depends(get_db),
                        _=Depends(get_current_user)):
    """Los departamentos que TIENEN gasto en este escenario, con su conteo.

    No se ofrece el catálogo entero: un departamento sin cuentas no puede
    generar checkbook —el archivo saldría sin una sola fila que llenar— y
    ofrecerlo es mandar a alguien a un callejón sin salida. Se listan los que
    sirven, con cuántas cuentas trae cada uno para que la elección sea
    informada.
    """
    await _scenario_or_404(db, scenario_id)
    filas = (await db.execute(select(OpexEntry).where(
        OpexEntry.scenario_id == scenario_id))).scalars().all()
    cuentas: dict[str, set] = {}
    lineas: dict[str, int] = {}
    for f in filas:
        d = (f.dept_code or "").strip()
        if not d:
            continue
        cuentas.setdefault(d, set()).add(str(f.account_code))
        lineas[d] = lineas.get(d, 0) + 1

    cat = {c.dept_code: c.dept_name for c in
           (await db.execute(select(DepartmentCatalog))).scalars().all()}
    return {"departamentos": [
        {"dept_code": d, "dept_name": cat.get(d, ""), "cuentas": len(c),
         "lineas": lineas.get(d, 0)}
        for d, c in sorted(cuentas.items())]}


@router.get("/{scenario_id}/{dept_code}/preview/")
async def preview(scenario_id: str, dept_code: str,
                  detalles: int = Query(11, ge=1, le=30),
                  ref: list[str] = Query(default_factory=list),
                  db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """El config que se usaría, sin generar el archivo. Para ver qué va a salir."""
    scenario = await _scenario_or_404(db, scenario_id)
    cfg, usados, desbordes, ids, opciones = await _armar_config(
        db, scenario, dept_code, detalles, _refs(ref))
    return {
        "departamento": cfg["departamento"],
        "anio_version": cfg["anio_version"],
        "cuentas": len(cfg["cuentas"]),
        "detalles_por_cuenta": cfg["detalles_por_cuenta"],
        "filas_de_captura": len(cfg["cuentas"]) * cfg["detalles_por_cuenta"],
        "con_estadisticas": bool(cfg["estadisticas"]),
        # De qué escenario salió cada año de referencia. Sin esto, «TOTAL 2026»
        # en el archivo no dice si es el Final o el Working de 2026.
        # Cada ano con su escenario elegido y TODAS las opciones de ese ano,
        # para poder cambiarlo desde la pantalla.
        "referencias": {a: {"escenario": usados.get(a, ""),
                            "escenario_id": ids.get(a, ""),
                            "cuentas": len(m),
                            "opciones": opciones.get(a, [])}
                        for a, m in cfg["referencias"].items()},
        # Cuentas cuyas líneas NO entran en las ranuras del archivo. Vacío hoy
        # —el máximo medido son 11— pero perder renglones en silencio no.
        "desbordes": desbordes,
        "cuentas_detalle": cfg["cuentas"],
    }


@router.get("/{scenario_id}/{dept_code}/excel.xlsx")
async def exportar(scenario_id: str, dept_code: str,
                   detalles: int = Query(11, ge=1, le=30),
                   ref: list[str] = Query(default_factory=list),
                   db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Genera el checkbook del departamento, precargado con sus referencias."""
    scenario = await _scenario_or_404(db, scenario_id)
    cfg, _usados, _desb, _ids, _op = await _armar_config(
        db, scenario, dept_code, detalles, _refs(ref))

    # `build` escribe a disco (es el motor original, y no se toca). Se le da un
    # temporal y se devuelve el contenido en memoria.
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    tmp.close()
    try:
        build(cfg, tmp.name, force=True)
        with open(tmp.name, "rb") as fh:
            contenido = fh.read()
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    nombre = _nombre_archivo(cfg)
    return StreamingResponse(io.BytesIO(contenido), media_type=XLSX,
                             headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


# ─── La vuelta: subir el archivo lleno ───────────────────────────────────────

def _cargar(data: bytes) -> dict:
    """`leer()` trabaja sobre un archivo en disco — es el motor original y no se
    toca. Se le da un temporal."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    try:
        tmp.write(data)
        tmp.close()
        return leer(tmp.name)
    except ErrorApi:
        raise
    except Exception as exc:
        raise ErrorApi(422, "checkbook.no_se_pudo_leer",
                       detalle=f"{type(exc).__name__}: {exc}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@router.post("/{scenario_id}/{dept_code}/importar/", dependencies=[Depends(registro_de_subida)])
async def importar(scenario_id: str, dept_code: str,
                   archivo: UploadFile = File(...),
                   dry_run: bool = Query(False),
                   db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    """Sube el checkbook lleno. Con `dry_run` solo dice que haria.

    ⚠️ **Se mapea por POSICION, invirtiendo exactamente lo que hizo la bajada.**
    `_lineas_actuales` manda la linea n-esima de una cuenta a la ranura n-esima
    (`800 + n`) porque los codigos de detalle de FinPlan (`''`, `001`…`011`) y
    los del formato del owner (`800`…`810`) son listas distintas para la misma
    idea. Si aca se buscara por codigo, no coincidiria NINGUNA linea: se crearian
    once lineas nuevas por cuenta y las viejas quedarian con su monto viejo. El
    total del departamento se DUPLICARIA, y el archivo se veria perfectamente
    normal.

    Por eso el orden de la consulta —`account_code, detail_code`— tiene que ser
    **el mismo** que el de la bajada. Esta escrito en los dos lados a proposito;
    `tests/test_checkbook_ida_y_vuelta.py` falla si se separan.

    ⚠️ **Las lineas en COLONES se convierten de vuelta.** El archivo muestra
    dolares, pero en una linea marcada CRC el dato maestro son los colones y el
    dolar se DERIVA con el TC del mes. Escribir el dolar directo sobrevive hasta
    el proximo recalculo y despues se revierte solo, sin avisar. Asi que el
    dolar tecleado se pasa a colones al TC de ese mes y se vuelve a derivar.

    ⚠️ **Una linea que vuelve vacia se pone en CERO, no se borra.** Borrarla
    correria las posiciones de las que siguen, y la proxima bajada pondria los
    montos en ranuras distintas. La respuesta dice cuantas fueron: vaciar sin
    contarlo es como se pierde plata sin que nadie lo note.
    """
    from decimal import Decimal

    from app.models.exchange_rate import ExchangeRate, get_tc_for_month

    def tc_de(rates, mes):
        """El TC del mes, o None si no hay ninguno.

        ⚠️ `get_tc_for_month` LANZA `ValueError` cuando la lista viene vacía —no
        devuelve 0—, así que preguntarle en un `if` reventaba con un 500 justo
        en el caso que este endpoint quiere contestar con un 422 explicado.
        Lo encontró `test_una_linea_en_colones_SIN_tipo_de_cambio_se_rechaza`."""
        try:
            return get_tc_for_month(rates, mes) or None
        except ValueError:
            return None

    scenario = await _scenario_or_404(db, scenario_id)
    await _depto_or_404(db, dept_code)
    datos = _cargar(await archivo.read())

    # ── Que el archivo sea de ACA ────────────────────────────────────────────
    #
    # Subir el archivo de Habitaciones dentro de A&B reescribiria el
    # departamento equivocado con montos que no son suyos, y el total general
    # podria hasta quedar parecido. Es el error mas caro que se puede cometer en
    # esta pantalla, y el archivo trae con que detectarlo.
    del_archivo = str(datos.get("codigo_departamento") or "").strip()
    if del_archivo and del_archivo != dept_code:
        raise ErrorApi(422, "checkbook.otro_departamento",
                       archivo=del_archivo, elegido=dept_code)
    if datos.get("anio_version") and int(datos["anio_version"]) != scenario.year:
        raise ErrorApi(422, "checkbook.otro_anio",
                       archivo=datos["anio_version"], escenario=scenario.year)

    # ── Que las formulas sigan enteras ───────────────────────────────────────
    #
    # `leer()` compara el GRAN TOTAL de la fila 9 contra la suma de las lineas.
    # Si no cuadra, alguien pego encima de una formula: cargar la mitad buena
    # seria peor que no cargar nada.
    if not datos.get("cuadra", True):
        raise ErrorApi(422, "checkbook.no_cuadra",
                       calculado=f"{datos['gran_total']:,.2f}",
                       enhoja=f"{datos['gran_total_en_hoja']:,.2f}")

    # ── Lo que el escenario tiene hoy, en el MISMO orden que la bajada ───────
    filas = (await db.execute(select(OpexEntry).where(
        OpexEntry.scenario_id == scenario_id,
        OpexEntry.dept_code == dept_code)
        .order_by(OpexEntry.account_code, OpexEntry.detail_code))).scalars().all()
    por_cuenta: dict[str, list[OpexEntry]] = {}
    for f in filas:
        por_cuenta.setdefault(str(f.account_code), []).append(f)

    # ── Lo que trae el archivo, por cuenta y ranura ─────────────────────────
    trae: dict[str, dict[int, dict]] = {}
    for r in datos["detalle"]:
        trae.setdefault(str(r["cuenta"]), {})[int(r["detalle"])] = r

    desconocidas = sorted(c for c in trae if c not in por_cuenta)
    if desconocidas:
        raise ErrorApi(422, "checkbook.cuentas_que_no_estan",
                       cuentas=", ".join(desconocidas[:12]),
                       cuantas=len(desconocidas))

    rates = (await db.execute(select(ExchangeRate).where(
        ExchangeRate.scenario_id == scenario_id))).scalars().all()

    # ── Que se va a hacer ───────────────────────────────────────────────────
    actualizadas = vaciadas = nuevas = en_colones = 0
    sin_tc: list[str] = []
    cambios: list[tuple] = []          # (entry|None, cuenta, ranura, desc, montos)

    for cuenta, lineas in por_cuenta.items():
        ranuras = trae.get(cuenta, {})
        for j, e in enumerate(lineas):
            r = ranuras.get(800 + j)
            if r is None:
                # Estaba y vuelve vacia: el owner la borro en el Excel.
                if any(float(getattr(e, m) or 0) for m in MESES) or (e.detail_desc or ""):
                    cambios.append((e, cuenta, 800 + j, "", [0.0] * 12))
                    vaciadas += 1
                continue
            cambios.append((e, cuenta, 800 + j,
                            r.get("descripcion_detalle") or "", r["montos"]))
            actualizadas += 1
            if e.en_colones:
                en_colones += 1
                for m in range(1, 13):
                    if r["montos"][m - 1] and not tc_de(rates, m):
                        sin_tc.append(f"{cuenta} · mes {m}")
        # Ranuras mas alla de lo que existe: lineas nuevas.
        for ranura in sorted(k for k in ranuras if k - 800 >= len(lineas)):
            r = ranuras[ranura]
            if not any(r["montos"]) and not (r.get("descripcion_detalle") or ""):
                continue
            cambios.append((None, cuenta, ranura,
                            r.get("descripcion_detalle") or "", r["montos"]))
            nuevas += 1

    if sin_tc:
        # No se puede pasar un dolar a colones sin el TC del mes. Inventar uno
        # seria inventar el dato maestro de esa linea.
        raise ErrorApi(422, "checkbook.sin_tipo_de_cambio",
                       lineas=" · ".join(sin_tc[:8]), cuantas=len(sin_tc))

    resumen = {
        "departamento": dept_code,
        "anio": datos.get("anio_version"),
        "lineas_actualizadas": actualizadas,
        "lineas_vaciadas": vaciadas,
        "lineas_nuevas": nuevas,
        "lineas_en_colones": en_colones,
        "gran_total_del_archivo": round(datos["gran_total"], 2),
        # El archivo tiene celdas de captura para las noches. NO se escriben:
        # `scenario_stats` es de otra pantalla y otra dimension, y llenarla desde
        # un checkbook de GASTO seria un efecto que nadie pidio. Se informa por
        # si el dato sirve.
        "estadisticas_en_el_archivo": datos.get("estadisticas", {}),
    }
    if dry_run:
        return {"dry_run": True, **resumen}

    if scenario.is_locked:
        raise ErrorApi(409, "escenario.enllavado",
                       escenario=f"{scenario.type} {scenario.version} {scenario.year}")

    # ── Escribir ────────────────────────────────────────────────────────────
    siguiente: dict[str, int] = {}
    for e, cuenta, ranura, desc, montos in cambios:
        if e is None:
            # El correlativo sigue el de FinPlan (`001`…), no el del archivo: el
            # 800 es una ranura del formato, no una llave con sentido propio.
            usados = [int(x.detail_code) for x in por_cuenta.get(cuenta, [])
                      if (x.detail_code or "").isdigit()]
            base = siguiente.get(cuenta, max(usados or [0])) + 1
            siguiente[cuenta] = base
            e = OpexEntry(
                scenario_id=scenario_id, hotel_id=scenario.hotel_id,
                dept_code=dept_code, account_code=cuenta,
                account_name=next((x.account_name for x in por_cuenta.get(cuenta, [])), ""),
                detail_code=str(base).zfill(3))
            db.add(e)
        e.detail_desc = (desc or "")[:200]
        for m in range(1, 13):
            usd = Decimal(str(montos[m - 1] or 0))
            if e.en_colones:
                tc = tc_de(rates, m) or Decimal("0")
                e.set_crc(m, (usd * tc).quantize(Decimal("0.01")))
                e.set_month(m, e.derivar_usd(m, tc))
            else:
                e.set_month(m, usd)

    await db.commit()
    return {"ok": True, **resumen}
