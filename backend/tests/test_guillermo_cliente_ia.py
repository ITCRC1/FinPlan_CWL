# -*- coding: utf-8 -*-
"""La llamada al modelo — pendiente 18 (`docs/GUILLERMO.md` §8 y §9).

⚠️ **Nada de esto prueba la API de verdad.** La llave se pone al clonar
(decisión del owner, 2026-08-20), así que el cliente se escribió sin poder
llamar una vez. Lo que sí se prueba es lo que decide si el módulo es seguro: que
el payload sucio **no salga**, que una cuenta inventada **no entre**, y que un
fallo no tumbe la ronda.
"""
import inspect

import pytest

from app.guillermo import cliente_ia, ia

CANDIDATAS = [{"codigo": "7065", "nombre": "Cleaning Supplies"},
              {"codigo": "7250", "nombre": "Guest Supplies"}]


# ── Sin llave no se llama ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sin_llave_no_se_llama_y_dice_donde_va(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    p, motivo = await cliente_ia.proponer_cuenta("mant piscina", "MANT PISCINA",
                                                 CANDIDATAS)
    assert p is None
    assert "ANTHROPIC_API_KEY" in motivo


# ── El guardia del payload ───────────────────────────────────────────────────

def test_el_guardia_se_CONSULTA_antes_de_llamar():
    """⚠️ **El defecto que esto evita.** `payload_limpio` ya existía y nadie lo
    llamaba: una regla que nadie verifica no protege de nada. La comprobación
    tiene que estar ANTES de construir el mensaje, no después."""
    fuente = inspect.getsource(cliente_ia.proponer_cuenta)
    assert "payload_limpio" in fuente
    assert fuente.index("payload_limpio") < fuente.index("messages.create")


@pytest.mark.asyncio
async def test_un_payload_con_PII_NO_SALE(monkeypatch):
    """Aunque haya llave. El concepto trae un correo embebido: `redactar` lo
    tapa, y si algún día dejara de taparlo, el guardia frena la llamada."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-de-mentira")

    llamadas = []
    monkeypatch.setattr(ia, "payload_limpio",
                        lambda p: (False, ["PII sin redactar en concepto"]))
    monkeypatch.setattr(cliente_ia, "_cliente",
                        lambda: llamadas.append("¡llamó!"))

    p, motivo = await cliente_ia.proponer_cuenta("pago a juan@x.com", "X",
                                                 CANDIDATAS)
    assert p is None
    assert "PII" in motivo
    assert llamadas == [], "llamó al modelo con un payload que no pasó el guardia"


@pytest.mark.asyncio
async def test_sin_candidatas_no_se_llama(monkeypatch):
    """Elegir fuera de la lista es lo que el system prompt prohíbe; mandarlo
    sin lista es pedirle que lo haga."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-de-mentira")
    p, motivo = await cliente_ia.proponer_cuenta("x", "X", [])
    assert p is None and "candidatas" in motivo


# ── Lo que vuelve ────────────────────────────────────────────────────────────

class _Bloque:
    def __init__(self, entrada):
        self.type = "tool_use"
        self.input = entrada


class _Respuesta:
    def __init__(self, contenido, stop="tool_use"):
        self.content = contenido
        self.stop_reason = stop


def _responde(resp):
    class _Msgs:
        async def create(self, **kw):
            _responde.ultimo = kw
            return resp

    class _C:
        messages = _Msgs()

    return lambda: _C()


