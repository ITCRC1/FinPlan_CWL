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

import pathlib
import functools
import re
import unicodedata
import hashlib
import io
import json
from datetime import datetime, timezone
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
from app.models.payroll_position import PayrollPosition
from app.models.payroll_concept_entry import PayrollConceptEntry
from app.models.opex_entry import OpexEntry
from app.models.precierre import Precierre, PrecierreFila, PrecierrePosicion
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

# ─── El espejo que hace legible el borrador ───────────────────────────────────
#
# Owner, 2026-09-10: los 19 sub-tabs del cierre tienen que poder mirar el mes
# que se está revisando, sin pasarlo a Final.
#
# ⚠️ **No se toca ninguno de los ocho cargadores del P&L.** Cada uno consulta
# por `scenario_id` en sus propias tablas y no hay punto único donde
# interceptar; enseñarles una fuente nueva son ocho reescrituras y ocho
# oportunidades de que el mismo mes dé un número distinto según el sub-tab.
# El borrador se materializa en un escenario y los ocho lo leen sin saberlo.
#
# Ver migración 140 para el porqué de la bandera y sus tres límites.

#: La versión del espejo. Es un nombre y no un id: se busca por
#: (hotel, año, es_precierre), y esto es lo que se lee en pantalla.
VERSION_ESPEJO = "Pre-Cierre"


async def _espejo(db: AsyncSession, anio: int) -> Scenario:
    """El escenario espejo de este año. Se crea la primera vez y se reusa.

    **Uno por año, no uno por vuelta.** El owner avisó que «seguro se suban
    varias antes de llegar a final»: con uno por vuelta, a la quinta habría
    cinco ACTUAL del mismo año y Pre-Closing tendría que adivinar cuál mirar.
    Con uno solo, la última subida sobreescribe el mes y no hay nada que
    elegir.
    """
    esp = (await db.execute(select(Scenario).where(
        Scenario.hotel_id == HOTEL_ID, Scenario.year == anio,
        Scenario.es_precierre.is_(True)))).scalars().first()
    if esp is not None:
        return esp
    esp = Scenario(hotel_id=HOTEL_ID, year=anio, type="ACTUAL",
                   version=VERSION_ESPEJO, status="draft",
                   es_precierre=True, source_mode="imported",
                   source_file="pre-cierre", created_by="sistema")
    db.add(esp)
    await db.flush()
    return esp


