# -*- coding: utf-8 -*-
"""Traer al forecast los meses que el Actual ya cerró.

Owner, 2026-10-13, con el Forecast September abierto y el YTD en 2.760 noches
cuando el Actual lleva 8.190: *«puedes copiar los actuales en forecast
September»* · *«de enero a setiembre»*.

Un forecast nuevo arranca sin room stats. Los meses ya cerrados hay que traerlos
del Actual, y hasta hoy se hacía a mano: SEIS categorías por NUEVE meses, 54
filas de tres números cada una. Basta que una quede en blanco para que se vayan
sus NOCHES DISPONIBLES, y entonces el denominador se achica y la ocupación y el
RevPAR salen MÁS ALTOS de lo real — el error que ya pasó en agosto 2026 y que
documenta `put_room_stats_entry`.

## Lo que esta puerta NO hace

* **No toca los meses posteriores.** Son la proyección del escenario. En el caso
  del owner, octubre, noviembre y diciembre ya estaban cargados por él y tienen
  que quedar intactos.
* **No recalcula las noches disponibles**: las copia. Derivarlas de nuevo es
  justo donde se pierde una categoría.
* **No toca `actuals_through`.** Ese campo decide hasta dónde el P&L espeja el
  Actual: moverlo cambia de dónde sale la plata de cada mes, y eso es una
  decisión del cierre, no un efecto secundario de copiar estadísticas.
"""
import inspect

from app.api import revenue_api


def test_la_puerta_existe_y_no_escribe_sobre_el_actual():
    """Copiar el Actual sobre sí mismo no tiene sentido y borraría el dato
    bueno para reemplazarlo por una copia de sí mismo."""
    fuente = inspect.getsource(revenue_api.copiar_room_stats_de_actuales)
    assert 'raise ErrorApi(422, "room_stats.destino_es_el_actual")' in fuente
    # Y el origen es el ACTUAL DE VERDAD, no el espejo del Pre-Cierre: son dos
    # ACTUAL del mismo año y el espejo es un borrador.
    assert "actual_de_verdad()" in fuente


def test_solo_copia_hasta_el_mes_pedido():
    """Los meses posteriores son la proyección del escenario y no se tocan."""
    fuente = inspect.getsource(revenue_api.copiar_room_stats_de_actuales)
    assert "if not 1 <= f.month <= hasta:" in fuente
    assert "continue" in fuente
    # El borrado también está acotado: si borrara todo, se llevaría puestos los
    # meses que el owner acababa de cargar a mano.
    assert "ActualRoomStat.month.in_(meses)" in fuente


def test_el_tope_por_defecto_es_el_ultimo_mes_CON_NOCHES():
    """«De enero a setiembre», sin que haya que decirlo.

    El Actual trae los meses futuros en CERO —octubre, noviembre y diciembre
    existen con seis filas vacías—, así que «el último mes que tiene filas» se
    pasaría hasta diciembre y traería ceros encima de la proyección. El corte
    correcto es el último mes con noches OCUPADAS.
    """
    fuente = inspect.getsource(revenue_api.copiar_room_stats_de_actuales)
    assert "float(f.nights_occupied or 0) > 0" in fuente


def test_las_noches_disponibles_se_COPIAN_no_se_recalculan():
    """⚠️ El error más caro de este cuadro, y ya pasó una vez.

    Si se derivaran de nuevo y una categoría quedara fuera, el denominador se
    achica y la ocupación sale MÁS ALTA de lo real: 46,8 % en vez de 45,8 % en
    agosto 2026. Un número malo se revisa; uno favorable se acepta.
    """
    fuente = inspect.getsource(revenue_api.copiar_room_stats_de_actuales)
    assert "nights_available=f.nights_available" in fuente


def test_no_mueve_actuals_through():
    """Ese campo decide de dónde sale la plata de cada mes en el P&L. Moverlo
    como efecto secundario de copiar estadísticas sería cambiar el resultado
    sin que nadie lo pida."""
    fuente = inspect.getsource(revenue_api.copiar_room_stats_de_actuales)
    assert "actuals_through" not in fuente.replace(
        "`actuals_through`", "")          # solo se nombra en el comentario


def test_la_pantalla_pregunta_antes_y_no_lo_ofrece_en_el_actual():
    """Reemplaza meses: se pregunta. Y en el ACTUAL el botón no existe, porque
    ahí el dato ya es el bueno."""
    import pathlib

    pagina = (pathlib.Path(__file__).resolve().parents[2] / "frontend" / "app"
              / "operation-insight" / "room-stats" / "page.tsx")
    txt = pagina.read_text(encoding="utf-8", errors="replace")
    assert "copiarRoomStatsDeActuales" in txt
    assert "copiarConfirmar" in txt and "confirm(" in txt
    assert '?.type !== "ACTUAL"' in txt


# ── Las noches de un mes cerrado no entran por NINGUNA puerta ───────────────

def test_el_panel_de_carga_no_ofrece_noches_en_un_mes_cerrado():
    """Owner, 2026-10-13, por SEXTA vez sobre el mismo número: *«REVISA ESTO»*.

    Tras traer los actuales, el YTD seguía en 10.950. Octubre tenía 930 noches
    GUARDADAS porque el panel de carga calculaba `calendar.monthrange()` sin
    mirar el cierre: al grabar el mes, escribía la disponibilidad de un mes que
    el hotel no abre.
    """
    fuente_get = inspect.getsource(revenue_api.get_room_stats_entry)
    fuente_put = inspect.getsource(revenue_api.put_room_stats_entry)
    for f in (fuente_get, fuente_put):
        assert "_dias_vendibles" in f
        assert "calendar.monthrange" not in f


def test_la_regla_sale_de_UNA_sola_funcion():
    """⚠️ Lo que hizo que esto tomara seis vueltas.

    Cada lugar que calculaba las noches por su cuenta se olvidó del cierre en su
    propio momento: el motor, la pantalla de Ocupación, el panel de carga, el
    camino de drivers. Mientras la regla se repita, va a haber un séptimo.
    """
    fuente = inspect.getsource(revenue_api._dias_vendibles)
    assert "meses_cerrados_resueltos" in fuente


def test_el_cierre_manda_tambien_al_LEER():
    """Las filas ya guardadas con el calendario viejo no obligan a volver a
    grabar el mes: la regla se aplica al leer y la fila se corrige sola la
    próxima vez que alguien la guarde."""
    fuente = inspect.getsource(revenue_api._room_stats_from_actuals)
    assert "meses_cerrados_resueltos" in fuente
    assert "def _disp(" in fuente


def test_el_camino_de_DRIVERS_tambien():
    """Un escenario sin estadísticas cargadas sale por los drivers. Si sólo se
    arreglara el camino de los actuales, la mitad de los forecast seguiría
    contando octubre — que es exactamente lo que pasó con `Working`."""
    fuente = inspect.getsource(revenue_api.get_revenue_by_room_type)
    if "room_type_breakdown" in fuente:
        assert "cerrado=" in fuente
    else:
        # Vive en el helper que arma la respuesta por drivers.
        import app.api.revenue_api as m
        todo = inspect.getsource(m)
        i = todo.index("room_type_breakdown(")
        assert "cerrado=" in todo[i:i + 400]
