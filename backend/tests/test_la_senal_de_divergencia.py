# -*- coding: utf-8 -*-
"""LA SEÑAL DE DIVERGENCIA: no impide, MUESTRA.

El candado por mes en las grillas ya se descartó, y con razón: cubría lo chico
—una celda del checkbook— y dejaba abierto el recálculo, que reescribe los doce
meses desde doce pantallas. Un candado que tapa el agujero pequeño y deja el
grande da **seguridad falsa**.

Esto es lo barato que sí sirve: comparar el escenario vivo contra su última foto
y decir **qué mes, qué línea y cuánto** se movió en los meses YA CERRADOS.

⚠️ **Sin foto previa no hay línea base.** Se dice con esas palabras. Comparar el
escenario contra sí mismo daría cero siempre y no probaría nada — sería un
control que parece encendido y no mira nada, que es el modo de falla que ya
apareció dos veces en este sistema.

⚠️ **Un mes cerrado DESPUÉS de la foto no se compara.** Nunca estuvo adentro de
la foto: contarlo como diferencia sería inventar un desvío.
"""
from decimal import Decimal

import pytest

from app.engine import meses_cerrados as mc


class _Esc:
    def __init__(self, tipo="FORECAST", corte=7, version="Working", sid="vivo"):
        self.id = sid
        self.type = tipo
        self.version = version
        self.year = 2026
        self.hotel_id = "CWL"
        self.actuals_through = corte
        self.created_at = None


def _linea(code, name, monto):
    class L:
        line_code = code
        line_name = name
        amount_usd = monto
    return L()


@pytest.fixture
def sin_fotos(monkeypatch):
    async def _no_hay(session, scenario):
        return None
    monkeypatch.setattr(mc, "ultima_foto", _no_hay)


def _con_foto(monkeypatch, version="Jul"):
    foto = _Esc(version=version, sid="foto")

    async def _hay(session, scenario):
        return foto
    monkeypatch.setattr(mc, "ultima_foto", _hay)
    return foto


def _pl(monkeypatch, por_escenario):
    """`por_escenario` = {scenario_id: {mes: {code: (name, monto)}}}."""
    async def _fake(session, scenario, meses):
        todo = por_escenario[scenario.id]
        return {m: todo.get(m, {}) for m in meses}
    monkeypatch.setattr(mc, "_pl_por_mes", _fake)


# ── Sin foto no se inventa línea base ────────────────────────────────────────

@pytest.mark.asyncio
async def test_sin_foto_lo_dice_y_no_compara(sin_fotos):
    r = await mc.divergencia(None, _Esc(corte=7))
    assert r["veredicto"] == "sin_foto"
    assert r["hay_foto"] is False
    assert r["diferencias"] == []
    assert "no hay contra qué comparar" in r["mensaje"]


@pytest.mark.asyncio
async def test_sin_meses_cerrados_no_hay_nada_que_proteger(sin_fotos):
    r = await mc.divergencia(None, _Esc(corte=0))
    assert r["veredicto"] == "sin_meses_cerrados"
    assert r["meses_cerrados"] == []


# ── La señal detecta el cambio, y lo nombra ──────────────────────────────────

@pytest.mark.asyncio
async def test_detecta_un_cambio_en_un_mes_cerrado_con_mes_linea_y_monto(monkeypatch):
    """El caso que motiva todo: julio ya cerrado y fotografiado, y algo lo movió
    durante los días de revisión."""
    _con_foto(monkeypatch, "Jul")
    _pl(monkeypatch, {
        "foto": {7: {"TOTAL_GOP": ("Gross Operating Profit", Decimal("100000"))}},
        "vivo": {7: {"TOTAL_GOP": ("Gross Operating Profit", Decimal("104500"))}},
    })
    r = await mc.divergencia(None, _Esc(corte=7))

    assert r["veredicto"] == "cambio_en_mes_cerrado"
    assert r["meses_movidos"] == [7]
    (d,) = r["diferencias"]
    assert d["mes"] == 7
    assert d["line_code"] == "TOTAL_GOP"
    assert d["line_name"] == "Gross Operating Profit"
    assert d["foto"] == 100000.0
    assert d["ahora"] == 104500.0
    assert d["delta"] == 4500.0


@pytest.mark.asyncio
async def test_un_mes_igual_no_produce_ruido(monkeypatch):
    _con_foto(monkeypatch, "Jul")
    igual = {7: {"TOTAL_GOP": ("GOP", Decimal("100000"))}}
    _pl(monkeypatch, {"foto": igual, "vivo": igual})
    r = await mc.divergencia(None, _Esc(corte=7))
    assert r["veredicto"] == "sin_cambios"
    assert r["diferencias"] == []