@pytest.mark.asyncio
async def test_una_propuesta_valida_vuelve_con_su_explicacion(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-de-mentira")
    monkeypatch.setattr(cliente_ia, "_cliente", _responde(_Respuesta(
        [_Bloque({"cuenta": "7065", "confianza": 0.9,
                  "explicacion": "es limpieza de áreas comunes"})])))

    p, motivo = await cliente_ia.proponer_cuenta("mant piscina quimicos",
                                                 "MANT PISCINA QUIMICOS",
                                                 CANDIDATAS)
    assert motivo == "ok"
    assert p.cuenta == "7065" and p.confianza == 0.9
    assert "limpieza" in p.explicacion
    # ⚠️ El «por qué» es obligatorio por el principio rector: una propuesta sin
    # explicación no se puede auditar ni discutir.
    assert p.explicacion


@pytest.mark.asyncio
async def test_una_cuenta_INVENTADA_se_descarta(monkeypatch):
    """⚠️ El system prompt pide elegir de la lista, pero **pedirlo no es
    garantizarlo**. Un código inventado guardado en la cola parecería una
    propuesta legítima, y alguien la aprobaría."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-de-mentira")
    monkeypatch.setattr(cliente_ia, "_cliente", _responde(_Respuesta(
        [_Bloque({"cuenta": "9999", "confianza": 1.0, "explicacion": "x"})])))

    p, motivo = await cliente_ia.proponer_cuenta("x", "X", CANDIDATAS)
    assert p is None
    assert "9999" in motivo and "candidatas" in motivo


@pytest.mark.asyncio
async def test_una_respuesta_SIN_herramienta_no_revienta(monkeypatch):
    """Un rechazo o un tope de tokens deja la respuesta sin `tool_use`, y
    `content[0].input` reventaría."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-de-mentira")
    monkeypatch.setattr(cliente_ia, "_cliente",
                        _responde(_Respuesta([], stop="max_tokens")))

    p, motivo = await cliente_ia.proponer_cuenta("x", "X", CANDIDATAS)
    assert p is None and "max_tokens" in motivo


@pytest.mark.asyncio
async def test_un_fallo_de_red_NO_tumba_la_ronda(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-de-mentira")

    class _Explota:
        class messages:
            @staticmethod
            async def create(**kw):
                raise ConnectionError("se cayó")

    monkeypatch.setattr(cliente_ia, "_cliente", lambda: _Explota())
    p, motivo = await cliente_ia.proponer_cuenta("x", "X", CANDIDATAS)
    assert p is None and "ConnectionError" in motivo


@pytest.mark.asyncio
async def test_una_confianza_absurda_se_recorta(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-de-mentira")
    monkeypatch.setattr(cliente_ia, "_cliente", _responde(_Respuesta(
        [_Bloque({"cuenta": "7065", "confianza": 42, "explicacion": "x"})])))
    p, _ = await cliente_ia.proponer_cuenta("x", "X", CANDIDATAS)
    assert p.confianza == 1.0

    monkeypatch.setattr(cliente_ia, "_cliente", _responde(_Respuesta(
        [_Bloque({"cuenta": "7065", "confianza": "muy", "explicacion": "x"})])))
    p, _ = await cliente_ia.proponer_cuenta("x", "X", CANDIDATAS)
    assert p.confianza == 0.0


# ── Lo que el módulo NO puede hacer ──────────────────────────────────────────

def test_el_cliente_NO_PUEDE_ESCRIBIR_en_el_modelo_financiero():
    """⚠️ La regla absoluta del §4: una propuesta nunca se aplica sola. La
    forma más fuerte de garantizarlo es que el módulo no tenga con qué — no
    importa una sola tabla del modelo."""
    fuente = inspect.getsource(cliente_ia)
    for prohibido in ("actual_entries", "checkbook", "scenario", "commit(",
                      "db.add", "session"):
        assert prohibido not in fuente.lower(), prohibido


def test_la_herramienta_NO_PIDE_NI_UN_MONTO():
    """⚠️ §9.1: los números nunca los produce el modelo. Toda cifra viene de
    una query; el modelo elige una cuenta, no calcula."""
    campos = cliente_ia.HERRAMIENTA["input_schema"]["properties"]
    assert set(campos) == {"cuenta", "confianza", "explicacion"}
    assert cliente_ia.HERRAMIENTA["input_schema"]["additionalProperties"] is False
    assert cliente_ia.HERRAMIENTA["strict"] is True


def test_la_herramienta_va_FORZADA():
    """Sin `tool_choice` el modelo puede contestar en prosa, y ahí habría que
    parsear texto libre — que es donde se cuela un número inventado."""
    fuente = inspect.getsource(cliente_ia.proponer_cuenta)
    assert 'tool_choice={"type": "tool"' in fuente


def test_los_ids_de_modelo_NO_llevan_sufijo_de_fecha():
    """⚠️ `claude-haiku-4-5-20251001` es una forma vieja. Un id inventado no
    falla al escribirlo: falla con un 404 la primera vez que se llame de
    verdad, que va a ser el día del clonado y no hoy."""
    for m in (ia.MODELO_CHICO, ia.MODELO_GRANDE):
        assert not any(ch.isdigit() for ch in m.split("-")[-1]) or "-20" not in m, m
    assert ia.MODELO_CHICO == "claude-haiku-4-5"
    assert ia.MODELO_GRANDE == "claude-opus-5"
