# -*- coding: utf-8 -*-
"""La API de Guillermo — estado, configuración, historial y cola.

Ver `docs/GUILLERMO.md`. Cuatro cosas:

* `/estado/` — el semáforo del header (§10.1). **Lo calcula el backend**: el
  componente del frontend no infiere ni recuerda nada (§10.2.7).
* `/config/` — los diez parámetros, editables (§8).
* `/importaciones/` — qué archivo entró, cuándo y quién lo subió. Es la traza
  que hasta la Fase 0 no existía.
* `/excepciones/` — la cola. Aprobar o rechazar exige `guillermo_approver`.

⚠️ **Ningún endpoint de acá escribe en el modelo financiero.** Guillermo puede
decidir, pero no puede esconder — y por ahora tampoco puede escribir: el nivel
de autonomía nace en `shadow`.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from app.auth import get_current_user, get_guillermo_approver
from app.db import get_db
from app.guillermo.core import estado_visible, latido_vencido
from app.hotel_actual import HOTEL_ID
from app.models.guillermo import (ExpectedReport, GuillermoConfig,
                                  GuillermoHeartbeat, ImportException)
from app.models.import_registro import ImportBatch, ImportFile
from app.models.scenario import Scenario

router = APIRouter(prefix="/guillermo", tags=["guillermo"])


async def _config(db) -> dict[str, str]:
    filas = (await db.execute(
        select(GuillermoConfig).where(GuillermoConfig.hotel_id == HOTEL_ID)
    )).scalars().all()
    return {f.clave: f.valor for f in filas}


@router.get("/estado/")
async def estado(db=Depends(get_db), _=Depends(get_current_user)):
    """El semáforo. ⚠️ **Siempre sale del backend** (§10.2.7): si la UI y la
    base discrepan, gana la base."""
    cfg = await _config(db)
    max_horas = int(cfg.get("heartbeat_max_hours", "26") or 26)

    ultimo = (await db.execute(
        select(GuillermoHeartbeat)
        .where(GuillermoHeartbeat.hotel_id == HOTEL_ID)
        .order_by(desc(GuillermoHeartbeat.latido_en)).limit(1)
    )).scalars().first()

    pendientes = (await db.execute(
        select(func.count()).select_from(ImportException).where(
            ImportException.hotel_id == HOTEL_ID,
            ImportException.estado == "pending")
    )).scalar() or 0

    corriendo = (await db.execute(
        select(func.count()).select_from(ImportBatch).where(
            ImportBatch.hotel_id == HOTEL_ID, ImportBatch.estado == "running")
    )).scalar() or 0

    # ⚠️ El manifiesto vacío se DICE. Sin él, la validación de nivel 1 no puede
    # opinar sobre si llegó todo — y un Guillermo que nunca reclama nada se ve
    # igual que uno que no tiene nada que reclamar.
    esperados = (await db.execute(
        select(func.count()).select_from(ExpectedReport).where(
            ExpectedReport.hotel_id == HOTEL_ID, ExpectedReport.activo.is_(True))
    )).scalar() or 0

    vencido, motivo = latido_vencido(
        ultimo.latido_en if ultimo else None, max_horas)
    # ⚠️ Recién instalado, «nunca latió» NO puede pintarse igual que «se
    # trabó»: el gato saldría en rojo en todas las pantallas desde el día cero,
    # y una alarma que suena siempre se aprende a ignorar. En cuanto haya
    # manifiesto, no haber corrido pasa a ser una falla de verdad.
    e = estado_visible(latido_vencido_=vencido, motivo_latido=motivo,
                       pendientes=int(pendientes), corriendo=bool(corriendo),
                       nunca_arranco=ultimo is None,
                       configurado=int(esperados) > 0)

    return {
        "state": e.state, "color": e.color, "pendientes": e.pendientes,
        "mensaje": e.mensaje, "detalles": e.detalles,
        "autonomia": _nivel_actual(cfg).clave,
        "autonomia_nombre": _nivel_actual(cfg).nombre,
        "gato_encendido": (cfg.get("cat_enabled", "true") or "").lower() == "true",
        "ultima_ronda": ultimo.latido_en.isoformat() if ultimo else None,
        "reportes_esperados": int(esperados),
        "sin_manifiesto": int(esperados) == 0,
    }


@router.get("/faltantes/")
async def faltantes(db=Depends(get_db), _=Depends(get_current_user)):
    """¿Qué falta subir? — D-1 del owner (2026-08-20).

    ⚠️ Cada reporte dice **cómo** se lo verificó. Los mensuales se miden por
    cobertura y eso funciona hacia atrás; los diarios se miden por última
    subida, y el registro arrancó el 2026-08-20 — de antes no se sabe, y eso
    se informa en vez de inventar un atraso.
    """
    from app.guillermo.faltantes import que_falta

    filas = await que_falta(db, HOTEL_ID)
    return {"reportes": [
        {"report_id": f.report_id, "etiqueta": f.etiqueta,
         "frecuencia": f.frecuencia, "como_se_mide": f.como_se_mide,
         "al_dia": f.al_dia, "ultimo": f.ultimo, "faltan": f.faltan,
         "mensaje": f.mensaje}
        for f in filas],
        "al_dia": all(f.al_dia for f in filas),
        "cuantos_faltan": sum(1 for f in filas if not f.al_dia)}


def _nivel_actual(cfg: dict):
    from app.guillermo.core import nivel

    return nivel(cfg.get("autonomy_level"))


@router.get("/ia/")
async def ia(db=Depends(get_db), _=Depends(get_current_user)):
    """El estado de la conexión con Claude, y **qué se le mandaría**.

    ⚠️ **Nunca devuelve la llave ni un pedazo de ella.** Sólo dice si está
    configurada. Vive en el entorno del backend, no en el repo ni en el front.

    ⚠️ Y muestra el payload EXACTO de una propuesta, con un ejemplo real del
    catálogo. Poder ver lo que saldría **antes** de que salga es lo que hace
    revisable la minimización de datos del §9.2 — una lista de campos
    prohibidos que nadie mira no protege de nada.
    """
    from sqlalchemy import select as _select

    from app.guillermo import ia as IA
    from app.models.mapping import ReportLineConfig

    con = IA.estado()

    # Un ejemplo con cuentas de verdad, para que se vea la forma real.
    lineas = (await db.execute(_select(ReportLineConfig).limit(6))).scalars().all()
    candidatas = [{"codigo": getattr(l, "line_code", ""),
                   "nombre": getattr(l, "label_es", "") or getattr(l, "label_en", "")}
                  for l in lineas]
    ejemplo = IA.payload_de_propuesta(
        "MANT. PISCINA QUÍMICOS  juan.perez@correo.com  8888-1234",
        "MANT PISCINA QUIMICOS", candidatas)
    limpio, motivos = IA.payload_limpio(ejemplo)

    return {
        "conectado": con.conectado,
        "motivo": con.motivo,
        "modelo_chico": con.modelo_chico,
        "modelo_grande": con.modelo_grande,
        "donde_va_la_llave": "ANTHROPIC_API_KEY, en el entorno del backend en Railway",
        "para_que_se_usa": [
            "Proponer una cuenta para un concepto que no reconoce (modelo chico)",
            "Redactar el resumen semanal (modelo grande)",
        ],
        "para_que_NO_se_usa": [
            "Esquema, tipos, fechas, totales y cuadre — eso es código, nunca IA",
            "El match contra las reglas — lookup exacto, nunca IA",
            "Producir números: toda cifra sale de una query",
            "Aplicar nada: una propuesta va a la cola y ahí se detiene",
        ],
        "nunca_se_envia": list(IA.PROHIBIDOS),
        "ejemplo_de_payload": ejemplo,
        "ejemplo_limpio": limpio,
        "ejemplo_motivos": motivos,
        "system_prompt": IA.SYSTEM_PROMPT,
    }


@router.post("/ronda/")
async def ronda(db=Depends(get_db), usuario=Depends(get_current_user)):
    """Correr la ronda de control ahora.

    Pedido del owner (2026-08-20): «pongo a recorrer y que vaya acumulando
    esas notas para después ir resolviendo uno a uno».

    Recorre qué falta subir y si los auxiliares amarran con el GL, y deja cada
    hallazgo en la cola. No duplica lo que ya está anotado, y **cierra solo lo
    que se resolvió** — una nota que dice «falta junio» no puede quedar
    esperando que alguien la marque a mano después de subir junio.

    ⚠️ **No escribe en el modelo financiero**: sólo anota. Su batch termina en
    `shadowed` aunque el nivel sea alto.
    """
    from app.guillermo.ronda_control import ronda_de_control

    return await ronda_de_control(
        db, HOTEL_ID, disparado_por=getattr(usuario, "email", "") or "guillermo")


@router.get("/niveles/")
async def niveles(db=Depends(get_db), _=Depends(get_current_user)):
    """Los tres niveles y qué puede hacer cada uno.

    ⚠️ **Lo que crece entre niveles es CUÁNDO actúa, no QUÉ decide solo.** En
    los tres, una propuesta del modelo va a la cola y ahí se detiene; lo único
    que se auto-aplica son reglas que un humano aprobó antes. Un nivel «alto»
    que rompiera eso no sería más capaz: sería otro sistema.
    """
    from app.guillermo.core import NIVELES

    cfg = await _config(db)
    actual = _nivel_actual(cfg).clave
    return {
        "actual": actual,
        "niveles": [
            {"clave": n.clave, "nombre": n.nombre, "resumen": n.resumen,
             "capacidades": {
                 "avisa": n.avisa, "encola": n.encola, "importa": n.importa,
                 "aplica_reglas": n.aplica_reglas, "recalcula": n.recalcula,
                 "corre_solo": n.corre_solo,
                 "aplica_propuestas_del_modelo": False}}
            for n in NIVELES.values()],
    }


@router.get("/recalculos/")
async def recalculos(db=Depends(get_db), _=Depends(get_current_user)):
    """Cuándo se recalculó cada escenario por última vez."""
    scs = (await db.execute(select(Scenario))).scalars().all()
    return {"escenarios": [
        {"id": sc.id,
         "nombre": f"{sc.type}/{sc.year}/{sc.version}",
         "enllavado": sc.status == "locked",
         "ultimo": sc.last_recalc_at.isoformat() if sc.last_recalc_at else None}
        for sc in sorted(scs, key=lambda z: (z.type, z.year, z.version))]}


class Recalculo(BaseModel):
    # Vacío = todos los que se puedan.
    scenario_ids: list[str] = []


@router.post("/recalcular/")
async def recalcular(cuerpo: Recalculo, db=Depends(get_db),
                     usuario=Depends(get_current_user)):
    """Corre el recálculo **cuando el owner quiere**, no en cada guardado.

    Decisión del owner (2026-08-20): «dame un botón para que corra cuando yo
    quiero — yo podría hacer unas 30 actualizaciones y no quiero que me pegue a
    cada rato».

    ⚠️ **Un escenario enllavado se SALTEA, no falla.** Recalcular «todos» con
    uno enllavado adentro reventaría el lote entero y no se recalcularía
    ninguno — el candado tiene que frenar ese escenario, no la corrida.

    ⚠️ **Y un escenario que falla no frena a los demás.** Se anota cuál y por
    qué, y sigue: treinta cambios perdidos porque el escenario número tres tenía
    un problema sería exactamente lo contrario de lo que este botón viene a
    resolver.
    """
    from app.engine import recalculate as recalc

    scs = (await db.execute(select(Scenario))).scalars().all()
    if cuerpo.scenario_ids:
        elegidos = [s for s in scs if s.id in set(cuerpo.scenario_ids)]
    else:
        elegidos = list(scs)

    resultados = []
    for sc in sorted(elegidos, key=lambda z: (z.type, z.year, z.version)):
        nombre = f"{sc.type}/{sc.year}/{sc.version}"
        if sc.status == "locked":
            resultados.append({"escenario": nombre, "estado": "saltado",
                               "detalle": "enllavado"})
            continue
        try:
            r = await recalc.recalculate_scenario(db, sc.id)
            await db.commit()
            resultados.append({"escenario": nombre, "estado": "ok",
                               "detalle": str(r)[:200]})
        except Exception as e:                      # noqa: BLE001
            await db.rollback()
            resultados.append({"escenario": nombre, "estado": "falló",
                               "detalle": str(e)[:300]})

    return {
        "corridos": sum(1 for r in resultados if r["estado"] == "ok"),
        "saltados": sum(1 for r in resultados if r["estado"] == "saltado"),
        "fallaron": sum(1 for r in resultados if r["estado"] == "falló"),
        "resultados": resultados,
    }


@router.get("/cuadre/")
async def cuadre(db=Depends(get_db), _=Depends(get_current_user)):
    """Todo auxiliar contra el GL — D-8 del owner (2026-08-20).

    ⚠️ **TRES estados, no dos.** Un escenario sin detalle del mayor **no
    cuadra: no se puede verificar**. Pintarlo verde sería el peor resultado
    posible — catorce presupuestos saldrían «al día» sin que nadie haya
    comparado nada.

    ⚠️ Y los descuadres **conocidos** se marcan en vez de esconderse, para que
    uno nuevo no se pierda entre los viejos.
    """
    from app.guillermo.cuadre import cuadre_de_todos, que_hacer, resumen

    filas = await cuadre_de_todos(db)
    return {
        "resumen": resumen(filas),
        "escenarios": [
            {"escenario": f.escenario, "estado": f.estado, "manda": f.manda,
             "motivo": f.motivo, "meses_evaluados": f.meses_evaluados,
             "conocida": f.conocida,
             "peor_diferencia": f.peor_diferencia,
             # ⚠️ La acción concreta, cuando se puede nombrar. Un número sin
             # el mes manda a abrir una investigación; con el mes, manda a
             # subir un archivo.
             "que_hacer": que_hacer(f),
             "meses_culpables": f.meses_culpables,
             "diferencias": f.diferencias}
            for f in filas],
    }


@router.get("/config/")
async def leer_config(db=Depends(get_db), _=Depends(get_current_user)):
    filas = sorted((await db.execute(
        select(GuillermoConfig).where(GuillermoConfig.hotel_id == HOTEL_ID)
    )).scalars().all(), key=lambda f: f.clave)
    return {"parametros": [
        {"clave": f.clave, "valor": f.valor, "descripcion": f.descripcion}
        for f in filas]}


class CambioConfig(BaseModel):
    clave: str
    valor: str


@router.put("/config/")
async def guardar_config(cambio: CambioConfig, db=Depends(get_db),
                         _=Depends(get_guillermo_approver)):
    """⚠️ Cambiar la configuración exige `guillermo_approver` (§9.5): acá vive
    el nivel de autonomía, o sea el permiso de escribir en el modelo."""
    fila = (await db.execute(
        select(GuillermoConfig).where(GuillermoConfig.hotel_id == HOTEL_ID,
                                      GuillermoConfig.clave == cambio.clave)
    )).scalars().first()
    if fila is None:
        raise HTTPException(404, f"parámetro desconocido: {cambio.clave}")

    # ⚠️ Subir a `assisted` es dar permiso de ESCRIBIR. No se acepta un valor
    # cualquiera: un typo dejaría a Guillermo en un modo que no existe, y el
    # código trataría «asistido» o «Assisted» como distinto de shadow — o sea,
    # con permiso, por un error de tipeo.
    if cambio.clave == "autonomy_level":
        from app.guillermo.core import NIVELES, _ALIAS

        v = cambio.valor.strip().lower()
        if v not in NIVELES and v not in _ALIAS:
            raise HTTPException(
                400, f"nivel desconocido: «{cambio.valor}». "
                     f"Los que hay son: {', '.join(NIVELES)}")
        # Se guarda el nombre canónico: los del spec original siguen entrando,
        # pero no se acumulan dos formas de decir lo mismo en la base.
        cambio.valor = _ALIAS.get(v, v)

    fila.valor = cambio.valor[:120]
    await db.commit()
    return {"clave": fila.clave, "valor": fila.valor}


@router.get("/importaciones/")
async def historial(limite: int = Query(50, ge=1, le=500),
                    db=Depends(get_db), _=Depends(get_current_user)):
    """Qué archivo entró, cuándo y quién lo subió.

    Antes de la Fase 0 esto **no existía**: la respuesta HTTP era efímera y no
    quedaba traza. Si un total no cuadraba, no había forma de saber qué entró.
    """
    lotes = (await db.execute(
        select(ImportBatch).where(ImportBatch.hotel_id == HOTEL_ID)
        .order_by(desc(ImportBatch.iniciado_en)).limit(limite)
    )).scalars().all()
    ids = [b.id for b in lotes]
    archivos: dict[str, list] = {}
    if ids:
        for f in (await db.execute(
                select(ImportFile).where(ImportFile.batch_id.in_(ids))
        )).scalars().all():
            archivos.setdefault(f.batch_id, []).append(f)

    return {"lotes": [
        {
            "id": b.id, "estado": b.estado, "modo": b.modo,
            "endpoint": b.endpoint, "origen": b.origen,
            "scenario_id": b.scenario_id,
            "disparado_por": b.disparado_por,
            "iniciado_en": b.iniciado_en.isoformat() if b.iniciado_en else None,
            "archivos": [
                {"nombre": f.nombre, "checksum": f.checksum[:12],
                 "tamano": f.tamano, "subido_por": f.subido_por}
                for f in archivos.get(b.id, [])
            ],
        }
        for b in lotes]}


@router.get("/excepciones/")
async def cola(estado_filtro: str = Query("pending", alias="estado"),
               db=Depends(get_db), _=Depends(get_current_user)):
    filas = (await db.execute(
        select(ImportException).where(
            ImportException.hotel_id == HOTEL_ID,
            ImportException.estado == estado_filtro)
        .order_by(desc(ImportException.creado_en)).limit(500)
    )).scalars().all()
    return {"excepciones": [
        {
            "id": x.id, "batch_id": x.batch_id, "tipo": x.tipo,
            "linea": x.linea, "valor_crudo": x.valor_crudo,
            "valor_normalizado": x.valor_normalizado,
            "destino_sugerido": x.destino_sugerido,
            "confianza": str(x.confianza), "rationale": x.rationale,
            "estado": x.estado,
            "creado_en": x.creado_en.isoformat() if x.creado_en else None,
        }
        for x in filas]}


class Resolucion(BaseModel):
    decision: str            # approved | rejected
    destino: str | None = None


@router.put("/excepciones/{excepcion_id}/")
async def resolver(excepcion_id: str, r: Resolucion, db=Depends(get_db),
                   usuario=Depends(get_guillermo_approver)):
    """Aprobar o rechazar. **Sólo un humano con el rol** (§4 y §9.5).

    ⚠️ Una propuesta del modelo NUNCA se aplica sola. Lo único que se
    auto-aplica son reglas que un humano aprobó antes — y ésta es la puerta por
    donde un humano las aprueba.
    """
    if r.decision not in ("approved", "rejected"):
        raise HTTPException(400, "la decisión sólo puede ser «approved» o «rejected»")

    x = (await db.execute(
        select(ImportException).where(ImportException.id == excepcion_id,
                                      ImportException.hotel_id == HOTEL_ID)
    )).scalars().first()
    if x is None:
        raise HTTPException(404, "excepción no encontrada")
    # ⚠️ Una excepción ya resuelta no se vuelve a resolver: dos aprobaciones
    # sobre la misma línea crearían dos reglas y la traza diría cualquier cosa.
    if x.estado != "pending":
        raise HTTPException(
            409, f"esta excepción ya está «{x.estado}», resuelta por "
                 f"{x.resuelto_por or 'alguien'}")

    x.estado = r.decision
    x.resuelto_por = getattr(usuario, "email", "") or ""
    x.resuelto_en = datetime.now(timezone.utc)
    if r.destino:
        x.destino_sugerido = r.destino[:40]
    await db.commit()
    return {"id": x.id, "estado": x.estado, "resuelto_por": x.resuelto_por}


@router.get("/correo/")
async def estado_correo(db=Depends(get_db), _=Depends(get_current_user)):
    """¿Puede Guillermo avisar por correo, y a quién?

    ⚠️ **Nunca devuelve la contraseña del servidor ni un pedazo.** Igual que la
    llave del modelo, vive en el entorno del backend.

    ⚠️ Y contesta **por qué no** cuando no puede. Un correo que no sale porque
    falta una variable es indistinguible de uno que no salía porque no había
    nada que avisar — y esa diferencia es justamente la que sostiene el
    dead-man switch.
    """
    from app.guillermo import correo as _correo

    cfg = await _config(db)
    con = _correo.estado(cfg.get(_correo.CLAVE_DESTINATARIOS))
    return {
        "configurado": con.configurado,
        "servidor": con.servidor,
        "remitente": con.remitente,
        "destinatarios": list(con.destinatarios),
        "motivo": con.motivo,
        "clave_destinatarios": _correo.CLAVE_DESTINATARIOS,
        "variables_de_entorno": list(_correo.VARIABLES),
    }


# ── El manifiesto: qué reportes espera ESTA propiedad ────────────────────────
#
# ⚠️ **Es la decisión D-1, y es por propiedad** (owner, 2026-08-20: «cada
# propiedad decide cómo manejar a Guillermo»). Hasta hoy el manifiesto sólo se
# podía sembrar desde el código: una propiedad nueva quedaba con lo que le
# tocara del seed y sin forma de cambiarlo desde la app. Ahora se declara acá.
#
# ⚠️ Y el manifiesto **decide qué reclama Guillermo**: agregar un reporte hace
# que su ausencia se convierta en una excepción, y sacarlo lo vuelve invisible.
# Por eso escribir exige `guillermo_approver`, igual que la config.

VERIFICACIONES = ("cobertura", "ultima_subida", "actualizado")
FRECUENCIAS = ("daily", "weekly", "monthly")


class ReporteEsperado(BaseModel):
    report_id: str
    notas: str = ""
    frecuencia: str = "daily"
    verifica: str = "cobertura"
    objetivo: str = ""
    gracia_dias: int = 0
    obligatorio: bool = True
    activo: bool = True
    patron: str = ""
    formato: str = ""
    tamano_min: int = 0


def _valida(r: ReporteEsperado) -> None:
    """⚠️ Un valor fuera de la lista **no falla al guardar: falla al
    verificar**, y ahí se ve como «este reporte nunca está al día» sin decir
    por qué. Se rechaza acá, donde todavía se puede explicar."""
    if not r.report_id.strip():
        raise HTTPException(400, "el reporte necesita un identificador")
    if r.frecuencia not in FRECUENCIAS:
        raise HTTPException(
            400, f"frecuencia desconocida: «{r.frecuencia}». "
                 f"Las que hay son: {', '.join(FRECUENCIAS)}")
    if r.verifica not in VERIFICACIONES:
        raise HTTPException(
            400, f"forma de verificar desconocida: «{r.verifica}». "
                 f"Las que hay son: {', '.join(VERIFICACIONES)}")
    if not r.objetivo.strip():
        raise HTTPException(
            400, "falta el objetivo: la tabla contra la que se mide la "
                 "cobertura, o el trozo de ruta de la subida")


def _como_sale(r: ExpectedReport) -> dict:
    return {
        "id": r.id, "report_id": r.report_id, "notas": r.notas,
        "frecuencia": r.frecuencia, "verifica": r.verifica,
        "objetivo": r.objetivo, "gracia_dias": r.gracia_dias,
        "obligatorio": r.obligatorio, "activo": r.activo,
        "patron": r.patron, "formato": r.formato, "tamano_min": r.tamano_min,
    }


@router.get("/manifiesto/")
async def leer_manifiesto(db=Depends(get_db), _=Depends(get_current_user)):
    """Qué espera esta propiedad. **Vacío es una respuesta válida**: quiere
    decir que su owner todavía no decidió D-1, y el semáforo lo dice."""
    filas = sorted((await db.execute(
        select(ExpectedReport).where(ExpectedReport.hotel_id == HOTEL_ID)
    )).scalars().all(), key=lambda r: (r.frecuencia, r.report_id))
    return {
        "hotel_id": HOTEL_ID,
        "reportes": [_como_sale(r) for r in filas],
        "verificaciones": list(VERIFICACIONES),
        "frecuencias": list(FRECUENCIAS),
    }


@router.post("/manifiesto/")
async def crear_esperado(r: ReporteEsperado, db=Depends(get_db),
                         _=Depends(get_guillermo_approver)):
    _valida(r)
    ya = (await db.execute(
        select(ExpectedReport).where(ExpectedReport.hotel_id == HOTEL_ID,
                                     ExpectedReport.report_id == r.report_id)
    )).scalars().first()
    # ⚠️ 409 con el motivo, no un segundo registro: dos filas con el mismo
    # `report_id` harían que Guillermo reclamara el mismo archivo dos veces.
    if ya is not None:
        raise HTTPException(409, f"«{r.report_id}» ya está en el manifiesto")

    fila = ExpectedReport(hotel_id=HOTEL_ID, **r.model_dump())
    db.add(fila)
    await db.commit()
    return _como_sale(fila)


@router.put("/manifiesto/{esperado_id}/")
async def editar_esperado(esperado_id: str, r: ReporteEsperado,
                          db=Depends(get_db),
                          _=Depends(get_guillermo_approver)):
    _valida(r)
    fila = (await db.execute(
        select(ExpectedReport).where(ExpectedReport.id == esperado_id,
                                     ExpectedReport.hotel_id == HOTEL_ID)
    )).scalars().first()
    if fila is None:
        raise HTTPException(404, "ese reporte no está en el manifiesto")
    for k, v in r.model_dump().items():
        setattr(fila, k, v)
    await db.commit()
    return _como_sale(fila)


@router.delete("/manifiesto/{esperado_id}/")
async def borrar_esperado(esperado_id: str, db=Depends(get_db),
                          _=Depends(get_guillermo_approver)):
    """⚠️ Borrar un reporte del manifiesto **apaga su vigilancia**: deja de
    reclamarse y su ausencia deja de ser una excepción. Para dejar de mirarlo
    sin perder la definición está `activo`."""
    fila = (await db.execute(
        select(ExpectedReport).where(ExpectedReport.id == esperado_id,
                                     ExpectedReport.hotel_id == HOTEL_ID)
    )).scalars().first()
    if fila is None:
        raise HTTPException(404, "ese reporte no está en el manifiesto")
    await db.delete(fila)
    await db.commit()
    return {"borrado": esperado_id}


@router.get("/cuadre-opera/")
async def cuadre_opera(db=Depends(get_db), _=Depends(get_current_user)):
    """Nivel 3 · los reportes de Opera entre sí (pendiente 22).

    Country Mix, Channel Mix y On the Books salen del MISMO XML: las noches de
    un mes tienen que dar lo mismo en los tres.

    ⚠️ **Tres estados, nunca dos.** Falta un lado no es «no cuadra»: es «no se
    puede verificar». Y cero comparaciones tampoco es «cuadra» — pintarlo verde
    diría que los reportes coinciden cuando nadie comparó nada.
    """
    from app.guillermo.cuadre_opera import resumen_opera

    escenarios = (await db.execute(
        select(Scenario).where(Scenario.hotel_id == HOTEL_ID)
    )).scalars().all()

    fuera = []
    for sc in escenarios:
        r = await resumen_opera(db, sc, HOTEL_ID)
        # Sólo lo que aporta algo: un escenario sin nada que comparar llena la
        # pantalla de filas grises que enseñan a no mirarla.
        if r.verificados == 0 and not r.descuadres:
            continue
        fuera.append({
            "escenario": r.escenario,
            "estado": r.estado,
            "verificados": r.verificados,
            "pares": [
                {"mes": p.mes, "izquierda": p.izquierda, "derecha": p.derecha,
                 "valor_izq": str(p.valor_izq) if p.valor_izq is not None else None,
                 "valor_der": str(p.valor_der) if p.valor_der is not None else None,
                 "diferencia": str(p.diferencia),
                 "estado": p.estado, "motivo": p.motivo}
                for p in r.pares if p.estado != "sin_verificar"
            ],
            "sin_verificar": sum(1 for p in r.pares if p.estado == "sin_verificar"),
        })

    return {
        "escenarios": fuera,
        "criterio": ("Country Mix, Channel Mix y On the Books salen del mismo "
                     "XML de Opera: las noches de un mes tienen que dar lo "
                     "mismo en los tres. Sólo se comparan las filas que "
                     "vinieron del XML, y contra el On the Books sólo los "
                     "meses cerrados — para un mes futuro es parcial por "
                     "definición."),
    }