@pytest.mark.asyncio
async def test_un_redondeo_no_es_un_cambio(monkeypatch):
    """Un dólar de tolerancia: por debajo es redondeo, no un movimiento."""
    _con_foto(monkeypatch, "Jul")
    _pl(monkeypatch, {
        "foto": {7: {"TOTAL_GOP": ("GOP", Decimal("100000.00"))}},
        "vivo": {7: {"TOTAL_GOP": ("GOP", Decimal("100000.40"))}},
    })
    r = await mc.divergencia(None, _Esc(corte=7))
    assert r["veredicto"] == "sin_cambios"


@pytest.mark.asyncio
async def test_una_linea_que_aparecio_de_la_nada_tambien_cuenta(monkeypatch):
    """Que la línea no estuviera en la foto no la hace inocente: es plata que
    entró a un mes cerrado."""
    _con_foto(monkeypatch, "Jul")
    _pl(monkeypatch, {
        "foto": {7: {}},
        "vivo": {7: {"OH_UTILITIES": ("Utilities", Decimal("3200"))}},
    })
    r = await mc.divergencia(None, _Esc(corte=7))
    (d,) = r["diferencias"]
    assert d["foto"] == 0.0 and d["ahora"] == 3200.0


# ── Los meses abiertos NO son asunto de la señal ─────────────────────────────

@pytest.mark.asyncio
async def test_un_mes_abierto_puede_moverse_todo_lo_que_quiera(monkeypatch):
    """El forecast de agosto en adelante es justamente lo que el owner está
    editando. Avisar por eso sería un aviso siempre encendido, o sea ninguno."""
    _con_foto(monkeypatch, "Jul")
    _pl(monkeypatch, {
        "foto": {7: {"TOTAL_GOP": ("GOP", Decimal("100000"))}},
        "vivo": {7: {"TOTAL_GOP": ("GOP", Decimal("100000"))}},
    })
    r = await mc.divergencia(None, _Esc(corte=7))
    assert r["veredicto"] == "sin_cambios"
    # agosto (mes 8) ni siquiera entra en la comparación
    assert 8 not in r["meses_cerrados"]


# ── La foto anterior al cierre ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_un_mes_cerrado_despues_de_la_foto_no_se_compara(monkeypatch):
    """Julio cerró DESPUÉS de la foto de junio: nunca estuvo adentro de ella.
    Contarlo como diferencia sería inventar un desvío."""
    _con_foto(monkeypatch, "Jun")
    _pl(monkeypatch, {
        "foto": {m: {"TOTAL_GOP": ("GOP", Decimal("100000"))} for m in range(1, 8)},
        "vivo": {m: {"TOTAL_GOP": ("GOP", Decimal("999999"))} for m in range(1, 8)},
    })
    r = await mc.divergencia(None, _Esc(corte=7))
    # se comparan 1..6 (los que la foto cubrió); julio queda fuera
    assert r["meses_movidos"] == [1, 2, 3, 4, 5, 6]
    assert 7 not in r["meses_movidos"]


@pytest.mark.asyncio
async def test_avisa_cuando_hay_meses_cerrados_sin_foto(monkeypatch):
    """El paso que el sistema no acompañaba: cerró julio y no sacó la foto. No
    es un error —puede estar revisando— pero sin esto nada se lo recuerda."""
    _con_foto(monkeypatch, "Jun")
    _pl(monkeypatch, {"foto": {}, "vivo": {}})
    r = await mc.divergencia(None, _Esc(corte=7))
    assert r["meses_cerrados_sin_foto"] == [7]


@pytest.mark.asyncio
async def test_la_foto_entera_anterior_al_cierre_lo_dice(monkeypatch):
    _con_foto(monkeypatch, "Jan")
    r = await mc.divergencia(None, _Esc(corte=0))
    assert r["veredicto"] == "sin_meses_cerrados"


# ── La forma de la respuesta no cambia según el caso ─────────────────────────

LLAVES = {"scenario_id", "escenario", "meses_cerrados", "tolerancia", "hay_foto",
          "foto", "meses_cerrados_sin_foto", "diferencias", "meses_movidos",
          "veredicto", "mensaje"}


@pytest.mark.asyncio
async def test_todos_los_veredictos_devuelven_la_misma_forma(monkeypatch, sin_fotos):
    """Quien consuma esto no tiene que adivinar si la llave existe."""
    r = await mc.divergencia(None, _Esc(corte=7))
    assert LLAVES <= set(r)

    _con_foto(monkeypatch, "Jul")
    _pl(monkeypatch, {"foto": {7: {}}, "vivo": {7: {}}})
    r = await mc.divergencia(None, _Esc(corte=7))
    assert LLAVES <= set(r)
