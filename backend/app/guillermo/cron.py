# -*- coding: utf-8 -*-
"""El disparador de la ronda — pendiente 17 (`docs/GUILLERMO.md` §2 y §11).

Hasta hoy Guillermo sólo recorría **si alguien apretaba el botón**, y por eso el
semáforo estaba en gris: sin ronda automática no hay latido, y sin latido el
dead-man switch del apéndice §5 no distingue «todo bien» de «el worker está
muerto» — que es exactamente lo que existe para distinguir.

Este módulo es el entry point que llama el **cron de Railway** (ver
`backend/railway.cron.json`). Abre la sesión, decide si toca, corre la ronda de
control, cierra el pool y **termina**. Railway saltea la ejecución siguiente si
la anterior sigue viva, así que un proceso que no sale apaga el cron entero.

⚠️ **Y los tics que NO son la ronda hacen de vigilante** (pendiente 20). Un
dead-man switch que vive dentro del proceso que vigila no puede avisar cuando
ese proceso muere; pero acá el cron despierta 48 veces por día y 47 no tienen
nada que hacer. Esos 47 miran el latido y mandan el correo rojo si se venció.
**El vigilante no late**: escribir un latido al avisar silenciaría la alarma
que se acaba de disparar.

⚠️ **La hora vive en la base, no en el crontab.** `daily_run_at` es un parámetro
que el owner edita en la pantalla. Si la hora estuviera además en el crontab
habría **dos fuentes de verdad para el mismo dato** —el problema de las dos
tablas de rack, otra vez— y cambiarla en la app no movería nada. Así que el cron
de Railway dispara SEGUIDO (cada 30 minutos) y **acá se decide si toca**. El
crontab dice «fijate»; la base dice «a las seis».

⚠️ **Y por eso el horario se lee en la zona del hotel.** Los crons de Railway
corren en UTC. `06:00` en `report_timezone` (America/Costa_Rica) no es `06:00`
UTC — sería medianoche. La conversión se hace acá, con la zona configurada.

⚠️ **Qué ronda corre, y por qué ésta.** Corre `ronda_de_control`, que **no
escribe en el modelo financiero**: recorre qué falta subir y si los auxiliares
amarran con el GL, y deja cada hallazgo en la cola. La otra ronda
(`runner.correr_ronda`) necesita una fuente que le traiga archivos, y hoy no hay
ninguna conectada (D-2 y D-4, del owner). Conectar la fuente es cambiar esta
función, no reescribir el cron.

⚠️ **Lo que el nivel de autonomía gatilla, y lo que no.** `corre_solo` sólo es
`True` en el nivel «alto», que además prende `importa` y `recalcula`. Exigirlo
para esta ronda obligaría al owner a **darle permiso de escritura para que pueda
mirar** — y esta ronda no escribe un número: sólo anota, y `encola` ya está
prendido desde el nivel más bajo. Así que el recorrido va en todos los niveles y
`corre_solo` sigue gobernando lo que sí escribe. Si el owner prefiere lo
contrario, es una línea: `if not puede(modo, "corre_solo"): return`.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.guillermo import correo
from app.guillermo.core import latido_vencido
from app.hotel_actual import HOTEL_ID
from app.models.guillermo import GuillermoConfig, GuillermoHeartbeat
from app.models.import_registro import ImportBatch

# Quién figura como disparador. Se distingue del email de una persona para que
# «¿corrió solo o lo apretaron?» se pueda contestar mirando el historial.
DISPARADOR = "cron"
ENDPOINT = "ronda-de-control"

# Los defaults de `app/seed_guillermo.py`. Se repiten acá como piso: si la fila
# todavía no existe (base recién migrada), el cron igual sabe qué hacer.
HORA_DEFAULT = "06:00"
ZONA_DEFAULT = "America/Costa_Rica"

# Marca de «esto ya lo avisé hoy». Vive en la config, que es la tabla que ya
# existe para esto — no una tabla nueva para guardar una fecha.
CLAVE_AVISO_LATIDO = "ultimo_aviso_latido"
CLAVE_RESUMEN = "ultimo_resumen_semanal"

# Lunes = 0, como `date.weekday()`.
DIAS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6}


def zona_de(nombre: str | None) -> ZoneInfo:
    """La zona del hotel. ⚠️ Una zona mal escrita **no tumba el cron**: cae al
    default y sigue. Tumbarlo dejaría a Guillermo sin latido por un error de
    tipeo en una pantalla de configuración, y el semáforo diría «trabado»."""
    try:
        return ZoneInfo((nombre or "").strip() or ZONA_DEFAULT)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(ZONA_DEFAULT)


def _hora(valor: str | None) -> time:
    """`HH:MM` → `time`. Un valor ilegible cae al default, no revienta."""
    try:
        h, m = (valor or "").strip().split(":")[:2]
        return time(int(h), int(m))
    except (ValueError, TypeError):
        h, m = HORA_DEFAULT.split(":")
        return time(int(h), int(m))


def _falta(d: timedelta) -> str:
    minutos = int(d.total_seconds() // 60)
    return f"{minutos // 60}h {minutos % 60:02d}m" if minutos >= 60 else f"{minutos}m"


def toca_ahora(*, ahora_local: datetime, hora_configurada: str | None,
               ultima_local: datetime | None) -> tuple[bool, str]:
    """¿Le toca correr? **Función pura: se prueba sin base y sin reloj.**

    Tres reglas, en orden:

    1. Antes de la hora configurada, no.
    2. Ya corrió hoy (por cron), no. Es lo que hace que disparar cada 30
       minutos no dé 48 rondas por día: 47 salen por acá sin tocar nada.
    3. Si no, sí.

    ⚠️ Y **no se persigue la hora exacta**. Si el contenedor estuvo caído a las
    06:00 y vuelve a las 09:00, corre a las 09:00 — tarde es infinitamente mejor
    que nunca, y un latido tardío sigue siendo un latido. Railway además avisa
    que no garantiza el minuto.
    """
    objetivo = datetime.combine(ahora_local.date(), _hora(hora_configurada),
                                tzinfo=ahora_local.tzinfo)
    if ahora_local < objetivo:
        return False, (f"todavía no: la ronda es a las {objetivo:%H:%M} y "
                       f"faltan {_falta(objetivo - ahora_local)}")
    if ultima_local is not None and ultima_local.date() == ahora_local.date():
        return False, f"ya corrió hoy a las {ultima_local:%H:%M}"
    return True, (f"toca: son las {ahora_local:%H:%M} y la ronda "
                  f"es a las {objetivo:%H:%M}")


async def _config(db: AsyncSession) -> dict[str, str]:
    filas = (await db.execute(
        select(GuillermoConfig).where(GuillermoConfig.hotel_id == HOTEL_ID)
    )).scalars().all()
    return {f.clave: f.valor for f in filas}


async def _ultima_del_cron(db: AsyncSession, tz: ZoneInfo) -> datetime | None:
    """La última ronda **disparada por el cron**, en hora local.

    ⚠️ A propósito **no cuenta las manuales**: si el owner aprieta el botón a las
    05:00, eso no puede cancelar el recorrido del día ni, sobre todo, el latido
    — que es lo que sostiene el dead-man switch.
    """
    fila = (await db.execute(
        select(ImportBatch)
        .where(ImportBatch.hotel_id == HOTEL_ID,
               ImportBatch.disparado_por == DISPARADOR,
               ImportBatch.endpoint == ENDPOINT)
        .order_by(desc(ImportBatch.iniciado_en)).limit(1)
    )).scalars().first()
    if fila is None or fila.iniciado_en is None:
        return None
    cuando = fila.iniciado_en
    if cuando.tzinfo is None:                       # SQLite, en las pruebas
        cuando = cuando.replace(tzinfo=timezone.utc)
    return cuando.astimezone(tz)


async def _marca(db: AsyncSession, clave: str, valor: str) -> None:
    """Deja una marca en la config. Se usa para «esto ya lo avisé»."""
    fila = (await db.execute(
        select(GuillermoConfig).where(GuillermoConfig.hotel_id == HOTEL_ID,
                                      GuillermoConfig.clave == clave)
    )).scalars().first()
    if fila is None:
        db.add(GuillermoConfig(hotel_id=HOTEL_ID, clave=clave, valor=valor,
                               descripcion="Lo escribe el cron. No se edita a mano."))
    else:
        fila.valor = valor
    await db.commit()


async def vigilar(db: AsyncSession, cfg: dict[str, str],
                  ahora_local: datetime) -> str:
    """El dead-man switch, **en los tics que NO son la ronda**.

    ⚠️ **Un vigilante que vive dentro del proceso que vigila no puede avisar
    cuando ese proceso muere.** Pero el cron despierta 48 veces por día y 47 no
    hacen nada: ahí es donde el vigilante sirve. Si la ronda se trabó, estos
    tics lo notan y mandan el correo rojo.

    ⚠️ **Y NO late.** Escribir un latido acá silenciaría la alarma que se acaba
    de disparar: el próximo tic vería el latido fresco y diría que todo está
    bien. El aviso informa; el latido lo da únicamente la ronda que corrió.

    ⚠️ Se manda **una vez por día**. Cuarenta y siete correos iguales no avisan
    mejor: enseñan a filtrar el remitente.
    """
    ultimo = (await db.execute(
        select(GuillermoHeartbeat)
        .where(GuillermoHeartbeat.hotel_id == HOTEL_ID)
        .order_by(desc(GuillermoHeartbeat.latido_en)).limit(1)
    )).scalars().first()

    max_horas = int(cfg.get("heartbeat_max_hours", "26") or 26)
    vencido, motivo = latido_vencido(
        ultimo.latido_en if ultimo else None, max_horas,
        ahora_local.astimezone(timezone.utc))
    if not vencido:
        return ""

    hoy = ahora_local.date().isoformat()
    if cfg.get(CLAVE_AVISO_LATIDO) == hoy:
        return "latido vencido, ya avisado hoy"

    asunto, cuerpo = correo.aviso_de_latido(HOTEL_ID, motivo, max_horas)
    ok, detalle = correo.enviar(asunto, cuerpo, cfg.get(correo.CLAVE_DESTINATARIOS))
    if ok:
        await _marca(db, CLAVE_AVISO_LATIDO, hoy)
    return f"latido vencido → correo: {detalle}"


async def correr(db: AsyncSession, *, ahora: datetime | None = None) -> dict:
    """Decide y, si toca, recorre. Devuelve siempre un resumen legible."""
    from app.guillermo.ronda_control import ronda_de_control

    cfg = await _config(db)
    tz = zona_de(cfg.get("report_timezone"))
    ahora_local = (ahora or datetime.now(timezone.utc)).astimezone(tz)

    # El vigilante corre SIEMPRE, toque o no toque la ronda.
    vigilancia = await vigilar(db, cfg, ahora_local)

    toca, motivo = toca_ahora(
        ahora_local=ahora_local,
        hora_configurada=cfg.get("daily_run_at", HORA_DEFAULT),
        ultima_local=await _ultima_del_cron(db, tz))

    if not toca:
        return {"corrio": False, "motivo": motivo, "vigilancia": vigilancia}

    salida = await ronda_de_control(db, HOTEL_ID, disparado_por=DISPARADOR)

    # ⚠️ El aviso sale **sólo si hay algo nuevo**. Un correo diario que casi
    # siempre dice «0 nuevos» se aprende a saltear, y con él se saltea el que
    # sí traía algo. Lo que confirma que el canal vive es el resumen semanal.
    aviso = "sin novedad: no se manda correo"
    if salida.get("nuevas"):
        asunto, cuerpo = correo.aviso_de_hallazgos(
            HOTEL_ID, int(salida["nuevas"]), int(salida.get("cerradas", 0)),
            int(salida.get("abiertas", 0)), str(salida.get("detalle", "")))
        _, aviso = correo.enviar(asunto, cuerpo,
                                 cfg.get(correo.CLAVE_DESTINATARIOS))

    semanal = await _resumen_si_toca(db, cfg, ahora_local, salida)

    return {"corrio": True, "motivo": motivo, "vigilancia": vigilancia,
            "aviso": aviso, "semanal": semanal, **salida}


async def _resumen_si_toca(db: AsyncSession, cfg: dict[str, str],
                           ahora_local: datetime, salida: dict) -> str:
    """El resumen de la semana (§12.2).

    ⚠️ **Va aunque no haya nada que contar**, y por eso es el que sostiene todo
    lo demás: es el único aviso cuya AUSENCIA significa algo. Los otros callan
    cuando no hay novedad, así que su silencio no prueba que el canal funcione;
    éste llega todas las semanas, y si no llega, el canal está roto.
    """
    dia = DIAS.get((cfg.get("weekly_summary_day", "monday") or "").strip().lower())
    if dia is None or ahora_local.weekday() != dia:
        return ""

    # ⚠️ Por SEMANA, no por día: si el owner mueve el día del resumen, no puede
    # recibir dos en la misma semana.
    semana = f"{ahora_local.isocalendar().year}-W{ahora_local.isocalendar().week:02d}"
    if cfg.get(CLAVE_RESUMEN) == semana:
        return "el resumen de esta semana ya salió"

    hace_una_semana = ahora_local.astimezone(timezone.utc) - timedelta(days=7)
    corridas = (await db.execute(
        select(func.count()).select_from(ImportBatch).where(
            ImportBatch.hotel_id == HOTEL_ID,
            ImportBatch.disparado_por == DISPARADOR,
            ImportBatch.iniciado_en >= hace_una_semana)
    )).scalar() or 0

    lineas = [l for l in str(salida.get("detalle", "")).split(" · ") if l]
    asunto, cuerpo = correo.resumen_semanal(
        HOTEL_ID, int(salida.get("abiertas", 0)), int(corridas), lineas)
    ok, detalle = correo.enviar(asunto, cuerpo,
                                cfg.get(correo.CLAVE_DESTINATARIOS))
    if ok:
        await _marca(db, CLAVE_RESUMEN, semana)
    return f"resumen semanal → {detalle}"


async def main() -> int:
    """Entry point del cron. ⚠️ **Cierra el pool y sale**: Railway saltea la
    ejecución siguiente si la anterior sigue viva, así que un proceso que no
    termina apaga el cron sin avisar."""
    from app.db import engine, get_session

    try:
        async with get_session() as db:
            salida = await correr(db)
        print(f"[guillermo/cron] {salida}", flush=True)
        return 0
    except Exception as e:                          # noqa: BLE001
        # ⚠️ Sale con código != 0 para que la corrida figure como fallida en
        # Railway. Y **no late**: un fallo antes de la ronda no es «Guillermo
        # corrió», y hacerlo pasar por latido sería taparle la boca justo al
        # mecanismo que existe para gritar.
        print(f"[guillermo/cron] FALLÓ: {e}", file=sys.stderr, flush=True)
        return 1
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
