# -*- coding: utf-8 -*-
"""Los avisos por correo — pendiente 20 (`docs/GUILLERMO.md` §12.2, apéndice 5).

Lo que se vigila acá es que el aviso **no se coma a sí mismo**: el vigilante no
puede latir, no puede mandar el mismo correo cuarenta y siete veces por día, y
un fallo del correo no puede tumbar la ronda.
"""
import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.guillermo import correo, cron

CR = ZoneInfo("America/Costa_Rica")
ENTORNO = {"SMTP_HOST": "smtp.x.com", "SMTP_PORT": "587",
           "SMTP_USER": "u", "SMTP_PASSWORD": "p", "SMTP_FROM": "g@x.com"}


# ── Destinatarios ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("crudo,esperado", [
    ("a@x.com, b@y.com", ("a@x.com", "b@y.com")),
    ("a@x.com;b@y.com", ("a@x.com", "b@y.com")),
    ("  a@x.com ,, a@x.com ", ("a@x.com",)),          # sin duplicados ni vacíos
    ("", ()), (None, ()),
])
def test_los_destinatarios_se_leen_de_una_lista_suelta(crudo, esperado):
    assert correo.destinatarios_de(crudo) == esperado


# ── Sin configurar: no manda, y lo DICE ──────────────────────────────────────

def test_sin_variables_de_entorno_no_manda_y_explica(monkeypatch):
    for v in correo.VARIABLES:
        monkeypatch.delenv(v, raising=False)
    con = correo.estado("a@x.com")
    assert con.configurado is False
    assert "SMTP_HOST" in con.motivo


def test_sin_destinatarios_no_manda_y_MANDA_A_LA_PANTALLA(monkeypatch):
    """⚠️ Es la decisión D-5 y es de cada propiedad. El motivo tiene que decir
    dónde se arregla, no sólo que falta."""
    for k, v in ENTORNO.items():
        monkeypatch.setenv(k, v)
    con = correo.estado("")
    assert con.configurado is False
    assert correo.CLAVE_DESTINATARIOS in con.motivo
    assert "Admin" in con.motivo


def test_configurado_completo_da_verde(monkeypatch):
    for k, v in ENTORNO.items():
        monkeypatch.setenv(k, v)
    con = correo.estado("a@x.com, b@y.com")
    assert con.configurado is True
    assert con.destinatarios == ("a@x.com", "b@y.com")


def test_enviar_sin_configurar_NO_LEVANTA(monkeypatch):
    """Un fallo de correo no puede tumbar la ronda: el aviso es lo accesorio,
    el latido es lo importante."""
    for v in correo.VARIABLES:
        monkeypatch.delenv(v, raising=False)
    ok, motivo = correo.enviar("asunto", "cuerpo", "a@x.com")
    assert ok is False and motivo


def test_la_contrasena_NUNCA_sale(monkeypatch):
    for k, v in ENTORNO.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("SMTP_PASSWORD", "secreto-de-verdad")
    con = correo.estado("a@x.com")
    assert "secreto-de-verdad" not in repr(con)
    assert "secreto-de-verdad" not in con.motivo


# ── Qué dice cada aviso ──────────────────────────────────────────────────────

def test_el_aviso_rojo_dice_QUE_dejo_de_pasar_y_DONDE_mirar():
    """⚠️ «Algo pasó» obliga a entrar a la app para saber qué — o sea, no
    avisó nada (§10: específicos y técnicos, nunca en voz de gato)."""
    asunto, cuerpo = correo.aviso_de_latido("CWL", "nunca latió", 26)
    assert "CWL" in asunto
    assert "26" in cuerpo
    assert "Railway" in cuerpo
    for gatuno in ("miau", "🐱", "ups"):
        assert gatuno not in cuerpo.lower()


def test_el_resumen_semanal_va_AUNQUE_no_haya_nada():
    """Es el único aviso cuya ausencia significa algo: confirma que el canal
    funciona."""
    _, cuerpo = correo.resumen_semanal("CWL", 0, 7, [])
    assert "No quedó ningún hallazgo abierto" in cuerpo


# ── El vigilante ─────────────────────────────────────────────────────────────

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
    def __init__(self, latido=None):
        self.latido = [latido] if latido is not None else []
        self.agregados: list = []
        self.commits = 0

    async def execute(self, stmt):
        return _Resultado(self.latido)

    def add(self, obj):
        self.agregados.append(obj)

    async def commit(self):
        self.commits += 1


@pytest.mark.asyncio
async def test_el_vigilante_NO_LATE(monkeypatch):
    """⚠️ **La trampa.** Si el vigilante escribiera un latido al avisar,
    silenciaría la alarma que se acaba de disparar: el próximo tic vería el
    latido fresco y diría que todo está bien. El latido lo da únicamente la
    ronda que corrió.
    """
    enviados = []
    monkeypatch.setattr(correo, "enviar",
                        lambda a, c, d: (enviados.append(a), (True, "ok"))[1])

    db = _SesionFalsa(latido=None)                 # nunca latió → vencido
    salida = await cron.vigilar(db, {}, datetime(2026, 8, 20, 9, 0, tzinfo=CR))

    assert enviados, "no avisó estando vencido"
    assert "correo" in salida
    from app.models.guillermo import GuillermoHeartbeat
    assert not any(isinstance(o, GuillermoHeartbeat) for o in db.agregados), (
        "el vigilante escribió un latido y se silenció a sí mismo")


