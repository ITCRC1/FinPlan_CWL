# -*- coding: utf-8 -*-
"""El disparador de la ronda — pendiente 17 (`docs/GUILLERMO.md` §2 y §11).

Lo que se vigila acá es **que el cron no invente un segundo lugar donde vive la
hora**, que disparar seguido no se convierta en cuarenta y ocho rondas por día,
y que el proceso termine — porque un cron que no sale apaga al siguiente sin
avisar y eso se vería igual que un Guillermo sano.
"""
import inspect
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.guillermo import cron

CR = ZoneInfo("America/Costa_Rica")
CONFIG_CRON = Path(__file__).resolve().parents[1] / "railway.cron.json"


def _local(y, m, d, hh, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=CR)


# ── La decisión: función pura, sin base y sin reloj ──────────────────────────

def test_antes_de_la_hora_NO_corre():
    toca, motivo = cron.toca_ahora(ahora_local=_local(2026, 8, 20, 5, 30),
                                   hora_configurada="06:00", ultima_local=None)
    assert toca is False
    assert "06:00" in motivo and "30m" in motivo


def test_pasada_la_hora_y_sin_haber_corrido_hoy_SI_corre():
    toca, _ = cron.toca_ahora(ahora_local=_local(2026, 8, 20, 6, 0),
                              hora_configurada="06:00", ultima_local=None)
    assert toca is True


def test_disparar_cada_30_MINUTOS_no_da_48_rondas_por_dia():
    """⚠️ **El defecto que esto evita.** El crontab de Railway dispara seguido
    a propósito —la hora del negocio vive en la base—, así que si «ya corrió
    hoy» no frenara, Guillermo recorrería 48 veces por día: 48 batches, 48
    latidos y una cola reescrita cada media hora.
    """
    ya = _local(2026, 8, 20, 6, 0)
    corridas = 0
    for tick in range(48):                       # un día entero, cada 30 min
        ahora = _local(2026, 8, 20, 0, 0) + timedelta(minutes=30 * tick)
        toca, _ = cron.toca_ahora(ahora_local=ahora, hora_configurada="06:00",
                                  ultima_local=ya if ahora > ya else None)
        corridas += bool(toca)
    assert corridas == 1


def test_al_dia_siguiente_vuelve_a_correr():
    ayer = _local(2026, 8, 20, 6, 1)
    toca, _ = cron.toca_ahora(ahora_local=_local(2026, 8, 21, 6, 0),
                              hora_configurada="06:00", ultima_local=ayer)
    assert toca is True


def test_si_el_contenedor_estuvo_caido_corre_TARDE_y_no_saltea_el_dia():
    """Tarde es infinitamente mejor que nunca: un latido tardío sigue siendo un
    latido, y saltear el día dejaría el dead-man switch sin señal."""
    toca, _ = cron.toca_ahora(ahora_local=_local(2026, 8, 20, 9, 0),
                              hora_configurada="06:00", ultima_local=None)
    assert toca is True


@pytest.mark.parametrize("valor", ["", None, "seis de la mañana", "25:99", "6"])
def test_una_hora_ilegible_cae_al_default_y_NO_tumba_el_cron(valor):
    """Un typo en una pantalla de configuración no puede dejar a Guillermo sin
    latido: el semáforo diría «trabado» y el motivo estaría en otro lado."""
    assert cron._hora(valor).isoformat()[:5] == cron.HORA_DEFAULT


def test_una_zona_ilegible_cae_al_default_y_NO_tumba_el_cron():
    assert cron.zona_de("Marte/Olympus").key == cron.ZONA_DEFAULT
    assert cron.zona_de(None).key == cron.ZONA_DEFAULT
    assert cron.zona_de("America/Costa_Rica").key == "America/Costa_Rica"


# ── La zona horaria: 06:00 en Corcovado no es 06:00 en UTC ───────────────────

def test_las_06_00_DEL_HOTEL_no_son_las_06_00_UTC():
    """⚠️ Los crons de Railway corren en UTC. Si la hora se comparara contra el
    reloj del contenedor, `daily_run_at = 06:00` dispararía a **medianoche** en
    Costa Rica — seis horas antes, y todos los días.
    """
    medianoche_cr = datetime(2026, 8, 20, 6, 0, tzinfo=timezone.utc)
    toca, _ = cron.toca_ahora(ahora_local=medianoche_cr.astimezone(CR),
                              hora_configurada="06:00", ultima_local=None)
    assert toca is False, "disparó a medianoche hora de Costa Rica"

    seis_cr = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    toca, _ = cron.toca_ahora(ahora_local=seis_cr.astimezone(CR),
                              hora_configurada="06:00", ultima_local=None)
    assert toca is True


# ── La ronda completa, con una sesión de mentira ─────────────────────────────

class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def scalars(self):
        return self

    def all(self):
        return list(self._filas)

    def first(self):
        return self._filas[0] if self._filas else None


class _SesionFalsa:
    """Devuelve la config primero y el último batch después, y **guarda las
    sentencias** para poder mirar contra qué filtró."""

    def __init__(self, cfg: dict, ultimo=None):
        self.filas_cfg = [SimpleNamespace(clave=k, valor=v)
                          for k, v in cfg.items()]
        self.ultimo = [ultimo] if ultimo is not None else []
        self.sentencias: list[str] = []

    async def execute(self, stmt):
        self.sentencias.append(str(stmt))
        return _Resultado(self.filas_cfg if len(self.sentencias) == 1
                          else self.ultimo)


