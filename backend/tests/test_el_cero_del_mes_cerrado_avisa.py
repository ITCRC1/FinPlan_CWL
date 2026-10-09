# -*- coding: utf-8 -*-
"""El cero más caro del sistema tiene que avisar en TODAS las pantallas.

Owner, 2026-10-06: *«por qué no hay ingresos forecast en setiembre»*.

Un mes dentro del corte de un forecast **no se calcula con su checkbook**: se lee
del ACTUAL enlazado (`recalculate._compute_pl_month_core`). Si ese mes todavía no
se subió, el Actual devuelve un P&L vacío y la columna sale en **cero** — sin
error, sin aviso, y pisando la proyección que el forecast sí tenía.

Y queda incoherente consigo mismo: los KPIs del mes SÍ caen de vuelta al
forecast, así que la pantalla muestra noches vendidas y cero ingreso. Dos
fuentes para la misma columna.

El aviso existía desde el 2026-10-06 en el **12m Summary**, que lee por
`/pl/monthly/` y `/pl/doce-meses/`. Pero el **P&L Statement** —donde el owner
mira— lee por `/pl/compare/`, que no traía la señal. Estas pruebas vigilan que
los cuatro caminos la lleven.
"""
import inspect

from app.api import pl_api


def _fuente(nombre: str) -> str:
    return inspect.getsource(getattr(pl_api, nombre))


def test_la_senal_viaja_en_los_CUATRO_caminos():
    """⚠️ Si una pantalla lee por un camino que no la lleva, el cero vuelve a
    pasar en silencio — que es exactamente lo que paso con el P&L Statement."""
    for nombre in ("get_pl_monthly", "get_pl_doce_meses", "get_pl_compare",
                   "get_pl_compare_range"):
        assert hasattr(pl_api, nombre), f"no existe {nombre}"
        assert "meses_cerrados_sin_dato" in _fuente(nombre), (
            f"{nombre} no lleva `meses_cerrados_sin_dato`: una pantalla que lea "
            f"por ahi no va a poder avisar del cero")


def test_la_regla_es_SOLO_para_forecast_con_corte():
    """Un BUDGET o un ACTUAL no leen del Actual enlazado: no hay cero que avisar.
    Y un forecast sin corte tampoco."""
    f = _fuente("meses_cerrados_sin_dato")
    assert 'scenario.type != "FORECAST"' in f
    assert "corte <= 0" in f


def test_se_AVISA_no_se_arregla_solo():
    """⚠️ Cuál de las dos cosas está mal —falta subir el mes, o el corte se
    adelantó— lo decide quien cierra. Que el sistema «arregle» esto tapando el
    cero con la proyección sería inventar un número."""
    f = _fuente("meses_cerrados_sin_dato")
    assert "return" in f
    for verbo in ("session.add", "db.add", "commit", "update("):
        assert verbo not in f, "esto solo informa: no puede escribir nada"


def test_el_banner_del_PL_Statement_NOMBRA_la_version():
    """En el 12m Summary hay un escenario; en el P&L Statement, hasta cuatro.
    Decir «hay un mes en cero» sin decir de quién obliga a adivinar entre cuatro
    columnas."""
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[2]
    tsx = (raiz / "frontend" / "app" / "month-end" / "pl" / "Pantalla.tsx"
           ).read_text(encoding="utf-8")
    assert "meses_cerrados_sin_dato" in tsx, "el P&L Statement no lee la señal"
    i = tsx.index("meses_cerrados_sin_dato")
    tramo = tsx[i - 2000:i + 2000]
    assert "d.label" in tramo, "el aviso tiene que nombrar la versión afectada"
