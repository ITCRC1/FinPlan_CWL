# -*- coding: utf-8 -*-
"""
CADA LINEA DEL CHECKBOOK LLEVA SU MONEDA.

El Budget 2026 se armo con TC 500 y hoy el TC es 450. Los costos que se PAGAN en
colones —cafeteria, alimentos y bebidas— estaban congelados en dolares, asi que
un movimiento del tipo de cambio desalineaba el presupuesto sin avisar.

Ahora la linea declara su moneda. Si es CRC, el dato maestro son los colones y el
dolar de cada mes se DERIVA con el TC de ese mes. Mover el TC y recalcular
re-expresa el mes solo: asi el forecast absorbe el impacto cambiario.
"""
from decimal import Decimal

import pytest

from tests._rutas import FRONT as _FRONT

from app.models.cost_entry import CostEntry
from app.models.opex_entry import OpexEntry

MESES = ["jan", "feb", "mar", "apr", "may", "jun",
         "jul", "aug", "sep", "oct", "nov", "dec"]


def _linea(Model, moneda="USD"):
    e = Model(scenario_id="s", hotel_id="CWL", dept_code="0220",
              account_code="5700", account_name="Cafetería", currency=moneda)
    for m in MESES:
        setattr(e, m, Decimal("0"))
        setattr(e, "crc_" + m, Decimal("0"))
    return e


@pytest.mark.parametrize("Model", [OpexEntry, CostEntry])
def test_una_linea_en_dolares_no_se_convierte(Model):
    """Convertirla seria inventar un efecto cambiario que no existe."""
    e = _linea(Model, "USD")
    e.set_month(1, Decimal("1000"))
    assert e.derivar_usd(1, Decimal("450")) == Decimal("1000")
    assert e.en_colones is False


@pytest.mark.parametrize("Model", [OpexEntry, CostEntry])
def test_los_colones_se_pasan_con_el_tc_del_mes(Model):
    e = _linea(Model, "CRC")
    e.set_crc(1, Decimal("5000000"))
    assert e.derivar_usd(1, Decimal("500")) == Decimal("10000.0000")
    assert e.derivar_usd(1, Decimal("450")) == Decimal("11111.1111")


def test_el_caso_del_owner_budget_2026():
    """TC 500 al presupuestar, 450 hoy: el costo en dolares SUBE 11%."""
    e = _linea(OpexEntry, "CRC")
    e.set_crc(1, Decimal("2500000"))
    a_500 = e.derivar_usd(1, Decimal("500"))
    a_450 = e.derivar_usd(1, Decimal("450"))
    assert a_500 == Decimal("5000.0000")
    assert a_450 == Decimal("5555.5556")
    assert (a_450 / a_500 - 1) * 100 > 11


def test_cada_mes_usa_SU_tipo_de_cambio():
    """Es el punto: el forecast corrige mes a mes y cada mes queda con el suyo."""
    e = _linea(OpexEntry, "CRC")
    for m in range(1, 13):
        e.set_crc(m, Decimal("450000"))
    tc = {1: Decimal("500"), 6: Decimal("475"), 12: Decimal("450")}
    assert e.derivar_usd(1, tc[1]) == Decimal("900.0000")
    assert e.derivar_usd(6, tc[6]) == Decimal("947.3684")
    assert e.derivar_usd(12, tc[12]) == Decimal("1000.0000")


def test_sin_tipo_de_cambio_no_inventa_un_monto():
    e = _linea(OpexEntry, "CRC")
    e.set_crc(1, Decimal("5000000"))
    assert e.derivar_usd(1, Decimal("0")) == Decimal("0")
    assert e.derivar_usd(1, None) == Decimal("0")


def test_las_lineas_existentes_nacen_en_dolares():
    """La migración no debe cambiar ningún número de lo ya cargado."""
    e = OpexEntry(scenario_id="s", hotel_id="CWL", dept_code="0110",
                  account_code="7065", account_name="X")
    assert (e.currency or "USD") == "USD"


def test_el_recalculo_reexpresa_antes_del_pl():
    """La derivación va ANTES de la planilla y del P&L: si fuera después, el P&L
    leería los dólares viejos."""
    import inspect
    from app.engine import recalculate
    src = inspect.getsource(recalculate.recalculate_scenario)
    assert "_derivar_monedas" in src
    assert src.index("_derivar_monedas") < src.index("_recalc_payroll")
    # el ultimo _persist_pl es el del camino presupuesto; el primero es el de la
    # rama ACTUAL, que sale antes y NO convierte (ver la prueba de abajo)
    assert src.index("_derivar_monedas") < src.rindex("_persist_pl")


def test_un_ACTUAL_no_se_convierte():
    """Un actual es un hecho historico ya expresado en dolares. Reexpresarlo con
    el TC de hoy inventaria un efecto cambiario que nunca ocurrio."""
    import inspect
    from app.engine import recalculate
    src = inspect.getsource(recalculate.recalculate_scenario)
    rama = src[src.index('scenario.type == "ACTUAL"'):src.index("_derivar_monedas")]
    assert "_derivar_monedas" not in rama
    assert "return" in rama


# ── La API guarda y devuelve la moneda ───────────────────────────────────────
def test_la_api_de_costos_acepta_moneda_y_colones():
    import inspect
    from app.api import costs_api
    crear = inspect.getsource(costs_api.EntryCreate)
    editar = inspect.getsource(costs_api.EntryUpdate)
    assert "currency" in crear and "crc_jan" in crear and "crc_dec" in crear
    assert "currency" in editar and "crc_jan" in editar


