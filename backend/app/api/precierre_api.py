# -*- coding: utf-8 -*-
"""Pre-Cierre — subir el Integrity crudo, revisarlo, y recién ahí cerrar.

## Qué resuelve

Hasta hoy el cierre mensual se armaba a mano en un libro de Excel de 104 MB en
Drive: de Integrity baja sólo la hoja `Final` hasta la columna U, y todo lo
demás —signo, tipo de cambio, departamento, división— se pedía con fórmulas
hasta que cuadrara. Recién entonces se llenaba la plantilla y se subía.

El trabajo manual era determinístico. El problema de fondo no: **la revisión de
los actuales pasaba por el ojo de una persona**, y por ahí podía entrar
cualquier cosa —una cuenta que USALI no contempla, un departamento nuevo, un
gasto que nadie presupuestó—. Si nadie lo miraba, entraba igual y el P&L
cuadraba consigo mismo.

## ⚠️ Es una antesala, no una segunda puerta

`pasar-a-final` **no escribe**. Arma la plantilla de upload con
`export/detail_excel` y se la da a `import_gl_detail`, que es el único camino
que escribe actuales en este sistema. Este repo ya se quemó con dos puertas al
mismo dato; no se abre una tercera.

Y un pre-cierre **no es un escenario**: ningún reporte lo lee. Si se filtrara
habría dos versiones del mismo mes conviviendo.
"""
from __future__ import annotations

import hashlib
import io
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.engine import pl_engine
from app.errores import ErrorApi
from app.export import precierre_xlsx, revision_mes_xlsx as revision
from app.hotel_actual import HOTEL_ID
from app.importers import integrity_final
from app.revision import (nivel1_estructura, nivel2_coherencia,
                          nivel3_fuentes, nivel4_expectativa)
from app.importers.registro_dep import registro_de_subida
from app.models.department_catalog import DepartmentCatalog
from app.models.precierre import Precierre, PrecierreFila
from app.models.scenario import Scenario
from app.textos import Idioma

router = APIRouter()

MESES = ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"]


# ─── El puente y la clasificación ─────────────────────────────────────────────

async def _puente() -> dict:
    """El mapeo Integrity → FinPlan de esta propiedad."""
    from app.seed_data import semilla_cruda
    # Sin extensión: `semilla_cruda` la agrega. Y es `_cruda` a propósito —
    # `semilla()` convierte a Decimal lo que parece número y «0113» se vuelve
    # 113: el departamento perdería el cero de adelante y dejaría de existir.
    datos = semilla_cruda("mapd_integrity")
    if not datos:
        raise ErrorApi(422, "precierre.sin_puente")
    return {d["codigo"]: d for d in datos["departamentos"]}


async def _clasificador(db: AsyncSession):
    """`destino de FinPlan → grupo del P&L`, según el catálogo.

    Devuelve `None` para los departamentos que el catálogo deja SIN grupo a
    propósito: los que se abren por cuenta (`280` Misceláneos). Ahí no se
    inventa nada — el fallback los rotularía como overhead y son ingreso.
    """
    filas = (await db.execute(select(DepartmentCatalog))).scalars().all()
    pl_engine.set_dept_catalog([{"dept_code": r.dept_code,
                                 "default_pl_group": r.default_pl_group,
                                 "parent_dept_code": r.parent_dept_code}
                                for r in filas])
    sin_grupo = {r.dept_code for r in filas if not (r.default_pl_group or "")}

    def resolver(destino: str):
        if not destino or destino in sin_grupo:
            return None
        return pl_engine.group_for_dept(destino)
    return resolver


async def _traer(db: AsyncSession, precierre_id: str) -> Precierre:
    pc = await db.get(Precierre, precierre_id)
    if pc is None:
        raise ErrorApi(404, "precierre.no_encontrado")
    return pc


async def _filas(db: AsyncSession, precierre_id: str) -> list[dict]:
    filas = (await db.execute(select(PrecierreFila).where(
        PrecierreFila.precierre_id == precierre_id))).scalars().all()
    return [{"fila": f.fila, "cuenta": f.cuenta, "cuenta_base": f.cuenta_base,
             "descripcion": f.descripcion, "depto": f.depto,
             "destino_finplan": f.destino_finplan, "grupo": f.grupo or None,
             "categoria": f.categoria, "mes_usd": f.mes_usd,
             "acumulado_usd": f.acumulado_usd} for f in filas]


# ─── Subir ────────────────────────────────────────────────────────────────────

