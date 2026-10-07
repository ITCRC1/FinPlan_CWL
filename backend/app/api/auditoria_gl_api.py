# -*- coding: utf-8 -*-
"""Subir el detalle del mayor y recibir las discrepancias.

Owner, 2026-10-05: *«que herramienta puedes hacerme para yo solo subir el
archivo en este detalle y me salgan automaticamente la auditoria con las
discrepancias»*.

**No toca el P&L.** No hay escenario, no se arma un total, no entra plata por
aca: la del mes sigue entrando por `integrity_final` → borrador → espejo →
ACTUAL. Esto es el LIBRO, para mirarlo.

**Lo que si hace desde el 2026-10-06 es guardarlo.** Owner: *«me gustaria que
quede guardado pero cada vez que se corra se le caiga encima […] es solo para
poder revisar detalladamente a nivel de detalle»*. Un mes por hotel; subir el
mismo mes otra vez lo reemplaza. Ver `app/models/mayor_movimiento.py`.

Por eso sigue sin pasar por `registro_de_subida`: ese registro trae
anti-reimport, y volver a subir el mismo mes es justamente lo que se quiere.
"""
from __future__ import annotations

from decimal import Decimal

import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, insert, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.engine import auditoria_gl
from app.engine import pl_engine
from app.errores import ErrorApi
from app.export.auditoria_gl_xlsx import QUE_MIRA, construir
from app.hotel_actual import HOTEL_ID
from app.importers.balance_comprobacion import leer

#: Los meses como los escribe Integrity, para rearmar el periodo del mes
#: guardado. El mismo nombre que el lector entiende de vuelta.
MESES_ES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
            "Agosto", "Setiembre", "Octubre", "Noviembre", "Diciembre"]
from app.models.mayor_movimiento import (COLUMNAS_A_COPIAR, MayorMovimiento,
                                         MayorMovimientoPrevio)

router = APIRouter(tags=["auditoria-gl"])

#: 25 MB. El de setiembre pesa 1,5 MB con 8.852 lineas; con margen de sobra para
#: un ano entero. Un archivo mas grande que esto no es el reporte que se espera.
MAXIMO = 25 * 1024 * 1024


async def _revisar(archivo: UploadFile, desde_clase: int):
    contenido = await archivo.read()
    if not contenido:
        raise ErrorApi(422, "auditoria.archivo_vacio")
    if len(contenido) > MAXIMO:
        raise ErrorApi(422, "auditoria.archivo_muy_grande")
    try:
        leido = leer(contenido)
    except Exception as e:                       # noqa: BLE001
        raise ErrorApi(422, "auditoria.no_se_pudo_leer", detalle=str(e)[:200]) from e
    if not leido.lineas:
        raise ErrorApi(422, "auditoria.sin_lineas")
    return leido, auditoria_gl.revisar(leido.lineas, desde_clase, leido.periodo)


async def _guardar(db: AsyncSession, leido, contenido: bytes,
                   archivo: str, usuario: str) -> dict:
    """Deja el mes guardado, pisando lo que hubiera de ese mismo mes.

    Un solo `DELETE` + el `INSERT`, en la transaccion de la peticion: o queda el
    mes nuevo entero, o queda el viejo entero. Nunca medio y medio, que con un
    libro contable es la peor forma de fallar.

    ⚠️ Se guardan TODAS las lineas, no solo las clases que se revisan. Ver el
    modelo: recortar ahorraba ~10 MB al año y dejaba un «eso no lo guardamos»
    para el dia que haga falta mirar un banco.

    Si el periodo del archivo no se entiende, NO se guarda y se dice. Adivinar
    el mes guardaria los asientos de setiembre bajo otro mes, y despues no hay
    como darse cuenta.
    """
    am = leido.anio_mes
    if am is None:
        return {"guardado": False, "motivo": "periodo_no_entendido",
                "periodo": leido.periodo}
    anio, mes = am
    # ── La vigente pasa a ser la ANTERIOR, antes de borrarla ─────────────────
    #
    # Owner, 2026-10-07: *«hicimos cambios en esta version… como se que cambio
    # con respecto a la primera»*. Sin esto, corregir un posteo y volver a subir
    # borraba el punto de comparacion y no habia forma de ver si el cambio quedo.
    #
    # ⚠️ Se guarda UNA anterior: la de antes de ESTA subida. La tercera subida
    # compara contra la segunda, no contra la primera. Eso es a proposito — ver
    # el modelo.
    #
    # Y la copia se hace en la base (`INSERT ... SELECT`), no trayendo 9.000
    # filas a Python para volver a mandarlas.
    ahora = datetime.now(timezone.utc)
    await db.execute(sa_delete(MayorMovimientoPrevio).where(
        MayorMovimientoPrevio.hotel_id == HOTEL_ID,
        MayorMovimientoPrevio.anio == anio, MayorMovimientoPrevio.mes == mes))
    cols = list(COLUMNAS_A_COPIAR)
    # El `id` se copia tal cual: la fila de origen se borra tres lineas mas
    # abajo, asi que no hay dos filas con el mismo id en ningun momento.
    await db.execute(insert(MayorMovimientoPrevio).from_select(
        ["id", *cols, "reemplazado_en"],
        select(MayorMovimiento.id, *[getattr(MayorMovimiento, c) for c in cols],
               literal(ahora)).where(
            MayorMovimiento.hotel_id == HOTEL_ID,
            MayorMovimiento.anio == anio, MayorMovimiento.mes == mes)))
    await db.execute(sa_delete(MayorMovimiento).where(
        MayorMovimiento.hotel_id == HOTEL_ID,
        MayorMovimiento.anio == anio, MayorMovimiento.mes == mes))
    sello = {
        "hotel_id": HOTEL_ID, "anio": anio, "mes": mes,
        "archivo": (archivo or "")[:255],
        "checksum": hashlib.sha256(contenido).hexdigest(),
        "subido_en": datetime.now(timezone.utc), "subido_por": (usuario or "")[:120],
    }
    for l in leido.lineas:
        db.add(MayorMovimiento(
            cuenta=l.cuenta[:40], seg1=l.seg1[:6], seg2=l.seg2[:6], seg3=l.seg3[:6],
            asiento=l.asiento[:20], linea=l.linea[:10], fecha=l.fecha[:20],
            descripcion=l.descripcion[:250], desc_asiento=l.desc_asiento[:250],
            origen=l.origen[:20], referencia=l.referencia[:120],
            num_doc=l.num_doc[:40],
            debito=_dec(l.debito), credito=_dec(l.credito), tc=_dec(l.tc),
            moneda=(l.moneda or "")[:10],
            # La del ENCABEZADO, no la del renglon: es la que dice si los montos
            # son colones o dolares. Sin ella el mes guardado no se vuelve a
            # leer bien.
            moneda_archivo=(l.moneda_archivo or "COL")[:10], **sello))
    await db.commit()
    return {"guardado": True, "anio": anio, "mes": mes,
            "movimientos": len(leido.lineas)}


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v or 0))
    except Exception:                                # noqa: BLE001
        return Decimal("0")