@pytest.mark.asyncio
async def test_la_ronda_NO_arranca_si_no_toca():
    db = _SesionFalsa({"daily_run_at": "06:00",
                       "report_timezone": "America/Costa_Rica"})
    salida = await cron.correr(db, ahora=datetime(2026, 8, 20, 6, 0,
                                                  tzinfo=timezone.utc))
    assert salida["corrio"] is False
    assert "todavía no" in salida["motivo"]


@pytest.mark.asyncio
async def test_cuando_toca_corre_la_ronda_DE_CONTROL_y_firma_como_cron(monkeypatch):
    """La ronda de control es la que sirve hoy: no necesita fuente conectada, y
    **no escribe en el modelo financiero** — sólo anota."""
    llamadas = []

    async def _falsa(db, hotel_id, disparado_por="guillermo"):
        llamadas.append(disparado_por)
        return {"batch_id": "x", "estado": "shadowed", "resultado": "ok",
                "detalle": "", "nuevas": 0, "cerradas": 0, "abiertas": 0}

    from app.guillermo import ronda_control
    monkeypatch.setattr(ronda_control, "ronda_de_control", _falsa)

    db = _SesionFalsa({"daily_run_at": "06:00",
                       "report_timezone": "America/Costa_Rica"})
    salida = await cron.correr(db, ahora=datetime(2026, 8, 20, 12, 0,
                                                  tzinfo=timezone.utc))
    assert salida["corrio"] is True
    assert llamadas == [cron.DISPARADOR]
    assert salida["estado"] == "shadowed"


@pytest.mark.asyncio
async def test_una_ronda_MANUAL_no_cancela_la_del_cron_ni_su_latido():
    """⚠️ Si «ya corrió hoy» contara los botonazos, apretar el botón a las 05:00
    saltearía el recorrido **y el latido** de ese día — y el dead-man switch
    existe justamente para que el silencio signifique algo."""
    db = _SesionFalsa({"daily_run_at": "06:00",
                       "report_timezone": "America/Costa_Rica"})
    await cron.correr(db, ahora=datetime(2026, 8, 20, 6, 0, tzinfo=timezone.utc))
    filtro = db.sentencias[-1]
    assert "disparado_por" in filtro and "endpoint" in filtro


@pytest.mark.asyncio
async def test_sin_config_en_la_base_igual_sabe_que_hacer():
    """Base recién migrada, sin la semilla todavía: cae a los defaults del seed
    en vez de no correr nunca."""
    db = _SesionFalsa({})
    salida = await cron.correr(db, ahora=datetime(2026, 8, 20, 6, 0,
                                                  tzinfo=timezone.utc))
    assert salida["corrio"] is False        # 00:00 en Costa Rica


# ── El proceso: tiene que terminar ───────────────────────────────────────────

def test_el_proceso_CIERRA_el_pool_y_sale():
    """⚠️ Railway saltea la ejecución siguiente si la anterior sigue viva. Un
    proceso que deja abierta la conexión apaga el cron entero, y desde afuera
    eso se ve igual que un Guillermo que no tiene nada que reclamar."""
    fuente = inspect.getsource(cron.main)
    assert "finally:" in fuente
    assert fuente.index("finally:") < fuente.index("engine.dispose()")
    assert "SystemExit(asyncio.run(main()))" in inspect.getsource(cron)


def test_un_fallo_del_cron_NO_late():
    """El latido dice «Guillermo corrió». Un fallo antes de la ronda no lo es, y
    hacerlo pasar por latido sería taparle la boca al mecanismo que grita."""
    fuente = inspect.getsource(cron)
    assert "GuillermoHeartbeat(" not in fuente
    assert "return 1" in inspect.getsource(cron.main)


# ── El crontab NO puede traer la hora del negocio ────────────────────────────

def test_la_HORA_vive_en_la_base_y_no_en_el_crontab():
    """⚠️ **El defecto que esto evita.** Si el crontab dijera `0 12 * * *`, la
    hora quedaría escrita en dos lugares: mover `daily_run_at` en la pantalla no
    movería nada y nadie sabría por qué. El crontab dice «fijate»; la base dice
    «a las seis»."""
    cfg = json.loads(CONFIG_CRON.read_text(encoding="utf-8"))
    schedule = cfg["deploy"]["cronSchedule"]
    minuto, hora = schedule.split()[0], schedule.split()[1]
    assert hora == "*", f"el crontab fijó una hora ({schedule})"
    assert re.fullmatch(r"\*/\d+|\*", minuto), schedule
    # Railway no acepta menos de 5 minutos entre corridas.
    paso = int(minuto.split("/")[1]) if "/" in minuto else 1
    assert paso >= 5, f"Railway rechaza cada {paso} minutos"


def test_el_servicio_del_cron_NO_migra_ni_siembra():
    """Dos servicios corriendo `alembic upgrade head` a la vez es una carrera
    que nadie quiere depurar. Las migraciones son del servicio web."""
    cfg = json.loads(CONFIG_CRON.read_text(encoding="utf-8"))
    start = cfg["deploy"]["startCommand"]
    assert start == "python -m app.guillermo.cron"
    assert "alembic" not in start and "seed" not in start
    assert cfg["deploy"]["restartPolicyType"] == "NEVER", (
        "un reintento automático volvería a correr la ronda que acaba de fallar")
