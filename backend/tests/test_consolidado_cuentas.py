# -*- coding: utf-8 -*-
"""El P&L por cuenta para el Owner Dashboard (owner, 2026-10-26).

Sin versión, el forecast que sale es el ★ Current y el actual es el real — nunca
el espejo del Pre-Cierre, que es lo último creado y trae un solo mes.
"""
from types import SimpleNamespace as E

from app.api.consolidado_api import _escoger_escenario


def test_forecast_sin_version_es_el_current():
    lista = [E(version="October", is_current_forecast=False), E(version="September", is_current_forecast=True)]
    assert _escoger_escenario(lista, "FORECAST", None).version == "September"


def test_forecast_sin_marca_es_el_mas_reciente():
    lista = [E(version="October", is_current_forecast=False), E(version="September", is_current_forecast=False)]
    assert _escoger_escenario(lista, "FORECAST", None).version == "October"


def test_actual_salta_el_espejo_del_precierre():
    lista = [E(version="Pre-Cierre", es_precierre=True), E(version="actual", es_precierre=False)]
    assert _escoger_escenario(lista, "ACTUAL", None).version == "actual"


def test_version_exacta_manda():
    lista = [E(version="Pre-Cierre", es_precierre=True), E(version="actual", es_precierre=False)]
    assert _escoger_escenario(lista, "ACTUAL", "Pre-Cierre").version == "Pre-Cierre"


def test_el_pl_por_linea_escoge_igual_que_por_cuenta():
    """`/propia/` (el que lee el Excel en vivo) usaba «el más reciente» a secas y
    entregaba el espejo del Pre-Cierre como ACTUAL (owner, 2026-11-06)."""
    import inspect
    from app.api.consolidado_api import consolidado_propia
    assert "_escoger_escenario(" in inspect.getsource(consolidado_propia)


def test_la_ruta_esta_registrada():
    from app.api.consolidado_api import router
    assert "/consolidado/propia/cuentas/" in [r.path for r in router.routes]


def test_el_consolidado_por_cuenta_no_saca_la_cafeteria():
    """El Full Detail saca el 0220 de los reales importados; el consolidado por cuenta lo trae (owner, 2026-11-01)."""
    import inspect
    from app.api import consolidado_api
    src = inspect.getsource(consolidado_api.consolidado_cuentas)
    assert "_cargar_detalle(session, escenario, frozenset())" in src