async def _reflejar(db: AsyncSession, pc: Precierre, idioma: str) -> dict:
    """Escribe el mes del borrador en el espejo, por la puerta de siempre.

    Usa `_plantilla_para_importar` + `import_gl_detail`, igual que
    `pasar-a-final`. No hay un segundo camino de escritura: es el mismo, con
    otro destino.

    ⚠️ **Un espejo roto no puede tumbar una subida que funcionó.** El borrador
    es la fuente de verdad y ya está guardado; si esto falla, se devuelve el
    error en la respuesta y la revisión sigue disponible en su propia pantalla.
    """
    from app.api.scenarios_api import import_gl_detail

    esp = await _espejo(db, pc.anio)
    datos = await _plantilla_para_importar(db, pc)

    class _Archivo:
        filename = f"precierre_espejo_{pc.anio}_{pc.mes:02d}.xlsx"

        async def read(self):
            return datos

    # `mes_de_cierre` recorta al mes del borrador: un espejo de agosto no puede
    # tocar julio. `merge=True` deja los otros meses como estaban.
    # `confirmar_diferencias=True` a propósito: el espejo es para MIRAR, y un
    # mes que todavía no cuadra es justamente el que hay que poder mirar. El
    # bloqueo por cuadre sigue vivo donde importa, en `pasar-a-final`.
    resultado = await import_gl_detail(
        file=_Archivo(), dry_run=False, merge=True, scenario_id=esp.id,
        confirmar_diferencias=True, mes_de_cierre=pc.mes, db=db, idioma=idioma)
    bloques = resultado.get("blocks") or resultado.get("results") or []
    return {"escenario_id": esp.id, "version": esp.version,
            "escrito": bool(any(b.get("matched") for b in bloques))}


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
        reemplazado = {"id": ya.id, "archivo": ya.archivo_nombre,
                       "subido_en": ya.creado_en.isoformat() if ya.creado_en else None}
    # ⚠️ **El borrador anterior NO se descarta todavía.** Antes se marcaba
    # `descartado` con un `flush()` acá arriba, ANTES de leer el archivo — y
    # `get_db()` no hace rollback al fallar. Si el archivo nuevo no se podía
    # leer, la subida devolvía error y el mes se quedaba SIN borrador: el
    # trabajo bueno se iba a la basura por un intento que nunca llegó a
    # reemplazarlo. Pasó con el cierre de agosto 2026.
    #
    # Se descarta más abajo, recién cuando el archivo nuevo ya se leyó.
    vueltas = len((await db.execute(select(Precierre.id).where(
        Precierre.hotel_id == HOTEL_ID, Precierre.anio == anio,
        Precierre.mes == mes))).all()) + 1

    puente = await _puente()
    grupo_de = await _clasificador(db)
    try:
        leido = integrity_final.leer(data, tc, puente, grupo_de)
    except integrity_final.FormatoInesperado as e:
        raise ErrorApi(422, "precierre.formato", detalle=str(e))

    # El archivo nuevo se leyó: ahora sí el anterior queda reemplazado.
    if ya is not None:
        ya.estado = "descartado"
        await db.flush()

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
    # La planilla abierta por POSICIÓN — el tercer nivel de las cuentas 6.
    #
    # No entra a ningún total: el nivel `concepto-departamento` de arriba ya
    # suma esta misma plata. Se guarda para poder abrirla por quién la cobra
    # (owner, 2026-09-10). Ver `PrecierrePosicion`.
    for pz in leido.get("posiciones", []):
        db.add(PrecierrePosicion(
            precierre_id=pc.id, fila=pz["fila"], cuenta=pz["cuenta"],
            cuenta_base=pz["cuenta_base"], posicion=pz["posicion"],
            depto=pz["depto"], destino_finplan=pz["destino_finplan"],
            descripcion=pz["descripcion"][:200], mes_usd=pz["mes_usd"]))
    await db.commit()

    # El espejo, para que los 19 sub-tabs puedan mirar este mes sin pasarlo a
    # Final. Si falla, la subida ya está: se dice y se sigue.
    espejo: dict = {"escrito": False, "error": None}
    try:
        espejo = await _reflejar(db, pc, idioma)
        await db.commit()
    except Exception as e:            # noqa: BLE001 — ver docstring de _reflejar
        await db.rollback()
        espejo = {"escrito": False, "error": str(e)[:300]}

    return {"id": pc.id, "anio": anio, "mes": mes, "tc": float(tc),
            "filas": len(leido["filas"]), "espejo": espejo,
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


# ─── Qué cambió respecto de la vuelta anterior ────────────────────────────────
#
# Owner, 2026-09-10: «necesito tener la opción de subir N cantidad de veces» ·
# «y que el sistema me diga qué cambió versus lo que estaba».
#
# La revisión es iterativa por diseño: se sube, se mira, se corrige el posteo en
# Integrity, se vuelve a subir. Lo que faltaba era cerrar el lazo — decir qué se
# movió entre una vuelta y la siguiente, para no tener que compararlo a ojo
# contra la vuelta anterior que ya no está en pantalla.

#: Por debajo de esto no es un cambio, es la división por el tipo de cambio.
#: Los montos se guardan con seis decimales a propósito (ver el modelo).
RUIDO = Decimal("0.01")


@router.get("/precierre/{precierre_id}/cambios/")
async def cambios(precierre_id: str, db: AsyncSession = Depends(get_db),
                  _=Depends(get_current_user)):
    """Qué cambió respecto de la subida anterior del MISMO mes.

    Se compara cuenta por cuenta, que es la llave del mayor. Tres clases de
    cambio, y las tres importan por razones distintas:

    * **movidas** — la cuenta está en las dos y el monto cambió. Es la
      corrección que se fue a buscar.
    * **nuevas** — aparecieron. Un posteo que faltaba, o una cuenta que nadie
      esperaba: por eso se listan aunque el monto sea chico.
    * **ausentes** — estaban y ya no. ⚠️ Es la más peligrosa: un renglón que
      desaparece no hace ruido en ningún total, porque el total también baja.

    Si es la primera vuelta del mes, `anterior` viene en `null` y las tres
    listas vacías: no hay contra qué comparar y no se inventa una base.
    """
    pc = await _traer(db, precierre_id)

    prev = (await db.execute(
        select(Precierre)
        .where(Precierre.hotel_id == pc.hotel_id, Precierre.anio == pc.anio,
               Precierre.mes == pc.mes, Precierre.id != pc.id,
               Precierre.creado_en <= pc.creado_en)
        .order_by(Precierre.creado_en.desc()))).scalars().first()

    if prev is None:
        return {"precierre_id": precierre_id, "anterior": None,
                "movidas": [], "nuevas": [], "ausentes": [],
                "total_antes": None, "total_ahora": None, "delta_total": None}

    def por_cuenta(filas):
        return {f["cuenta"]: f for f in filas}

    ahora = por_cuenta(await _filas(db, pc.id))
    antes = por_cuenta(await _filas(db, prev.id))

    movidas, nuevas, ausentes = [], [], []
    for cuenta, f in ahora.items():
        viejo = antes.get(cuenta)
        if viejo is None:
            nuevas.append({**_resumen(f), "mes_usd_antes": None})
        elif abs(f["mes_usd"] - viejo["mes_usd"]) >= RUIDO:
            movidas.append({**_resumen(f),
                            "mes_usd_antes": viejo["mes_usd"],
                            "delta": f["mes_usd"] - viejo["mes_usd"]})
    for cuenta, viejo in antes.items():
        if cuenta not in ahora:
            ausentes.append({**_resumen(viejo), "mes_usd_antes": viejo["mes_usd"],
                             "mes_usd": Decimal("0")})

    # El orden es por tamaño del movimiento: lo que más plata mueve, primero.
    movidas.sort(key=lambda x: -abs(x["delta"]))
    nuevas.sort(key=lambda x: -abs(x["mes_usd"]))
    ausentes.sort(key=lambda x: -abs(x["mes_usd_antes"]))

    total_antes = sum((f["mes_usd"] for f in antes.values()), Decimal("0"))
    total_ahora = sum((f["mes_usd"] for f in ahora.values()), Decimal("0"))
    return {
        "precierre_id": precierre_id,
        "anterior": {"id": prev.id, "archivo": prev.archivo_nombre,
                     "estado": prev.estado, "tc": prev.tc,
                     "creado_en": prev.creado_en.isoformat() if prev.creado_en else None},
        "tc_cambio": (pc.tc != prev.tc),
        "movidas": movidas, "nuevas": nuevas, "ausentes": ausentes,
        "total_antes": total_antes, "total_ahora": total_ahora,
        "delta_total": total_ahora - total_antes,
    }


def _resumen(f: dict) -> dict:
    """Lo mínimo para identificar la fila en pantalla y poder ir a mirarla."""
    return {"cuenta": f["cuenta"], "descripcion": f["descripcion"],
            "depto": f["depto"], "categoria": f["categoria"],
            "fila": f["fila"], "mes_usd": f["mes_usd"]}


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


async def _plantilla_para_importar(db: AsyncSession, pc: Precierre) -> bytes:
    """El mes en el formato estándar de FinPlan, listo para el importador.

    Es EXACTAMENTE el mismo archivo que baja `detalle.xlsx`. Que sean el mismo
    importa: lo que se revisa y lo que se escribe no pueden ser dos cosas
    parecidas.
    """
    from app.engine.recalculate import load_active_account_mappings
    filas = await _filas(db, pc.id)
    valores = revision.valores_completos(filas)
    resolver = pl_engine.construir_resolvedor(await load_active_account_mappings(db))

    def linea_de(depto: str, cuenta: str) -> str:
        regla, _como = resolver(depto, cuenta)
        return (regla or {}).get("report_line_code", "") if regla else ""

    nombres = {r.dept_code: r.dept_name for r in
               (await db.execute(select(DepartmentCatalog))).scalars().all()}
    return precierre_xlsx.plantilla_finplan(
        pc.mes, pc.anio, f"Actual {pc.anio}", filas, valores, nombres, linea_de)


@router.post("/precierre/{precierre_id}/pasar-a-final/")
async def pasar_a_final(
    precierre_id: str,
    dry_run: bool = Query(False, description="Sólo reporta qué se escribiría"),
    confirmar_diferencias: bool = Query(
        False, description="Escribir aunque la verificación no cuadre"),
    db: AsyncSession = Depends(get_db),
    usuario=Depends(get_current_user),
    idioma: str = Idioma,
):
    """Declara el mes final y lo escribe.

    ## No escribe acá

    Arma la plantilla estándar y se la da a `import_gl_detail`, que es **el
    único camino que escribe actuales en este sistema**. Este repo ya se quemó
    con dos puertas al mismo dato: el pre-cierre es una antesala, no un atajo.

    De ahí salen gratis las protecciones que ese importador ya tiene: la
    verificación por buckets que bloquea si ingresos, GOP, EBITDA o utilidad
    neta no cuadran contra el detalle; el recorte al mes de cierre; y la negativa
    a escribir una fila con monto y sin cuenta.

    ## Los hallazgos abiertos no lo impiden — pero quedan escritos

    Ninguno bloquea: bloquear enseñaría a esquivarlos. Pero al pasar a final se
    guarda **con cuántos se cerró el mes y cuáles eran**. Ignorar uno es una
    decisión, y una decisión sin registro no se puede revisar después.
    """
    pc = await _traer(db, precierre_id)
    if pc.estado == "pasado_a_final":
        raise ErrorApi(409, "precierre.ya_paso_a_final")
    if pc.estado == "descartado":
        raise ErrorApi(409, "precierre.esta_descartado")

    datos = await _plantilla_para_importar(db, pc)

    # El importador de siempre. Se le pasa `mes_de_cierre` para que escriba SOLO
    # este mes y descarte el resto — un pre-cierre es de un mes, no de un año.
    from app.api.scenarios_api import import_gl_detail

    class _Archivo:
        """Lo mínimo que `import_gl_detail` necesita de un `UploadFile`."""
        filename = f"precierre_{pc.anio}_{pc.mes:02d}.xlsx"

        async def read(self):
            return datos

    resultado = await import_gl_detail(
        file=_Archivo(), dry_run=dry_run, merge=True, scenario_id=None,
        confirmar_diferencias=confirmar_diferencias,
        mes_de_cierre=pc.mes, db=db, idioma=idioma)

    if dry_run:
        return {"dry_run": True, "importacion": resultado}

    # ⚠️ Que haya devuelto 200 no quiere decir que haya escrito.
    #
    # `import_gl_detail` empareja cada bloque del archivo con un escenario por
    # (tipo, año). Si no encuentra ninguno —no existe el ACTUAL del año, o se
    # renombró— **no falla**: devuelve el bloque con `matched: null` y sigue.
    # Marcar el mes como final ahí sería declarar un cierre que no ocurrió, y el
    # pre-cierre quedaría cerrado con la base intacta.
    bloques = resultado.get("blocks") or resultado.get("results") or []
    if not any(b.get("matched") for b in bloques):
        raise ErrorApi(409, "precierre.sin_escenario_destino",
                       anio=pc.anio,
                       bloques=", ".join(str(b.get("label") or "?") for b in bloques))

    # Con cuántos hallazgos abiertos se cerró el mes, y cuáles.
    abiertos = json.loads(pc.hallazgos_archivo or "[]")
    pc.hallazgos = json.dumps(abiertos, ensure_ascii=False)
    pc.hallazgos_abiertos = len(abiertos)
    pc.estado = "pasado_a_final"
    pc.pasado_por = getattr(usuario, "email", "") or ""
    pc.pasado_en = datetime.now(timezone.utc)
    await db.commit()
    return {"id": pc.id, "estado": pc.estado,
            "hallazgos_abiertos": pc.hallazgos_abiertos,
            "importacion": resultado}


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


# ⚠️ El año y el mes van en el PATH, no en el query.
#
# `/precierre/{precierre_id}/` se registra antes que esto, y FastAPI resuelve
# por orden: una ruta `/precierre/planilla-por-posicion/` habría entrado por
# ahí con `precierre_id="planilla-por-posicion"` y contestado 404 sin que nada
# dijera por qué.
#: Los conceptos de nómina, tal como los escribe Integrity al principio de la
#: descripción. No es una lista de adorno: es lo que hay que quitar para que
#: quede el nombre del puesto. Integrity escribe el mismo concepto de varias
#: formas —«SALARIES AND WAGES» y «SALARY AND WAGES»—, así que no se puede
#: deducir de un prefijo común: se declara.
_CONCEPTOS_AL_FRENTE = (
    "SALARIES AND WAGES", "SALARY AND WAGES", "WAGES AND SALARIES",
    "OVERTIME", "DAYS OFF LAB", "DAY OFF", "WORKED HOLIDAYS", "DISABILITIES",
    "COMMISSIONS", "CCSS", "SOCIAL SECURITY", "13TH SALARY", "AGUINALDO",
    "OCCUPATIONAL HAZARDS", "OCCUPATIONAL RISKS OF THE",
    "PROVISION VACATIONS", "PROVISION VACATION", "VACATIONS TAKEN",
    "CAFETERIA", "NOTICE AND SEVERANCE", "SEVERANCE", "INCENTIVE BONUS",
    "HOUSING", "TRANSPORTATION", "OTHER BENEFITS",
)


def _sin_el_concepto(descripcion: str) -> str:
    """La descripción del asiento sin el concepto de nómina adelante.

    «SALARIES AND WAGES FRONT DESK AGENT» → «FRONT DESK AGENT».
    «OVERTIME» → «» (esa fila no nombra a nadie).
    """
    t = " ".join((descripcion or "").split())
    arriba = t.upper()
    for c in sorted(_CONCEPTOS_AL_FRENTE, key=len, reverse=True):
        if arriba.startswith(c):
            return t[len(c):].strip(" -/")
    return t


@functools.lru_cache(maxsize=1)
def _catalogo_de_posiciones() -> dict[str, str]:
    """`501` → «FRONT DESK AGENT / RECEPTIONIST».

    Sale de `seed_data/posiciones_integrity.json`, extraído de la hoja
    `Planning` del catálogo del grupo. Es un ARCHIVO y no un join porque el
    checkbook de planilla de la app usa su propio código de posición
    (`0112-01`) — owner, 2026-09-10: *«acá en planning se nombra la posición
    pero tiene otro control»*. Los dos sistemas no comparten espacio de
    códigos.
    """
    from app.seed_data import semilla_del_grupo
    try:
        return (semilla_del_grupo("posiciones_integrity") or {})["posiciones"]
    except Exception:      # noqa: BLE001 — sin catálogo se cae al nombre del mayor
        return {}


def _llave_de_puesto(nombre: str) -> str:
    """El nombre del puesto, normalizado para poder aparearlo entre versiones.

    ⚠️ Se aparea por NOMBRE y no por código, y eso hay que decirlo.

    El Actual trae la posición del mayor de Integrity —el tercer nivel,
    `501`—. El Budget y el Forecast se SUBEN con el código del checkbook
    (`0112-01`): owner, 2026-09-10, *«acá en planning se nombra la posición
    pero tiene otro control»*. Los dos sistemas no comparten espacio de
    códigos, así que aparear por número emparejaría puestos distintos **sin
    fallar** — el modo de falla más caro que tiene esta app.

    Lo único que comparten es cómo se llama el puesto. Se normaliza lo que
    varía sin cambiar el significado —mayúsculas, tildes, dobles espacios,
    barras y guiones— y nada más: «Reservations Agent» y «RESERVATIONS AGENT»
    son el mismo puesto; «Reservations Agent Supervisora» NO lo es, y tiene que
    seguir sin serlo.
    """
    t = unicodedata.normalize("NFKD", (nombre or "").strip().upper())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[/\-]+", " ", t)
    return " ".join(t.split())


async def _planilla_por_puesto(db: AsyncSession, scenario_id: str,
                               meses: set[int]) -> dict[tuple[str, str], float]:
    """{(cuenta, llave de puesto): monto} de una versión del checkbook.

    Es el mismo corte que el del mayor —cuenta × puesto— armado desde
    `PayrollConceptEntry`, que es de donde sale el reporte de planilla por
    departamento. Misma fuente, mismo filtro: si saliera de otro lado, los dos
    cuadros dirían cosas distintas.
    """
    from app.api.consulta_api import CONCEPTOS

    posiciones = {p.id: p for p in (await db.execute(select(PayrollPosition).where(
        PayrollPosition.scenario_id == scenario_id))).scalars().all()}
    out: dict[tuple[str, str], float] = {}
    for e in (await db.execute(select(PayrollConceptEntry).where(
            PayrollConceptEntry.scenario_id == scenario_id))).scalars().all():
        if (e.month or 0) not in meses:
            continue
        p = posiciones.get(e.position_id)
        # La posición sintética del GL no nombra a nadie: no se puede aparear.
        if p is None or (p.position_code or "").strip() == "GL":
            continue
        llave = _llave_de_puesto(p.position_name)
        if not llave:
            continue
        for campo, codigo, _rotulo in CONCEPTOS:
            v = getattr(e, campo, None)
            if v:
                k = (codigo, llave)
                out[k] = out.get(k, 0.0) + float(v)
    return out


@router.get("/precierre/planilla-por-posicion/{anio}/{mes}/")
async def planilla_por_posicion(
    anio: int,
    mes: int,
    scenarios: str = Query("", description="ids a comparar, separados por coma"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """La planilla del mes en revisión, abierta por DEPARTAMENTO · CUENTA · POSICIÓN.

    Owner, 2026-09-10: *«le metemos departamento, cuenta y posición — la
    posición en las cuentas 6 es el tercer nivel»* · *«eso solo para actuales
    del mes»* · *«y pones el nombre de la posición»*.

    Sale del BORRADOR más reciente de ese mes, que es lo que significa «los
    actuales del mes» en esta pantalla: lo último que se subió, todavía sin
    pasar a Final.

    ⚠️ **No es un total nuevo, es el mismo abierto.** Las filas suman
    exactamente la planilla del nivel cuenta — verificado sobre agosto 2026:
    244 filas, US$227.497,60, al centavo. Por eso el `total` viaja aparte y la
    pantalla no lo recalcula sumando lo que dibuja.

    Un mes subido ANTES de la migración 143 no tiene este detalle: se llena al
    leer el archivo. La respuesta lo dice con `hay_detalle: false` en vez de
    devolver una tabla vacía que parecería «no hubo planilla».
    """
    pc = (await db.execute(select(Precierre).where(
        Precierre.hotel_id == HOTEL_ID, Precierre.anio == anio,
        Precierre.mes == mes).order_by(
        Precierre.creado_en.desc()))).scalars().first()
    if pc is None:
        return {"anio": anio, "mes": mes, "precierre_id": None,
                "hay_detalle": False, "filas": [], "total": 0.0,
                "motivo": "sin_borrador"}

    filas = (await db.execute(select(PrecierrePosicion).where(
        PrecierrePosicion.precierre_id == pc.id).order_by(
        PrecierrePosicion.destino_finplan, PrecierrePosicion.cuenta_base,
        PrecierrePosicion.posicion))).scalars().all()

    nombres = {d.dept_code: d.dept_name for d in
               (await db.execute(select(DepartmentCatalog))).scalars().all()}
    from app.api.consulta_api import CONCEPTOS
    rotulo_cuenta = {c: r for _campo, c, r in CONCEPTOS}
    catalogo_pos = _catalogo_de_posiciones()

    # El nombre que trae el propio mayor, para los códigos que el catálogo no
    # tiene.
    #
    # ⚠️ Solo de la línea de SALARIO (6000). Es la que nombra el puesto —
    # «SALARIES AND WAGES ROOM ATTENDANT»—; las demás repiten el concepto
    # («OVERTIME») o traen variantes que no son un puesto («13th Sal
    # Mandatory»), y ésa, por ser más larga, le ganaría al nombre de verdad.
    del_mayor: dict[str, str] = {}
    for f in filas:
        if f.cuenta_base != 6000:
            continue
        n = _sin_el_concepto(f.descripcion)
        if n and len(n) > len(del_mayor.get(f.posicion, "")):
            del_mayor[f.posicion] = n

    # ── Las otras versiones, al lado ─────────────────────────────────────
    #
    # Owner, 2026-09-10: *«hay una forma de poner el detalle a la par de Budget
    # y Forecast; estos fueron SUBIDOS, no se generaron por auxiliares»*. Tenía
    # razón: su planilla está por puesto en `PayrollConceptEntry`, no salió de
    # drivers. Se aparea por NOMBRE del puesto — ver `_llave_de_puesto`.
    comparar: dict[str, dict[tuple[str, str], float]] = {}
    etiquetas: dict[str, str] = {}
    for sid in [x.strip() for x in scenarios.split(",") if x.strip()]:
        esc = await db.get(Scenario, sid)
        if esc is None:
            continue
        etiquetas[sid] = f"{esc.year} · {esc.type} {esc.version}".strip()
        comparar[sid] = await _planilla_por_puesto(db, sid, {mes})

    def _llave_fila(f) -> tuple[str, str]:
        return (str(f.cuenta_base or ""),
                _llave_de_puesto(catalogo_pos.get(f.posicion)
                                 or del_mayor.get(f.posicion, "")))

    # ── Lo que la planilla tiene y NINGUNA posición cobra ─────────────────
    #
    # Owner, 2026-09-10: *«que pegue a un vistazo»*.
    #
    # El detalle por posición sale del mayor y suma US$227.497,60 en agosto; el
    # tab Payroll x Cuenta dice US$251.819,00. La diferencia son los
    # US$24.321,93 de la 6025 Cafetería, que **no existe en el archivo de
    # Integrity**: no es planilla posteada, es el reparto de cafetería que el
    # sistema carga a cada departamento. Nadie la cobra, así que no tiene
    # posición — y por eso el detalle no podía llegar al total.
    #
    # En vez de dejar dos números sin explicación, se agrega la línea que
    # falta, rotulada. Repartirla entre las posiciones habría hecho que el
    # total pegara inventando plata que nadie cobró: eso sí sería mentir.
    #
    # El faltante se mide contra la MISMA fuente que usa Payroll x Cuenta
    # —`PayrollConceptEntry` del espejo—, así que los dos tabs cierran en el
    # mismo número por construcción y no por coincidencia.
    cubierto: dict[tuple[str, str], Decimal] = {}
    for f in filas:
        k = (f.destino_finplan, str(f.cuenta_base or ""))
        cubierto[k] = cubierto.get(k, Decimal("0")) + f.mes_usd

    sin_posicion: list[dict] = []
    esp = (await db.execute(select(Scenario).where(
        Scenario.hotel_id == HOTEL_ID, Scenario.year == anio,
        Scenario.es_precierre.is_(True)))).scalars().first()
    if esp is not None:
        from app.api.consulta_api import CONCEPTOS
        rotulo = {c: r for _campo, c, r in CONCEPTOS}
        total_mes: dict[tuple[str, str], Decimal] = {}
        for e in (await db.execute(select(PayrollConceptEntry).where(
                PayrollConceptEntry.scenario_id == esp.id,
                PayrollConceptEntry.month == mes))).scalars().all():
            for campo, codigo, _r in CONCEPTOS:
                v = getattr(e, campo, None)
                if v:
                    k = ((e.dept_code or "").strip(), codigo)
                    total_mes[k] = total_mes.get(k, Decimal("0")) + Decimal(str(v))
        for (dep, cta), total in sorted(total_mes.items()):
            resto = total - cubierto.get((dep, cta), Decimal("0"))
            if abs(resto) < Decimal("0.005"):
                continue
            sin_posicion.append({
                "dept_code": dep,
                "dept_name": nombres.get(dep, dep),
                "depto_integrity": "",
                "cuenta": cta,
                "cuenta_nombre": rotulo_cuenta.get(cta, ""),
                "posicion": "",
                "posicion_nombre": "",
                "cuenta_completa": "",
                "fila": 0,
                "monto": round(float(resto), 2),
                "sin_posicion": True,
            })

    vistas = {_llave_fila(f) for f in filas}
    # Lo que una versión tiene y el mes NO: se dice, no se esconde. Un puesto
    # presupuestado que este mes no se pagó es justo lo que hay que ver.
    sin_pareja = []
    for sid, mapa in comparar.items():
        for (cta, llave), monto in sorted(mapa.items()):
            if (cta, llave) not in vistas and abs(monto) >= 0.005:
                sin_pareja.append({"scenario_id": sid, "version": etiquetas[sid],
                                   "cuenta": cta, "puesto": llave,
                                   "monto": round(monto, 2)})

    return {
        "anio": anio, "mes": mes, "precierre_id": pc.id,
        "subido": pc.creado_en.isoformat() if pc.creado_en else "",
        "hay_detalle": bool(filas),
        "motivo": "" if filas else "borrador_sin_detalle",
        "comparar": [{"scenario_id": sid, "version": etiquetas[sid],
                      "total": round(sum(m.values()), 2)}
                     for sid, m in comparar.items()],
        "sin_pareja": sin_pareja,
        "filas": [{
            "dept_code": f.destino_finplan,
            "dept_name": nombres.get(f.destino_finplan, f.destino_finplan),
            "depto_integrity": f.depto,
            "cuenta": str(f.cuenta_base or ""),
            "cuenta_nombre": rotulo_cuenta.get(str(f.cuenta_base or ""), ""),
            "posicion": f.posicion,
            # ⚠️ El NOMBRE de la posición, no la descripción del asiento.
            #
            # Owner, 2026-09-10: *«en algún lugar tenés el nombre de la
            # posición; que donde diga Name vaya la posición y no ese texto
            # repetitivo»*. Tenía razón: el mayor repite el concepto en cada
            # fila («SALARIES AND WAGES FRONT DESK AGENT», «OVERTIME FRONT DESK
            # AGENT»), y el concepto ya está en su propia columna.
            #
            # El orden importa: manda el CATÁLOGO —el mismo nombre para el
            # mismo puesto en todos los departamentos y meses—; si no lo tiene,
            # el que traiga el mayor; y si tampoco, se muestra el código solo.
            # Inventar un nombre sería peor que no tenerlo.
            "posicion_nombre": (catalogo_pos.get(f.posicion)
                                or del_mayor.get(f.posicion, "")),
            # La descripción cruda se conserva para el tooltip: es la prueba de
            # de dónde salió el número.
            "descripcion": f.descripcion,
            "cuenta_completa": f.cuenta,
            "fila": f.fila,
            "monto": round(float(f.mes_usd), 2),
            # Lo mismo en las otras versiones, apareado por cuenta + puesto.
            "otros": {sid: round(mapa.get(_llave_fila(f), 0.0), 2)
                      for sid, mapa in comparar.items()},
            "sin_posicion": False,
        } for f in filas] + [
            {**r, "otros": {sid: 0.0 for sid in comparar}} for r in sin_posicion],
        # El total incluye lo que ninguna posición cobra: así pega con Payroll
        # x Cuenta de un vistazo, que es lo que el owner pidió.
        "total": round(float(sum(f.mes_usd for f in filas))
                       + sum(r["monto"] for r in sin_posicion), 2),
        "total_con_posicion": round(float(sum(f.mes_usd for f in filas)), 2),
        "total_sin_posicion": round(sum(r["monto"] for r in sin_posicion), 2),
    }


def _llave_detalle(v) -> str:
    """El código de detalle, normalizado. `800` de un lado y `800` del otro.

    A diferencia del puesto, acá SÍ se aparea por código: el checkbook de gasto
    usa las subcuentas 800-810 (CLAUDE.md §19.2) y el tercer nivel de Integrity
    usa la misma numeración. Es la misma llave en los dos sistemas, no dos que
    se parecen.
    """
    t = str(v or "").strip()
    return str(int(t)) if t.isdigit() else t


async def _gasto_por_detalle_del_checkbook(
        db: AsyncSession, scenario_id: str, mes: int) -> dict[tuple[str, str, str], float]:
    """{(depto, cuenta, detalle): monto} del checkbook de OPEX de una versión."""
    col = ["jan", "feb", "mar", "apr", "may", "jun",
           "jul", "aug", "sep", "oct", "nov", "dec"][mes - 1]
    out: dict[tuple[str, str, str], float] = {}
    for e in (await db.execute(select(OpexEntry).where(
            OpexEntry.scenario_id == scenario_id))).scalars().all():
        v = float(getattr(e, col, 0) or 0)
        if not v:
            continue
        k = ((e.dept_code or "").strip(), (e.account_code or "").strip(),
             _llave_detalle(e.detail_code))
        out[k] = out.get(k, 0.0) + v
    return out


@router.get("/precierre/gasto-por-detalle/{anio}/{mes}/")
async def gasto_por_detalle(
    anio: int,
    mes: int,
    scenarios: str = Query("", description="ids a comparar, separados por coma"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """El gasto del mes abierto por DEPARTAMENTO · CUENTA · DETALLE.

    Owner, 2026-09-10: *«te vas al tercer nivel de gastos, `7310-0110-800`
    ROOMS / LAUNDRY AND DRY CLEANING […] por departamento y por detalle repetís
    la cuenta y me das un total por cuenta, pero hacés el split por detalle»* ·
    *«y un total de gasto por departamento»*.

    Es el gemelo de `planilla-por-posicion`: el mismo tercer segmento de la
    cuenta, que en las 6 es el puesto y en las 7 es el detalle del gasto.

    ## El renglón «(sin detalle)»

    ⚠️ **Cada cuenta cierra contra su propio total**, y cuando el detalle no
    llega —o se pasa— se agrega una línea con la diferencia en vez de dejar un
    subtotal que no cuadra. Sub-filas que no suman su total es el defecto más
    caro de un cuadro contable: se ve bien y no dice la verdad.

    ⚠️ **Hoy no hay ningún caso, y eso hay que decirlo.** Barridas las 1.020
    relaciones padre-hijo del archivo de agosto 2026 —todas las clases, todos
    los niveles— cuadran al centavo. Este renglón es una RED, no un hallazgo.

    Un primer barrido dijo que ocho no cuadraban, entre ellas `7105-0180` por
    $11.196,00. Estaba mal medido: sumaba la columna del mes en crudo, sin la
    regla de signo. En el mayor de Integrity un ingreso viene con el acumulado
    en negativo, y una DEVOLUCIÓN viene en positivo —`4000-0110-001` «Best
    Available Rate»—, así que sumar en crudo la contaba al revés y el padre
    parecía no cuadrar. Con `monto_mes`, que es la regla que usa el P&L, las
    ocho desaparecen.

    Queda escrito porque el error es fácil de repetir y cuesta caro: acusar de
    descuadre a un libro que está bien.
    """
    pc = (await db.execute(select(Precierre).where(
        Precierre.hotel_id == HOTEL_ID, Precierre.anio == anio,
        Precierre.mes == mes).order_by(
        Precierre.creado_en.desc()))).scalars().first()
    if pc is None:
        return {"anio": anio, "mes": mes, "precierre_id": None,
                "hay_detalle": False, "departamentos": [], "total": 0.0,
                "motivo": "sin_borrador"}

    detalle = (await db.execute(select(PrecierrePosicion).where(
        PrecierrePosicion.precierre_id == pc.id,
        PrecierrePosicion.cuenta_base >= 7000,
        PrecierrePosicion.cuenta_base < 8000).order_by(
        PrecierrePosicion.destino_finplan, PrecierrePosicion.cuenta_base,
        PrecierrePosicion.posicion))).scalars().all()

    # El total de cada cuenta sale del nivel `cuenta-departamento`, que es el
    # que suma el P&L. El detalle se compara CONTRA él, no al revés.
    totales_cuenta: dict[tuple[str, int], Decimal] = {}
    for f in (await db.execute(select(PrecierreFila).where(
            PrecierreFila.precierre_id == pc.id))).scalars().all():
        if f.cuenta_base and 7000 <= f.cuenta_base < 8000:
            k = (f.destino_finplan, f.cuenta_base)
            totales_cuenta[k] = totales_cuenta.get(k, Decimal("0")) + f.mes_usd

    nombres = {d.dept_code: d.dept_name for d in
               (await db.execute(select(DepartmentCatalog))).scalars().all()}

    # ── Las otras versiones, al lado ─────────────────────────────────────
    #
    # Owner, 2026-09-10: *«pongamos totales a la par, y la idea es tener algo
    # con qué comparar»*.
    #
    # Acá el apareo es EXACTO, no por nombre: el checkbook de gasto usa las
    # subcuentas 800-810 (CLAUDE.md §19.2) y el tercer nivel de Integrity usa
    # la misma numeración. Es la misma llave en los dos sistemas.
    comparar: dict[str, dict[tuple[str, str, str], float]] = {}
    etiquetas: dict[str, str] = {}
    for sid in [x.strip() for x in scenarios.split(",") if x.strip()]:
        esc = await db.get(Scenario, sid)
        if esc is None:
            continue
        etiquetas[sid] = f"{esc.year} · {esc.type} {esc.version}".strip()
        comparar[sid] = await _gasto_por_detalle_del_checkbook(db, sid, mes)

    deptos: dict[str, dict] = {}
    for f in detalle:
        dep = deptos.setdefault(f.destino_finplan, {
            "dept_code": f.destino_finplan,
            "dept_name": nombres.get(f.destino_finplan, f.destino_finplan),
            "cuentas": {}, "total": Decimal("0")})
        cta = dep["cuentas"].setdefault(f.cuenta_base, {
            "cuenta": str(f.cuenta_base), "filas": [], "detalle": Decimal("0")})
        llave = (f.destino_finplan, str(f.cuenta_base or ""),
                 _llave_detalle(f.posicion))
        cta["filas"].append({
            "detalle": f.posicion,
            "nombre": f.descripcion,
            "cuenta_completa": f.cuenta,
            "fila": f.fila,
            "monto": round(float(f.mes_usd), 2),
            "otros": {sid: round(m.get(llave, 0.0), 2)
                      for sid, m in comparar.items()},
        })
        cta["detalle"] += f.mes_usd

    # Las cuentas del P&L que NO tienen detalle: van igual, con una sola línea.
    # Esconderlas haría que el total por departamento no fuera el del P&L.
    for (dep_code, base), total in totales_cuenta.items():
        dep = deptos.setdefault(dep_code, {
            "dept_code": dep_code,
            "dept_name": nombres.get(dep_code, dep_code),
            "cuentas": {}, "total": Decimal("0")})
        dep["cuentas"].setdefault(base, {
            "cuenta": str(base), "filas": [], "detalle": Decimal("0")})

    # ── Y las cuentas que SOLO tiene el presupuesto ──────────────────────
    #
    # Owner, 2026-09-10: *«si no tiene detalle, al menos pongamos el total»*.
    #
    # Una cuenta presupuestada que este mes no se movió no aparecía en ningún
    # lado: ni su línea ni su plata. Eso hacía que la columna de Budget del
    # departamento fuera MENOR que el presupuesto de verdad — un número más
    # chico, sin nada que lo delatara, que es la peor forma de equivocarse.
    #
    # Ahora entran con el mes en cero y su total presupuestado al lado. Un
    # gasto presupuestado que no se ejecutó es justo lo que una revisión tiene
    # que ver.
    for mapa in comparar.values():
        for (dep_code, cta_code, _det) in mapa:
            if not dep_code or not cta_code.isdigit():
                continue
            dep = deptos.setdefault(dep_code, {
                "dept_code": dep_code,
                "dept_name": nombres.get(dep_code, dep_code),
                "cuentas": {}, "total": Decimal("0")})
            dep["cuentas"].setdefault(int(cta_code), {
                "cuenta": cta_code, "filas": [], "detalle": Decimal("0")})

    salida = []
    gran_total = Decimal("0")
    otros_gran: dict[str, float] = {}
    for dep_code in sorted(deptos):
        dep = deptos[dep_code]
        cuentas = []
        otros_dep: dict[str, float] = {}
        for base in sorted(dep["cuentas"]):
            cta = dep["cuentas"][base]
            total = totales_cuenta.get((dep_code, base), cta["detalle"])
            resto = total - cta["detalle"]
            filas = list(cta["filas"])
            if abs(resto) >= Decimal("0.005"):
                filas.append({"detalle": "", "nombre": "(sin detalle)",
                              "cuenta_completa": "", "fila": 0,
                              "monto": round(float(resto), 2),
                              "otros": {sid: 0.0 for sid in comparar}})
            # El total de la CUENTA en las otras versiones sale de sumar SU
            # cuenta entera, no las filas que aparearon: el checkbook puede
            # tener detalles que el mes no trajo, y esconderlos haría que la
            # columna no fuera el total del presupuesto.
            otros_cta = {sid: round(sum(
                v for (dc, ac, _d), v in m.items()
                if dc == dep_code and ac == cta["cuenta"]), 2)
                for sid, m in comparar.items()}
            cuentas.append({"cuenta": cta["cuenta"], "filas": filas,
                            "total": round(float(total), 2),
                            "otros": otros_cta})
            dep["total"] += total
            for sid, v in otros_cta.items():
                otros_dep[sid] = otros_dep.get(sid, 0.0) + v
        gran_total += dep["total"]
        for sid, v in otros_dep.items():
            otros_gran[sid] = otros_gran.get(sid, 0.0) + v
        salida.append({"dept_code": dep_code, "dept_name": dep["dept_name"],
                       "cuentas": cuentas,
                       "total": round(float(dep["total"]), 2),
                       "otros": {sid: round(v, 2) for sid, v in otros_dep.items()}})

    return {"anio": anio, "mes": mes, "precierre_id": pc.id,
            "hay_detalle": bool(detalle),
            "motivo": "" if detalle else "borrador_sin_detalle",
            "comparar": [{"scenario_id": sid, "version": etiquetas[sid],
                          "total": round(otros_gran.get(sid, 0.0), 2)}
                         for sid in comparar],
            "departamentos": salida, "total": round(float(gran_total), 2)}