@pytest.mark.asyncio
async def test_el_vigilante_avisa_UNA_VEZ_POR_DIA(monkeypatch):
    """Cuarenta y siete correos iguales no avisan mejor: enseñan a filtrar el
    remitente."""
    enviados = []
    monkeypatch.setattr(correo, "enviar",
                        lambda a, c, d: (enviados.append(a), (True, "ok"))[1])

    db = _SesionFalsa(latido=None)
    cfg = {cron.CLAVE_AVISO_LATIDO: "2026-08-20"}
    salida = await cron.vigilar(db, cfg, datetime(2026, 8, 20, 9, 0, tzinfo=CR))
    assert enviados == []
    assert "ya avisado hoy" in salida


@pytest.mark.asyncio
async def test_con_latido_fresco_el_vigilante_se_queda_callado(monkeypatch):
    enviados = []
    monkeypatch.setattr(correo, "enviar",
                        lambda a, c, d: (enviados.append(a), (True, "ok"))[1])

    ahora = datetime(2026, 8, 20, 9, 0, tzinfo=CR)
    fresco = SimpleNamespace(
        latido_en=ahora.astimezone(timezone.utc) - timedelta(hours=2))
    db = _SesionFalsa(latido=fresco)
    assert await cron.vigilar(db, {}, ahora) == ""
    assert enviados == []


def test_el_vigilante_corre_en_TODOS_los_tics_no_solo_cuando_toca():
    """⚠️ Un dead-man switch que sólo mira cuando la ronda corre no detecta
    nunca que la ronda dejó de correr. Los 47 tics que no hacen nada son
    justamente donde sirve."""
    fuente = inspect.getsource(cron.correr)
    assert fuente.index("await vigilar(") < fuente.index("toca, motivo ="), (
        "la vigilancia quedó después de la decisión de si toca")


@pytest.mark.asyncio
async def test_sin_hallazgos_nuevos_NO_se_manda_correo(monkeypatch):
    """Un correo diario que casi siempre dice «0 nuevos» se aprende a saltear,
    y con él se saltea el que sí traía algo."""
    enviados = []
    monkeypatch.setattr(correo, "enviar",
                        lambda a, c, d: (enviados.append(a), (True, "ok"))[1])
    monkeypatch.setattr(cron, "vigilar", _sin_vigilancia)

    from app.guillermo import ronda_control
    monkeypatch.setattr(ronda_control, "ronda_de_control", _ronda_vacia)

    db = _ConfigFalsa({"daily_run_at": "06:00"})
    salida = await cron.correr(db, ahora=datetime(2026, 8, 20, 12, 0,
                                                  tzinfo=timezone.utc))
    assert salida["corrio"] is True
    assert enviados == []
    assert "sin novedad" in salida["aviso"]


async def _sin_vigilancia(db, cfg, ahora_local):
    return ""


async def _ronda_vacia(db, hotel_id, disparado_por="guillermo"):
    return {"batch_id": "x", "estado": "shadowed", "resultado": "ok",
            "detalle": "", "nuevas": 0, "cerradas": 0, "abiertas": 3}


class _ConfigFalsa:
    """Devuelve la config primero y nada después (no hay batch previo)."""

    def __init__(self, cfg):
        self.filas = [SimpleNamespace(clave=k, valor=v) for k, v in cfg.items()]
        self.n = 0

    async def execute(self, stmt):
        self.n += 1
        return _Resultado(self.filas if self.n == 1 else [])

    def add(self, obj):
        pass

    async def commit(self):
        pass


# ── El resumen semanal ───────────────────────────────────────────────────────

class _ConCorridas(_ConfigFalsa):
    """Como la config falsa, pero la tercera consulta cuenta corridas."""

    def __init__(self, cfg, corridas=7):
        super().__init__(cfg)
        self.corridas = corridas

    async def execute(self, stmt):
        # Primero cuenta las corridas; después `_marca` busca la fila donde
        # anotar que el resumen de esta semana ya salió.
        self.n += 1
        if self.n == 1:
            return SimpleNamespace(scalar=lambda: self.corridas)
        return _Resultado([])


@pytest.mark.asyncio
async def test_el_resumen_semanal_sale_SOLO_su_dia(monkeypatch):
    enviados = []
    monkeypatch.setattr(correo, "enviar",
                        lambda a, c, d: (enviados.append(a), (True, "ok"))[1])

    # 2026-08-20 es jueves. Con el resumen en lunes, no sale.
    jueves = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    salida = await cron._resumen_si_toca(
        _ConCorridas({}), {"weekly_summary_day": "monday"},
        jueves.astimezone(CR), {"abiertas": 3, "detalle": "x"})
    assert salida == "" and enviados == []

    salida = await cron._resumen_si_toca(
        _ConCorridas({}), {"weekly_summary_day": "thursday"},
        jueves.astimezone(CR), {"abiertas": 3, "detalle": "x"})
    assert "resumen semanal" in salida and len(enviados) == 1


@pytest.mark.asyncio
async def test_mover_el_dia_del_resumen_NO_manda_dos_en_la_misma_semana(monkeypatch):
    """⚠️ La marca es por SEMANA, no por día: si fuera por día, correr el
    resumen del lunes al martes daría dos resúmenes de la misma semana."""
    enviados = []
    monkeypatch.setattr(correo, "enviar",
                        lambda a, c, d: (enviados.append(a), (True, "ok"))[1])

    jueves = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc).astimezone(CR)
    semana = f"{jueves.isocalendar().year}-W{jueves.isocalendar().week:02d}"
    salida = await cron._resumen_si_toca(
        _ConCorridas({}),
        {"weekly_summary_day": "thursday", cron.CLAVE_RESUMEN: semana},
        jueves, {"abiertas": 3, "detalle": "x"})
    assert "ya salió" in salida and enviados == []


def test_un_dia_mal_escrito_NO_manda_todos_los_dias():
    """Cae a «ningún día», no a «todos»: el error quita ruido, no lo agrega."""
    assert cron.DIAS.get("lunes") is None
    assert cron.DIAS["monday"] == 0 and cron.DIAS["sunday"] == 6