@router.post("/precierre/", dependencies=[Depends(registro_de_subida)])
async def crear(
    file: UploadFile = File(...),
    tc: Decimal = Query(..., gt=0, description="Tipo de cambio CRC/USD del mes"),
    mes: int = Query(..., ge=1, le=12),
    anio: int = Query(...),
    db: AsyncSession = Depends(get_db),
    usuario=Depends(get_current_user),
    idioma: str = Idioma,
):
    """Sube el estado de resultados CRUDO de Integrity y lo deja en revisión.

    **Subir de nuevo es el flujo normal, no la excepción.** Durante la revisión
    el mismo mes se sube muchas veces: aparece un error de posteo, se corrige en
    Integrity, se vuelve a bajar y se sube otra vez, hasta llegar al cierre
    acordado. Por eso cada subida **reemplaza** el borrador anterior sin
    preguntar — pedir confirmación en cada vuelta convertiría el camino principal
    en una molestia, y a la quinta nadie lee el aviso.

    No se pierde nada: el borrador anterior queda `descartado`, con su archivo y
    su hora, y la respuesta dice a cuál reemplazó. La cuenta de vueltas es parte
    de la historia del mes.

    El **tipo de cambio es obligatorio** y no tiene default: cambia todos los
    meses y es un dato del cierre, no una constante del sistema. Inventarlo
    pondría todo el P&L a un TC que nadie decidió, y cuadraría igual.
    """
    data = await file.read()
    if not data:
        raise ErrorApi(422, "precierre.archivo_vacio")

    ya = (await db.execute(select(Precierre).where(
        Precierre.hotel_id == HOTEL_ID, Precierre.anio == anio,
        Precierre.mes == mes, Precierre.estado == "borrador"))).scalars().first()
    reemplazado = None
    if ya is not None:
        ya.estado = "descartado"
        reemplazado = {"id": ya.id, "archivo": ya.archivo_nombre,
                       "subido_en": ya.creado_en.isoformat() if ya.creado_en else None}
        await db.flush()
    vueltas = len((await db.execute(select(Precierre.id).where(
        Precierre.hotel_id == HOTEL_ID, Precierre.anio == anio,
        Precierre.mes == mes))).all()) + 1

    puente = await _puente()
    grupo_de = await _clasificador(db)
    try:
        leido = integrity_final.leer(data, tc, puente, grupo_de)
    except integrity_final.FormatoInesperado as e:
        raise ErrorApi(422, "precierre.formato", detalle=str(e))

    # ── Los hallazgos DEL ARCHIVO se calculan ahora ─────────────────────────
    #
    # Los niveles 1 y 2 dependen de lo que el lector descarta —las filas sin
    # cuenta, el subdetalle, los departamentos que el puente no traduce— y eso
    # no se guarda. Recalcularlos después exigiría volver a leer el archivo, que
    # ya no está. Los niveles 3 y 4 sí se recalculan en cada consulta: dependen
    # de los auxiliares y de los escenarios, que cambian.
    from app.engine.recalculate import load_active_account_mappings
    resolver = pl_engine.construir_resolvedor(await load_active_account_mappings(db))

    def linea_de(depto: str, cuenta: str) -> str:
        regla, _como = resolver(depto, cuenta)
        return (regla or {}).get("report_line_code", "") if regla else ""

    fuentes = {r.dept_code for r in
               (await db.execute(select(DepartmentCatalog).where(
                   DepartmentCatalog.is_allocation_source.is_(True)))).scalars().all()}
    vistas = await _cuentas_de_meses_anteriores(db, anio, mes)
    del_archivo = (
        nivel1_estructura.revisar(leido["filas"], linea_de=linea_de,
                                  sin_mapeo=leido["sin_mapeo"],
                                  vistas_antes=vistas)
        + nivel2_coherencia.revisar(leido["filas"], tc=tc,
                                    sin_cuenta=leido["sin_cuenta"],
                                    subdetalle=leido["subdetalle"],
                                    fuentes_de_reparto=fuentes))

    pc = Precierre(hotel_id=HOTEL_ID, anio=anio, mes=mes, tc=tc,
                   hallazgos_archivo=json.dumps(
                       [h.como_dict() for h in del_archivo], ensure_ascii=False),
                   archivo_nombre=(file.filename or "")[:255],
                   # El checksum se guarda para poder decir DE QUE archivo salió
                   # este mes. El anti-reimport NO vive acá: lo hace
                   # `registro_de_subida`, enganchado en el decorador, que es UN
                   # mecanismo para las veinticuatro puertas y no veinticuatro.
                   checksum=hashlib.sha256(data).hexdigest(),
                   subido_por=getattr(usuario, "email", "") or "")
    db.add(pc)
    await db.flush()
    for f in leido["filas"]:
        db.add(PrecierreFila(
            precierre_id=pc.id, fila=f["fila"], cuenta=f["cuenta"],
            cuenta_base=f["cuenta_base"], descripcion=f["descripcion"][:200],
            depto=f["depto"], destino_finplan=f["destino_finplan"],
            grupo=f["grupo"] or "", categoria=f["categoria"],
            mes_usd=f["mes_usd"], acumulado_usd=f["acumulado_usd"]))
    await db.commit()

    return {"id": pc.id, "anio": anio, "mes": mes, "tc": float(tc),
            "filas": len(leido["filas"]),
            # A cuál reemplazó y cuántas vueltas lleva el mes. Reemplazar sin
            # decirlo sería pisar en silencio; decirlo lo vuelve historia.
            "reemplaza_a": reemplazado, "vuelta": vueltas,
            # Los departamentos que nadie mapeó, CON su monto: sin eso no hay
            # forma de saber si es ruido o si falta media operación.
            "sin_mapeo": [{"depto": x["depto"], "mes_usd": float(x["mes_usd"]),
                           "cuentas": x["cuentas"][:8]}
                          for x in leido["sin_mapeo"]],
            "hallazgos": [h.como_dict() for h in del_archivo]}


