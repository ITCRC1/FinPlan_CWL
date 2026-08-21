# -*- coding: utf-8 -*-
"""UN MES CERRADO NO SE MUEVE NI UN CENTAVO.

**El ciclo real del owner (2026-08-16).**

    «Subo julio → se actualiza el ACTUAL 2026 → el Forecast Working se actualiza
    automáticamente → cierro y hago ajustes en el forecast y lo guardo como
    Agosto una vez que ya lo he revisado. **Esto no sucede inmediato, puede ser
    días.**»

Durante esa ventana de días el Working está VIVO. Si algo toca julio ahí, se
mete en la foto de agosto sin que nadie lo note, y la foto queda con un julio
distinto del que él revisó y cerró.

**El agujero grande no era una grilla, era el recálculo.** `recalculate_scenario`
escribía los DOCE meses sin filtro y se dispara como efecto secundario desde doce
pantallas — incluido `AvisoMoneda`, que es un banner descartable de un clic. Y
dos de sus etapas (`_recalc_allocations`, `_persist_pl`) hacían `DELETE` de TODO
el escenario antes de reescribir.

⚠️ **El modo de falla que vigila este archivo es filtrar la escritura y NO el
borrado.** Eso deja el resultado peor que sin proteger: los meses cerrados se
pierden y nada los repone. Por eso hay una prueba por cada `DELETE`.

⚠️ **Y el segundo: sacar los meses cerrados del REPARTO.** `repartir_beneficio`
reparte un monto ANUAL entre las filas del año por FTE. Si las filas cerradas se
excluyeran de la lista, el mismo monto se repartiría entre menos filas y los
meses ABIERTOS subirían solos — proteger julio movería agosto, que es justo lo
contrario de lo que se está construyendo.
"""
import inspect
from decimal import Decimal

import pytest

from app.engine import meses_cerrados as mc
from app.engine import recalculate as recalc


# ── Qué es un mes cerrado ────────────────────────────────────────────────────

class _Esc:
    def __init__(self, tipo="FORECAST", corte=6, sid="x"):
        self.id = sid
        self.type = tipo
        self.actuals_through = corte
        self.version = "Working"
        self.year = 2026
        self.hotel_id = "CWL"


@pytest.mark.asyncio
async def test_un_forecast_cierra_hasta_su_corte():
    """El caso vivo: Working 2026 con corte=6 → enero a junio cerrados."""
    assert await mc.meses_cerrados(None, _Esc("FORECAST", 6)) == {1, 2, 3, 4, 5, 6}


@pytest.mark.asyncio
async def test_un_forecast_sin_corte_no_cierra_nada():
    assert await mc.meses_cerrados(None, _Esc("FORECAST", 0)) == set()


@pytest.mark.asyncio
async def test_un_budget_no_cierra_meses_aunque_traiga_corte():
    """Un presupuesto no cierra meses. Si trae `actuals_through` cargado por
    accidente no se le hace caso: el desvío al ACTUAL enlazado tampoco se le
    aplica, así que tomarlo acá inventaría un cierre que ningún otro camino
    reconoce."""
    assert await mc.meses_cerrados(None, _Esc("BUDGET", 6)) == set()


@pytest.mark.asyncio
async def test_un_actual_cierra_los_meses_con_dato(monkeypatch):
    async def _con_dato(session, sid):
        return {1, 2, 3, 4, 5}
    monkeypatch.setattr(mc, "meses_con_dato", _con_dato)
    assert await mc.meses_cerrados(None, _Esc("ACTUAL", 0)) == {1, 2, 3, 4, 5}


# ── El recálculo respeta el corte ────────────────────────────────────────────

@pytest.fixture(scope="module")
def orquestador() -> str:
    return inspect.getsource(recalc.recalculate_scenario)


def test_el_conjunto_se_calcula_una_sola_vez(orquestador):
    """Que cada etapa lo resolviera por su cuenta es exactamente cómo se separan
    dos reglas que tienen que decir lo mismo."""
    assert orquestador.count("meses_cerrados_de(session, scenario)") == 1


@pytest.mark.parametrize("etapa", [
    "_derivar_monedas(session, scenario, cerrados",
    "_recalc_payroll(session, scenario, avisos, cerrados)",
    "_recalc_allocations(session, scenario, avisos, cerrados)",
    "_persist_pl(session, scenario, revenue_results, cerrados)",
])
def test_las_cuatro_etapas_reciben_los_meses_cerrados(orquestador, etapa):
    assert etapa in orquestador, (
        f"{etapa} volvió a correr sin el corte: esa etapa reescribe los doce "
        f"meses y se dispara desde doce pantallas")


def test_el_recalculo_avisa_que_hay_meses_cerrados(orquestador):
    """Proteger en silencio es el mismo defecto con otro signo."""
    assert "Meses cerrados:" in orquestador


# ── Los DELETE totales: el modo de falla caro ────────────────────────────────

@pytest.mark.parametrize("fn,tabla", [
    (recalc._recalc_allocations, "AllocationEntry"),
    (recalc._persist_pl, "PLLine"),
])
def test_el_borrado_se_filtra_igual_que_la_escritura(fn, tabla):
    """Filtrar la escritura y no el borrado deja el resultado PEOR que hoy:
    los meses cerrados se pierden y nada los repone."""
    src = inspect.getsource(fn)
    assert f"{tabla}.month.notin_" in src, (
        f"{fn.__name__} volvió a borrar TODO el escenario antes de reescribir "
        f"solo los meses abiertos: los meses cerrados se pierden")
    assert "protegidos" in src


