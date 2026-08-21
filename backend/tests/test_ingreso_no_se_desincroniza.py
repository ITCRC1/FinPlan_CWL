# -*- coding: utf-8 -*-
"""EL INGRESO DERIVADO BAJA AL SUB-MAYOR, Y NO PUEDE VOLVER A SEPARARSE.

Owner, 2026-08-17, viendo el desfase: *«no puede quedar así… si todo estaba
trabajando bien… no entiendo por qué se desincroniza. Esto no puede volver a
pasar.»*

**Cómo se separó, sin que nada fallara.** Hasta el 15-ago los presupuestos
leían el ingreso del checkbook (`revenue_source = 'checkbook'`): el checkbook
ERA la fuente, y el botón «pasar al checkbook» era el único camino. Con el
mixer de canales (migraciones 116-117) los seis presupuestos 2027 pasaron a
`drivers`, y desde entonces el P&L calcula el ingreso con tarifas × ocupación ×
canales mientras **nadie vuelve a escribir el checkbook**. Quedó una foto de la
última vez que alguien apretó un botón.

Medido en el `BUDGET Working 2027`: checkbook **$6.449.238** contra un modelo
vivo de **$6.374.026** — $75.212, y **$118.218 solo en Rooms**. Los dos números
estaban bien guardados y decían cosas distintas.

Por eso el arreglo va en el RECÁLCULO y no en otro botón: un botón es
exactamente lo que falló.
"""
from decimal import Decimal

import pytest

from app.engine import recalculate as rc


class _Escenario:
    def __init__(self, revenue_source="drivers"):
        self.id = "esc-1"
        self.hotel_id = "CWL"
        self.revenue_source = revenue_source


class _Resultado:
    """Lo mínimo que `revenue_line_dict` necesita leer."""
    def __init__(self, **kw):
        for campo in ("rooms", "food", "beverage", "activities", "transport",
                      "sustainability", "spa", "retail", "fnb_misc",
                      "innoceana", "laundry", "club", "club_actividad",
                      "club_visitantes"):
            setattr(self, campo, kw.get(campo, Decimal("0")))


class _Filas:
    """Un `session` de mentira: guarda lo que se agrega y lo que se pide."""
    def __init__(self, existentes=()):
        self.existentes = list(existentes)
        self.agregadas = []

    async def execute(self, _q):
        filas = self.existentes

        class _R:
            def scalars(self_inner):
                class _S:
                    def all(self_s):
                        return filas
                return _S()
        return _R()

    def add(self, obj):
        self.agregadas.append(obj)

    async def flush(self):
        return None


@pytest.mark.asyncio
async def test_el_recalculo_baja_el_ingreso_derivado_al_submayor():
    """Lo que el modelo calcula tiene que quedar escrito en el sub-mayor."""
    ses = _Filas()
    escritas = await rc.sincronizar_ingreso_al_checkbook(
        ses, _Escenario(), {1: _Resultado(rooms=Decimal("1000"))})
    assert escritas >= 1
    rooms = [f for f in ses.agregadas if f.line == "ROOMS"]
    assert rooms and Decimal(str(rooms[0].jan)) == Decimal("1000")


@pytest.mark.asyncio
async def test_en_modo_checkbook_NO_escribe_nada():
    """⚠️ La guarda que no se puede quitar.

    En `checkbook` las filas son montos **tipeados por el usuario** y son la
    fuente del P&L. Sobrescribirlas con el ingreso derivado le borraría el
    presupuesto a alguien — y el P&L seguiría cuadrando, contra el número
    equivocado, así que no habría forma de notarlo.

    La condición es el `revenue_source`, **no** el tipo ni el año del escenario.
    """
    ses = _Filas()
    escritas = await rc.sincronizar_ingreso_al_checkbook(
        ses, _Escenario(revenue_source="checkbook"),
        {1: _Resultado(rooms=Decimal("999999"))})
    assert escritas == 0
    assert ses.agregadas == []


@pytest.mark.asyncio
async def test_no_toca_los_meses_cerrados():
    """Misma regla que el resto del recálculo: un mes cerrado no se reescribe."""
    ses = _Filas()
    await rc.sincronizar_ingreso_al_checkbook(
        ses, _Escenario(), {1: _Resultado(rooms=Decimal("1000"))}, cerrados={1})
    rooms = [f for f in ses.agregadas if f.line == "ROOMS"]
    # La fila se crea, pero enero queda como estaba (en cero) porque está cerrado.
    assert not rooms or Decimal(str(rooms[0].jan or 0)) == Decimal("0")


@pytest.mark.asyncio
async def test_el_recalculo_llama_a_la_sincronizacion():
    """El centinela: que el arreglo siga colgado del RECÁLCULO.

    Si alguien lo saca de ahí y lo vuelve a poner detrás de un botón, el desfase
    regresa igual que la primera vez — y otra vez sin que nada falle.
    """
    import inspect
    fuente = inspect.getsource(rc.recalculate_scenario)
    assert "sincronizar_ingreso_al_checkbook" in fuente, (
        "el recálculo dejó de sincronizar el ingreso al sub-mayor")