async def _cuentas_de_meses_anteriores(db: AsyncSession, anio: int, mes: int) -> set:
    """`(cuenta_base, depto)` de los meses ya pasados por Pre-Cierre este año.

    Es contra lo que se decide si una cuenta es NUEVA. Se miran los borradores y
    los pasados a final: un mes que se revisó cuenta como visto aunque todavía no
    se haya cerrado."""
    filas = (await db.execute(
        select(PrecierreFila.cuenta_base, PrecierreFila.depto)
        .join(Precierre, Precierre.id == PrecierreFila.precierre_id)
        .where(Precierre.hotel_id == HOTEL_ID, Precierre.anio == anio,
               Precierre.mes < mes,
               Precierre.estado.in_(("borrador", "pasado_a_final"))))).all()
    return {(c, d) for c, d in filas}


# ─── Ver ──────────────────────────────────────────────────────────────────────

@router.get("/precierre/")
async def listar(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    filas = (await db.execute(select(Precierre).where(
        Precierre.hotel_id == HOTEL_ID).order_by(
        Precierre.anio.desc(), Precierre.mes.desc()))).scalars().all()
    return {"precierres": [
        {"id": p.id, "anio": p.anio, "mes": p.mes, "estado": p.estado,
         "tc": float(p.tc), "archivo": p.archivo_nombre,
         "subido_por": p.subido_por,
         "creado_en": p.creado_en.isoformat() if p.creado_en else None,
         "hallazgos_abiertos": p.hallazgos_abiertos} for p in filas]}


@router.get("/precierre/{precierre_id}/")
async def detalle(precierre_id: str, db: AsyncSession = Depends(get_db),
                  _=Depends(get_current_user)):
    """La hoja de revisión del mes, en la misma forma que el tab del owner."""
    pc = await _traer(db, precierre_id)
    filas = await _filas(db, precierre_id)
    valores = revision.valores_completos(filas)
    return {
        "id": pc.id, "anio": pc.anio, "mes": pc.mes, "estado": pc.estado,
        "tc": float(pc.tc),
        "hoja": [{"fila": f, "etiqueta": e, "clave": c,
                  "actual": float(valores.get(c, 0)) if c else None}
                 for f, e, c in revision.PLAN],
        "filas": len(filas),
    }


@router.get("/precierre/{precierre_id}/hoja.xlsx")
async def hoja(precierre_id: str, db: AsyncSession = Depends(get_db),
               _=Depends(get_current_user)):
    """La hoja de revisión, con el layout exacto del tab que el owner revisa a
    ojo — mismas filas, mismas columnas, mismas etiquetas."""
    pc = await _traer(db, precierre_id)
    valores = revision.valores_desde_precierre(await _filas(db, precierre_id))
    wb = revision.construir(MESES[pc.mes - 1], pc.anio, {}, valores)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nombre = f"Revision_{MESES[pc.mes - 1]}_{pc.anio}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


def _sin_revisar(stats: dict, noches_opera, comp: dict) -> list[str]:
    """Los cruces que esta corrida NO pudo hacer, y por qué.

    Se listan aunque no sea culpa de nadie. Una lista de hallazgos vacía puede
    significar «está todo bien» o «no se miró nada», y desde afuera se ven igual.
    """
    faltan = []
    # Todavía sin conectar: el mayor contra los auxiliares del mes. Los chequeos
    # están escritos y probados (`nivel3_fuentes`), pero falta identificar de
    # dónde sale la planilla y el checkbook de un mes de ACTUALES — los que hay
    # hoy cuelgan de un escenario, y un pre-cierre no es un escenario.
    faltan.append("planilla contra el mayor (falta conectar el auxiliar del mes)")
    faltan.append("checkbook de gastos contra el mayor (idem)")
    if not stats:
        faltan.append("coherencia de las estadísticas (no se cargaron)")
    if noches_opera is None:
        faltan.append("noches contra Opera (no se pasó el dato)")
    if "forecast" not in comp:
        faltan.append("varianzas contra el Forecast (no hay uno marcado como "
                      "vigente para el año)")
    if "budget" not in comp:
        faltan.append("varianzas contra el Budget (no hay Budget del año)")
    return faltan


async def _valores_de_escenario(db: AsyncSession, escenario, mes: int) -> dict:
    """El P&L de un escenario en las MISMAS claves que la hoja de revisión."""
    from app.engine import recalculate as recalc
    lineas = await recalc.compute_pl_month(db, escenario, mes)
    return revision.valores_desde_lineas_pl(
        {ln.line_code: ln.amount_usd for ln in lineas})


async def _comparativos(db: AsyncSession, anio: int, mes: int) -> dict:
    """El Forecast vigente y el Budget del año, si existen.

    El Forecast es el marcado `is_current_forecast` — el vivo. Si no hay
    ninguno, no se elige uno por descarte: comparar contra un forecast que nadie
    designó daría varianzas que no significan nada.
    """
    escs = (await db.execute(select(Scenario).where(
        Scenario.year == anio))).scalars().all()
    fcst = next((e for e in escs
                 if e.type == "FORECAST" and e.is_current_forecast), None)
    bud = next((e for e in escs if e.type == "BUDGET"), None)
    out = {}
    if fcst is not None:
        out["forecast"] = {"escenario": f"{fcst.type} {fcst.version}",
                           "valores": await _valores_de_escenario(db, fcst, mes)}
    if bud is not None:
        out["budget"] = {"escenario": f"{bud.type} {bud.version}",
                         "valores": await _valores_de_escenario(db, bud, mes)}
    return out


@router.get("/precierre/{precierre_id}/hallazgos/")
async def hallazgos(
    precierre_id: str,
    umbral_monto: Decimal = Query(nivel4_expectativa.UMBRAL_MONTO, ge=0),
    umbral_pct: Decimal = Query(nivel4_expectativa.UMBRAL_PCT, ge=0),
    rooms_disponibles: int | None = Query(None),
    rooms_ocupadas: int | None = Query(None),
    huespedes: int | None = Query(None),
    noches_opera: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """El informe de la revisión — varianzas y discrepancias, los cuatro niveles.

    **Ninguno rechaza la carga.** Bloquear es potestad de los cuatro controles de
    la verificación, y de nadie más: un hallazgo que rechazara enseñaría a
    esquivarlo. Lo que se pide es que no se calle nada.

    Los del **archivo** (niveles 1 y 2) se calcularon al subir y se leen tal
    cual. Los de **contexto** (3 y 4) se recalculan acá, porque los auxiliares y
    los escenarios cambian — y porque los umbrales se ajustan sin volver a subir.
    """
    pc = await _traer(db, precierre_id)
    filas = await _filas(db, precierre_id)
    del_archivo = json.loads(pc.hallazgos_archivo or "[]")

    stats = {k: v for k, v in (("rooms_disponibles", rooms_disponibles),
                               ("rooms_ocupadas", rooms_ocupadas),
                               ("huespedes", huespedes)) if v is not None}
    valores = revision.valores_completos(filas)
    contexto = nivel3_fuentes.revisar(
        filas, stats=stats,
        ingreso_habitaciones=valores.get("rev.Rooms"),
        noches_opera=noches_opera)

    comp = await _comparativos(db, pc.anio, pc.mes)
    contexto += nivel4_expectativa.revisar(
        valores,
        forecast=comp.get("forecast", {}).get("valores"),
        budget=comp.get("budget", {}).get("valores"),
        umbral_monto=umbral_monto, umbral_pct=umbral_pct)

    todos = del_archivo + [h.como_dict() for h in contexto]
    orden = {"critico": 0, "aviso": 1, "info": 2}
    todos.sort(key=lambda h: (orden.get(h["gravedad"], 9), -abs(h["monto"])))
    return {
        "id": pc.id, "anio": pc.anio, "mes": pc.mes,
        "umbrales": {"monto": float(umbral_monto), "pct": float(umbral_pct)},
        "comparativos": {k: v["escenario"] for k, v in comp.items()},
        "hallazgos": todos,
        "resumen": {g: len([h for h in todos if h["gravedad"] == g])
                    for g in ("critico", "aviso", "info")},
        # ⚠️ Lo que NO se pudo mirar, dicho. Importa tanto como el hallazgo:
        # «no se revisó» y «está bien» se ven IGUAL en una lista vacía, y esa
        # confusión es justo la que este módulo viene a eliminar.
        "sin_revisar": _sin_revisar(stats, noches_opera, comp),
    }


def _descarga(contenido: bytes, nombre: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(contenido),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/precierre/{precierre_id}/detalle.xlsx")
async def detalle_xlsx(precierre_id: str, db: AsyncSession = Depends(get_db),
                       _=Depends(get_current_user)):
    """El mes en el formato ESTÁNDAR de FinPlan — el mismo que la app baja y
    vuelve a leer.

    Se edita y se sube por la puerta de siempre (`import-gl-detail`), sin pasar
    por Pre-Cierre. Es también el archivo que `pasar-a-final` le va a dar al
    importador: una sola forma del dato, no dos parecidas.
    """
    from app.engine.recalculate import load_active_account_mappings
    pc = await _traer(db, precierre_id)
    filas = await _filas(db, precierre_id)
    valores = revision.valores_completos(filas)

    resolver = pl_engine.construir_resolvedor(await load_active_account_mappings(db))

    def linea_de(depto: str, cuenta: str) -> str:
        regla, _como = resolver(depto, cuenta)
        return (regla or {}).get("report_line_code", "") if regla else ""

    nombres = {r.dept_code: r.dept_name for r in
               (await db.execute(select(DepartmentCatalog))).scalars().all()}
    etiqueta = f"Actual {pc.anio}"
    datos = precierre_xlsx.plantilla_finplan(pc.mes, pc.anio, etiqueta, filas,
                                             valores, nombres, linea_de)
    return _descarga(datos, f"Detalle_{MESES[pc.mes - 1]}_{pc.anio}.xlsx")


@router.get("/precierre/{precierre_id}/filas.xlsx")
async def filas_xlsx(precierre_id: str, db: AsyncSession = Depends(get_db),
                     _=Depends(get_current_user)):
    """El detalle traducido, con la fila del Excel de origen de cada número."""
    pc = await _traer(db, precierre_id)
    datos = precierre_xlsx.filas_editables(await _filas(db, precierre_id))
    return _descarga(datos, f"Traducido_{MESES[pc.mes - 1]}_{pc.anio}.xlsx")


@router.get("/precierre/listado.xlsx")
async def listado_xlsx(db: AsyncSession = Depends(get_db),
                       _=Depends(get_current_user)):
    """Las vueltas de cada mes: quién subió qué, cuándo, y en qué quedó."""
    filas = (await db.execute(select(Precierre).where(
        Precierre.hotel_id == HOTEL_ID).order_by(
        Precierre.anio.desc(), Precierre.mes.desc(),
        Precierre.creado_en.desc()))).scalars().all()
    datos = precierre_xlsx.listado([
        {"anio": p.anio, "mes": p.mes, "estado": p.estado, "tc": p.tc,
         "archivo": p.archivo_nombre, "subido_por": p.subido_por,
         "creado_en": p.creado_en.strftime("%Y-%m-%d %H:%M") if p.creado_en else "",
         "hallazgos_abiertos": p.hallazgos_abiertos} for p in filas])
    return _descarga(datos, "Pre-cierres.xlsx")


@router.delete("/precierre/{precierre_id}/")
async def descartar(precierre_id: str, db: AsyncSession = Depends(get_db),
                    _=Depends(get_current_user)):
    """Se marca descartado, no se borra: queda la traza de que se intentó."""
    pc = await _traer(db, precierre_id)
    if pc.estado == "pasado_a_final":
        raise ErrorApi(409, "precierre.ya_paso_a_final")
    pc.estado = "descartado"
    await db.commit()
    return {"id": pc.id, "estado": pc.estado}