@router.post("/auditoria-gl/revisar/")
async def revisar(
    file: UploadFile = File(...),
    #: El owner revisa «las cuentas que empiezan con 4 en adelante». Se deja
    #: mover por si alguna vez quiere mirar el balance tambien.
    desde_clase: int = Query(4, ge=1, le=9),
    #: Guardar el mes es el comportamiento normal. Se puede apagar para mirar un
    #: archivo sin tocar lo que ya esta guardado — por ejemplo, para comparar dos
    #: exportes del mismo mes antes de decidir cual es el bueno.
    guardar: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    contenido = await file.read()
    await file.seek(0)
    leido, r = await _revisar(file, desde_clase)
    guardado = (await _guardar(db, leido, contenido, file.filename or "",
                               getattr(user, "email", "") or str(user or ""))
                if guardar else {"guardado": False, "motivo": "no_pedido"})
    return {
        "guardado": guardado,
        "archivo": file.filename,
        "titulo": leido.titulo,
        "periodo": r.periodo,
        "moneda": leido.moneda,
        "hojas": leido.hojas,
        "lineas_del_archivo": r.lineas_del_archivo,
        # Lineas que el archivo traia repetidas en otra hoja y NO se contaron.
        # Viaja siempre: que el export repita es un dato del archivo del owner,
        # y callarlo dejaria el numero de lineas sin explicacion.
        "lineas_repetidas": leido.repetidas,
        "lineas_revisadas": r.lineas_revisadas,
        "lineas_senaladas": r.lineas_senaladas,
        "monto_en_revision_crc": r.monto_en_revision_crc,
        "por_regla": r.por_regla,
        "por_severidad": r.por_severidad,
        # ⚠️ El corte por tipo de cuenta. Se quedo fuera de la respuesta y la
        # pantalla lo lee sin preguntar (`Object.entries(data.por_grupo)`), asi
        # que TODA subida exitosa terminaba en «Esta pantalla no se pudo
        # dibujar · Cannot convert undefined or null to object» — owner,
        # 2026-10-06. El motor siempre lo calculo; faltaba mandarlo.
        "por_grupo": r.por_grupo,
        # Solo lo que esta regla encontro: explicar reglas que no dispararon
        # llena la pantalla de texto que no corresponde a nada en la tabla.
        "que_mira": {k: v for k, v in QUE_MIRA.items() if k in r.por_regla},
        "hallazgos": [h.dict() for h in r.hallazgos],
    }


@router.post("/auditoria-gl/excel/")
async def excel(
    file: UploadFile = File(...),
    desde_clase: int = Query(4, ge=1, le=9),
    user=Depends(get_current_user),
):
    """El mismo analisis, como hoja de trabajo para revisar fuera de la pantalla."""
    _leido, r = await _revisar(file, desde_clase)
    nombre = "Auditoria_Detalle_{}.xlsx".format(
        (r.periodo or "mayor").replace(" ", "").replace("-", "_"))
    return Response(
        construir(r, archivo=file.filename or ""),
        media_type=("application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet"),
        headers={"Content-Disposition": 'attachment; filename="{}"'.format(nombre)})


# ── El mayor guardado: leerlo ────────────────────────────────────────────────

@router.get("/mayor/meses/")
async def meses_guardados(db: AsyncSession = Depends(get_db),
                          _=Depends(get_current_user)):
    """Qué meses tienen el libro guardado, y de qué archivo salió cada uno.

    La pantalla lo necesita para no ofrecer un mes vacío: «setiembre no está
    subido» es una respuesta; una tabla en blanco no.
    """
    from sqlalchemy import func, select

    filas = (await db.execute(
        select(MayorMovimiento.anio, MayorMovimiento.mes,
               func.count().label("movimientos"),
               func.max(MayorMovimiento.archivo).label("archivo"),
               func.max(MayorMovimiento.subido_en).label("subido_en"))
        .where(MayorMovimiento.hotel_id == HOTEL_ID)
        .group_by(MayorMovimiento.anio, MayorMovimiento.mes)
        .order_by(MayorMovimiento.anio.desc(), MayorMovimiento.mes.desc()))).all()
    return {"meses": [
        {"anio": a, "mes": m, "movimientos": n, "archivo": arch,
         "subido_en": sub.isoformat() if sub else None}
        for a, m, n, arch, sub in filas]}


@router.get("/mayor/{anio}/{mes}/movimientos/")
async def movimientos(
    anio: int,
    mes: int,
    cuenta: str = Query("", description="cuenta completa o su raíz: 7310 o 7310-0110"),
    depto: str = Query("", description="código de departamento (seg2)"),
    q: str = Query("", description="texto en la descripción, el asiento o la referencia"),
    limite: int = Query(500, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Los asientos que forman una cuenta de un mes.

    Owner, 2026-10-06: *«es solo para poder revisar detalladamente a nivel de
    detalle»* · *«máximo detalle y descripción del asiento»*.

    `cuenta` acepta la raíz: `7310` trae la cuenta en todos los departamentos y
    `7310-0110` sólo la de Habitaciones. Es la forma en que se lee un cuadro —
    se ve un número por cuenta y se quiere abrir ÉSE.

    ⚠️ **El total viaja aparte del listado.** `limite` recorta lo que se dibuja,
    no lo que se suma: si se sumara lo dibujado, una cuenta con 600 asientos
    mostraría un total que no es el de la cuenta, y el cuadro mentiría sin
    avisar. Es el mismo cuidado que `planilla-por-posicion`.
    """
    from sqlalchemy import func, or_, select

    if not 1 <= mes <= 12:
        raise ErrorApi(422, "precierre.mes_invalido")
    cond = [MayorMovimiento.hotel_id == HOTEL_ID,
            MayorMovimiento.anio == anio, MayorMovimiento.mes == mes]
    if cuenta:
        cond.append(MayorMovimiento.cuenta.like(f"{cuenta.strip()}%"))
    if depto:
        cond.append(MayorMovimiento.seg2 == depto.strip())
    if q:
        patron = f"%{q.strip()}%"
        cond.append(or_(MayorMovimiento.descripcion.ilike(patron),
                        MayorMovimiento.desc_asiento.ilike(patron),
                        MayorMovimiento.referencia.ilike(patron),
                        MayorMovimiento.asiento.ilike(patron)))

    tot = (await db.execute(select(
        func.count(), func.coalesce(func.sum(MayorMovimiento.debito), 0),
        func.coalesce(func.sum(MayorMovimiento.credito), 0)).where(*cond))).one()
    filas = (await db.execute(
        select(MayorMovimiento).where(*cond)
        .order_by(MayorMovimiento.cuenta, MayorMovimiento.asiento,
                  MayorMovimiento.linea)
        .limit(limite))).scalars().all()
    return {
        "anio": anio, "mes": mes,
        "hay_mes": bool(tot[0]) or bool((await db.execute(select(func.count()).where(
            MayorMovimiento.hotel_id == HOTEL_ID,
            MayorMovimiento.anio == anio,
            MayorMovimiento.mes == mes))).scalar()),
        "movimientos": int(tot[0]),
        "debito": float(tot[1]), "credito": float(tot[2]),
        "neto": float(tot[1]) - float(tot[2]),
        "recortado": int(tot[0]) > limite,
        "filas": [{
            "cuenta": f.cuenta, "seg2": f.seg2, "seg3": f.seg3,
            "asiento": f.asiento, "linea": f.linea, "fecha": f.fecha,
            "descripcion": f.descripcion, "desc_asiento": f.desc_asiento,
            "origen": f.origen, "referencia": f.referencia, "num_doc": f.num_doc,
            "debito": float(f.debito), "credito": float(f.credito),
            "neto": float(f.debito) - float(f.credito),
            "tc": float(f.tc), "moneda": f.moneda,
        } for f in filas],
    }


def _orden_cat(nombre: str) -> int:
    """Donde va cada categoria: el orden del numero de cuenta, 1 -> 9."""
    try:
        return auditoria_gl.ORDEN_CATEGORIAS.index(nombre)
    except ValueError:
        return len(auditoria_gl.ORDEN_CATEGORIAS)


@router.get("/mayor/{anio}/{mes}/cambios/")
async def cambios(
    anio: int,
    mes: int,
    umbral: float = Query(0.005, description="diferencia mínima para reportarla"),
    limite: int = Query(400, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Qué cambió entre la subida vigente y la anterior del mismo mes.

    Owner, 2026-10-07: *«hicimos cambios en esta versión… cómo sé qué cambió con
    respecto a la primera. Tendrías que guardar 2 versiones para poder comparar
    el nuevo versus el anterior y ver si los cambios quedaron»*.

    Contesta en dos niveles, porque son dos preguntas distintas:

    * **por cuenta** — «¿se movió la plata de donde la quería mover?». Es el
      nivel al que se piden las correcciones y al que se verifican.
    * **por asiento** — «¿qué movimiento entró, salió o cambió de monto?». Es el
      nivel al que se va a Integrity a mirar.

    ⚠️ **El asiento se compara por `(cuenta, asiento, línea)`**, que es lo que
    identifica un renglón del mayor. Un renglón que cambia de CUENTA sale como
    uno que desapareció y otro que apareció — y así debe ser: es exactamente lo
    que pasa cuando se reclasifica, y verlo en los dos lados es la prueba de que
    la reclasificación quedó.

    Si no hay subida anterior —la primera vez que se sube el mes— se dice, en
    vez de devolver «no cambió nada», que se leería como que el archivo es igual.
    """
    if not 1 <= mes <= 12:
        raise ErrorApi(422, "precierre.mes_invalido")

    # Una sola vez, fuera de los dos bucles.
    minimo = _dec(umbral)

    async def _traer(Modelo):
        return (await db.execute(select(Modelo).where(
            Modelo.hotel_id == HOTEL_ID, Modelo.anio == anio,
            Modelo.mes == mes))).scalars().all()

    hoy = await _traer(MayorMovimiento)
    antes = await _traer(MayorMovimientoPrevio)
    if not hoy:
        return {"anio": anio, "mes": mes, "hay": False, "motivo": "mes_no_subido"}
    if not antes:
        return {"anio": anio, "mes": mes, "hay": False, "motivo": "sin_subida_anterior",
                "vigente": {"archivo": hoy[0].archivo,
                            "subido_en": hoy[0].subido_en.isoformat() if hoy[0].subido_en else None,
                            "movimientos": len(hoy)}}

    def neto(f):
        return _dec(f.debito) - _dec(f.credito)

    # ── Por cuenta ───────────────────────────────────────────────────────────
    def por_cuenta(filas):
        d = {}
        for f in filas:
            d[f.cuenta] = d.get(f.cuenta, Decimal("0")) + neto(f)
        return d

    a_cta, h_cta = por_cuenta(antes), por_cuenta(hoy)
    cuentas = []
    for cta in sorted(set(a_cta) | set(h_cta)):
        va, vh = a_cta.get(cta, Decimal("0")), h_cta.get(cta, Decimal("0"))
        if abs(vh - va) <= minimo:
            continue
        cuentas.append({"cuenta": cta,
                        "categoria": auditoria_gl.categoria_de(cta),
                        "antes": float(va), "ahora": float(vh),
                        "diferencia": float(vh - va)})
    # ⚠️ Por NUMERO DE CUENTA, no por monto. Owner, 2026-10-07: *«debe ir por
    # cuenta del 1 al 8 y debe ir por categoria»*. Ordenado por monto el cuadro
    # se lee como una lista de sorpresas; ordenado por cuenta se lee como el
    # mayor, que es contra lo que el owner lo compara.
    cuentas.sort(key=lambda x: (_orden_cat(x["categoria"]), x["cuenta"]))

    # ── Por asiento ──────────────────────────────────────────────────────────
    llave = lambda f: (f.cuenta, f.asiento, f.linea)
    ia = {llave(f): f for f in antes}
    ih = {llave(f): f for f in hoy}
    def fila(f, que):
        return {"que": que, "cuenta": f.cuenta,
                "categoria": auditoria_gl.categoria_de(f.cuenta),
                "asiento": f.asiento, "linea": f.linea,
                "fecha": f.fecha, "descripcion": f.descripcion,
                "desc_asiento": f.desc_asiento, "origen": f.origen,
                "neto": float(neto(f))}
    movs = []
    for k in sorted(set(ia) | set(ih)):
        a, h = ia.get(k), ih.get(k)
        if a is None:
            movs.append({**fila(h, "aparecio"), "antes": 0.0,
                         "ahora": float(neto(h)), "diferencia": float(neto(h))})
        elif h is None:
            movs.append({**fila(a, "desaparecio"), "antes": float(neto(a)),
                         "ahora": 0.0, "diferencia": float(-neto(a))})
        elif abs(neto(h) - neto(a)) > minimo:
            movs.append({**fila(h, "cambio_de_monto"), "antes": float(neto(a)),
                         "ahora": float(neto(h)),
                         "diferencia": float(neto(h) - neto(a))})
    movs.sort(key=lambda x: (_orden_cat(x["categoria"]), x["cuenta"],
                            x["asiento"], x["linea"]))

    def resumen(filas):
        return {"movimientos": len(filas),
                "debito": float(sum(_dec(f.debito) for f in filas)),
                "credito": float(sum(_dec(f.credito) for f in filas)),
                "archivo": filas[0].archivo,
                "subido_en": filas[0].subido_en.isoformat() if filas[0].subido_en else None}

    ra, rh = resumen(antes), resumen(hoy)
    # El subtotal de cada categoria. Viaja calculado y no se suma en la
    # pantalla: el listado puede venir recortado, y un subtotal que suma lo
    # dibujado no seria el de la categoria.
    por_cat: dict[str, dict] = {}
    for c in cuentas:
        d = por_cat.setdefault(c["categoria"],
                               {"categoria": c["categoria"], "cuentas": 0,
                                "antes": 0.0, "ahora": 0.0, "diferencia": 0.0})
        d["cuentas"] += 1
        for k in ("antes", "ahora", "diferencia"):
            d[k] += c[k]
    categorias = sorted(por_cat.values(), key=lambda x: _orden_cat(x["categoria"]))
    return {
        "categorias": categorias,
        "anio": anio, "mes": mes, "hay": True,
        "anterior": {**ra, "reemplazado_en": (antes[0].reemplazado_en.isoformat()
                                              if antes[0].reemplazado_en else None)},
        "vigente": rh,
        "diferencia": {"movimientos": rh["movimientos"] - ra["movimientos"],
                       "debito": rh["debito"] - ra["debito"],
                       "credito": rh["credito"] - ra["credito"]},
        # ⚠️ El conteo viaja aparte del listado recortado: si la pantalla contara
        # lo que dibuja, un mes con 600 cambios mostraría un total que no es.
        "cuentas_que_cambiaron": len(cuentas),
        "movimientos_que_cambiaron": len(movs),
        "cuentas": cuentas[:limite],
        "movimientos": movs[:limite],
        "recortado": len(movs) > limite or len(cuentas) > limite,
    }


@router.get("/auditoria-gl/{anio}/{mes}/")
async def auditoria_guardada(
    anio: int,
    mes: int,
    desde_clase: int = Query(4, ge=1, le=9),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Los hallazgos del mes YA SUBIDO, recalculados desde el mayor guardado.

    Owner, 2026-10-07: *«me gustaría que el análisis de diferencias una vez que
    se suba no desaparezca, que quede ahí hasta subir la otra versión… que sirva
    para validación y revisión… veo que todo desaparece una vez que uno sale y
    entra otra vez»*.

    Tenía razón: la pantalla no cargaba nada al entrar. Los hallazgos vivían en
    la memoria del navegador desde la subida, y salir de la pantalla los borraba.

    ## Se RECALCULAN, no se guardan

    Podría haber guardado los hallazgos en una tabla. No: se recalculan del mayor
    almacenado, que ya está ahí desde la migración 151. Así hay **una sola
    fuente** — el libro — y el día que se le agregue una regla a la auditoría,
    los meses viejos la aplican sin volver a subir nada. Guardar los hallazgos
    los habría congelado con las reglas del día que se subió el archivo.

    ⚠️ Por eso hacía falta `moneda_archivo` (migración 153): sin saber si los
    montos guardados son colones o dólares, los montos de los hallazgos saldrían
    multiplicados por el tipo de cambio.
    """
    from app.importers.balance_comprobacion import Linea

    if not 1 <= mes <= 12:
        raise ErrorApi(422, "precierre.mes_invalido")
    filas = (await db.execute(select(MayorMovimiento).where(
        MayorMovimiento.hotel_id == HOTEL_ID, MayorMovimiento.anio == anio,
        MayorMovimiento.mes == mes))).scalars().all()
    if not filas:
        return {"anio": anio, "mes": mes, "hay": False, "motivo": "mes_no_subido"}

    lineas = [Linea(
        cuenta=f.cuenta, seg1=f.seg1, seg2=f.seg2, seg3=f.seg3,
        asiento=f.asiento, linea=f.linea, fecha=f.fecha,
        descripcion=f.descripcion, desc_asiento=f.desc_asiento,
        origen=f.origen, referencia=f.referencia, num_doc=f.num_doc,
        tc=float(f.tc or 0), moneda=f.moneda,
        debito=float(f.debito or 0), credito=float(f.credito or 0),
        moneda_archivo=f.moneda_archivo or "COL") for f in filas]
    periodo = f"{MESES_ES[mes - 1]} - {anio}"
    r = auditoria_gl.revisar(lineas, desde_clase, periodo)
    cabeza = filas[0]
    return {
        "anio": anio, "mes": mes, "hay": True,
        "de_lo_guardado": True,
        "archivo": cabeza.archivo,
        "moneda": cabeza.moneda_archivo,
        "subido_en": cabeza.subido_en.isoformat() if cabeza.subido_en else None,
        "subido_por": cabeza.subido_por,
        "periodo": r.periodo,
        "lineas_del_archivo": r.lineas_del_archivo,
        "lineas_revisadas": r.lineas_revisadas,
        "lineas_senaladas": r.lineas_senaladas,
        "monto_en_revision_crc": r.monto_en_revision_crc,
        "por_regla": r.por_regla,
        "por_severidad": r.por_severidad,
        "por_grupo": r.por_grupo,
        "que_mira": {k: v for k, v in QUE_MIRA.items() if k in r.por_regla},
        "hallazgos": [h.dict() for h in r.hallazgos],
    }


# ── AUDIT INTEGRAL: el mes a máximo detalle, contra Budget y Forecast ────────

#: El orden en que el owner lee este cuadro. Owner, 2026-10-07: *«por
#: departamento y categorías de cuentas, a decir ingresos, costos, planilla,
#: opex, gastos dueños»*.
#:
#: ⚠️ Usa `GRUPOS` —la categorización de los HALLAZGOS, con la 7 y la 8
#: separadas— y NO `CATEGORIAS`, que junta 7 con 8 y agrega balance y
#: estadísticas. Acá se mira el estado de resultados, así que la 8 es su propia
#: línea («gastos dueños») y el balance no entra. Las dos conviven a propósito;
#: ver la nota en `auditoria_gl`.
#: 4 Ingresos, 5 Costos, 6 Payroll, 7 Opex, 8 Property Expenses — el orden de
#: la clase, tal cual lo dicto el owner el 2026-10-07.
ORDEN_INTEGRAL = ("Ingresos", "Costos", "Planilla", "Opex", "Gastos de propiedad")


def _usd(f) -> float:
    """El movimiento en DOLARES, venga el archivo como venga.

    La misma regla que `balance_comprobacion.Linea.monto_usd`, aplicada a la
    fila guardada: si el archivo venia en dolares, la columna YA es dolares; si
    venia en colones, se divide por el tipo de cambio del asiento.
    """
    monto = float(f.debito or 0) - float(f.credito or 0)
    if (f.moneda_archivo or "COL").upper().startswith("DOL"):
        return monto
    tc = float(f.tc or 0)
    return monto / tc if tc else 0.0


def _puente_de_departamentos() -> dict[str, str]:
    """`{departamento de Integrity: departamento de FinPlan}`.

    ⚠️ **Sin el puente la comparacion sale mal**, y el diagnostico tambien: el
    2026-09-11 una pasada sin puente dio una lista larga de fallbacks falsos, y
    con el puente aplicado quedaban exactamente dos.

    Se lee de la semilla, que es donde vive, y se cachea: son 34 filas que no
    cambian entre peticiones.
    """
    global _PUENTE
    if _PUENTE is None:
        import json
        import pathlib

        ruta = (pathlib.Path(__file__).resolve().parents[1]
                / "seed_data" / HOTEL_ID / "mapd_integrity.json")
        try:
            datos = json.loads(ruta.read_text(encoding="utf-8"))["departamentos"]
            _PUENTE = {d["codigo"]: d["destino_finplan"] for d in datos}
        except Exception:                                # noqa: BLE001
            # Sin puente el cuadro sale igual, con los departamentos crudos de
            # Integrity. Que falte el archivo no puede tumbar la pantalla.
            _PUENTE = {}
    return _PUENTE


_PUENTE: dict[str, str] | None = None


async def _por_cuenta_del_escenario(db, escenario, mes: int) -> dict[tuple, float]:
    """`{(depto, cuenta): monto}` de un escenario para un mes.

    Usa el MISMO camino que el motor del P&L —`actual_rows_for_month` para lo
    importado, el checkbook para lo que se construye en la app— para que la
    comparación sea contra lo que el sistema reporta y no contra otra lectura.
    """
    from app.engine import recalculate as recalc

    filas = []
    if (getattr(escenario, "source_mode", "imported") or "imported") != "checkbook":
        filas = await recalc.actual_rows_for_month(db, escenario.id, mes)
        filas = [f for f in filas if f.get("amount")]
    if not filas:
        filas = await recalc.checkbook_account_rows_for_month(db, escenario.id, mes)
    fuera: dict[tuple, float] = {}
    for f in filas:
        k = (pl_engine.consolidate_dept(f.get("dept_code") or ""),
             str(f.get("account_code") or ""))
        fuera[k] = fuera.get(k, 0.0) + float(f.get("amount") or 0)
    return fuera


def _rotulo_de_cuenta(cuenta, dept, catalogo, crudo_del_asiento):
    """Cómo se llama una cuenta en el Audit Integral. **Nunca vacío.**

    ⚠️ El orden es al revés que en el resto del sistema, y a propósito. El
    `nombre_de_cuenta` general prefiere «lo que trajo el asiento» porque allá
    eso ES el nombre de la cuenta —viene del mapeo—. Acá viene del mayor, y en
    el mayor ese campo es *«lo que escribió quien registró»*: la 4000 salía
    «Adjusment Room Charge» y las diez cuentas de planilla, todas, «ORDINARIO».

    Así que primero el catálogo (`account_mapping`), después los conceptos de
    nómina —ese camino ya está dentro de `nombre_de_cuenta`—, y la descripción
    del asiento sólo si no quedó nada mejor: mal rótulo es mejor que ninguno.
    """
    from app.nombres_cuenta import limpiar_nombre, nombre_de_cuenta

    nombre = nombre_de_cuenta(cuenta, None, catalogo, dept)
    if nombre == f"Cuenta {cuenta}":        # ni el catálogo ni los conceptos
        return limpiar_nombre(crudo_del_asiento) or nombre
    return nombre


async def _nombres_del_detalle(db, scenario_ids):
    """Devuelve `nombre(dept, cuenta, detalle)` → cómo se llama ese detalle.

    El «detalle» es el tercer segmento, y qué nombra depende de la clase:

    * **Clase 6** — el PUESTO. `501` es «FRONT DESK AGENT / RECEPTIONIST», y el
      diccionario que lo dice es el mismo que usa el Pre-Cierre
      (`posiciones_integrity.json`), para que el puesto no se llame de dos
      formas en dos pantallas. No depende del departamento: un `501` es el
      mismo puesto en todos.
    * **Clase 7** — el detalle del gasto, y el que lo nombra es el CHECKBOOK:
      `7065/801` es «Utensilios de limpieza» porque así lo escribió quien armó
      el presupuesto. Que el nombre salga justo de donde se compara es lo que
      se quiere: nombra la línea a la que la plata debería haber ido.
    * **Las demás** — no hay diccionario, y devuelve `""` para que el que
      llama use la descripción del asiento, que ahí sí sirve: en las 4 dice
      «Accomodation», «Adjustement Extra Pax».

    Se devuelve una función y no un diccionario porque las dos fuentes se
    buscan con llaves distintas —el checkbook por departamento, el puesto
    sin él— y armar una sola tabla obligaría a repetir los 17 conceptos de
    planilla por cada uno de los 27 departamentos.
    """
    from app.api.precierre_api import _catalogo_de_posiciones
    from app.models.opex_entry import OpexEntry

    # Clase 7, del checkbook de los escenarios que se están comparando.
    del_checkbook: dict[tuple[str, str, str], str] = {}
    ids = [x for x in (scenario_ids or []) if x]
    if ids:
        filas = (await db.execute(
            select(OpexEntry.dept_code, OpexEntry.account_code,
                   OpexEntry.detail_code, OpexEntry.detail_desc)
            .where(OpexEntry.scenario_id.in_(ids)))).all()
        for dept, cta, det, desc in filas:
            desc = (desc or "").strip()
            if not desc:
                continue
            # `consolidate_dept` porque el cuadro muestra el departamento
            # consolidado, igual que el actual.
            del_checkbook.setdefault(
                (pl_engine.consolidate_dept(dept or ""), cta or "", det or ""), desc)

    posiciones = _catalogo_de_posiciones() or {}

    def nombre(dept: str, cuenta: str, detalle: str) -> str:
        if not detalle:
            return ""
        if (cuenta or "").startswith("6"):
            return posiciones.get(str(detalle), "")
        return del_checkbook.get((dept, cuenta, detalle), "")

    return nombre


@router.get("/mayor/{anio}/{mes}/integral/")
async def audit_integral(
    anio: int,
    mes: int,
    scenarios: str = Query("", description="ids a comparar, separados por coma"),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """El mes real a máximo detalle, depurado, contra el Budget y el Forecast.

    Owner, 2026-10-07: *«aprovechando que hay máximo detalle en las cuentas de
    resultados por cuenta, se pueda generar un tipo de revisión versus budget o
    forecast a máximo detalle por departamento y categorías de cuentas […] si
    hay algo que no debería estar ahí, a máximo detalle, sólo copio y mando la
    nota para que reclasifiquen»*.

    ## Qué significa «depurado»

    Del mayor guardado entran **sólo las clases 4 a 8** —el estado de
    resultados—. El balance (1-3) y las estadísticas (9) quedan fuera: no se
    comparan contra un presupuesto.

    Y se aplican las dos reglas que el sistema ya usa para leer ese archivo, que
    son las que hacen que los números coincidan con el cierre:

    * **El signo** (`integrity_final.signo_de`): en el mayor un ingreso es un
      crédito, o sea negativo. La `4999` es la excepción, porque son las
      contrapartidas de reparto y ya vienen bien.
    * **El puente de departamentos**: el mayor trae el departamento de Integrity
      y el presupuesto el de FinPlan. Sin el puente la comparación sale mal — y
      el diagnóstico también: medido el 2026-09-11, sin puente aparecían
      fallbacks falsos a montones.

    ## Por qué el Actual sale de acá y no del Pre-Cierre

    Porque el Pre-Cierre llega a la cuenta y se acaba, y lo que el owner quiere
    es el asiento: *«sólo copio y mando la nota para que reclasifiquen»*. El
    mayor guardado tiene el asiento, la fecha y el concepto.

    ⚠️ **Esto NO cambia de dónde sale la plata del cierre.** El P&L sigue
    saliendo del Pre-Cierre; esto es una lupa que compara. Verificado contra la
    pantalla de setiembre 2026: Rooms 20.259,00 contra 20.258,87, A&B 7.448,63
    contra 7.447,27 — las diferencias son centavos del tipo de cambio por
    asiento.
    """
    from app.api.auditoria_api import _catalogo_gl
    from app.importers.integrity_final import signo_de
    from app.models.department_catalog import DepartmentCatalog
    from app.models.scenario import Scenario
    from app.nombres_cuenta import limpiar_nombre

    if not 1 <= mes <= 12:
        raise ErrorApi(422, "precierre.mes_invalido")
    filas = (await db.execute(select(MayorMovimiento).where(
        MayorMovimiento.hotel_id == HOTEL_ID, MayorMovimiento.anio == anio,
        MayorMovimiento.mes == mes))).scalars().all()
    if not filas:
        return {"anio": anio, "mes": mes, "hay": False, "motivo": "mes_no_subido"}

    puente = _puente_de_departamentos()
    deptos = {d.dept_code: d.dept_name
              for d in (await db.execute(select(DepartmentCatalog))).scalars().all()}
    # El catálogo de nombres del GL. Owner, 2026-10-07: *«no tengo el nombre
    # real del GL»* — en la pantalla la 4000 salía como «Adjusment Room Charge»
    # y las 6000 todas como «ORDINARIO».
    #
    # ⚠️ Eso NO es el nombre de la cuenta: es lo que escribió quien registró el
    # asiento (`MayorMovimiento.descripcion`, «lo que escribio quien registro»).
    # El nombre sale de `account_mapping`, que es el catálogo real y está en
    # producción —1.098 reglas sobre 27 departamentos, y toda cuenta del ACTUAL
    # 2026 tiene una—. `accounts` y `payroll_accounts` están VACÍOS en
    # producción, así que no servían (medido; ver `auditoria_api._catalogo_gl`).
    catalogo = await _catalogo_gl(db)

    # ── El actual, del mayor ────────────────────────────────────────────────
    # ⚠️ El grano es (departamento, cuenta, DETALLE). Owner, 2026-10-07: *«la
    # regla de orden es Departamento, si es 4-Ingresos, 5-Costos, 6-Payroll,
    # 7-Opex, 8-Property Expenses; e internamente por Detalle»*.
    #
    # El «detalle» es el tercer segmento de la cuenta, que en las 6 es el puesto
    # y en las 7 el detalle del gasto — el mismo eje que abre `Opex by Detail`.
    real: dict[tuple, dict] = {}
    por_cta: dict[tuple, dict] = {}
    for f in filas:
        if (f.seg1 or "")[:1] not in "45678":
            continue
        dep = pl_engine.consolidate_dept(puente.get(f.seg2, f.seg2))
        monto = signo_de(f.seg1) * _usd(f)
        k = (dep, f.seg1, f.seg3 or "")
        d = real.setdefault(k, {"monto": 0.0, "lineas": 0,
                                "nombre": f.descripcion or ""})
        d["monto"] += monto
        d["lineas"] += 1
        # El total por CUENTA, que es el nivel donde SÍ se compara.
        c = por_cta.setdefault((dep, f.seg1), {"monto": 0.0, "lineas": 0,
                                               "nombre": f.descripcion or ""})
        c["monto"] += monto
        c["lineas"] += 1

    # ── Las versiones contra las que se compara ─────────────────────────────
    ids = [x for x in (scenarios or "").split(",") if x.strip()]
    versiones = []
    for sid in ids:
        esc = await db.get(Scenario, sid.strip())
        if esc is None:
            continue
        versiones.append({
            "scenario_id": esc.id,
            "escenario": f"{esc.type} {esc.version} {esc.year}",
            "por_cuenta": await _por_cuenta_del_escenario(db, esc, mes),
        })

    # ── El cuadro ───────────────────────────────────────────────────────────
    #
    # Dos niveles de fila: la CUENTA, que es donde se compara, y su DETALLE
    # debajo, que sólo trae el actual.
    #
    # ⚠️ **La comparación NO baja al detalle, y es a propósito.** El presupuesto
    # numera sus detalles por su cuenta, así que apareados darían una
    # correspondencia inventada. Lo exacto —y lo que se compara— son los totales
    # por CUENTA. Es lo mismo que ya hace `Opex by Detail`, y está escrito ahí
    # por la misma razón.
    nombres_det = await _nombres_del_detalle(db, [v["scenario_id"] for v in versiones])
    llaves_cta = set(por_cta) | {k for v in versiones for k in v["por_cuenta"]}
    cuadro = []
    for dep, cta in llaves_cta:
        r = por_cta.get((dep, cta))
        montos = {v["scenario_id"]: v["por_cuenta"].get((dep, cta), 0.0)
                  for v in versiones}
        if not r and not any(abs(x) > 0.005 for x in montos.values()):
            continue
        detalles = sorted(
            ({"detalle": d3,
              "nombre": nombres_det(dep, cta, d3) or limpiar_nombre(v["nombre"]),
              "actual": round(v["monto"], 2), "lineas": v["lineas"]}
             for (dd, cc, d3), v in real.items() if dd == dep and cc == cta),
            key=lambda x: x["detalle"])
        cuadro.append({
            "grupo": auditoria_gl.grupo_de(cta),
            "dept_code": dep, "dept_name": deptos.get(dep, dep),
            "cuenta": cta,
            "nombre": _rotulo_de_cuenta(cta, dep, catalogo, (r or {}).get("nombre")),
            "actual": round((r or {}).get("monto", 0.0), 2),
            "lineas": (r or {}).get("lineas", 0),
            "versiones": {k: round(x, 2) for k, x in montos.items()},
            "detalles": detalles,
        })
    # El orden del owner: DEPARTAMENTO primero, y adentro la clase 4 -> 8.
    orden = {g: i for i, g in enumerate(ORDEN_INTEGRAL)}
    cuadro.sort(key=lambda x: (x["dept_code"], orden.get(x["grupo"], 9), x["cuenta"]))
    cabeza = filas[0]
    return {
        "anio": anio, "mes": mes, "hay": True,
        "archivo": cabeza.archivo, "moneda": cabeza.moneda_archivo,
        "subido_en": cabeza.subido_en.isoformat() if cabeza.subido_en else None,
        "orden_grupos": list(ORDEN_INTEGRAL),
        "versiones": [{"scenario_id": v["scenario_id"], "escenario": v["escenario"]}
                      for v in versiones],
        "filas": cuadro,
    }


@router.get("/mayor/{anio}/{mes}/integral/asientos/")
async def asientos_de_la_cuenta(
    anio: int,
    mes: int,
    dept: str = Query(..., description="departamento FinPlan, como sale en el cuadro"),
    cuenta: str = Query(..., description="cuenta base de 4 dígitos"),
    limite: int = Query(300, ge=1, le=3000),
    db: AsyncSession = Depends(get_db),
    _=Depends(get_current_user),
):
    """Los asientos que forman UNA celda del Audit Integral.

    Owner, 2026-10-07: *«favor dar la opción para que me abra los asientos,
    expand, y ver el detalle ahí mismo»*.

    ⚠️ **No sirve el filtro del visor de movimientos**, y por una razón que no
    se ve: el cuadro muestra el departamento de **FinPlan** —`0121 Private
    Bar`— y el mayor guarda el de **Integrity** —`0128`—. Filtrar por el que se
    ve en pantalla no traería nada, o peor, traería lo de otro departamento.

    Acá se aplica el MISMO camino que arma el cuadro —puente de departamentos y
    después `consolidate_dept`— para que lo que se abre sume exactamente lo que
    se ve en la fila. Y el monto lleva el signo aplicado (`signo_de`), por lo
    mismo: sin él, las líneas de un ingreso sumarían al revés que su total.
    """
    from app.importers.integrity_final import signo_de

    if not 1 <= mes <= 12:
        raise ErrorApi(422, "precierre.mes_invalido")
    puente = _puente_de_departamentos()
    filas = (await db.execute(select(MayorMovimiento).where(
        MayorMovimiento.hotel_id == HOTEL_ID, MayorMovimiento.anio == anio,
        MayorMovimiento.mes == mes,
        MayorMovimiento.seg1 == cuenta.strip()))).scalars().all()

    objetivo = dept.strip()
    mias = [f for f in filas
            if pl_engine.consolidate_dept(puente.get(f.seg2, f.seg2)) == objetivo]
    mias.sort(key=lambda f: (f.fecha, f.asiento, f.linea))
    total = sum(signo_de(f.seg1) * _usd(f) for f in mias)
    return {
        "anio": anio, "mes": mes, "dept": objetivo, "cuenta": cuenta,
        "asientos": len(mias),
        # ⚠️ El total viaja aparte del listado recortado: si la pantalla sumara
        # lo que dibuja, una cuenta con 300 asientos mostraría un total que no
        # es el de la fila que se abrió.
        "total": round(total, 2),
        "recortado": len(mias) > limite,
        "filas": [{
            "cuenta": f.cuenta, "seg2": f.seg2, "seg3": f.seg3,
            "asiento": f.asiento, "linea": f.linea, "fecha": f.fecha,
            "descripcion": f.descripcion, "desc_asiento": f.desc_asiento,
            "origen": f.origen, "referencia": f.referencia, "num_doc": f.num_doc,
            "monto": round(signo_de(f.seg1) * _usd(f), 2),
            "moneda": f.moneda, "tc": float(f.tc or 0),
        } for f in mias[:limite]],
    }