def test_un_mes_cerrado_sin_filas_no_se_protege():
    """Si no tiene nada que congelar, saltearlo dejaría un agujero permanente en
    un escenario que nunca se recalculó."""
    for fn in (recalc._recalc_allocations, recalc._persist_pl):
        src = inspect.getsource(fn)
        assert "protegidos &" in src or "cerrados & con_reparto" in src, (
            f"{fn.__name__} protege meses cerrados que todavía no tienen filas: "
            f"quedarían vacíos para siempre")


def test_el_pl_solo_congela_lo_que_el_escenario_produce():
    """Un forecast rodante ESPEJA sus meses cerrados del ACTUAL enlazado. Ahí la
    única fuente es lo subido —«en un histórico manda lo subido»— y congelar el
    espejo solo lo dejaría viejo."""
    src = inspect.getsource(recalc._persist_pl)
    assert "meses_propios(session, scenario)" in src


def test_la_rama_actual_no_se_congela():
    """No calcula nada: proyecta a `pl_lines` lo que ya está cargado. Congelarla
    dejaría el proyectado viejo frente a lo subido.

    El anclaje sigue a la condición, que dejó de mirar el TIPO y pasa a mirar el
    ORIGEN (`lo_subido_manda`). Lo que se prueba no cambió."""
    orq = inspect.getsource(recalc.recalculate_scenario)
    i = orq.index('if scenario.type == "ACTUAL" or await lo_subido_manda(')
    j = orq.index("return", i)
    assert "cerrados" not in orq[i:j]


# ── La planilla: proteger julio no puede mover agosto ────────────────────────

@pytest.fixture(scope="module")
def planilla() -> str:
    return inspect.getsource(recalc._recalc_payroll)


def test_las_filas_cerradas_siguen_pesando_en_el_reparto(planilla):
    """`repartir_beneficio` reparte un monto ANUAL entre las filas del año. Si
    las cerradas se excluyeran, el mismo monto iría a menos filas y los meses
    ABIERTOS subirían solos."""
    i = planilla.index("if month in cerrados:")
    bloque = planilla[i:i + 600]
    assert "para_ins.append((entry, pos))" in bloque, (
        "las filas de meses cerrados salieron del reparto: proteger julio "
        "ahora mueve agosto")


def test_las_filas_cerradas_se_devuelven_como_estaban(planilla):
    assert "congeladas" in planilla
    assert "setattr(entry, col, valor)" in planilla


def test_no_se_inventa_planilla_en_un_mes_cerrado(planilla):
    """Una posición creada en agosto no nace con filas de julio."""
    i = planilla.index("if month in cerrados:")
    assert "if entry is None:" in planilla[i:i + 200]


def test_la_foto_de_la_planilla_cubre_los_17_conceptos(planilla):
    """Congelar solo algunos dejaría el resto moviéndose sin que nada lo diga."""
    assert "PAYROLL_ALL_COLS" in planilla
    assert len(recalc.PAYROLL_ALL_COLS) == 17


# ── El tipo de cambio ────────────────────────────────────────────────────────

def test_el_tipo_de_cambio_no_reescribe_meses_cerrados():
    """El TC vive en una tabla aparte: basta tocarlo para que julio ya cerrado
    cambie de monto, porque `_derivar_monedas` re-expresa los DOCE."""
    src = inspect.getsource(recalc._derivar_monedas)
    assert "if month in cerrados:" in src
    assert "congelados" in src, (
        "el mes cerrado se congela en silencio: el owner no tiene cómo saber "
        "que su cambio de TC no entró")


# ── El candado que le faltaba a costos ───────────────────────────────────────

def test_la_pantalla_de_repartos_protege_igual_que_el_recalculo():
    """Dos caminos a la misma tabla que protegen distinto son un camino SIN
    protección. `calculate_allocations` delega en `_recalc_allocations`, pero el
    corte es un ARGUMENTO: llamarla sin él dejaba esa pantalla borrando y
    refabricando los doce meses."""
    from app.api import allocation_api
    src = inspect.getsource(allocation_api.calculate_allocations)
    assert "meses_cerrados(session, scenario)" in src
    assert "_recalc_allocations(session, scenario, avisos, cerrados)" in src


def test_el_recalculo_de_costos_respeta_el_candado():
    """Reescribe los DOCE meses y era el único de su familia sin candado: corría
    igual sobre una versión enllavada, que es justo lo que `locked` promete que
    no puede pasar."""
    from app.api import costs_api
    src = inspect.getsource(costs_api.recalculate_costs)
    assert "assert_editable()" in src


# ── La foto y el motor tienen que nombrar los meses igual ────────────────────

def test_la_foto_y_el_motor_nombran_igual():
    """Si se separaran, «la última foto» apuntaría a un mes distinto del que dice."""
    from app.api.scenarios_api import _SNAP_MONTHS
    assert mc.SNAP_MONTHS == _SNAP_MONTHS


@pytest.mark.parametrize("version,mes", [("Jan", 1), ("Jul", 7), ("Dec", 12)])
def test_el_mes_de_la_foto_sale_del_nombre(version, mes):
    assert mc.mes_de_la_foto(_Foto(version)) == mes


class _Foto:
    def __init__(self, version):
        self.version = version


def test_sin_foto_no_hay_mes():
    assert mc.mes_de_la_foto(None) == 0