def test_la_api_de_opex_acepta_moneda_y_colones():
    import inspect
    from app.api import opex_api
    fuente = inspect.getsource(opex_api)
    assert "currency" in fuente and "crc_jan" in fuente


def test_al_guardar_una_linea_en_colones_ya_queda_en_dolares():
    """Sin esto la linea se ve en cero hasta que alguien recalcule el escenario."""
    import inspect
    from app.api import costs_api
    crear = inspect.getsource(costs_api.create_cost_entry)
    assert "_derivar_si_es_crc" in crear
    helper = inspect.getsource(costs_api._derivar_si_es_crc)
    assert "get_tc_for_month" in helper and "derivar_usd" in helper


def test_la_moneda_sale_al_leer_la_linea():
    """La pantalla necesita saber en que moneda esta para mostrarlo."""
    import inspect
    from app.api import costs_api
    assert '"currency"' in inspect.getsource(costs_api._entry_to_dict)


# ── El control que evita el analisis con cifra vieja ─────────────────────────
def test_hay_un_control_de_tipo_de_cambio_desactualizado():
    """Si el TC se mueve y nadie recalcula, el P&L muestra el dolar anterior y
    nada lo avisa. Un analisis hecho sobre esa cifra sale mal sin que se note."""
    import inspect
    from app.api import costs_api
    src = inspect.getsource(costs_api.estado_moneda)
    assert "derivar_usd" in src, "no compara contra el TC actual"
    assert "desactualizadas" in src
    assert "sin_tipo_de_cambio" in src


def test_el_control_compara_mes_por_mes():
    """Un solo mes desalineado ya invalida el analisis de ese mes."""
    import inspect
    from app.api import costs_api
    src = inspect.getsource(costs_api.estado_moneda)
    assert "range(1, 13)" in src
    assert "meses" in src


def test_el_aviso_esta_en_el_PL_no_solo_donde_se_carga():
    """Quien LEE el numero tiene que enterarse, no solo quien lo carga."""
    import pathlib
    for rel in ("app/pl/full/page.tsx", "app/costs/checkbook/page.tsx",
                "app/opex/checkbook/page.tsx"):
        p = _FRONT / rel
        if not p.exists():
            continue
        assert "AvisoMoneda" in p.read_text(encoding="utf-8"), (
            f"{rel} no muestra el aviso de tipo de cambio desactualizado")


# ── OPEX: la moneda tambien por linea ────────────────────────────────────────
def test_opex_devuelve_la_moneda_y_los_colones():
    import inspect
    from app.api import opex_api
    src = inspect.getsource(opex_api)
    assert '"currency"' in src and '"crc_months"' in src and '"crc_annual"' in src


def test_opex_guarda_los_colones_y_deriva():
    import inspect
    from app.api import opex_api
    upd = inspect.getsource(opex_api.update_opex_entry)
    assert "currency" in upd and "crc_" in upd
    assert "_derivar_si_es_crc" in upd
    helper = inspect.getsource(opex_api._derivar_si_es_crc)
    assert "get_tc_for_month" in helper and "derivar_usd" in helper


def test_la_pantalla_de_opex_tiene_el_selector():
    import pathlib
    p = _FRONT / "app" / "opex" / "checkbook" / "page.tsx"
    if not p.exists():
        return
    s = p.read_text(encoding="utf-8")
    assert "onToggleMoneda" in s, "no se puede cambiar la moneda de una linea"
    # y cuando esta en colones, los meses editan COLONES, no dolares
    assert "crc_${mk}" in s, "los meses seguirian editando dolares en una linea CRC"


# ── La moneda viaja al copiar una version ────────────────────────────────────
def test_la_moneda_y_los_colones_viajan_al_copiar():
    """Si no viajaran, la copia tomaria los dolares como si fueran el dato y la
    linea perderia su condicion de colones: el mismo presupuesto dejaria de
    absorber el tipo de cambio y nadie se enteraria."""
    from sqlalchemy.orm import class_mapper
    from app.api.scenarios_api import COPY_DATASETS, DEFAULT_COPY_DATASETS
    from app.models.cost_entry import CostEntry
    from app.models.opex_entry import OpexEntry

    for ds, Model in (("opex", OpexEntry), ("costs", CostEntry)):
        assert Model in COPY_DATASETS[ds]
        assert ds in DEFAULT_COPY_DATASETS
        # el copy clona columna por columna: basta con que esten MAPEADAS
        cols = {c.key for c in class_mapper(Model).columns}
        assert "currency" in cols, f"{Model.__name__}: la moneda no se copiaria"
        faltan = [m for m in MESES if f"crc_{m}" not in cols]
        assert not faltan, f"{Model.__name__}: no se copiarian los colones de {faltan}"


def test_el_tipo_de_cambio_tambien_viaja():
    """Una copia con los colones pero sin el TC calcularia otro dolar."""
    from app.api.scenarios_api import COPY_DATASETS, DEFAULT_COPY_DATASETS
    from app.models.exchange_rate import ExchangeRate
    assert ExchangeRate in COPY_DATASETS["rates"]
    assert "rates" in DEFAULT_COPY_DATASETS
