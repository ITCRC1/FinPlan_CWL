# -*- coding: utf-8 -*-
"""
EL CORTE DEL FORECAST AVANZA SOLO, Y NO SE PASA.

**Cómo trabaja el rolling forecast (owner, 2026-08-13):** el Forecast Working de
un año está compuesto por los meses ya cerrados —que salen del ACTUAL— y los que
faltan, que salen de su propia proyección. Cada vez que se sube un actual, ese
mes tiene que pasarse al lado cerrado.

Eso ya lo hacía `actuals_through`, pero solo al subir **mes a mes** (merge). Una
recarga completa del año —que es justo cuando uno no se quiere acordar de mover
nada a mano— dejaba el corte donde estaba.

## Por qué no basta con «el último mes del archivo»

Una recarga anual sube los DOCE meses aunque solo los primeros tengan cifras:
las columnas de los meses que faltan vienen en cero, no vacías.

Si el corte avanzara al último mes PRESENTE, un archivo con datos hasta julio lo
empujaría hasta diciembre. De agosto en adelante el forecast mostraría los ceros
del Actual como si fueran el cierre real, en lugar de su propia proyección — y
el GOP seguiría cuadrando. El año se acabaría en julio sin que nada lo dijera.

Por eso se mira el VALOR y no la presencia. De paso queda más conservador con
los meses cerrados de verdad: en Corcovado octubre cierra en cero, así que un
archivo que termine ahí deja el corte en septiembre. Quedarse corto no hace daño
—el forecast proyecta un mes cerrado, que da casi cero igual—; pasarse sí.
"""
import pytest

from app.api.scenarios_api import _ultimo_mes_con_dato

MESES_VACIOS = {m: {} for m in range(1, 13)}


def _bloque(stats=None, lines=None) -> dict:
    return {"stats": stats or {}, "lines": lines or {}}


def test_toma_el_ultimo_mes_con_cifras():
    blk = _bloque(lines={m: {"TOTAL_REVENUES": 1000.0 * m} for m in range(1, 8)})
    assert _ultimo_mes_con_dato(blk) == 7


def test_los_meses_en_cero_del_final_no_arrastran_el_corte():
    """El caso que motiva todo: recarga anual con datos hasta julio."""
    lines = {m: {"TOTAL_REVENUES": 1000.0 * m} for m in range(1, 8)}
    lines.update({m: {"TOTAL_REVENUES": 0.0} for m in range(8, 13)})
    assert _ultimo_mes_con_dato(_bloque(lines=lines)) == 7, (
        "el corte se paso a diciembre: el forecast pierde su proyeccion de "
        "agosto en adelante y muestra los ceros del Actual como si fueran cierre")


def test_un_cero_en_medio_no_corta_el_avance():
    """Octubre cerrado no puede dejar el corte en septiembre si noviembre y
    diciembre sí tienen cifras."""
    lines = {m: {"TOTAL_REVENUES": 1000.0} for m in range(1, 13)}
    lines[10] = {"TOTAL_REVENUES": 0.0}
    assert _ultimo_mes_con_dato(_bloque(lines=lines)) == 12


def test_las_estadisticas_tambien_cuentan_como_dato():
    """Un mes puede traer noches y ocupación sin líneas del P&L."""
    blk = _bloque(stats={5: {"rooms_occupied": 320.0}}, lines={})
    assert _ultimo_mes_con_dato(blk) == 5


def test_un_bloque_sin_una_sola_cifra_no_mueve_nada():
    assert _ultimo_mes_con_dato(_bloque(lines=MESES_VACIOS)) == 0
    assert _ultimo_mes_con_dato(_bloque()) == 0


def test_los_none_no_cuentan_como_dato():
    assert _ultimo_mes_con_dato(_bloque(lines={3: {"X": None}})) == 0


def test_un_negativo_es_dato():
    """Una pérdida o un ajuste en contra es un cierre igual de real."""
    assert _ultimo_mes_con_dato(_bloque(lines={4: {"NET_PROFIT": -5000.0}})) == 4


# ── Que el endpoint lo use, y con las condiciones correctas ─────────────────
import inspect

from app.api import scenarios_api


@pytest.fixture(scope="module")
def fuente() -> str:
    return inspect.getsource(scenarios_api.import_pl_snapshot)


def test_el_avance_ya_no_depende_del_modo_merge(fuente):
    """Era `if merge and typ == "ACTUAL"`. Con el modo por defecto —reemplazo
    total— la recarga completa no movia el corte."""
    assert 'if typ == "ACTUAL":' in fuente
    assert 'if merge and typ == "ACTUAL"' not in fuente


def test_el_avance_usa_la_regla_del_ultimo_mes_con_dato(fuente):
    assert "_ultimo_mes_con_dato(blk)" in fuente
    assert "max(upload_months)" not in fuente, (
        "volvio a avanzar al ultimo mes PRESENTE en vez del ultimo con dato")


def test_el_corte_solo_avanza_nunca_retrocede(fuente):
    """Un actual viejo resubido no puede echar para atrás el cierre de meses
    que ya se cerraron."""
    assert "(s.actuals_through or 0) < last_m" in fuente


def test_solo_se_mueve_el_forecast_vivo(fuente):
    """Los reforecasts archivados y los snapshots son fotos de una decision:
    si se les moviera el corte dejarian de decir lo que decian el dia que se
    tomaron."""
    assert 'getattr(s, "is_current_forecast", False)' in fuente
    assert 's.type == "FORECAST"' in fuente
    assert "s.year == yr" in fuente and "s.hotel_id == hotel_id" in fuente


# ── El camino que usa la pantalla ────────────────────────────────────────────
# La pantalla de carga llama a `import-gl-detail`, no a `import-pl-snapshot`.
# Ese endpoint NO movía el corte, así que el arreglo del otro no habría servido
# de nada: se sube el cierre de un mes y el forecast lo sigue proyectando.
#
# Se descubrió porque el typecheck del frontend marcó que `cut_advanced` no
# existía en el tipo de esa respuesta. Un error de tipos delatando un error de
# diseño.

@pytest.fixture(scope="module")
def fuente_gl() -> str:
    return inspect.getsource(scenarios_api.import_gl_detail)


def test_el_endpoint_de_la_pantalla_mueve_el_corte(fuente_gl):
    assert "cut_advanced" in fuente_gl, (
        "import_gl_detail no mueve el corte: es el que usa la pantalla de carga")
    assert '"cut_advanced": cut_advanced' in fuente_gl, (
        "lo calcula pero no lo devuelve, asi que la pantalla no lo puede mostrar")


def test_solo_avanza_por_escenarios_de_tipo_actual(fuente_gl):
    """Subir un Budget o un Forecast no puede cerrar meses."""
    assert 'if target.type == "ACTUAL":' in fuente_gl


def test_no_avanza_en_vista_previa(fuente_gl):
    """La Vista previa no escribe nada — tampoco el corte."""
    assert "if not dry_run:" in fuente_gl
    i = fuente_gl.index("cut_advanced = []")
    assert "if not dry_run:" in fuente_gl[i:i + 200], (
        "el avance del corte no esta protegido por dry_run")


def test_solo_cuenta_los_meses_con_cifras(fuente_gl):
    """Mismo criterio que el otro endpoint: un mes en cero del final no puede
    arrastrar el corte y dejar al forecast sin proyección."""
    assert "con_dato" in fuente_gl and "max(con_dato)" in fuente_gl


def test_no_retrocede_ni_toca_los_archivados(fuente_gl):
    assert "(f.actuals_through or 0) < last_m" in fuente_gl
    assert "Scenario.is_current_forecast == True" in fuente_gl
